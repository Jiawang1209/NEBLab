"""Translate non-English queries to English before retrieval.

Why this exists: Sprint-2 baseline showed that Chinese questions retrieve
unrelated documents even when the topic exists in the corpus, because the
corpus is English and the cross-lingual embedding gap is real.

Workflow when wired into the pipeline:
  - User asks 中文 question
  - Rewriter detects CJK → asks LLM to translate to natural English
  - Translated query goes to retriever (better match against EN corpus)
  - Original 中文 query goes to generator (so the answer comes back in 中文)

Failure mode: if the LLM call fails, we fall back to the original query
rather than crash. Worst case we get the same retrieval quality as before
the rewriter existed.
"""

from pydantic import BaseModel

from neblab_rag.logging_config import get_logger
from neblab_rag.providers.llm.base import ChatMessage, ChatRequest, LLMProvider

log = get_logger(__name__)


REWRITE_SYSTEM_PROMPT = """You translate user research questions into natural English suitable for searching an English-language academic literature corpus.

Rules:
1. Output ONLY the translated English query, nothing else. No quotes, no commentary, no markdown.
2. Preserve the user's intent and any technical terms.
3. If the input is already English, return it unchanged.
4. Keep it concise — aim to match what a researcher would type into a search box."""


class RewrittenQuery(BaseModel):
    original: str
    rewritten: str
    was_rewritten: bool


def has_cjk(text: str) -> bool:
    """True if text contains any CJK unified ideograph (rough Chinese marker)."""
    return any(0x4E00 <= ord(c) <= 0x9FFF for c in text)


class QueryRewriter:
    def __init__(self, llm: LLMProvider):
        self._llm = llm

    async def rewrite(self, query: str) -> RewrittenQuery:
        if not has_cjk(query):
            return RewrittenQuery(original=query, rewritten=query, was_rewritten=False)

        try:
            resp = await self._llm.chat(
                ChatRequest(
                    messages=[
                        ChatMessage(role="system", content=REWRITE_SYSTEM_PROMPT),
                        ChatMessage(role="user", content=query),
                    ],
                    temperature=0.0,  # deterministic — same query, same translation
                    max_tokens=256,
                )
            )
        except Exception as exc:
            log.warning("query_rewrite_failed", error=str(exc), query=query)
            return RewrittenQuery(original=query, rewritten=query, was_rewritten=False)

        cleaned = resp.content.strip().strip('"').strip("'").strip()
        if not cleaned:
            log.warning("query_rewrite_empty", query=query)
            return RewrittenQuery(original=query, rewritten=query, was_rewritten=False)

        log.info("query_rewritten", original=query, rewritten=cleaned)
        return RewrittenQuery(original=query, rewritten=cleaned, was_rewritten=True)
