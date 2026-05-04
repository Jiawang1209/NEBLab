# Sprint 5b — chunk_size 500 → 1000 (2026-05-04 → 2026-05-05)

One change A/B'd against the existing hierarchical+topk7 baseline (1810-doc
corpus, no other changes):

- `ChunkIndexer` and `chunk_text` defaults: `chunk_size=500, overlap=100`
  → `chunk_size=1000, overlap=200`. Re-indexed all 1810 docs.

After reindex: 1810 docs / **4717 chunks** in Postgres (down from 8001 with
chunk_size=500, ~halved as expected) / 4807 Qdrant points (90 orphans from
prior reindexes; harmless — retriever filters them out via Postgres lookup).

## Headline numbers

| Metric | hier+topk7 + chunk=500 | **hier+topk7 + chunk=1000** | Δ |
|---|---|---|---|
| n_cases (errors) | 86 (0) | 86 (0) | — |
| n_judgments | 638 | **699** | +61 |
| citation_validity | 100% | 100% | — |
| answered_rate | 82.6% | **84.9%** | ⬆ +2.3pp |
| expected_yes_answered | 89.2% | **95.4%** | ⬆ +6.2pp |
| expected_no_refused | 85.7% | 85.7% | — |
| **citation_supported** | **51.3%** | **63.9%** | **⬆ +12.6pp** |
| citation_partial | 32.1% | 27.8% | ⬇ −4.3pp |
| citation_not_supported | 16.6% | **8.3%** | ⬇ −8.3pp |
| avg_citations_per_answer | 7.65 | 6.52 | ⬇ −1.13 |
| avg_chunks_retrieved | ~7 | 6.55 | — |
| latency p50 / p95 (s) | 14.8 / 19.1 | 21.0 / 41.2 | ⬆ regression |

(Comparison row "hier+topk7 + chunk=500" is from `v2-2k-hier-topk7-2026-05-04T003246Z.json`.)

## Real wins

- **+12.6pp citation_supported (51.3% → 63.9%)** — biggest single-change
  jump in the project so far. Bigger chunks keep mid-paragraph claims
  intact; the judge can verify the whole logical unit instead of a
  sentence cut off mid-thought.
- **−8.3pp not_supported (16.6% → 8.3%)** — fewer hallucinated/unsupported
  cited spans. The honesty signal compounds with the supported jump:
  more of what the LLM cites actually backs the claim.
- **−4.3pp partial (32.1% → 27.8%)** — the hypothesized "partial verdicts
  came from claim spanning two chunks" mechanism showed up in the data.
  Doubling chunk size promotes some partials → supported.
- **+6.2pp expected_yes_answered (89.2% → 95.4%)** — fewer "literature
  insufficient" soft-refusals on answerable questions. Bigger context
  per chunk seems to help the LLM judge its own confidence.

## Cost: latency regression

- p50 went 14.8s → 21.0s, p95 went 19.1s → 41.2s. Roughly doubled.
- Cause: each chunk now has ~2× the text. Reranker scoring + LLM input
  both grow proportionally.
- avg_citations_per_answer dropped slightly (7.65 → 6.52) — the LLM is
  citing fewer but more substantive chunks. Net token count to the
  generator likely similar, but reranker pays the full chunk cost.
- Acceptable trade-off given the +12.6pp supported gain. Worth revisiting
  if interactive UX becomes a constraint (Sprint 3 UI).

## Cumulative trajectory toward spec

`citation_supported_rate` over the project:

| Config | supported |
|---|---|
| Sprint 0 abstract baseline (50 doc, flat) | 39.3% |
| 2k corpus + flat | 38.9% |
| 2k corpus + hierarchical (chunk=500, topk=5) | 50.2% |
| 2k corpus + hier + topk=7 (chunk=500) | 51.3% |
| **2k corpus + hier + topk=7 + chunk=1000** | **63.9%** |

Spec target: 95%. Remaining gap: 31pp. Easiest next levers:
- Generator prompt to refuse on weak chunks (the `out-of-scope-tech`
  CRISPR over-answer case is a generator issue, not retrieval).
- Reranker swap (Qwen3 reranker is current; Cohere multilingual or
  BGE-reranker-v2 may close more of the partial→supported gap).
- Fulltext expansion beyond 22% PDF hit rate (Tier-2 TDM API procurement).

## What I checked

- Postgres `documents` status: 1810 / 1810 FULLTEXT_INDEXED ✅
- Postgres `chunks`: 4717 (≈8001 / 1.7, consistent with chunk_size doubling
  + slightly less overlap reuse from `overlap=200`)
- Qdrant point count: 4807 (90 orphans, retriever filters them via
  Postgres lookup — no impact)
- 13/13 chunker + indexer unit tests pass with new defaults.
- `python -m neblab_rag.eval --label v2-2k-hier-chunk1000 --judge
  --hierarchical` ran clean, 0 errors over 86 cases.

Report → `evals/runs/v2-2k-hier-chunk1000-2026-05-04T195940Z.json`
