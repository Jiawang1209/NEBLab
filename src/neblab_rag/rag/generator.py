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
from neblab_rag.rag.conversation import ConvMessage
from neblab_rag.rag.retriever import RetrievedChunk
from neblab_rag.rag.task_classifier import TaskType


class Citation(BaseModel):
    number: int
    doc_id: int
    openalex_id: str | None
    title: str


class GeneratedAnswer(BaseModel):
    content: str
    citations: list[Citation]


# Strict QA prompt — used for definition / mechanism / fact-lookup queries.
# Sprint 5b drove citation_supported_rate from 39% → 64% specifically by
# tightening this prompt; do not soften without re-running the 86q eval.
QA_SYSTEM_PROMPT = """你是北方生态屏障数字实验室的科研助手。
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

# Planning prompt — for design / strategy / "how do I do X" queries. The
# strict QA prompt makes the model refuse extrapolation from adjacent
# regions / cases, which is the wrong move for design tasks where users
# need synthesised guidance, not a literature search.
#
# Adopted verbatim from docs/PlanRAG.md (科研规划型 RAG system prompt).
# Tightens four levers vs the QA prompt:
#   1. allows labeled reasoning beyond literal evidence
#   2. enforces explicit "where evidence ends, where inference begins"
#      phrasing so the user can audit every claim
#   3. enforces a 10-section structured output (总体判断 ... 后续数据需求)
#   4. distinguishes evidence layers (direct / migratable / mechanism /
#      background) so adjacent-region cases get used, not refused
PLANNING_SYSTEM_PROMPT = """你是一个面向科研规划、生态治理、数据平台建设与技术方案设计的专业 RAG 助手。

你的核心任务不是简单复述文献，而是在严格尊重检索证据边界的前提下，帮助用户形成可执行、可解释、可落地的科研方案、治理方案、技术路线或规划建议。

你必须遵守以下原则：

一、证据边界原则
1. 优先基于检索到的文献、报告、数据库或知识片段回答。
2. 如果检索材料中没有直接针对用户问题的证据，不能假装已有直接证据。
3. 必须明确区分：
   - 文献直接支持的内容；
   - 可由文献迁移得到的通用原则；
   - 基于专业知识推理形成的建议；
   - 仍需补充数据验证的内容。
4. 不得将其他区域、其他物种、其他系统的案例直接表述为目标区域或目标对象的结论。

二、任务导向原则
用户的问题可能不是普通问答，而是以下类型之一：
1. 事实问答：要求准确回答已有事实；
2. 文献综述：要求总结研究进展；
3. 科研规划：要求提出研究方向、技术路线、实施路径；
4. 治理方案：要求提出设计布局、工程措施、管理措施；
5. 平台建设：要求提出系统架构、功能模块、数据流程；
6. 项目申报：要求凝练科学问题、研究内容、创新点和预期成果；
7. PPT/汇报：要求形成结构化、凝练、可展示的内容。
你必须先判断任务类型，再采用对应的回答策略。

三、当证据不足时的回答策略
当检索材料不足以直接回答用户问题时，不要只回答"无法回答"。
你应当采用以下结构：
1. 先说明证据边界：哪些内容有直接证据、哪些只能作为间接参考。
2. 再提取可迁移原则：从已有文献中抽象出机制、模式、约束和风险；不直接照搬案例，而是迁移其底层逻辑。
3. 然后形成初步方案：给出结构化框架；明确设计布局、技术路径、实施步骤、监测指标和风险控制；标注"初步建议，需本地化校正"。
4. 最后列出需要补充的数据：自然条件 / 样地调查 / 遥感数据 / 土壤 / 水文 / 气候 / 植被 / 土地利用 / 人类活动 等。

四、推理边界原则
你可以进行专业推理，但必须显式标注推理性质。推荐使用以下表达：
- "文献直接支持的是……"
- "可迁移的通用原则是……"
- "基于上述原则，可以初步推导……"
- "该部分属于规划性建议，仍需结合本地数据验证。"

五、科研规划输出要求
对于科研规划、治理方案、技术路线类问题，优先使用以下结构：
1. 总体判断
2. 证据基础与适用边界
3. 总体目标
4. 设计思路
5. 空间布局或系统架构
6. 技术方案
7. 实施步骤
8. 监测与评价指标
9. 风险与约束
10. 需要补充的数据
11. 可形成的成果

六、引用要求
1. 文献直接支持的内容必须引用来源编号（用 [N] 标记，N 是片段编号 1..N）。
2. 推理性内容可以不强制引用，但必须说明是"基于已有证据的推理"。
3. 不要把没有引用支持的推理说成文献结论。
4. 如果引用片段不足，应说明"现有片段支持有限"。

七、表达风格
1. 语言专业、清晰、务实。
2. 不要过度保守，也不要过度编造。
3. 回答应服务于用户的实际任务，而不仅是判断文献是否充分。
4. 对科研人员、项目申报、平台建设和生态治理场景，要优先输出可执行框架。
"""

# Backward-compat alias: callers that still import SYSTEM_PROMPT get the
# strict one (same behavior as before Sprint 5c).
SYSTEM_PROMPT = QA_SYSTEM_PROMPT

EMPTY_CONTEXT_REPLY = "文献库中暂未找到相关结论。"


def _system_prompt_for(task_type: TaskType) -> str:
    if task_type == TaskType.PLANNING:
        return PLANNING_SYSTEM_PROMPT
    return QA_SYSTEM_PROMPT


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

    def _build_messages(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        task_type: TaskType,
        history: list[ConvMessage] | None = None,
    ) -> list[ChatMessage]:
        """Assemble the chat messages for the LLM call.

        Sprint 5e: when ``history`` is supplied, prior user/assistant
        turns slot in between the system prompt and the chunks-bearing
        user message. The chunks are always attached to the LATEST
        user turn so the model knows which prior turn they belong to.
        Single-turn callers can pass history=None — the behaviour is
        identical to the pre-5e generator.
        """
        out: list[ChatMessage] = [
            ChatMessage(role="system", content=_system_prompt_for(task_type)),
        ]
        if history:
            # Replay everything except the last user turn — that gets
            # rebuilt below to embed the retrieved chunks.
            replay = history[:-1] if history and history[-1].role == "user" else history
            for m in replay:
                out.append(ChatMessage(role=m.role, content=m.content))
        out.append(
            ChatMessage(
                role="user",
                content=f"文献片段：\n\n{_format_chunks(chunks)}\n\n问题：{query}",
            )
        )
        return out

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
        self,
        *,
        query: str,
        chunks: list[RetrievedChunk],
        task_type: TaskType = TaskType.QA,
        history: list[ConvMessage] | None = None,
    ) -> GeneratedAnswer:
        if not chunks:
            return GeneratedAnswer(content=EMPTY_CONTEXT_REPLY, citations=[])
        resp = await self._llm.chat(
            ChatRequest(
                messages=self._build_messages(query, chunks, task_type, history),
                temperature=GENERATOR_TEMPERATURE,
            )
        )
        return GeneratedAnswer(content=resp.content, citations=self._citations(chunks))

    async def stream(
        self,
        *,
        query: str,
        chunks: list[RetrievedChunk],
        task_type: TaskType = TaskType.QA,
        history: list[ConvMessage] | None = None,
    ) -> AsyncIterator[str]:
        if not chunks:
            yield EMPTY_CONTEXT_REPLY
            return
        async for chunk in self._llm.stream(
            ChatRequest(
                messages=self._build_messages(query, chunks, task_type, history),
                temperature=GENERATOR_TEMPERATURE,
            )
        ):
            if chunk.delta:
                yield chunk.delta
