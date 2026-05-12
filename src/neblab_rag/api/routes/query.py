# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportMissingTypeStubs=false
"""POST /query and POST /query/stream endpoints.

Sprint 5e: both endpoints accept a list of conversation messages
instead of a single query, so the frontend can carry follow-ups. The
SSE response shape is unchanged (task_type → citations → delta * N
→ done) so the streaming consumer doesn't need to care that the
request is now multi-turn.

The pipeline holds long-lived clients (qdrant, httpx) so we build it
once and cache it. Tests override ``get_pipeline`` via FastAPI's
``app.dependency_overrides``.
"""

from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from neblab_rag.providers.factory import (
    build_bm25_index,
    build_embedding_provider,
    build_llm_provider,
    build_qdrant_repo,
    build_reranker_provider,
)
from neblab_rag.rag.conversation import ConvMessage
from neblab_rag.rag.generator import AnswerGenerator
from neblab_rag.rag.pipeline import RAGPipeline
from neblab_rag.rag.query_rewriter import QueryRewriter
from neblab_rag.rag.retriever import HybridRetriever
from neblab_rag.rag.system_info import PostgresSystemInfoProvider
from neblab_rag.rag.task_classifier import TaskType

router = APIRouter(tags=["rag"])


class QueryRequest(BaseModel):
    """Multi-turn request shape: full conversation in ``messages``. The
    backend treats the latest user message as the active query and
    folds prior turns into a standalone retrieval query via the
    context-aware rewriter."""

    messages: list[ConvMessage]
    top_k: int = 7


class CitationOut(BaseModel):
    number: int
    doc_id: int
    openalex_id: str | None
    title: str


class QueryResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    citation_valid: bool
    task_type: TaskType


@lru_cache(maxsize=1)
def _build_pipeline() -> RAGPipeline:
    llm = build_llm_provider()
    retriever = HybridRetriever(
        embedder=build_embedding_provider(),
        qdrant=build_qdrant_repo(),
        reranker=build_reranker_provider(),
        bm25=build_bm25_index(),
    )
    return RAGPipeline(
        retriever=retriever,
        generator=AnswerGenerator(llm=llm),
        query_rewriter=QueryRewriter(llm=llm),
        system_info_provider=PostgresSystemInfoProvider(),
    )


def get_pipeline() -> RAGPipeline:
    return _build_pipeline()


PipelineDep = Annotated[RAGPipeline, Depends(get_pipeline)]


@router.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest, pipeline: PipelineDep) -> QueryResponse:
    result = await pipeline.answer(messages=req.messages, top_k=req.top_k)
    return QueryResponse(
        answer=result.answer.content,
        citations=[CitationOut(**c.model_dump()) for c in result.answer.citations],
        citation_valid=result.citation_validation.is_valid,
        task_type=result.task_type,
    )


@router.post("/query/stream")
async def stream_post(req: QueryRequest, pipeline: PipelineDep) -> EventSourceResponse:
    """Multi-turn SSE streaming endpoint. Frontend sends the full
    conversation; we relay handler events as SSE."""

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        async for ev in pipeline.stream(messages=req.messages, top_k=req.top_k):
            yield {"event": ev.event, "data": ev.data}

    return EventSourceResponse(event_generator())


@router.get("/query/stream")
async def stream_get(
    pipeline: PipelineDep,
    query: Annotated[str, Query(description="Single-turn query")] = "",
    top_k: int = 7,
) -> EventSourceResponse:
    """Single-turn SSE streaming endpoint kept for backward compat with
    smoke-test scripts and curl. New clients should POST to
    ``/query/stream`` with the full conversation."""

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        async for ev in pipeline.stream(query=query, top_k=top_k):
            yield {"event": ev.event, "data": ev.data}

    return EventSourceResponse(event_generator())
