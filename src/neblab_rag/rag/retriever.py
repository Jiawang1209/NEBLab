"""Retrieve + rerank pipeline.

Three stages:
  1. Embed query into a single 4096-d vector
  2. Qdrant cosine search → ``candidate_k`` (~30) hits
  3. Rerank candidates → ``top_k`` (~5) final chunks

For v1, ``RetrievedChunk.text`` is the title (payload has title only,
abstract lives in Postgres). Generator (Task 26) decides whether to
hydrate from DB by ``doc_id`` if it needs the full text.
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

        candidate_texts = [h.payload.get("title", "") for h in hits]
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
                    text=h.payload.get("title", ""),
                    score=r.score,
                )
            )
        return out
