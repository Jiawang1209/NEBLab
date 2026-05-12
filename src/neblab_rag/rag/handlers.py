"""Task handlers — one per TaskType, each owning its full request flow.

Sprint 5d introduced the router architecture (classify → handler).
Sprint 5e extends the handler interface to a list of conversation
messages instead of a single query string, so follow-ups can be wired
through:

    handler.stream(messages=...) → AsyncIterator[StreamEvent]

The latest user message is what gets retrieved/classified against; the
rewriter folds prior turns into a standalone query so "expand section
3" doesn't retrieve nonsense. The full conversation is passed to the
generator so its answers stay coherent across turns.

Single-turn callers (the eval runner) wrap their query in a one-element
``[ConvMessage(role="user", content=q)]`` list — no special-casing.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from neblab_rag.rag.citation import CitationValidation, validate_citations
from neblab_rag.rag.conversation import ConvMessage, latest_user_message
from neblab_rag.rag.generator import AnswerGenerator, GeneratedAnswer
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
    event: str
    data: str


@dataclass(frozen=True)
class HandlerResult:
    query: str
    chunks: list[RetrievedChunk]
    answer: GeneratedAnswer
    citation_validation: CitationValidation
    task_type: TaskType
    rewritten_query: str | None = None


class TaskHandler(Protocol):
    async def handle(self, *, messages: list[ConvMessage], top_k: int) -> HandlerResult: ...

    def stream(self, *, messages: list[ConvMessage], top_k: int) -> AsyncIterator[StreamEvent]: ...


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


# ---- Retrieval-based handlers (QA + Planning) -------------------------


class _RetrievalHandler:
    """Shared base for QA and Planning. Both share the same skeleton:
    rewrite latest user msg with conversation context → retrieve →
    generate with full conversation history. Subclasses only differ
    in which system prompt the generator picks (via task_type)."""

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

    async def _rewrite(self, messages: list[ConvMessage]) -> RewrittenQuery:
        latest = latest_user_message(messages)
        if self._rewriter is None:
            return RewrittenQuery(original=latest, rewritten=latest, was_rewritten=False)
        return await self._rewriter.rewrite_with_context(messages)

    async def handle(self, *, messages: list[ConvMessage], top_k: int) -> HandlerResult:
        rewritten = await self._rewrite(messages)
        chunks = await self._retriever.retrieve(query=rewritten.rewritten, top_k=top_k)
        answer = await self._generator.generate(
            query=rewritten.original,
            chunks=chunks,
            task_type=self.task_type,
            history=messages,
        )
        validation = validate_citations(answer.content, num_chunks=len(chunks))
        return HandlerResult(
            query=rewritten.original,
            rewritten_query=rewritten.rewritten if rewritten.was_rewritten else None,
            chunks=chunks,
            answer=answer,
            citation_validation=validation,
            task_type=self.task_type,
        )

    async def stream(
        self, *, messages: list[ConvMessage], top_k: int
    ) -> AsyncIterator[StreamEvent]:
        rewritten = await self._rewrite(messages)
        chunks = await self._retriever.retrieve(query=rewritten.rewritten, top_k=top_k)
        yield StreamEvent("task_type", self.task_type.value)
        yield StreamEvent("citations", _citations_payload(chunks))
        async for delta in self._generator.stream(
            query=rewritten.original,
            chunks=chunks,
            task_type=self.task_type,
            history=messages,
        ):
            yield StreamEvent("delta", delta)
        yield StreamEvent("done", "")


class QAHandler(_RetrievalHandler):
    task_type = TaskType.QA


class PlanningHandler(_RetrievalHandler):
    task_type = TaskType.PLANNING


# ---- Meta handler (no retrieval) -------------------------------------


class MetaHandler:
    """System-info / identity queries — skip retriever and generator
    entirely, render from canned templates. Ignores prior conversation
    turns: meta queries are intentionally self-contained."""

    task_type = TaskType.META

    def __init__(self, info_provider: SystemInfoProvider):
        self._info_provider = info_provider

    def _render(self, query: str) -> tuple[str, GeneratedAnswer]:
        if is_identity_query(query):
            text = IDENTITY_ANSWER
        else:
            info = self._info_provider.get()
            text = format_meta_answer(info)
        return text, GeneratedAnswer(content=text, citations=[])

    async def handle(self, *, messages: list[ConvMessage], top_k: int) -> HandlerResult:
        del top_k  # meta path is retrieval-free
        latest = latest_user_message(messages)
        _, answer = self._render(latest)
        return HandlerResult(
            query=latest,
            chunks=[],
            answer=answer,
            citation_validation=CitationValidation(
                is_valid=True, referenced_numbers=set(), invalid_numbers=set()
            ),
            task_type=self.task_type,
        )

    async def stream(
        self, *, messages: list[ConvMessage], top_k: int
    ) -> AsyncIterator[StreamEvent]:
        del top_k
        latest = latest_user_message(messages)
        text, _ = self._render(latest)
        yield StreamEvent("task_type", self.task_type.value)
        yield StreamEvent("citations", "[]")
        # Pace the deltas so the canned answer feels like real LLM
        # output instead of being dumped instantly. Sprint 5d UX fix.
        for chunk in _chunks_for_streaming(text):
            yield StreamEvent("delta", chunk)
            await asyncio.sleep(_DELTA_PACING_SECONDS)
        yield StreamEvent("done", "")


_DELTA_CHUNK_SIZE = 4
_DELTA_PACING_SECONDS = 0.025


def _chunks_for_streaming(text: str, *, size: int = _DELTA_CHUNK_SIZE) -> list[str]:
    if not text:
        return []
    return [text[i : i + size] for i in range(0, len(text), size)]
