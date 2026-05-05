"""Sprint 5c — task classifier sanity tests.

Covers the obvious bands: pure QA, pure planning, and the mixed cases
where a QA override should beat a planning keyword.
"""

import pytest

from neblab_rag.rag.task_classifier import TaskType, classify


@pytest.mark.parametrize(
    "query",
    [
        "什么是土地退化零增长？",
        "为什么过度放牧会加速荒漠化？",
        "三北防护林对当地气温有什么影响？",
        "What is the Land Degradation Neutrality framework?",
        "Why does shelterbelt structure affect wind erosion?",
    ],
)
def test_classifies_qa(query: str) -> None:
    assert classify(query) == TaskType.QA


@pytest.mark.parametrize(
    "query",
    [
        "帮我设计一个针对科尔沁沙地的防沙治沙方案",
        "给我一份针对干旱区造林的具体规划",
        "请提出一个针对民勤沙区的恢复策略",
        "Design a shelterbelt plan for the Loess Plateau",
        "Recommend strategies for restoring semi-arid grasslands",
        "How to allocate water resources in dryland restoration?",
    ],
)
def test_classifies_planning(query: str) -> None:
    assert classify(query) == TaskType.PLANNING


def test_qa_override_wins_when_both_signals_present() -> None:
    """Definition queries that include planning vocabulary should still QA."""
    assert classify("什么是 IUCN 的恢复方案？") == TaskType.QA
    assert classify("What is a desertification mitigation strategy?") == TaskType.QA


@pytest.mark.parametrize(
    "query",
    [
        "NEBLab 一共收录了多少篇文献？",
        "你们的语料库里有多少个文献？",
        "你的知识库覆盖哪些主题？",
        "what topics does this corpus cover?",
        "How many documents are in this system?",
        "describe this knowledge base",
        # identity queries also route through META
        "你是什么模型？",
        "你的模型底座是什么？",
        "What model are you?",
        "Which LLM do you use?",
    ],
)
def test_classifies_meta(query: str) -> None:
    assert classify(query) == TaskType.META


def test_meta_wins_over_planning_when_both_match() -> None:
    """'你的语料库里建议哪些主题' has both meta phrasing and planning
    vocabulary ('建议') — meta should win since the question is about
    the system, not about a strategy in the literature."""
    assert classify("你的语料库里建议哪些主题？") == TaskType.META


def test_empty_query_defaults_to_qa() -> None:
    assert classify("") == TaskType.QA


def test_unknown_phrasing_defaults_to_qa() -> None:
    """No keyword match → safe default. Strict QA prompt won't fabricate."""
    assert classify("生态系统服务功能") == TaskType.QA
