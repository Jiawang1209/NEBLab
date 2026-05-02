"""In-memory BM25 sparse index over chunk text.

Sprint 2.5 fix for the 'specific-term blindness' Sprint-4 baseline showed:
queries like 'connectivity hypothesis' missed the literal paper titled
'Do Changes in Connectivity Explain Desertification?' because dense
similarity drowned the exact keyword.

For the v1 corpus (~5K chunks max per spec), in-memory BM25 from
``rank_bm25.BM25Okapi`` is the simplest thing that could possibly work —
no extra infra, no Qdrant sparse-vector schema migration, ~10ms per query
even at 5K chunks. Plan 2 can swap in Qdrant native sparse if scale
demands it.

Tokenization:
  - English: lowercase + strip punctuation + whitespace split
  - CJK:     character-level (no word boundaries; standard for BM25/zh)
Mixed-language text falls out of the same regex naturally.
"""

import re

from pydantic import BaseModel
from rank_bm25 import BM25Okapi


class BM25Hit(BaseModel):
    chunk_id: int
    score: float


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    # First pass: lowercase and split English-style on non-alphanumerics
    # (preserves the unicode property for CJK ranges via re.UNICODE default)
    parts = re.findall(r"[\w]+", text.lower(), flags=re.UNICODE)
    for part in parts:
        # Split each "word" into runs of non-CJK vs single CJK chars
        buf = ""
        for ch in part:
            if 0x4E00 <= ord(ch) <= 0x9FFF:
                if buf:
                    tokens.append(buf)
                    buf = ""
                tokens.append(ch)
            else:
                buf += ch
        if buf:
            tokens.append(buf)
    return tokens


class BM25Index:
    """Build once, query many. Not thread-safe — caller serializes."""

    def __init__(self, *, chunk_ids: list[int], bm25: BM25Okapi | None) -> None:
        self._chunk_ids = chunk_ids
        self._bm25 = bm25  # None when corpus is empty

    @classmethod
    def from_chunks(cls, chunks: list[tuple[int, str]]) -> "BM25Index":
        """``chunks`` is a list of (chunk_id, text) — order doesn't matter."""
        if not chunks:
            return cls(chunk_ids=[], bm25=None)
        chunk_ids = [c[0] for c in chunks]
        tokenized = [_tokenize(c[1]) for c in chunks]
        return cls(chunk_ids=chunk_ids, bm25=BM25Okapi(tokenized))

    def search(self, query: str, *, top_k: int = 30) -> list[BM25Hit]:
        if self._bm25 is None:
            return []
        tokens = _tokenize(query)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        # Indices of the top_k highest scores, descending
        top_indices = sorted(range(len(scores)), key=lambda i: -scores[i])[:top_k]
        return [
            BM25Hit(chunk_id=self._chunk_ids[i], score=float(scores[i]))
            for i in top_indices
            if scores[i] > 0
        ]
