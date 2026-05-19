"""Tests for /query and /query/stream endpoints.

Pipeline is mocked via FastAPI dependency override — these are pure
HTTP-shape tests, no real LLM/Qdrant calls.
"""

import json
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from neblab_rag.api.main import create_app
from neblab_rag.api.routes.query import get_pipeline
from neblab_rag.rag.citation import CitationValidation
from neblab_rag.rag.generator import Citation, GeneratedAnswer
from neblab_rag.rag.handlers import StreamEvent
from neblab_rag.rag.pipeline import RAGResult
from neblab_rag.rag.retriever import RetrievedChunk
from neblab_rag.rag.task_classifier import TaskType


def _make_result(query: str = "What is sand control?") -> RAGResult:
    return RAGResult(
        query=query,
        chunks=[
            RetrievedChunk(
                chunk_id=1,
                doc_id=1,
                chunk_index=0,
                openalex_id="W1",
                title="A",
                text="x",
                score=0.9,
            )
        ],
        answer=GeneratedAnswer(
            content="Per [1].",
            citations=[Citation(number=1, doc_id=1, openalex_id="W1", title="A", chunk_text="x")],
        ),
        citation_validation=CitationValidation(
            is_valid=True, referenced_numbers={1}, invalid_numbers=set()
        ),
        task_type=TaskType.QA,
    )


def test_query_returns_answer_and_citations() -> None:
    """Sprint 5e: API now takes a `messages` array. Single-turn requests
    wrap the question in a one-element list."""
    fake_pipeline = MagicMock()
    fake_pipeline.answer = AsyncMock(return_value=_make_result())

    app = create_app()
    app.dependency_overrides[get_pipeline] = lambda: fake_pipeline

    client = TestClient(app)
    response = client.post(
        "/query",
        json={"messages": [{"role": "user", "content": "What is sand control?"}]},
    )

    assert response.status_code == 200
    data = response.json()
    assert "Per [1]" in data["answer"]
    assert data["citations"][0]["title"] == "A"
    assert data["citations"][0]["number"] == 1
    assert data["citation_valid"] is True


def test_query_passes_top_k_to_pipeline() -> None:
    fake_pipeline = MagicMock()
    fake_pipeline.answer = AsyncMock(return_value=_make_result())

    app = create_app()
    app.dependency_overrides[get_pipeline] = lambda: fake_pipeline

    client = TestClient(app)
    client.post(
        "/query",
        json={"messages": [{"role": "user", "content": "q"}], "top_k": 8},
    )

    fake_pipeline.answer.assert_awaited_once()
    kwargs = fake_pipeline.answer.await_args.kwargs
    assert kwargs["top_k"] == 8
    assert [m.content for m in kwargs["messages"]] == ["q"]


def test_query_endpoint_returns_chunk_text() -> None:
    """Sprint 3 v0.3: POST /query must include chunk_text per citation
    so non-streaming clients also see the preview text."""
    fake_pipeline = MagicMock()
    fake_pipeline.answer = AsyncMock(return_value=_make_result())

    app = create_app()
    app.dependency_overrides[get_pipeline] = lambda: fake_pipeline

    client = TestClient(app)
    resp = client.post(
        "/query",
        json={"messages": [{"role": "user", "content": "test"}], "top_k": 3},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["citations"]) >= 1
    assert "chunk_text" in data["citations"][0]
    assert data["citations"][0]["chunk_text"]


def test_query_stream_emits_citations_then_deltas_then_done() -> None:
    """Sprint 5d: the API route now relays StreamEvents from
    ``pipeline.stream()`` directly. Mock the pipeline's stream method
    instead of stitching the retriever+generator path inline."""

    async def fake_stream(*, query: str, top_k: int) -> AsyncIterator[StreamEvent]:
        del query, top_k
        yield StreamEvent("task_type", "qa")
        yield StreamEvent(
            "citations",
            json.dumps([{"number": 1, "doc_id": 1, "openalex_id": "W1", "title": "A"}]),
        )
        yield StreamEvent("delta", "Per ")
        yield StreamEvent("delta", "[1].")
        yield StreamEvent("done", "")

    fake_pipeline = MagicMock()
    fake_pipeline.stream = fake_stream

    app = create_app()
    app.dependency_overrides[get_pipeline] = lambda: fake_pipeline

    client = TestClient(app)
    with client.stream("GET", "/query/stream", params={"query": "q"}) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "event: task_type" in body
    assert "event: citations" in body
    citations_line = next(
        line for line in body.splitlines() if line.startswith("data: ") and '"title": "A"' in line
    )
    payload = json.loads(citations_line.removeprefix("data: "))
    assert payload[0]["title"] == "A"
    assert payload[0]["number"] == 1

    assert "event: delta" in body
    assert "data: Per" in body
    assert "data: [1]." in body
    assert "event: done" in body
