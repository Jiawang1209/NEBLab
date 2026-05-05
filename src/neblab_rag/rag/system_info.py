"""Sprint 5d — provide corpus stats from Postgres for the meta task handler.

The RAG handlers retrieve chunks from the literature; meta queries (e.g.
"how many documents are in NEBLab?") have no answer there and would be
confidently fabricated by the LLM. This module is the structured-data
backstop: live queries against `documents` / `chunks` plus baked-in
constants for things that don't change per request (eval rates,
retriever config, sprint version).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy import func
from sqlalchemy.orm import Session

from neblab_rag.db.engine import get_session
from neblab_rag.db.models import Chunk, Document, IndexStatus


@dataclass(frozen=True)
class SystemInfo:
    # Live counts
    total_docs: int
    indexed_docs: int
    total_chunks: int
    by_language: tuple[tuple[str, int], ...]

    # Baked-in config / latest eval results — update these alongside the
    # corresponding Sprint findings doc.
    chunk_size: int = 1000
    chunk_overlap: int = 200
    retriever: str = "hierarchical (top_docs=5, chunks_per_doc=3)"
    reranker_top_k: int = 7
    citation_supported_rate: float = 0.639
    answered_rate: float = 0.849
    eval_set_size: int = 86
    topics: tuple[str, ...] = ("desertification", "shelterbelt")
    sprint: str = "5d"


class SystemInfoProvider(Protocol):
    """Protocol so tests can inject a stub without touching Postgres."""

    def get(self) -> SystemInfo: ...


@dataclass
class PostgresSystemInfoProvider:
    """Reads corpus stats live from Postgres each call. The meta path is
    cold (a few requests/day at most), so caching adds complexity without
    real benefit. Revisit if meta queries become hot."""

    # Optional override hook for tests — defaults to the project's session
    # context manager if omitted.
    session_factory: object = field(default=None)

    @contextmanager
    def _session(self) -> Iterator[Session]:
        if self.session_factory is None:
            with get_session() as s:
                yield s
        else:
            # `session_factory` is expected to be a context manager itself
            # in tests (e.g. mock that yields a fake session).
            with self.session_factory() as s:  # type: ignore[misc]
                yield s

    def get(self) -> SystemInfo:
        with self._session() as session:
            total = session.query(Document).count()
            indexed = (
                session.query(Document)
                .filter(Document.status == IndexStatus.FULLTEXT_INDEXED)
                .count()
            )
            chunks = session.query(Chunk).count()
            lang_rows = (
                session.query(Document.language, func.count(Document.id))
                .filter(Document.status == IndexStatus.FULLTEXT_INDEXED)
                .group_by(Document.language)
                .all()
            )
        by_language = tuple(
            (lang or "unknown", count) for (lang, count) in sorted(lang_rows)
        )
        return SystemInfo(
            total_docs=total,
            indexed_docs=indexed,
            total_chunks=chunks,
            by_language=by_language,
        )


# Identity / model-base sub-routing inside the META path. These are
# meta queries that don't need SystemInfo data — they're answered from a
# fixed canned template. We keep both inside MetaHandler so the task
# classifier surface stays at 3 types (qa / planning / meta).
_IDENTITY_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"你是(?:什么|哪个|哪一个)(?:模型|AI|大模型|系统|助手)",
        r"你(?:的)?(?:模型)?(?:底座|基座|backbone)",
        r"谁(?:开发|训练|做)(?:了)?你",
        r"你由(?:什么|哪个).*?(?:模型|公司)",
        r"\bwhat (?:model|llm|ai) (?:are you|is this|powers?)\b",
        r"\bwhich (?:model|llm) (?:are you|do you use)\b",
        r"\bpowered by (?:what|which)\b",
    )
)


def is_identity_query(query: str) -> bool:
    """True when a META query is asking about the assistant's identity /
    underlying model rather than corpus stats."""
    return any(p.search(query) for p in _IDENTITY_PATTERNS)


IDENTITY_ANSWER = (
    "## 关于 NEBLab 知识助手\n\n"
    "我是 **NEBLab 知识助手**，"
    "北方生态屏障数字实验室（Northern Ecological Barrier Lab）的 RAG 检索增强问答系统。\n\n"
    "### 模型底座\n\n"
    "- **磐石大模型**（Pangshi LLM）作为本系统的底座大模型。\n\n"
    "### 系统职责\n\n"
    "- 基于已索引的中英文学术文献回答用户提问\n"
    "- 对事实/机制类问题严格按文献作答（QA 模式）\n"
    "- 对设计/规划/方案类问题允许标注过的合理推理（Planning 模式）\n"
    "- 对系统自身的元信息查询直接返回结构化数据（Meta 模式）\n\n"
    "### 引用纪律\n\n"
    "- 文献直接支持：句末标 `[N]`\n"
    "- 推理或类比：句末标 `※`\n"
    "- 文献无法回答：明确说明并列出补充建议\n\n"
    "---\n\n"
    "*想了解语料规模、覆盖主题、引用准确率等数据，问"
    '"NEBLab 收录了多少篇文献"。*\n'
)


def format_meta_answer(info: SystemInfo) -> str:
    """Render a uniform Markdown answer block from the SystemInfo struct.

    We keep this template-driven (not LLM-formatted) for v1: it's
    deterministic, costs no API tokens, and the answer surface is small
    enough that a single template covers all observed meta queries.
    """
    lang_lines = "\n".join(
        f"- **{lang}**：{count} 篇" for lang, count in info.by_language
    )
    topics = " / ".join(info.topics)
    supp = f"{info.citation_supported_rate * 100:.1f}%"
    ans = f"{info.answered_rate * 100:.1f}%"
    return (
        "## NEBLab 知识库当前状态（Sprint "
        f"{info.sprint}）\n\n"
        f"### 语料规模\n\n"
        f"- 已入库文献：**{info.total_docs}** 篇\n"
        f"- 已完成全文索引：**{info.indexed_docs}** 篇\n"
        f"- 已切分 chunks：**{info.total_chunks}** 个\n\n"
        f"### 语种分布\n\n"
        f"{lang_lines}\n\n"
        f"### 主题覆盖\n\n"
        f"- {topics}\n\n"
        f"### 检索与生成配置\n\n"
        f"- chunk_size = {info.chunk_size} 字符 / overlap = {info.chunk_overlap}\n"
        f"- retriever：{info.retriever}\n"
        f"- reranker top_k = {info.reranker_top_k}\n\n"
        f"### 最近一次评测（{info.eval_set_size} 题, judge=DeepSeek）\n\n"
        f"- 引用准确率：**{supp}**\n"
        f"- 回答覆盖率：**{ans}**\n\n"
        "---\n\n"
        "*以上为系统元信息，从 Postgres 实时查询而来，不来自文献检索。*\n"
    )
