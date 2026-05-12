"""CLI: ``python -m neblab_rag.eval.planning_main --label sprint-5d-planning``.

Sprint 5d: a separate eval entry point for planning/design queries. Uses
the same RAGPipeline as the QA eval (so the pipeline's task router will
correctly route these queries to PlanningHandler), but applies the
``PlanningJudge`` rubric to the answers and writes a planning-shaped
report.

Hits paid APIs (1 LLM call per question for generation, 1 per question
for judging — so ~16 calls for an 8-question set). Treat as a
developer command, not CI default.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from neblab_rag.eval.data import EvalCase, load_eval_set
from neblab_rag.eval.planning_judge import PlanningJudge, PlanningJudgment
from neblab_rag.logging_config import get_logger
from neblab_rag.providers.factory import (
    build_bm25_index,
    build_embedding_provider,
    build_llm_provider,
    build_qdrant_repo,
    build_reranker_provider,
)
from neblab_rag.rag.generator import AnswerGenerator
from neblab_rag.rag.pipeline import RAGPipeline
from neblab_rag.rag.query_rewriter import QueryRewriter
from neblab_rag.rag.retriever import HierarchicalRetriever
from neblab_rag.rag.system_info import PostgresSystemInfoProvider

log = get_logger(__name__)


class PlanningCaseResult(BaseModel):
    case_id: str
    question: str
    coverage_expected: str
    answer: str
    n_chunks: int
    task_type: str  # what the router actually picked
    latency_seconds: float
    judgment: PlanningJudgment


class PlanningReport(BaseModel):
    eval_set_version: str
    sprint_label: str
    timestamp_utc: str
    cases: list[PlanningCaseResult]
    avg_structure: float
    avg_evidence_boundary: float
    avg_actionability: float
    avg_inference_quality: float
    avg_boundary_acknowledgement: float
    avg_total: float
    avg_total_in_scope: float  # excludes coverage_expected="no" cases
    n_planning_routed: int  # how many queries the router classified as planning
    n_qa_routed: int


def _build_pipeline() -> RAGPipeline:
    """Same wiring as the API route. Hierarchical + topk7 + chunk1000 are
    the current production defaults."""
    llm = build_llm_provider()
    retriever = HierarchicalRetriever(
        embedder=build_embedding_provider(),
        qdrant=build_qdrant_repo(),
        reranker=build_reranker_provider(),
        bm25=build_bm25_index(),
    )
    return RAGPipeline(
        retriever=retriever,
        generator=AnswerGenerator(llm=llm),
        query_rewriter=QueryRewriter(llm=llm),
        system_info_provider=PostgresSystemInfoProvider(),
    )


async def _run_one(
    case: EvalCase, pipeline: RAGPipeline, judge: PlanningJudge, top_k: int
) -> PlanningCaseResult:
    log.info("planning_case_start", case_id=case.id)
    start = time.perf_counter()
    rag = await pipeline.answer(query=case.text, top_k=top_k)
    elapsed = time.perf_counter() - start

    judgment = await judge.judge(
        case_id=case.id,
        question=case.text,
        answer=rag.answer.content,
        n_chunks=len(rag.chunks),
        coverage_expected=case.corpus_coverage_expected,
    )

    log.info(
        "planning_case_done",
        case_id=case.id,
        task_type=rag.task_type.value,
        n_chunks=len(rag.chunks),
        score=judgment.total,
        latency=round(elapsed, 2),
    )
    return PlanningCaseResult(
        case_id=case.id,
        question=case.text,
        coverage_expected=case.corpus_coverage_expected,
        answer=rag.answer.content,
        n_chunks=len(rag.chunks),
        task_type=rag.task_type.value,
        latency_seconds=elapsed,
        judgment=judgment,
    )


def _aggregate(results: list[PlanningCaseResult]) -> dict[str, float]:
    if not results:
        return {
            "avg_structure": 0.0,
            "avg_evidence_boundary": 0.0,
            "avg_actionability": 0.0,
            "avg_inference_quality": 0.0,
            "avg_boundary_acknowledgement": 0.0,
            "avg_total": 0.0,
            "avg_total_in_scope": 0.0,
        }

    def mean(attr: str) -> float:
        return statistics.mean(getattr(r.judgment, attr) for r in results)

    in_scope = [r for r in results if r.coverage_expected != "no"]
    return {
        "avg_structure": mean("structure"),
        "avg_evidence_boundary": mean("evidence_boundary"),
        "avg_actionability": mean("actionability"),
        "avg_inference_quality": mean("inference_quality"),
        "avg_boundary_acknowledgement": mean("boundary_acknowledgement"),
        "avg_total": statistics.mean(r.judgment.total for r in results),
        "avg_total_in_scope": (
            statistics.mean(r.judgment.total for r in in_scope) if in_scope else 0.0
        ),
    }


def _print_summary(report_path: Path, report: PlanningReport) -> None:
    print(f"\n=== Planning eval summary ({report.sprint_label}) ===")
    print(f"  cases:                    {len(report.cases)}")
    print(f"  routed to PLANNING:       {report.n_planning_routed} / {len(report.cases)}")
    print(f"  routed to QA (mismatch):  {report.n_qa_routed}")
    print()
    print("  --- Avg dimension scores (1-5) ---")
    print(f"  structure                : {report.avg_structure:.2f}")
    print(f"  evidence_boundary        : {report.avg_evidence_boundary:.2f}")
    print(f"  actionability            : {report.avg_actionability:.2f}")
    print(f"  inference_quality        : {report.avg_inference_quality:.2f}")
    print(f"  boundary_acknowledgement : {report.avg_boundary_acknowledgement:.2f}")
    print()
    print(f"  avg total (out of 25)    : {report.avg_total:.2f}")
    print(f"  avg total (in-scope only): {report.avg_total_in_scope:.2f}")
    print()
    print("  --- Per case ---")
    for r in report.cases:
        j = r.judgment
        marker = "OOS" if r.coverage_expected == "no" else "   "
        print(
            f"  [{marker}] {r.case_id:<35} task={r.task_type:<8} "
            f"score={j.total:>2} "
            f"(s={j.structure} e={j.evidence_boundary} a={j.actionability} "
            f"i={j.inference_quality} b={j.boundary_acknowledgement})"
        )
    print(f"\nFull report → {report_path}\n")


async def _run(args: argparse.Namespace) -> int:
    eval_set = load_eval_set(Path(args.questions))
    pipeline = _build_pipeline()
    judge = PlanningJudge(llm=build_llm_provider())

    print(
        f"Running {len(eval_set.cases)} planning cases from {eval_set.version} "
        f"(retriever=hierarchical, top_k={args.top_k}, "
        f"judge=PlanningJudge) ..."
    )

    results: list[PlanningCaseResult] = []
    for case in eval_set.cases:
        result = await _run_one(case, pipeline, judge, args.top_k)
        results.append(result)

    aggregates = _aggregate(results)
    timestamp = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    report = PlanningReport(
        eval_set_version=eval_set.version,
        sprint_label=args.label,
        timestamp_utc=timestamp,
        cases=results,
        n_planning_routed=sum(1 for r in results if r.task_type == "planning"),
        n_qa_routed=sum(1 for r in results if r.task_type == "qa"),
        **aggregates,
    )

    out_path = Path(args.out_dir) / f"{args.label}-{timestamp.replace(':', '')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    _print_summary(out_path, report)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="neblab_rag.eval.planning")
    parser.add_argument(
        "--questions",
        default="evals/v1/planning-questions.json",
        help="Planning question set JSON (default: %(default)s)",
    )
    parser.add_argument(
        "--label",
        required=True,
        help="Sprint label, e.g. 'sprint-5d-planning-baseline'",
    )
    parser.add_argument(
        "--out-dir",
        default="evals/runs",
        help="Where to write the JSON report",
    )
    parser.add_argument("--top-k", type=int, default=7)
    args = parser.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
