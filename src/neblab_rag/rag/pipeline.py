"""End-to-end RAG pipeline: classify → dispatch → handler.

Sprint 5d: this used to be a single retrieve-then-generate flow tuned
for QA. It's now a thin router that picks a TaskHandler by classified
TaskType and delegates the full request to it. Each handler owns its
own pipeline (some skip retrieval entirely, e.g. META). Adding a new
task type is a new handler — no edits here.
"""

from collections.abc import AsyncIterator

from pydantic import BaseModel

from neblab_rag.rag.citation import CitationValidation
from neblab_rag.rag.generator import AnswerGenerator, GeneratedAnswer
from neblab_rag.rag.handlers import (
    HandlerResult,
    MetaHandler,
    PlanningHandler,
    QAHandler,
    StreamEvent,
    TaskHandler,
)
from neblab_rag.rag.query_rewriter import QueryRewriter
from neblab_rag.rag.retriever import RetrievedChunk, Retriever
from neblab_rag.rag.system_info import SystemInfoProvider
from neblab_rag.rag.task_classifier import TaskType, classify


class RAGResult(BaseModel):
    query: str
    chunks: list[RetrievedChunk]
    answer: GeneratedAnswer
    citation_validation: CitationValidation
    task_type: TaskType
    rewritten_query: str | None = None


def _to_rag_result(handler_result: HandlerResult) -> RAGResult:
    return RAGResult(
        query=handler_result.query,
        chunks=handler_result.chunks,
        answer=handler_result.answer,
        citation_validation=handler_result.citation_validation,
        task_type=handler_result.task_type,
        rewritten_query=handler_result.rewritten_query,
    )


class RAGPipeline:
    """Thin router: classify(query) → handler.stream(query). Holds the
    handler registry; the retriever / generator / rewriter / system_info
    providers are owned by individual handlers, not the pipeline."""

    def __init__(
        self,
        retriever: Retriever,
        generator: AnswerGenerator,
        *,
        query_rewriter: QueryRewriter | None = None,
        system_info_provider: SystemInfoProvider | None = None,
    ):
        self._retriever = retriever
        self._generator = generator
        self._rewriter = query_rewriter

        self._handlers: dict[TaskType, TaskHandler] = {
            TaskType.QA: QAHandler(retriever, generator, query_rewriter),
            TaskType.PLANNING: PlanningHandler(retriever, generator, query_rewriter),
        }
        if system_info_provider is not None:
            self._handlers[TaskType.META] = MetaHandler(system_info_provider)

    @property
    def retriever(self) -> Retriever:
        return self._retriever

    @property
    def generator(self) -> AnswerGenerator:
        return self._generator

    def _route(self, query: str) -> tuple[TaskType, TaskHandler]:
        task_type = classify(query)
        handler = self._handlers.get(task_type)
        if handler is None:
            # No handler registered for this type (e.g. META without a
            # SystemInfoProvider configured). Fall back to QA — the
            # strict prompt is the safe default.
            return TaskType.QA, self._handlers[TaskType.QA]
        return task_type, handler

    async def answer(self, *, query: str, top_k: int = 7) -> RAGResult:
        _, handler = self._route(query)
        result = await handler.handle(query=query, top_k=top_k)
        return _to_rag_result(result)

    async def stream(
        self, *, query: str, top_k: int = 7
    ) -> AsyncIterator[StreamEvent]:
        _, handler = self._route(query)
        async for event in handler.stream(query=query, top_k=top_k):
            yield event

    @staticmethod
    def classify_task(query: str) -> TaskType:
        return classify(query)
