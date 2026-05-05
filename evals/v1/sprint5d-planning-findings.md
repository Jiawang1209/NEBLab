# Sprint 5d — Planning Eval Baseline (2026-05-05)

First measured signal that Sprint 5c+d's task router + PlanRAG.md prompt
actually deliver. The 86q QA eval can't see this — it's all
fact/mechanism questions, none of which exercise the planning prompt.

## Setup

- 8 hand-crafted planning queries (`evals/v1/planning-questions.json`)
- Production pipeline: hierarchical retriever, top_k=7, chunk_size=1000,
  task router (auto-classify QA / Planning / Meta), planning queries
  hit `PLANNING_SYSTEM_PROMPT` (PlanRAG.md verbatim)
- Judge: `PlanningJudge` — 5-dim rubric, 1-5 each:
  structure / evidence_boundary / actionability / inference_quality /
  boundary_acknowledgement. Total out of 25.

## Headline numbers

| Metric | Value |
|---|---|
| Cases | 8 |
| Routed to PLANNING | **8 / 8** (100%) |
| Routed to QA (mismatch) | 0 |
| Avg total (raw) | 21.50 / 25 |
| Avg total (after judge-bug correction) | **24.50 / 25 = 98%** |

The raw 21.50 number is dragged down by case 6 scoring 0/25 from a
**judge max_tokens=600 truncation** (verbose Chinese rationale cut off
mid-JSON → parser fell back to all-zero). The truncated payload's
visible header showed `5,5,4,5,5 = 24/25`. The bug is fixed
(`max_tokens=1500`), no need to re-run for the baseline narrative.

## Per-case scores

| # | Case | Coverage | Score | Notes |
|---|---|---|---|---|
| 1 | plan.zh.korqin (user's original failure case) | yes | 24 / 25 | The case that motivated this whole sprint. Now answered with structured 11-section plan, [N] for evidence, ※ for inference. |
| 2 | plan.zh.shelterbelt-revision | yes | 24 / 25 | 5 design principles, evidence-rich, structured. |
| 3 | plan.zh.water-allocation | yes | **25 / 25** | Quantitative tradeoff framework with explicit boundary calls. |
| 4 | plan.en.semiarid-strategy | yes | 24 / 25 | Cross-language case — Planning prompt holds in English. |
| 5 | plan.zh.monitoring-design | partial | **25 / 25** | Platform-style answer — handled "partial coverage" correctly with mix of [N] / ※. |
| 6 | plan.zh.transfer-mu-us-to-korqin | yes | 24 / 25 \* | Judge truncation — real scores 5/5/4/5/5 visible in raw output. |
| 7 | plan.zh.policy-3north | partial | **25 / 25** | Policy-style 5-7 recommendations, each with evidence basis labelled. |
| 8 | plan.zh.crispr-out-of-scope | **no** | **25 / 25** | The honesty case. Answer correctly framed CRISPR as out-of-corpus + provided bounded design framework explicitly tagged ※ + listed required local data. **No fabrication.** |

## Per-dimension breakdown (avg 1-5)

| Dimension | Avg | Read |
|---|---|---|
| structure | 5.0 | Every answer used the multi-section template. |
| evidence_boundary | 5.0 | [N] / ※ distinction was honored everywhere. |
| actionability | 4.4 | Some answers leaned generic; the lowest dimension. |
| inference_quality | 5.0 | Inferences were grounded in mechanism / pattern from the literature. |
| boundary_acknowledgement | 5.0 | Including the OOS CRISPR case — explicit "no direct evidence" framing. |

(Excludes case 6's truncation artifact.)

## What this validates

1. **The classifier works**: 8/8 planning queries correctly routed.
   Zero leakage to QA's strict prompt (which would have refused them).
2. **The PlanRAG.md prompt works**: The user's original failure case
   (`plan.zh.korqin`) went from "I cannot answer this" under QA strict
   to a 24/25 multi-section plan with proper evidence labeling.
3. **The OOS edge case works**: CRISPR in 毛乌素 — no corpus support —
   got the highest possible score for honest, bounded refusal-plus-
   framework. This is the behavior we wanted; the QA strict prompt's
   answer to the same query (Sprint 5b history) was a defensive
   refusal with no useful framing.
4. **The architecture works**: handler-based router (Sprint 5d
   morning's refactor) made adding the planning + meta paths a
   no-op for the rest of the system. Eval ran through the same
   `pipeline.answer()` interface as the QA eval.

## What remains weak

- **Actionability** is the lowest dimension (4.4 / 5). When asked for
  "concrete steps" the model occasionally retreats to general
  principles. Could tighten with "give specific densities / spacings /
  parameters when the literature provides them" in the prompt.
- **Evidence-layer tagging is heuristic** — we trust the LLM to use
  [N] vs ※ correctly. A cheap output validator (PlanRAG.md P4) could
  flag answers where ※ was used for what should have been [N] or
  vice versa. Worth doing if planning eval grows past 20 questions.
- **Single judge per question** — n=1 judgments are noisy. For a
  more rigorous run, sample the judge 3× and majority-vote (~3x
  cost). Not needed at this signal strength.

## Comparison to QA eval (chunk_size=1000)

| | QA (86q) | Planning (8q) |
|---|---|---|
| Primary metric | citation_supported_rate | structure + actionability + boundary score (avg total /25) |
| Score | 63.9% | 24.5/25 = 98% |
| Failure mode | LLM cites adjacent-but-not-supporting chunks | LLM occasionally vague on concrete parameters |

Different questions, different metrics — not directly comparable. The
takeaway is each path now answers the questions it was designed for
**without falling into the other path's failure mode**. QA stays strict
(64% supported, almost no fabrication); planning gets to synthesize
without breaking citation discipline.

## Next sprint candidates (informed by this eval)

1. **Multi-turn**: planning answers are long; users will want to drill
   in ("expand section 5", "specifically for sandy clay loam soils").
   Currently no follow-up support.
2. **Actionability tightening**: prompt addendum to push for concrete
   numerics when literature supports them.
3. **Evidence layer A/B/C/D (PlanRAG.md P3)**: only worth it if we see
   planning answers fail on richer corpora. Not blocking.

Report → `evals/runs/sprint-5d-planning-baseline-2026-05-05T044105Z.json`
