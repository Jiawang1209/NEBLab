from unittest.mock import AsyncMock, MagicMock

import pytest

from neblab_rag.providers.reranker.base import RerankResult
from neblab_rag.rag.retriever import HybridRetriever
from neblab_rag.vector import SearchHit


def _hit(*, doc_id: int, title: str, abstract: str, oa_id: str, score: float) -> SearchHit:
    return SearchHit(
        id=doc_id,
        score=score,
        payload={
            "doc_id": doc_id,
            "openalex_id": oa_id,
            "title": title,
            "abstract": abstract,
        },
    )


@pytest.mark.asyncio
async def test_retrieve_calls_embed_then_search_then_rerank():
    embed = MagicMock()
    embed.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3, 0.4]])

    qdrant = MagicMock()
    qdrant.search.return_value = [
        _hit(doc_id=1, title="A", abstract="abs A", oa_id="W1", score=0.7),
        _hit(doc_id=2, title="B", abstract="abs B", oa_id="W2", score=0.6),
        _hit(doc_id=3, title="C", abstract="abs C", oa_id="W3", score=0.5),
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

    # Generator needs the abstract content, not just the title — title alone
    # is too sparse for the LLM to ground answers on.
    assert chunks[0].text == "abs C"
    assert chunks[1].text == "abs A"

    # Reranker should see both title + abstract so it scores against the
    # actual content, matching what was embedded into Qdrant.
    rr_docs = rr.rerank.call_args.kwargs["documents"]
    assert "A" in rr_docs[0] and "abs A" in rr_docs[0]


@pytest.mark.asyncio
async def test_retrieve_falls_back_to_title_when_abstract_missing():
    """Some OpenAlex records (IPCC reports) have no abstract — chunk.text
    should fall back to title rather than be empty."""
    embed = MagicMock()
    embed.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3, 0.4]])

    qdrant = MagicMock()
    qdrant.search.return_value = [
        SearchHit(
            id=1,
            score=0.7,
            payload={"doc_id": 1, "openalex_id": "W1", "title": "Only Title Here"},
        ),
    ]

    rr = MagicMock()
    rr.rerank = AsyncMock(return_value=[RerankResult(index=0, score=0.9)])

    retriever = HybridRetriever(embedder=embed, qdrant=qdrant, reranker=rr)
    chunks = await retriever.retrieve(query="q", top_k=1, candidate_k=1)

    assert chunks[0].text == "Only Title Here"
