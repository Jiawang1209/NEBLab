"""Task handlers — one per TaskType, each owning its full request flow.

Sprint 5d: the pipeline used to be a fixed retrieve→rewrite→generate
pipeline that worked great for QA but couldn't handle queries that have
no answer in the literature (meta queries about the system itself, e.g.
"how many documents are in NEBLab?"). The fix is a router architecture:

    classify(query) → TaskType
    handler = handlers[task_type]
    handler.stream(query) → stream of events

Each handler is independent and can use as much or as little of the RAG
pipeline as it needs. Adding a new task type (proposal / ppt / platform)
is just a new handler class — no changes to pipeline or API.

The streaming contract is uniform across handlers: each yields
``StreamEvent`` instances in the same order the SSE endpoint expects
(task_type → citations → delta * N → done). The API route doesn't need
to know which handler ran.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from neblab_rag.rag.citation import CitationValidation, validate_citations
from neblab_rag.rag.generator import AnswerGenerator, Citation, GeneratedAnswer
from neblab_rag.rag.query_rewriter import QueryRewriter, RewrittenQuery
from neblab_rag.rag.retriever import RetrievedChunk, Retriever
from neblab_rag.rag.system_info import (
    IDENTITY_ANSWER,
    SystemInfoProvider,
    format_meta_answer,
    is_identity_query,
)
from neblab_rag.rag.task_classifier import TaskType


@dataclass(frozen=True)
class StreamEvent:
    """Single SSE-shaped event yielded by a handler. The ``event`` field
    is the SSE event name; ``data`` is the (already serialised) body."""

    event: str
    data: str


@dataclass(frozen=True)
class HandlerResult:
    """Non-streaming result. Mirrors RAGResult but lives in the handler
    layer to keep the dependency direction clean (handlers don't know
    about RAGResult, the pipeline assembles that)."""

    query: str
    chunks: list[RetrievedChunk]
    answer: GeneratedAnswer
    citation_validation: CitationValidation
    task_type: TaskType
    rewritten_query: str | None = None


class TaskHandler(Protocol):
    """All handlers expose both a non-streaming ``handle`` and a streaming
    ``stream`` so the API can pick whichever its endpoint needs."""

    async def handle(self, *, query: str, top_k: int) -> HandlerResult: ...

    def stream(
        self, *, query: str, top_k: int
    ) -> AsyncIterator[StreamEvent]: ...


# ---- Helpers shared by retrieval-based handlers -----------------------


def _citations_payload(chunks: list[RetrievedChunk]) -> str:
    return json.dumps(
        [
            {
                "number": i + 1,
                "doc_id": c.doc_id,
                "openalex_id": c.openalex_id,
                "title": c.title,
            }
            for i, c in enumerate(chunks)
        ]
    )


def _ledger_citations(chunks: list[RetrievedChunk]) -> list[Citation]:
    return [
        Citation(
            number=i,
            doc_id=c.doc_id,
            openalex_id=c.openalex_id,
            title=c.title,
        )
        for i, c in enumerate(chunks, 1)
    ]


# ---- Retrieval-based handlers (QA + Planning) -------------------------


class _RetrievalHandler:
    """Shared base for QA and Planning. Both follow the same skeleton —
    rewrite → retrieve → generate — and only differ in which system
    prompt the generator picks. The task_type is plumbed through so the
    generator picks the right prompt."""

    task_type: TaskType  # set by subclass

    def __init__(
        self,
        retriever: Retriever,
        generator: AnswerGenerator,
        rewriter: QueryRewriter | None = None,
    ):
        self._retriever = retriever
        self._generator = generator
        self._rewriter = rewriter

    async def _maybe_rewrite(self, query: str) -> RewrittenQuery:
        if self._rewriter is None:
            return RewrittenQuery(
                original=query, rewritten=query, was_rewritten=False
            )
        return await self._rewriter.rewrite(query)

    async def handle(self, *, query: str, top_k: int) -> HandlerResult:
        rewritten = await self._maybe_rewrite(query)
        chunks = await self._retriever.retrieve(
            query=rewritten.rewritten, top_k=top_k
        )
        answer = await self._generator.generate(
            query=rewritten.original,
            chunks=chunks,
            task_type=self.task_type,
        )
        validation = validate_citations(answer.content, num_chunks=len(chunks))
        return HandlerResult(
            query=query,
            rewritten_query=rewritten.rewritten if rewritten.was_rewritten else None,
            chunks=chunks,
            answer=answer,
            citation_validation=validation,
            task_type=self.task_type,
        )

    async def stream(
        self, *, query: str, top_k: int
    ) -> AsyncIterator[StreamEvent]:
        rewritten = await self._maybe_rewrite(query)
        chunks = await self._retriever.retrieve(
            query=rewritten.rewritten, top_k=top_k
        )
        yield StreamEvent("task_type", self.task_type.value)
        yield StreamEvent("citations", _citations_payload(chunks))
        async for delta in self._generator.stream(
            query=rewritten.original,
            chunks=chunks,
            task_type=self.task_type,
        ):
            yield StreamEvent("delta", delta)
        yield StreamEvent("done", "")


class QAHandler(_RetrievalHandler):
    task_type = TaskType.QA


class PlanningHandler(_RetrievalHandler):
    task_type = TaskType.PLANNING


# ---- Meta handler (no retrieval) -------------------------------------


class MetaHandler:
    """Handles queries about the system itself. Skips retriever and
    generator entirely — the answer is rendered from a Postgres-backed
    SystemInfo struct via a fixed template. This is the right answer
    for queries like "how many documents are in NEBLab?" — RAG would
    fabricate; this returns ground truth."""

    task_type = TaskType.META

    def __init__(self, info_provider: SystemInfoProvider):
        self._info_provider = info_provider

    def _render(self, query: str) -> tuple[str, GeneratedAnswer]:
        # Identity queries don't need SystemInfo — short-circuit to the
        # canned identity template. This keeps "what model are you"
        # answered with our brand line ("磐石大模型") instead of letting
        # the LLM hallucinate a vendor name.
        if is_identity_query(query):
            text = IDENTITY_ANSWER
        else:
            info = self._info_provider.get()
            text = format_meta_answer(info)
        return text, GeneratedAnswer(content=text, citations=[])

    async def handle(self, *, query: str, top_k: int) -> HandlerResult:
        del top_k  # meta path is retrieval-free
        _, answer = self._render(query)
        return HandlerResult(
            query=query,
            chunks=[],
            answer=answer,
            citation_validation=CitationValidation(
                is_valid=True, missing_numbers=[], invalid_numbers=[]
            ),
            task_type=self.task_type,
        )

    async def stream(
        self, *, query: str, top_k: int
    ) -> AsyncIterator[StreamEvent]:
        del top_k
        text, _ = self._render(query)
        yield StreamEvent("task_type", self.task_type.value)
        yield StreamEvent("citations", "[]")
        # Pace the deltas so the canned answer feels like real LLM
        # output instead of being dumped instantly. Without the sleep
        # the user sees the whole answer in one flash and immediately
        # suspects it was precomputed (it was — but UX shouldn't
        # advertise that). 4-char chunks at ~25ms/chunk gives ~3s of
        # streaming for a typical 600-char meta answer, matching the
        # cadence of the LLM-driven QA / Planning paths.
        for chunk in _chunks_for_streaming(text):
            yield StreamEvent("delta", chunk)
            await asyncio.sleep(_DELTA_PACING_SECONDS)
        yield StreamEvent("done", "")


_DELTA_CHUNK_SIZE = 4
_DELTA_PACING_SECONDS = 0.025


def _chunks_for_streaming(text: str, *, size: int = _DELTA_CHUNK_SIZE) -> list[str]:
    """Split a canned answer into small stream-friendly pieces. The
    paired ``asyncio.sleep`` between yields is what makes this feel
    like LLM output; the chunk size alone just controls granularity."""
    if not text:
        return []
    return [text[i : i + size] for i in range(0, len(text), size)]
