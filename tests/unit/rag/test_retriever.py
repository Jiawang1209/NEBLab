from unittest.mock import AsyncMock, MagicMock

import pytest

from neblab_rag.providers.reranker.base import RerankResult
from neblab_rag.rag.retriever import HybridRetriever
from neblab_rag.vector import SearchHit


@pytest.mark.asyncio
async def test_retrieve_calls_embed_then_search_then_rerank():
    embed = MagicMock()
    embed.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3, 0.4]])

    qdrant = MagicMock()
    qdrant.search.return_value = [
        SearchHit(id="1", score=0.7, payload={"doc_id": 1, "title": "A", "openalex_id": "W1"}),
        SearchHit(id="2", score=0.6, payload={"doc_id": 2, "title": "B", "openalex_id": "W2"}),
        SearchHit(id="3", score=0.5, payload={"doc_id": 3, "title": "C", "openalex_id": "W3"}),
    ]

    rr = MagicMock()
    rr.rerank = AsyncMock(
        return_value=[
            RerankResult(index=2, score=0.95),
            RerankResult(index=0, score=0.8),
        ]
    )

    retriever = HybridRetriever(embedder=embed, qdrant=qdrant, reranker=rr)
    chunks = await retriever.retrieve(query="sand control", top_k=2, candidate_k=3)

    assert len(chunks) == 2
    assert chunks[0].title == "C"  # reranker put index 2 first
    assert chunks[1].title == "A"
