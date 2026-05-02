"""Structural metrics computed from RAGResult — no extra LLM calls.

These are the cheap-to-compute baseline metrics. The expensive metric
(LLM-as-judge for citation accuracy) lives in eval.judge.

We deliberately don't ship a "correctness" or "fluency" metric here —
those need either ground-truth answers (we don't have any) or LLM-judge
(separate module). What's measurable for free:

  - structural validity (citation_valid)
  - "did we attempt an answer" (non-empty / non-fallback)
  - retrieval shape (chunks per question, citations per question)
  - latency

Together these catch big regressions: if a sprint drops citation_valid
or doubles latency, the structural metrics will show it without a single
LLM call.
"""

from collections.abc import Sequence

from pydantic import BaseModel

from neblab_rag.rag.generator import EMPTY_CONTEXT_REPLY


class CaseResult(BaseModel):
    """Per-question outcome — what the runner records for each EvalCase."""

    case_id: str
    question: str
    answer: str
    citation_valid: bool
    citations_count: int
    chunks_retrieved: int
    latency_seconds: float
    expected_coverage: str  # echoes EvalCase.corpus_coverage_expected
    error: str | None = None


class AggregateMetrics(BaseModel):
    n_cases: int
    n_errors: int
    citation_validity_rate: float  # over non-error cases
    answered_rate: float  # % that did NOT fall back to "literature insufficient"
    expected_yes_answered_rate: float  # honesty: when corpus has it, did we answer?
    expected_no_refused_rate: float  # honesty: when corpus doesn't, did we refuse?
    avg_citations_per_answer: float
    avg_chunks_retrieved: float
    latency_p50: float
    latency_p95: float


def is_fallback_answer(answer: str) -> bool:
    """Detect both English and Chinese 'no relevant findings' templates."""
    if answer == EMPTY_CONTEXT_REPLY:
        return True
    # Generator's prompt nudges the LLM to use these phrases when chunks
    # are insufficient — same in both languages.
    fallback_markers = ("文献中暂未找到", "文献库中暂未找到", "literature insufficient")
    a = answer.strip()
    return any(m in a for m in fallback_markers)


def aggregate(results: Sequence[CaseResult]) -> AggregateMetrics:
    if not results:
        return AggregateMetrics(
            n_cases=0,
            n_errors=0,
            citation_validity_rate=0.0,
            answered_rate=0.0,
            expected_yes_answered_rate=0.0,
            expected_no_refused_rate=0.0,
            avg_citations_per_answer=0.0,
            avg_chunks_retrieved=0.0,
            latency_p50=0.0,
            latency_p95=0.0,
        )

    n_total = len(results)
    errors = [r for r in results if r.error]
    ok = [r for r in results if not r.error]
    n_ok = len(ok)

    answered = [r for r in ok if not is_fallback_answer(r.answer)]
    expected_yes = [r for r in ok if r.expected_coverage == "yes"]
    expected_yes_answered = [r for r in expected_yes if not is_fallback_answer(r.answer)]
    expected_no = [r for r in ok if r.expected_coverage == "no"]
    expected_no_refused = [r for r in expected_no if is_fallback_answer(r.answer)]

    latencies = sorted(r.latency_seconds for r in ok)

    return AggregateMetrics(
        n_cases=n_total,
        n_errors=len(errors),
        citation_validity_rate=_rate(sum(1 for r in ok if r.citation_valid), n_ok),
        answered_rate=_rate(len(answered), n_ok),
        expected_yes_answered_rate=_rate(len(expected_yes_answered), len(expected_yes)),
        expected_no_refused_rate=_rate(len(expected_no_refused), len(expected_no)),
        avg_citations_per_answer=_avg(r.citations_count for r in answered),
        avg_chunks_retrieved=_avg(r.chunks_retrieved for r in ok),
        latency_p50=_percentile(latencies, 0.50),
        latency_p95=_percentile(latencies, 0.95),
    )


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _avg(values: object) -> float:
    items = list(values)  # type: ignore[arg-type]
    return sum(items) / len(items) if items else 0.0


def _percentile(sorted_values: list[float], p: float) -> float:
    """Nearest-rank percentile. Returns 0 for empty input."""
    if not sorted_values:
        return 0.0
    idx = max(0, min(len(sorted_values) - 1, round(p * (len(sorted_values) - 1))))
    return sorted_values[idx]
