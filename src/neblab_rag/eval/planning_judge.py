"""LLM-as-judge for planning answers.

Sprint 5d: the 86q QA judge ("does this chunk support this claim?")
doesn't fit planning answers, where the value is in synthesis +
labeled inference, not per-claim citation faithfulness. This judge
scores 5 dimensions on a 1-5 scale per question:

  - structure          : section-based plan vs unstructured prose
  - evidence_boundary  : [N] for evidence vs ※ for inference, used correctly
  - actionability      : concrete executable steps vs abstract platitudes
  - inference_quality  : extrapolations grounded in mechanisms vs wild guesses
  - boundary_acknowledgement : explicit "what evidence is/isn't there" framing

For out-of-scope questions, ``boundary_acknowledgement`` becomes the
critical dimension (does it admit the gap rather than fabricate?). The
other 4 still score the parts that DO fit.
"""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel

from neblab_rag.logging_config import get_logger
from neblab_rag.providers.llm.base import ChatMessage, ChatRequest, LLMProvider

log = get_logger(__name__)


Dimension = Literal[
    "structure",
    "evidence_boundary",
    "actionability",
    "inference_quality",
    "boundary_acknowledgement",
]


class PlanningJudgment(BaseModel):
    case_id: str
    structure: int
    evidence_boundary: int
    actionability: int
    inference_quality: int
    boundary_acknowledgement: int
    rationale: str
    judge_error: str | None = None

    @property
    def total(self) -> int:
        return (
            self.structure
            + self.evidence_boundary
            + self.actionability
            + self.inference_quality
            + self.boundary_acknowledgement
        )

    @property
    def average(self) -> float:
        return self.total / 5.0


PLANNING_JUDGE_SYSTEM_PROMPT = """你是一个对科研规划/方案/设计答案进行质量评估的评审。

你会拿到：
- QUESTION（用户提出的规划/方案/设计请求）
- ANSWER（系统生成的回答，可能包含 [N] 引用与 ※ 推理标记）
- N_CHUNKS（系统检索到的文献片段数量）
- COVERAGE_EXPECTED（"yes" / "partial" / "no"，表示语料库对此问题的覆盖预期）

按以下五个维度，每项 1-5 分给出整数分数：

1. **structure（结构化程度）**
   1 = 单段散文，无结构 / 5 = 清晰的多节小标题，覆盖背景—证据—设计—风险—数据需求等关键维度
2. **evidence_boundary（证据边界标注）**
   1 = 把推理冒充成文献结论，或没有任何标注 / 5 = [N] 用于文献支持的论断、※ 用于推理或类比，二者清晰区分
3. **actionability（可执行性）**
   1 = 全是空洞口号 / 5 = 给出具体的空间布局、技术参数、监测指标、实施步骤等可落地内容
4. **inference_quality（推理合理度）**
   1 = 离谱推断或自相矛盾 / 5 = 推理与文献中提到的机制/模式扎实联系，类比恰当
5. **boundary_acknowledgement（边界承认）**
   1 = 假装语料完全覆盖 / 5 = 明确说明哪些方面有直接证据、哪些是推理、哪些需要补充本地数据
   特别注意：当 COVERAGE_EXPECTED == "no" 时，本项是关键维度——回答必须明确说证据不足并给出可控边界的推理，否则给低分。

输出严格 JSON（不要 markdown 围栏、不要解释）：
{
  "structure": 1-5,
  "evidence_boundary": 1-5,
  "actionability": 1-5,
  "inference_quality": 1-5,
  "boundary_acknowledgement": 1-5,
  "rationale": "2-3 句中文总结，说明扣分点和亮点"
}
"""


class PlanningJudge:
    def __init__(self, llm: LLMProvider):
        self._llm = llm

    async def judge(
        self,
        *,
        case_id: str,
        question: str,
        answer: str,
        n_chunks: int,
        coverage_expected: str,
    ) -> PlanningJudgment:
        try:
            resp = await self._llm.chat(
                ChatRequest(
                    messages=[
                        ChatMessage(
                            role="system", content=PLANNING_JUDGE_SYSTEM_PROMPT
                        ),
                        ChatMessage(
                            role="user",
                            content=(
                                f"QUESTION:\n{question}\n\n"
                                f"COVERAGE_EXPECTED: {coverage_expected}\n"
                                f"N_CHUNKS: {n_chunks}\n\n"
                                f"ANSWER:\n{answer}"
                            ),
                        ),
                    ],
                    temperature=0.0,
                    # Chinese rationales are wordy; 600 tokens truncated
                    # one in 8 cases on the baseline run. 1500 is safe
                    # without inviting the judge to ramble.
                    max_tokens=1500,
                )
            )
        except Exception as exc:
            log.warning("planning_judge_llm_error", case_id=case_id, error=str(exc))
            return PlanningJudgment(
                case_id=case_id,
                structure=0,
                evidence_boundary=0,
                actionability=0,
                inference_quality=0,
                boundary_acknowledgement=0,
                rationale="",
                judge_error=f"llm error: {exc}",
            )

        return _parse_planning_verdict(case_id, resp.content)


def _parse_planning_verdict(case_id: str, content: str) -> PlanningJudgment:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(
            r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.MULTILINE
        ).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return PlanningJudgment(
            case_id=case_id,
            structure=0,
            evidence_boundary=0,
            actionability=0,
            inference_quality=0,
            boundary_acknowledgement=0,
            rationale="",
            judge_error=f"non-JSON response: {content[:200]}",
        )

    def _clamp(v: object) -> int:
        if not isinstance(v, int | float):
            return 0
        return max(0, min(5, int(v)))

    return PlanningJudgment(
        case_id=case_id,
        structure=_clamp(data.get("structure")),
        evidence_boundary=_clamp(data.get("evidence_boundary")),
        actionability=_clamp(data.get("actionability")),
        inference_quality=_clamp(data.get("inference_quality")),
        boundary_acknowledgement=_clamp(data.get("boundary_acknowledgement")),
        rationale=str(data.get("rationale", "")),
    )
