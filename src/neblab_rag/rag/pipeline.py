"""End-to-end RAG pipeline: classify → dispatch → handler.

Sprint 5d introduced the router architecture; Sprint 5e extends the
public surface to a list of conversation messages so multi-turn
follow-ups can flow through. Single-query callers (eval runner)
construct a one-message list — there's no separate single-query path.
"""

from collections.abc import AsyncIterator

from pydantic import BaseModel

from neblab_rag.rag.citation import CitationValidation
from neblab_rag.rag.conversation import ConvMessage, latest_user_message
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


def _wrap_query(query: str) -> list[ConvMessage]:
    """Single-turn callers (eval) pass a query string; turn it into a
    one-message list so the rest of the pipeline doesn't branch."""
    return [ConvMessage(role="user", content=query)]


class RAGPipeline:
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

    def _route(self, messages: list[ConvMessage]) -> tuple[TaskType, TaskHandler]:
        task_type = classify(latest_user_message(messages))
        handler = self._handlers.get(task_type)
        if handler is None:
            return TaskType.QA, self._handlers[TaskType.QA]
        return task_type, handler

    async def answer(
        self,
        *,
        messages: list[ConvMessage] | None = None,
        query: str | None = None,
        top_k: int = 7,
    ) -> RAGResult:
        """Either ``messages`` (multi-turn) or ``query`` (single-turn) must
        be provided. Single-turn callers — primarily the eval runner —
        keep their old call shape; new clients should pass messages."""
        if messages is None and query is None:
            raise ValueError("either messages or query is required")
        msgs = messages if messages is not None else _wrap_query(query or "")
        _, handler = self._route(msgs)
        result = await handler.handle(messages=msgs, top_k=top_k)
        return _to_rag_result(result)

    async def stream(
        self,
        *,
        messages: list[ConvMessage] | None = None,
        query: str | None = None,
        top_k: int = 7,
    ) -> AsyncIterator[StreamEvent]:
        if messages is None and query is None:
            raise ValueError("either messages or query is required")
        msgs = messages if messages is not None else _wrap_query(query or "")
        _, handler = self._route(msgs)
        async for event in handler.stream(messages=msgs, top_k=top_k):
            yield event

    @staticmethod
    def classify_task(query: str) -> TaskType:
        return classify(query)
