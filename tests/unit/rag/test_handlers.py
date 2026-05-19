"""Unit tests for handlers.

Coverage focus: the non-streaming ``handle()`` paths. The streaming
paths are exercised indirectly through ``tests/unit/api/test_query.py``,
but ``handle()`` had a regression in Sprint 5e where the meta path
constructed a ``CitationValidation`` with the wrong field names — only
discovered by pyright. This module is the regression test that would
have caught it.
"""

from __future__ import annotations

from neblab_rag.rag.conversation import ConvMessage
from neblab_rag.rag.handlers import MetaHandler
from neblab_rag.rag.system_info import SystemInfo
from neblab_rag.rag.task_classifier import TaskType


class _StubSystemInfoProvider:
    """Returns a fixed SystemInfo — no Postgres dependency."""

    def __init__(self, info: SystemInfo):
        self._info = info

    def get(self) -> SystemInfo:
        return self._info


def _fake_info() -> SystemInfo:
    return SystemInfo(
        total_docs=1810,
        indexed_docs=1810,
        total_chunks=4717,
        by_language=(("en", 1500), ("zh", 310)),
    )


async def test_meta_handle_corpus_stats_returns_handler_result():
    """Non-identity meta query → renders corpus stats template + a
    well-formed CitationValidation. Regression for the Sprint 5e bug
    where ``CitationValidation(..., missing_numbers=[], ...)`` crashed
    at runtime because the model has no such field."""
    handler = MetaHandler(_StubSystemInfoProvider(_fake_info()))
    messages = [ConvMessage(role="user", content="NEBLab 收录了多少篇文献？")]

    result = await handler.handle(messages=messages, top_k=5)

    assert result.task_type is TaskType.META
    assert result.chunks == []
    assert result.answer.citations == []
    # The corpus-stats branch should produce non-empty markdown
    # mentioning the doc count.
    assert "1810" in result.answer.content
    # CitationValidation shape check — caught the Sprint 5e field-name bug.
    assert result.citation_validation.is_valid is True
    assert result.citation_validation.referenced_numbers == set()
    assert result.citation_validation.invalid_numbers == set()


async def test_meta_handle_identity_query_returns_identity_answer():
    """Identity-style query → returns the canned IDENTITY_ANSWER, no
    Postgres call. Provider should not be touched."""

    class _Boom:
        def get(self) -> SystemInfo:  # pragma: no cover - must not be called
            raise AssertionError("identity branch should not query SystemInfoProvider")

    handler = MetaHandler(_Boom())
    messages = [ConvMessage(role="user", content="你是什么模型？")]

    result = await handler.handle(messages=messages, top_k=5)

    assert result.task_type is TaskType.META
    assert "NEBLab" in result.answer.content
    assert result.citation_validation.is_valid is True


async def test_meta_handle_uses_latest_user_message():
    """Earlier turns are ignored — only the latest user message is what
    the meta path renders against."""
    handler = MetaHandler(_StubSystemInfoProvider(_fake_info()))
    messages = [
        ConvMessage(role="user", content="hi"),
        ConvMessage(role="assistant", content="hello"),
        ConvMessage(role="user", content="语料规模是多少？"),
    ]

    result = await handler.handle(messages=messages, top_k=5)

    assert result.query == "语料规模是多少？"
    assert "1810" in result.answer.content


def test_citations_payload_includes_chunk_text():
    """Sprint 3 v0.3: SSE 'citations' event must include chunk_text
    so the UI can render chunk previews from the streaming path."""
    import json

    from neblab_rag.rag.handlers import _citations_payload
    from neblab_rag.rag.retriever import RetrievedChunk

    chunks = [
        RetrievedChunk(
            chunk_id=11,
            doc_id=42,
            chunk_index=0,
            openalex_id="W123",
            title="Sand Storm Atlas",
            text="We observed that shelterbelt mass transport reduced by 40-60%.",
            score=0.9,
        ),
    ]
    payload = json.loads(_citations_payload(chunks))
    assert payload[0]["chunk_text"] == (
        "We observed that shelterbelt mass transport reduced by 40-60%."
    )
    assert payload[0]["number"] == 1
    assert payload[0]["doc_id"] == 42
    assert payload[0]["title"] == "Sand Storm Atlas"
