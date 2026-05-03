# Sprint 1 v0.2 Findings — Per-Doc Cap Fixes Honesty, Quality Half-Recovers (2026-05-03)

After v0.1's clear regression (one hallucination + supported −7.7pp vs
abstract-only baseline), v0.2 added a structural fix: a `max_chunks_per_doc`
cap (default 3) inside `HybridRetriever`, applied **after** RRF merge and
**before** the reranker. Both Qdrant and BM25 search are oversampled
(`candidate_k × max_chunks_per_doc`) so the cap doesn't starve the
candidate pool when one doc dominates.

Same 41-question eval, same Postgres state (50 docs, 4915 chunks: doc
19 alone = 4101 / 83% of total), same v0.2 settings (rewriter on, BM25
on, judge on, generator temp=0).

## Headline numbers

| | answered | refused | supported | partial | not_supp |
|---|---|---|---|---|---|
| baseline (abstract, Sprint 4 v1) | 34 | 7 | **46.6%** | 38.2% | 15.2% |
| v0.1 fulltext (no cap) | 31 | 10 | 38.4% | 42.1% | 19.5% |
| **v0.2 fulltext + cap=3** | 31 | 10 | **43.3%** | 32.7% | 24.0% |

Honesty headline (`expected_no_refused`):

| | baseline | v0.1 | **v0.2** |
|---|---|---|---|
| expected_no_refused | 100% | **80% (1 real hallucination)** | **100%** ✅ |

The `hard.en.china` hallucination from v0.1 (Toumma reserve in Niger
attributed to Chinese sand control) is **gone**: in v0.2 the same case
produces 5 citations, 0/5 supported, but no fabricated facts. The cap
prevents doc 19 (the 695-page book) from monopolizing all 5 retrieved
chunks, which is what gave v0.1 enough thematic coherence to invent
plausible-sounding nonsense.

## What v0.2 actually delivers

**Honest read:**

- **Honesty restored** — 100% of `expected_no` cases refused. Real
  correctness fix, not metric drift. The cap is the lever.
- **vs v0.1**: supported +4.9pp, partial −9.4pp, not_supported +4.5pp,
  same answered/refused split. Net: cap is strictly better than no-cap
  on all metrics that matter.
- **vs abstract baseline**: answered −3 cases (still soft-refusing 3
  cases the abstract corpus could answer), supported −3.3pp,
  not_supported +8.8pp. **Not at parity yet.**

**Why we still regress vs baseline:** fulltext brings genuine signal
(specific mechanisms, numbers, regional detail) but also genuine noise
(mid-paragraph 500-char fragments, dense academic prose without an
abstract's pre-summarization). The cap fixes the dominance problem but
not the chunk-quality problem. Specifically:

1. Cases where abstract was *enough* (definitional, summary-style
   questions): fulltext's noisier chunks pull the LLM into less
   confident territory → `answered` drops, e.g.
   `medium.en.shrub_invasion` (baseline 100% → v0.2 soft-refuse),
   `medium.en.causes-feedbacks` (86% → soft-refuse).
2. Cases where fulltext genuinely helps (mechanistic, multi-paper
   synthesis): real wins, e.g. `medium.en.bio_vs_climate` 60→83,
   `medium.zh.mechanisms` 20→63, `medium.en.zero-net-degradation`
   46→60.
3. `not_supported` rate up because the LLM, given more concrete-looking
   chunks, makes more confident claims that the chunk doesn't quite
   actually back. This is generator/prompt territory, not retrieval.

## Per-case wins/losses (vs baseline)

**Wins (≥+10pp supported):** `medium.en.bio_vs_climate` 60→83,
`medium.zh.mechanisms` 20→63, `medium.en.zero-net-degradation` 46→60,
`medium.en.hydrologic-aeolian-vegetation` 0→40,
`medium.zh.china-karst-desertification` 0→33,
`hard.en.land-use-planning-quandary` refused→33,
`easy.en.remote-sensing-use` 50→67.

**Losses (≥-30pp supported or refused→worse):**
`hard.en.china` 33→0, `hard.en.global-synthesis-regional` 100→0,
`hard.en.sub-saharan-monitoring-trends` 20→0,
`easy.zh.india-desertification-map` 100→20 (−80!),
`medium.en.shrub_invasion` 100→soft-refuse,
`medium.en.causes-feedbacks` 86→soft-refuse,
`medium.en.monitoring` 67→soft-refuse,
`medium.en.monitoring-indicators` 100→40.

The `easy.zh.india-desertification-map` loss is striking: a question the
abstract corpus answered cleanly is now being answered from a 500-char
mid-book fragment that doesn't actually contain an India-specific map.

## Verdict

**v0.2 is shippable as a correctness fix but not yet a net quality
win.** Three honest framings:

- **PR-now case**: cap is a structural fix that strictly improves on
  v0.1 and restores 100% honesty. Even if quality at n=41 is slightly
  below abstract baseline, the cap is the right architectural piece
  for a corpus that *will* grow more imbalanced. Ship cap, treat
  fulltext value as a separate ongoing problem.
- **Iterate-more case**: −3.3pp on `supported_rate` and 3 fewer
  answered cases is a real cost on a small eval. Try cap=5 (less
  aggressive), or larger chunks (1000 chars), or hierarchical retrieval
  (abstract-first then drill into fulltext) before merging.
- **Roll-back-fulltext case**: the entire pilot only got 4 fulltext docs
  (22% hit rate) — corpus is mostly still abstract. We could land the
  per-doc cap alone (it helps abstract-only retrieval too, even if less
  visibly), defer fulltext until we have Tier-2 TDM API access.

## Numbers to compare

| Metric | abstract baseline | v0.1 fulltext | **v0.2 cap=3** |
|---|---|---|---|
| answered_rate (regex) | 52.5% | 46.3% | 43.9% |
| answered (judge-based) | 34 | 31 | 31 |
| expected_yes_answered | 65.5% | 48.3% | 51.7% |
| expected_no_refused | 100% | 80% | **100%** |
| citation_validity | 100% | 100% | 100% |
| citation_supported | 46.6% | 38.4% | **43.3%** |
| citation_partial | 38.2% | 42.1% | 32.7% |
| citation_not_supported | 15.2% | 19.5% | 24.0% |
| n_judgments | 152 | ~150 | 148 |
| latency p50 | n/a | n/a | 15.4s |
| latency p95 | 34.0s | 24.6s | 20.3s |

## Files

- Run JSON: `evals/runs/sprint-1-v0.2-with-cap-2026-05-03T125254Z.json`
- Code: commit `55ada78` `feat(rag): cap chunks-per-doc in retrieval candidate pool`
- Predecessors: v0.1 baseline `dbb4831`, no-book A/B `64aeab4`
