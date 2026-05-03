# pyright: reportCallIssue=false, reportArgumentType=false
"""Retrieve + rerank pipeline.

Pipeline:
  1. Embed query (dense path) — Qdrant cosine search → ``candidate_k`` hits
  2. (Sprint 2.5, optional) BM25 lookup (sparse path) — ``candidate_k`` hits
  3. If both paths active, merge via reciprocal rank fusion
  4. Rerank merged candidates → ``top_k`` (~5) final chunks

Payload shape (set by Sprint-2 ChunkIndexer):
  chunk_id, doc_id, chunk_index, openalex_id, title, text,
  year, topic, language

``RetrievedChunk.text`` is the chunk text (stored under payload['text']).
Multiple retrieved chunks may share the same doc_id when a query matches
multiple parts of one document — the generator handles that fine, the
UI may want to group/dedupe by doc_id (Sprint 3 concern).

Why RRF (not score normalization): dense cosine and BM25 live on totally
different scales (cosine ∈ [-1,1] vs BM25 unbounded). Score fusion
requires hand-tuning weights; rank fusion is parameter-free except the
constant ``k`` (default 60 from the original RRF paper).
"""

from pydantic import BaseModel

from neblab_rag.providers.embedding.base import EmbeddingProvider
from neblab_rag.providers.reranker.base import RerankerProvider
from neblab_rag.rag.bm25_index import BM25Index
from neblab_rag.vector import QdrantRepo, SearchHit


class RetrievedChunk(BaseModel):
    chunk_id: int
    doc_id: int
    chunk_index: int
    openalex_id: str | None
    title: str
    text: str
    score: float


def _rerank_doc(payload: dict[str, object]) -> str:
    """Reranker sees title + chunk text — same shape the embedder saw."""
    title = str(payload.get("title") or "")
    text = str(payload.get("text") or "")
    return f"{title}\n\n{text}" if text else title


RRF_K = 60  # reciprocal-rank-fusion constant from the original paper

# Sprint 1 v0.2: a single fulltext doc can produce 100s-1000s of chunks
# and dominate the candidate pool against abstract-only docs (which produce
# 1-5 chunks each). Cap how many chunks any one doc contributes to the
# pre-rerank pool so retrieval stays diverse across docs.
DEFAULT_MAX_CHUNKS_PER_DOC = 3


def _cap_per_doc(candidates: list[SearchHit], max_per_doc: int) -> list[SearchHit]:
    """Drop chunks beyond ``max_per_doc`` for each doc_id, preserving rank order.

    Operates on the post-RRF candidate list so the cap respects whichever
    chunks scored highest under the combined dense+sparse ranking.
    """
    counts: dict[int, int] = {}
    out: list[SearchHit] = []
    for c in candidates:
        doc_id = int(c.payload.get("doc_id", -1))
        if counts.get(doc_id, 0) >= max_per_doc:
            continue
        out.append(c)
        counts[doc_id] = counts.get(doc_id, 0) + 1
    return out


def _merge_rrf(
    dense: list[SearchHit],
    sparse_chunk_ids: list[int],
    *,
    payloads_by_id: dict[int, dict[str, object]],
) -> list[SearchHit]:
    """Reciprocal rank fusion of dense + sparse rankings.

    sparse_chunk_ids is just the BM25 ranking — the corresponding payloads
    are looked up from ``payloads_by_id`` (which dense already populated;
    chunks unique to BM25 won't have payloads here, so we skip them rather
    than do a second Qdrant fetch — they'll get re-included when the next
    query happens to also retrieve them densely. Acceptable lossiness for
    Sprint-2.5 v0.1.)
    """
    rrf_scores: dict[int, float] = {}
    for rank, hit in enumerate(dense, start=1):
        rrf_scores[hit.id] = rrf_scores.get(hit.id, 0.0) + 1.0 / (RRF_K + rank)
    for rank, cid in enumerate(sparse_chunk_ids, start=1):
        if cid not in payloads_by_id:
            continue  # see docstring
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (RRF_K + rank)

    sorted_ids = sorted(rrf_scores, key=lambda i: -rrf_scores[i])
    return [
        SearchHit(id=cid, score=rrf_scores[cid], payload=payloads_by_id[cid]) for cid in sorted_ids
    ]


class HybridRetriever:
    def __init__(
        self,
        embedder: EmbeddingProvider,
        qdrant: QdrantRepo,
        reranker: RerankerProvider,
        *,
        bm25: BM25Index | None = None,
        max_chunks_per_doc: int = DEFAULT_MAX_CHUNKS_PER_DOC,
    ):
        self._embedder = embedder
        self._qdrant = qdrant
        self._reranker = reranker
        self._bm25 = bm25
        self._max_chunks_per_doc = max_chunks_per_doc

    async def retrieve(
        self, *, query: str, top_k: int = 5, candidate_k: int = 30
    ) -> list[RetrievedChunk]:
        [query_vec] = await self._embedder.embed([query])
        # Pull more dense candidates than we'll keep — the per-doc cap will
        # prune them down. Without the inflate, after capping 30→~12, we'd
        # starve the reranker of diverse-doc options.
        oversample = candidate_k * self._max_chunks_per_doc
        dense_hits = self._qdrant.search(query_vec, top_k=oversample)

        if self._bm25 is None:
            candidates = dense_hits
        else:
            sparse_hits = self._bm25.search(query, top_k=oversample)
            sparse_ids = [h.chunk_id for h in sparse_hits]
            payloads_by_id: dict[int, dict[str, object]] = {
                int(h.id): h.payload for h in dense_hits if isinstance(h.id, int)
            }
            candidates = _merge_rrf(dense_hits, sparse_ids, payloads_by_id=payloads_by_id)

        candidates = _cap_per_doc(candidates, self._max_chunks_per_doc)[:candidate_k]

        if not candidates:
            return []

        candidate_texts = [_rerank_doc(h.payload) for h in candidates]
        rerank_results = await self._reranker.rerank(
            query=query, documents=candidate_texts, top_k=top_k
        )

        out: list[RetrievedChunk] = []
        for r in rerank_results:
            h = candidates[r.index]
            out.append(
                RetrievedChunk(
                    chunk_id=h.payload.get("chunk_id", -1),
                    doc_id=h.payload.get("doc_id", -1),
                    chunk_index=h.payload.get("chunk_index", 0),
                    openalex_id=h.payload.get("openalex_id"),
                    title=h.payload.get("title", ""),
                    text=h.payload.get("text") or h.payload.get("title", ""),
                    score=r.score,
                )
            )
        return out
