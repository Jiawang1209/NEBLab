"""Retrieve + rerank pipeline.

Three stages:
  1. Embed query into a single 4096-d vector
  2. Qdrant cosine search → ``candidate_k`` (~30) chunk hits
  3. Rerank candidates → ``top_k`` (~5) final chunks

Payload shape (set by Sprint-2 ChunkIndexer):
  chunk_id, doc_id, chunk_index, openalex_id, title, text,
  year, topic, language

``RetrievedChunk.text`` is the chunk text (stored under payload['text']).
Multiple retrieved chunks may share the same doc_id when a query matches
multiple parts of one document — the generator handles that fine, the
UI may want to group/dedupe by doc_id (Sprint 3 concern).
"""

from pydantic import BaseModel

from neblab_rag.providers.embedding.base import EmbeddingProvider
from neblab_rag.providers.reranker.base import RerankerProvider
from neblab_rag.vector import QdrantRepo


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


class HybridRetriever:
    def __init__(
        self,
        embedder: EmbeddingProvider,
        qdrant: QdrantRepo,
        reranker: RerankerProvider,
    ):
        self._embedder = embedder
        self._qdrant = qdrant
        self._reranker = reranker

    async def retrieve(
        self, *, query: str, top_k: int = 5, candidate_k: int = 30
    ) -> list[RetrievedChunk]:
        [query_vec] = await self._embedder.embed([query])

        hits = self._qdrant.search(query_vec, top_k=candidate_k)
        if not hits:
            return []

        candidate_texts = [_rerank_doc(h.payload) for h in hits]
        rerank_results = await self._reranker.rerank(
            query=query, documents=candidate_texts, top_k=top_k
        )

        out: list[RetrievedChunk] = []
        for r in rerank_results:
            h = hits[r.index]
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
