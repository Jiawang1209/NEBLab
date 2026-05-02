# Sprint 2.5 Findings (2026-05-02)

Three changes shipped together:
1. Generator `temperature=0.3 → 0.0` (reproducibility + less paraphrasing)
2. Tighter generator system prompt (no extrapolation, "directly support" rule)
3. BM25 sparse retrieval + RRF hybrid merge (fix specific-term blindness)

## Headline numbers vs Sprint 4 baseline (rewriter+judge in both)

| Metric | Sprint 4 | Sprint 2.5 | Δ |
|---|---|---|---|
| **citation_supported_rate** | 58.1% | **85.7%** | **+28pp** ✅ |
| citation_partial_rate | 25.6% | 9.5% | −16pp ✅ |
| citation_not_supported | 16.3% | 4.8% | −12pp ✅ |
| citation_validity_rate | 100% | 100% | flat |
| answered_rate | 66.7% | 50.0% | −17pp ⚠️ |
| expected_yes_answered | 66.7% | 44.4% | −22pp ⚠️ |
| latency_p95 | 17.4s | 23.2s | +5.8s (BM25 cost) |

## What this means

**The trade was deliberate and (probably) the right call.** Spec §7.2 hard
target is **≥95% citation accuracy**; Sprint 4 baseline was 58%, Sprint
2.5 is 85.7% (gap to target shrunk from 37pp to 9pp). Spec has no hard
target on `answered_rate`. The prompt is now refusing borderline-coverage
cases instead of synthesizing weak answers — that's the spec intent.

But two of the 3 newly-refused cases are debatable:

```
[medium.en.shrub_invasion] How does shrub invasion affect grassland
                           ecosystems and soil resources?
  → "the chunks discuss grassland degradation and soil resource loss but
     not specifically shrub invasion" → REFUSED
  → corpus DOES have Schlesinger 'Biological Feedbacks in Global
     Desertification' which covers exactly this. Either BM25 didn't
     surface it strongly enough, or the prompt is too strict on the
     'directly support' rule.

[medium.en.monitoring] How is desertification monitored at regional and
                       global scales?
  → "no specific conclusions" → REFUSED
  → corpus has multiple monitoring/mapping papers; same diagnosis.
```

So the prompt is at least partially over-pruning. Two paths:

1. **Loosen the prompt slightly** — change "directly supports" to "supports
   or directly informs". Should recover some of the lost answered_rate
   without giving back much supported_rate.
2. **Diagnose BM25 separately** — if the right chunks aren't even being
   retrieved, no prompt tweak helps. Run an A/B with `--no-bm25` to
   isolate prompt-vs-retrieval as the cause.

## One real win on honesty side

`hard.zh.china_north` (中国北方沙漠化驱动因素，corpus has nothing) went from
FALLBACK to "answered" — which sounds like a regression but reading the
text, it's actually nuanced honest English:

> "...studies in this paper focus on regions like US New Mexico, Sahel, and
> India, not specifically northern China... general mechanisms may be
> referenced but no northern-China-specific conclusions found"

This is exactly the prose the judge wants — honest about the gap, cites
what IS adjacent. Same metric-artifact issue as Sprint 4's `hard.en.china`
case: our fallback-detector misses nuanced English hedging.

## Recommended next steps

Ranked by ROI:

1. **A/B `--no-bm25`** to isolate whether the answered_rate regression
   is from the tighter prompt OR from BM25 surfacing worse chunks. ~2 min
   to run, free.
2. **If BM25 is the culprit** — investigate the RRF "skip chunks not in
   dense" limitation; might need second Qdrant fetch for sparse-only hits.
3. **If prompt is the culprit** — soften "directly supports" → "supports
   or directly informs"; re-run; should recover lost answered_rate without
   giving back much supported_rate.
4. **Then move on** — Sprint 1 (full-text corpus) will likely have the
   biggest impact on remaining gap; chunk-level retrieval works fine,
   the limit is corpus coverage.

## Tracking targets

```
citation_supported_rate:  85.7% current → spec target ≥95% (close)
citation_not_supported:    4.8% current → drive to 0%
answered_rate:           50.0% current → restore to ~70% via prompt tuning
expected_yes_answered:    44.4% current → likewise
```
