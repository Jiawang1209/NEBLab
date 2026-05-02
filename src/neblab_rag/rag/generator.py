"""LLM-driven answer generation with inline citations.

Builds a system+user prompt from a list of retrieved chunks, asks the LLM
to answer in the project's house style with [N] citation markers, then
returns the answer paired with a citation ledger that maps each [N] back
to its source document. The ledger is built deterministically from the
chunk list (1-indexed) — we do not parse [N] out of the model output to
build it, because the model may forget or invent numbers; downstream
validation (Task 27) catches that mismatch.
"""

from collections.abc import AsyncIterator

from pydantic import BaseModel

from neblab_rag.providers.llm.base import ChatMessage, ChatRequest, LLMProvider
from neblab_rag.rag.retriever import RetrievedChunk


class Citation(BaseModel):
    number: int
    doc_id: int
    openalex_id: str | None
    title: str


class GeneratedAnswer(BaseModel):
    content: str
    citations: list[Citation]


SYSTEM_PROMPT = """你是北方生态屏障数字实验室的科研助手。
基于下面提供的文献片段回答用户的问题。

规则：
1. 必须用提供的文献片段中的信息作答，不要编造。
2. 在每个论断后用 [N] 标注引用来源（N 是片段编号）。
3. 如果文献片段不足以回答问题，明确说"文献中暂未找到相关结论"。
4. 学术风格，简洁专业，不要使用感叹号或营销式语言。
5. 中文问中文答，英文问英文答。
"""

EMPTY_CONTEXT_REPLY = "文献库中暂未找到相关结论。"


def _format_chunks(chunks: list[RetrievedChunk]) -> str:
    return "\n".join(f"[{i}] {c.title}\n{c.text}\n" for i, c in enumerate(chunks, 1))


class AnswerGenerator:
    def __init__(self, llm: LLMProvider):
        self._llm = llm

    def _build_messages(
        self, query: str, chunks: list[RetrievedChunk]
    ) -> list[ChatMessage]:
        return [
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            ChatMessage(
                role="user",
                content=f"文献片段：\n\n{_format_chunks(chunks)}\n\n问题：{query}",
            ),
        ]

    def _citations(self, chunks: list[RetrievedChunk]) -> list[Citation]:
        return [
            Citation(
                number=i,
                doc_id=c.doc_id,
                openalex_id=c.openalex_id,
                title=c.title,
            )
            for i, c in enumerate(chunks, 1)
        ]

    async def generate(
        self, *, query: str, chunks: list[RetrievedChunk]
    ) -> GeneratedAnswer:
        if not chunks:
            return GeneratedAnswer(content=EMPTY_CONTEXT_REPLY, citations=[])
        resp = await self._llm.chat(
            ChatRequest(messages=self._build_messages(query, chunks))
        )
        return GeneratedAnswer(content=resp.content, citations=self._citations(chunks))

    async def stream(
        self, *, query: str, chunks: list[RetrievedChunk]
    ) -> AsyncIterator[str]:
        if not chunks:
            yield EMPTY_CONTEXT_REPLY
            return
        async for chunk in self._llm.stream(
            ChatRequest(messages=self._build_messages(query, chunks))
        ):
            if chunk.delta:
                yield chunk.delta
