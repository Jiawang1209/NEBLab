"""Retrieve + rerank pipeline.

Three stages:
  1. Embed query into a single 4096-d vector
  2. Qdrant cosine search → ``candidate_k`` (~30) hits
  3. Rerank candidates → ``top_k`` (~5) final chunks

``RetrievedChunk.text`` is the abstract (or title if no abstract was
captured — some OpenAlex records like IPCC reports have no abstract).
The reranker sees ``title + "\\n\\n" + abstract`` to match what the
indexer embedded into Qdrant.
"""

from pydantic import BaseModel

from neblab_rag.providers.embedding.base import EmbeddingProvider
from neblab_rag.providers.reranker.base import RerankerProvider
from neblab_rag.vector import QdrantRepo


class RetrievedChunk(BaseModel):
    doc_id: int
    openalex_id: str | None
    title: str
    text: str
    score: float


def _chunk_body(payload: dict[str, object]) -> str:
    """Prefer the abstract; fall back to title for abstract-less records."""
    abstract = payload.get("abstract") or ""
    title = payload.get("title") or ""
    return str(abstract) if abstract else str(title)


def _rerank_doc(payload: dict[str, object]) -> str:
    title = str(payload.get("title") or "")
    abstract = str(payload.get("abstract") or "")
    return f"{title}\n\n{abstract}" if abstract else title


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
                    doc_id=h.payload.get("doc_id", -1),
                    openalex_id=h.payload.get("openalex_id"),
                    title=h.payload.get("title", ""),
                    text=_chunk_body(h.payload),
                    score=r.score,
                )
            )
        return out
