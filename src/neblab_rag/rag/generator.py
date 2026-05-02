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

引用纪律（最重要 — Sprint 2.5 加严）：
A. 论断必须直接来自文献片段。**禁止外推、禁止合成新结论、禁止意译扩展**超出片段字面内容。
B. 只有当某个 [N] 片段**直接支持**该论断时，才用 [N] 标注。如果片段只是"沾边/相关"但不直接背书该论断，**不要**为这个论断引用它。
C. 一个论断可以引用多个 [N]，但每个 [N] 都必须独立支持该论断。
D. 如果整段文献片段都不能直接支持要回答的问题，**明确说"文献中暂未找到相关结论"**而不是凑一个泛泛回答。

格式与语气：
1. 在每个论断后用 [N] 标注引用来源（N 是片段编号 1..N）。
2. 学术风格，简洁专业，不使用感叹号或营销式语言。
3. 中文问中文答，英文问英文答。
"""

EMPTY_CONTEXT_REPLY = "文献库中暂未找到相关结论。"

# Generator runs deterministic — same query + same chunks → same answer.
# Sprint 4 baseline showed temperature=0.3 (the LLM library default) made
# eval runs non-reproducible and likely contributed to the 16% not_supported
# citation rate (creative paraphrasing beyond chunk content).
GENERATOR_TEMPERATURE = 0.0


def _format_chunks(chunks: list[RetrievedChunk]) -> str:
    return "\n".join(f"[{i}] {c.title}\n{c.text}\n" for i, c in enumerate(chunks, 1))


class AnswerGenerator:
    def __init__(self, llm: LLMProvider):
        self._llm = llm

    def _build_messages(self, query: str, chunks: list[RetrievedChunk]) -> list[ChatMessage]:
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

    async def generate(self, *, query: str, chunks: list[RetrievedChunk]) -> GeneratedAnswer:
        if not chunks:
            return GeneratedAnswer(content=EMPTY_CONTEXT_REPLY, citations=[])
        resp = await self._llm.chat(
            ChatRequest(
                messages=self._build_messages(query, chunks),
                temperature=GENERATOR_TEMPERATURE,
            )
        )
        return GeneratedAnswer(content=resp.content, citations=self._citations(chunks))

    async def stream(self, *, query: str, chunks: list[RetrievedChunk]) -> AsyncIterator[str]:
        if not chunks:
            yield EMPTY_CONTEXT_REPLY
            return
        async for chunk in self._llm.stream(
            ChatRequest(
                messages=self._build_messages(query, chunks),
                temperature=GENERATOR_TEMPERATURE,
            )
        ):
            if chunk.delta:
                yield chunk.delta
