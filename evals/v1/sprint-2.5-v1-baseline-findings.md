# Sprint 2.5 v1 Baseline — n=41 (2026-05-02)

First eval against the expanded 41-question set (12 handwritten + 25
LLM-generated + 4 honesty/synthesis additions). Same Sprint-2.5 stack:
softened prompt + temperature=0 + BM25 hybrid + zh→en rewriter, with
LLM-as-judge enabled.

## Headline numbers

```
n_cases:                  41
n_errors:                  1   (SSL timeout on hard.en.asian-desertification-onset)
n_judgments:             191   (vs 67 at n=12 — much tighter signal)

citation_validity_rate:  100%
answered_rate:            55.0%
expected_yes_answered:    69.0%
expected_no_refused:      100%   (5/5 honesty tests refused)

citation_supported:       46.6%   (deep faithfulness)
citation_partial:         38.2%
citation_not_supported:   15.2%

latency_p50:             18.0s
latency_p95:             34.0s
```

## Key shift from the n=12 baseline

n=12 said `citation_supported = 56.7%`. n=41 says `46.6%`. The smaller
sample was lucky on easy questions; per-difficulty breakdown shows why:

| difficulty | n | answered | judged | supported_rate |
|---|---|---|---|---|
| easy | 11 | 7 | 46 | **69.6%** |
| medium | 17 | 13 | 108 | 38.9% |
| hard | 12 (1 errored) | 3 | 37 | 40.5% |

Easy questions cite well. Medium/hard cases are where the system
struggles — and that's where the bigger corpus + better retrieval will
matter most.

## Two metric improvements landed alongside this baseline

1. **Fallback-detector regex widened** — n=41 caught one expected-no
   case as "answered" because the LLM said "文献片段中暂未找到" instead of
   "文献中暂未找到". The detector now matches `r"文献[一-鿿]{0,4}中暂未找到"`,
   which absorbs the qualifier variants without false-positiving on
   genuine prose. The committed JSON report uses the corrected detector;
   the headline numbers above are the post-fix values.
2. **`scripts/generate_eval_questions.py`** — reusable for the next
   expansion (toward spec's 100-question target).

## Honesty score: clean

All 5 expected-no cases refused correctly:
- `hard.en.china` (China policies)
- `hard.zh.china_north` (China-specific drivers)
- `hard.en.three-north-shelterbelt` (Three-North program details)
- `hard.zh.crispr-drought` (CRISPR + drought tolerance)
- `hard.en.out-of-scope-ocean-acidification` (marine processes)

Zero hallucinations on out-of-coverage. The system is well-calibrated to
say "I don't know" when it doesn't.

## What we now know we should attack next

1. **Medium/hard cases drop supported_rate to ~40%.** Either the chunks
   retrieved for these are genuinely too sparse (more chunks per doc /
   bigger candidate_k), or the generator is over-extending claims when
   chunk content is partial. **Diagnosis:** spot-check 5-10 medium/hard
   cases manually — read the answer, read the chunks it cited, see
   whether the chunks really should have supported each claim.
2. **partial = 38%** is the largest bucket. Most "wrong" citations
   aren't outright wrong, they're "on-topic but doesn't fully back".
   This is what BM25 + better chunking should help with on a bigger
   corpus.
3. **Latency p95 = 34s** doubled from p50. Root cause is the slow tail
   of judge runs (each cited claim → 1 LLM call serial). For Sprint-3
   UI, judge runs offline, not on every query, so this is fine. For
   real-time SSE responses, the bottleneck is still the dense+rerank+gen
   chain, around 12-15s p95.
4. **One SSL timeout**. Provider hiccup; not actionable unless we add
   retry to provider clients (worth doing eventually).

## Spec-target tracking after n=41

```
citation_supported_rate:  46.6% baseline (n=41) → spec target ≥95%   gap 48pp
expected_no_refused:      100%  (perfect honesty) — DON'T regress
citation_validity_rate:   100%  (structural)    — DON'T regress
answered_rate:             55%  (acceptable; spec has no hard target)
expected_yes_answered:     69%  (acceptable; should rise with bigger corpus)
```

The 48pp gap is the real Sprint-1 → 5 challenge. Bigger corpus (full
text, more papers) is the highest-leverage move; better chunking and
prompt tweaks are second-order from here.
