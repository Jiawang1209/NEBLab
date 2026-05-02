# Sprint 2.5 Final Findings (corrected) — 2026-05-02

Two consecutive A/Bs revealed an important methodology pitfall that
inflated my Sprint-2.5 v0.1 numbers. Re-running with a **softened prompt**
gives the honest picture.

## Four runs, same 12 questions

| Variant | answered | n_judged | supported | partial | not_supported |
|---|---|---|---|---|---|
| Sprint 4 baseline (loose prompt + temp=0.3 + dense) | 67% | 43 | 58% | 26% | 16% |
| Sprint 2.5 strict + BM25 | 50% | 21 | **86%** | 10% | 5% |
| Sprint 2.5 strict − BM25 | 50% | 28 | 54% | 36% | 11% |
| Sprint 2.5 softened + BM25 | 58% | 67 | 57% | 25% | 18% |

## What actually happened

**The strict prompt's apparent supported_rate jump (58% → 86%) was largely
an artifact of refusing the hard cases.** When the LLM refuses a borderline
question, that question contributes zero citations to the judged pool. Only
the easy/clean cases survive into the judge — and those are easy to cite
well. So `n_judged` collapsed from 43 → 21, and the surviving citations
look great in aggregate.

The cleanest evidence: **same prompt, same temperature, softened wording**
recovered answered_rate back to 58% and supported_rate fell to 57% —
roughly the Sprint-4 baseline. The "win" wasn't a real improvement in
citation quality; it was a denominator effect.

## What's actually true

Looking at the matrix above, controlling for answered_rate:
- BM25 contribution is **smaller than first claimed** (the strict-prompt run
  with BM25 isn't fairly comparable to anything because of the small sample)
- Temperature=0 + tighter prompt do reduce hallucination at the cost of
  refusing more cases — but that's a *different* trade-off than "fewer
  citation errors per citation"
- At this eval size (n=12, ~30-70 judgments), the system is too stochastic
  to reliably distinguish 5-10pp differences between variants

## Real Sprint 2.5 deliverables (the parts that ARE solid)

1. ✅ **Generator at temperature=0.0** — eval runs reproducible now
2. ✅ **Generator prompt explicitly forbids extrapolation** — the soft
   variant is the one that ships (allows adjacent-content citations,
   forbids inventing new facts)
3. ✅ **BM25 hybrid with RRF** — code is clean, hooked into production
   pipeline; expected to help more on bigger corpora where dense semantic
   match is genuinely shallow
4. ✅ **Methodology learning** — the eval set MUST grow before we can A/B
   subtle prompt variants. Spec calls for 100 questions; we have 12.

## Tracking targets going forward

```
answered_rate:           58.3% baseline (softened-prompt Sprint-2.5 ships)
expected_yes_answered:   66.7% baseline
expected_no_refused:    100.0% baseline (perfect honesty)
citation_validity_rate: 100.0% baseline (structural)
citation_supported_rate: 56.7% baseline (deep — gap to spec ≥95% is real)
```

## What's actually next

Three real options, ranked by ROI for closing the supported_rate gap:

1. **Grow the eval set to 30-50 questions** so A/B variants are
   statistically distinguishable. Cheap (free APIs per memory) and removes
   the noise floor from every future decision.
2. **Sprint 1: full-text corpus** — dense + BM25 hybrid against 5K
   chunks of full text (vs current 120 chunks of abstracts) is where the
   retrieval quality actually lives. Big infra lift but biggest payoff.
3. **Multi-LLM judge** — run judge with deepseek-r1 alongside v3.2,
   compare verdicts, calibrate. Removes single-judge bias.
