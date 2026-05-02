"""Tests for RAGPipeline orchestration: retrieve → generate → validate."""

from unittest.mock import AsyncMock, MagicMock

from neblab_rag.rag.generator import Citation, GeneratedAnswer
from neblab_rag.rag.pipeline import RAGPipeline
from neblab_rag.rag.retriever import RetrievedChunk


async def test_answer_orchestrates_retriever_and_generator() -> None:
    chunks = [RetrievedChunk(doc_id=1, openalex_id="W1", title="t", text="x", score=0.9)]
    retriever = MagicMock()
    retriever.retrieve = AsyncMock(return_value=chunks)
    generator = MagicMock()
    generator.generate = AsyncMock(
        return_value=GeneratedAnswer(
            content="Per [1].",
            citations=[Citation(number=1, doc_id=1, openalex_id="W1", title="t")],
        )
    )

    pipeline = RAGPipeline(retriever=retriever, generator=generator)
    result = await pipeline.answer(query="x")

    assert result.query == "x"
    assert result.chunks == chunks
    assert result.answer.content == "Per [1]."
    assert result.citation_validation.is_valid is True
    retriever.retrieve.assert_awaited_once_with(query="x", top_k=5)
    generator.generate.assert_awaited_once_with(query="x", chunks=chunks)


async def test_answer_passes_top_k_through_to_retriever() -> None:
    retriever = MagicMock()
    retriever.retrieve = AsyncMock(return_value=[])
    generator = MagicMock()
    generator.generate = AsyncMock(
        return_value=GeneratedAnswer(content="文献库中暂未找到相关结论。", citations=[])
    )

    pipeline = RAGPipeline(retriever=retriever, generator=generator)
    await pipeline.answer(query="q", top_k=10)

    retriever.retrieve.assert_awaited_once_with(query="q", top_k=10)


async def test_answer_flags_invalid_citations() -> None:
    chunks = [RetrievedChunk(doc_id=1, openalex_id="W1", title="t", text="x", score=0.9)]
    retriever = MagicMock()
    retriever.retrieve = AsyncMock(return_value=chunks)
    generator = MagicMock()
    generator.generate = AsyncMock(
        return_value=GeneratedAnswer(
            content="Per [5] (hallucinated).",
            citations=[Citation(number=1, doc_id=1, openalex_id="W1", title="t")],
        )
    )

    pipeline = RAGPipeline(retriever=retriever, generator=generator)
    result = await pipeline.answer(query="x")

    assert result.citation_validation.is_valid is False
    assert 5 in result.citation_validation.invalid_numbers
