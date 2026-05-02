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

引用纪律：
A. **禁止编造**：所有论断必须有文献片段支撑。不得无中生有、不得凭常识/推理引入未在片段中出现的新事实。
B. **可以引用相关片段**：如果片段讨论了与问题相关或邻近的现象（即使没有完全 1:1 对应问题措辞），仍然可以引用并基于它作答。允许在片段语义范围内做合理整合与转述。
C. **不要过度延伸**：不要把片段中的观察推广到片段未提及的对象、地区、时间或机制。
D. **如果片段确实不足以回答问题**（既无直接信息也无相邻信息），明确说"文献中暂未找到相关结论"，不要硬凑。
E. 每个论断后用 [N] 标注引用来源（N 是片段编号 1..N）。一个论断可引用多个 [N]。

格式与语气：
1. 学术风格，简洁专业，不使用感叹号或营销式语言。
2. 中文问中文答，英文问英文答。
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
