# Sprint 4 v0.2: LLM-as-Judge Findings (2026-05-02)

Added a citation-faithfulness judge that asks the LLM, for each `(sentence,
[N])` pair in the answer: "does this chunk actually support this claim?"
3-bucket verdict: **supported / partial / not_supported**.

## Headline numbers (rewriter ON + judge ON, 12 questions, 43 citations judged)

```
citation_validity_rate:   100.0%   ← structural (every [N] maps to real chunk)
citation_supported_rate:  58.1%    ← deep   (chunk actually supports the claim)
citation_partial_rate:    25.6%    ← chunk on-topic but doesn't fully back
citation_not_supported:   16.3%    ← chunk doesn't back the claim — real citation error
```

## Headline takeaway

**Structural validity (100%) over-states real citation quality.** The deep
metric shows only 58% of citations are clean; the rest are partial (25%) or
outright unsupported (16%). Spec §7.2 hard target is ≥95% citation
accuracy — there's significant room to improve before v1 ships.

## What the buckets tell us about *which* layer to fix

The 3-way split is more useful than a single rate because the buckets map
to different fixes:

| Bucket | Likely root cause | Where to fix |
|---|---|---|
| **partial** (25.6%) | Retriever surfaced an on-topic chunk that doesn't *quite* back the specific claim. The LLM cited the closest available chunk because the better one wasn't retrieved. | **Retrieval recall** — better chunking strategy, BM25 hybrid, more chunks |
| **not_supported** (16.3%) | The retrieved chunks were probably fine, but the generator stretched a claim beyond what the chunk says. | **Generator prompt discipline** — tighter system prompt forbidding extrapolation, lower temperature, or post-hoc claim checking |

## Caveats

1. **Non-deterministic baseline:** generator runs at `temperature=0.3` (LLM
   default in `ChatRequest`), so the same eval re-run produces different
   `answered_rate` and judge numbers. The earlier rewriter-A/B run hit
   `answered_rate=83%`; this run hit `66.7%` with the same code. Same
   pipeline, different sample. **Future improvement:** drop generator
   temperature to 0.0 for eval runs (and consider it for production too —
   factual answers don't need creativity).

2. **Judge is also the LLM** — a different LLM might score differently. For
   now, the judge model is the same `deepseek-v3.2` we generate with. Spec
   §7.2 calls for "5% human spot-check" of judge verdicts to calibrate;
   that's a follow-up.

3. **Sample size is small** (43 citations across 8 answered cases). The
   buckets are stable enough to act on, but tighter confidence requires
   the spec's 100-question target.

## Tracking targets going forward

```
citation_supported_rate:  58.1% baseline → spec target ≥95%
citation_not_supported:   16.3% baseline → drive to 0%
citation_partial_rate:    25.6% baseline → noise floor (some claims will always
                                            be loosely-grounded synthesis)
```

Sprint-2.5 candidates ranked by likely impact on the judge metric:

1. **Generator temperature → 0.0** (free, deterministic) — should drop
   `not_supported` rate immediately
2. **Tighter generator system prompt** — explicit "do not paraphrase
   beyond the chunk's literal content" rule
3. **BM25 hybrid retrieval** — should drop `partial` rate by recovering
   the more-specific chunk
