"""Lightweight rule-based classifier: QA vs planning.

Sprint 5c — the 86q eval is all "is X?" / "why does X?" style, so the
generator was tuned to refuse extrapolation. Real users also ask "design
me a plan for X" — that fails badly under the strict QA prompt. Route
those to a separate planning prompt that allows labeled reasoning.

We deliberately keep this regex-based for v1: an LLM-call classifier
adds latency on the hot path and the cost/benefit doesn't justify it
when 80% of cases are decidable by surface keywords. Failure mode is
fine — misclassified planning queries fall back to QA's strict prompt
(no fabrication risk), misclassified QA queries get a slightly more
verbose answer (no correctness risk). Asymmetric upside.

Promote to LLM-based classification in a later sprint if eval shows
the regex misses non-trivial cases.
"""

from __future__ import annotations

import re
from enum import StrEnum


class TaskType(StrEnum):
    QA = "qa"
    PLANNING = "planning"
    META = "meta"


# Patterns indicating a meta query — about the SYSTEM (corpus size,
# coverage, configuration) rather than about the literature content.
# Sprint 5d: these need to be checked first. Without this branch the RAG
# pipeline retrieves arbitrary chunks for "how many documents are there"
# and the generator confidently reports the chunk count as the corpus
# size (real bug observed before this handler was added).
_META_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        # corpus stats / coverage
        r"多少篇",
        r"多少个(文献|文章|论文)",
        r"一共.*?(篇|个|条)",
        r"总共.*?(篇|个|条)",
        r"收录.*?(多少|哪些|什么)",
        r"(语料库|知识库|数据库|系统|文献库).*?(多少|有什么|包含|覆盖|哪些|规模|状态|信息)",
        r"(覆盖|包含|涵盖).*?(多少|哪些)(主题|语言|领域)",
        r"哪些(主题|语言|领域|来源)",
        r"\bhow many (?:docs?|documents?|papers?|articles?)\b",
        r"\bcorpus (?:size|coverage|stats?|info)\b",
        r"\b(?:what topics|which languages)\b",
        r"\b(?:about|describe) (?:this|the) (?:system|corpus|knowledge ?base)\b",
        # identity / model base — Sprint 5d: route these to META and let
        # the handler render the canned identity template instead of
        # asking the LLM (which would hallucinate "I'm DeepSeek" etc.).
        r"你是(?:什么|哪个|哪一个)(?:模型|AI|大模型|系统|助手)",
        r"你(?:的)?(?:模型)?(?:底座|基座|backbone)",
        r"谁(?:开发|训练|做)(?:了)?你",
        r"你由(?:什么|哪个).*?(?:模型|公司)",
        r"\bwhat (?:model|llm|ai) (?:are you|is this|powers?)\b",
        r"\bwhich (?:model|llm) (?:are you|do you use)\b",
        r"\bpowered by (?:what|which)\b",
    )
)

# Keywords that strongly suggest planning/design/strategy work. Both
# Chinese and English — users mix languages frequently.
_PLANNING_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        # zh: design/plan/strategy/proposal/measures/path/recommendation
        r"设计",
        r"方案",
        r"规划",
        r"计划",
        r"措施",
        r"策略",
        r"做法",
        r"路线",
        r"建议",
        # zh: imperative help phrases
        r"帮我",
        r"给我",
        r"如何制定",
        r"怎么安排",
        r"怎么做",
        # en
        r"\bdesign\b",
        r"\bplan\b",
        r"\bstrategy\b",
        r"\bstrategies\b",
        r"\bproposal\b",
        r"\bblueprint\b",
        r"\bframework\b",
        r"\brecommend(?:ation)?s?\b",
        r"\bhow to\b",
        r"\bhelp me\b",
    )
)

# Strong QA signals — when these appear we keep the strict prompt even
# if a planning keyword also matched (e.g. "什么是 land degradation
# neutrality 的具体方案"). Definition / mechanism / explanation queries.
_QA_OVERRIDE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"^什么是",
        r"是什么",
        r"^为什么",
        r"^如何理解",
        r"\bwhat is\b",
        r"\bwhat are\b",
        r"\bwhy (?:does|do|is|are)\b",
        r"\bdefine\b",
    )
)


def classify(query: str) -> TaskType:
    """Route a query to the right task type.

    Order matters:
      1. META  — checked first so "你的语料库收录多少文献" doesn't get
                 routed to PLANNING by the "你..." prefix.
      2. QA override — definition / mechanism queries that should stay
                 strict even if they include planning vocabulary.
      3. PLANNING — design / strategy / "how do I do X".
      4. Default → QA. Strict prompt is the safe fallback.
    """
    if not query:
        return TaskType.QA
    for p in _META_PATTERNS:
        if p.search(query):
            return TaskType.META
    for p in _QA_OVERRIDE_PATTERNS:
        if p.search(query):
            return TaskType.QA
    for p in _PLANNING_PATTERNS:
        if p.search(query):
            return TaskType.PLANNING
    return TaskType.QA
