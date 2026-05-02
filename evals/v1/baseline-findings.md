# v1 Baseline Findings — sprint-2 (2026-05-02)

12 questions × Sprint-2 chunked corpus (50 desertification papers / 120 chunks).

## Headline numbers

| Metric | Value | Notes |
|---|---|---|
| citation_validity_rate | **100%** | Every [N] in every answer maps to a real retrieved chunk. No hallucinated citation numbers. |
| answered_rate | 58.3% (7/12) | The other 5 fell back to "literature insufficient" |
| expected_yes_answered | 66.7% (6/9) | 3 of the 9 questions where corpus *should* answer got refused — real misses |
| expected_no_refused | **100%** (2/2) | Both China-policy questions correctly refused. No hallucinations. |
| avg_citations_per_answer | 5.00 | Equal to top_k — generator uses every chunk it sees |
| latency_p50 / p95 | 14.18s / 17.64s | **Spec target was P95 < 8s; we're 2.2× over** |

## What the misses tell us

Three questions retrieved chunks but the LLM said "no answer":

1. **easy.en.connectivity** (`What is the connectivity hypothesis?`)
   Corpus has the literal paper "Do Changes in Connectivity Explain Desertification?". The reranker picked OTHER chunks instead — likely because the semantic similarity for "hypothesis" was lower than for "desertification" generally. **Fix candidate:** sparse hybrid (BM25) so exact-keyword "connectivity hypothesis" gets weighted up.

2. **medium.zh.mechanisms** + **medium.zh.shrub** (Chinese questions)
   The English versions of the same topics worked fine (`medium.en.shrub_invasion` got a substantive answer). The Chinese versions retrieved unrelated docs (西南喀斯特石漠化, 地中海干旱). **Fix candidate:** query rewriting — translate ZH question to EN before retrieval (corpus is English-only). This is the single highest-impact improvement we can make.

## What the wins tell us

- The 7 substantive answers each cite 5 papers, with verifiable [N] markers. The Sprint-2 chunking pays off — answers cite specific mechanisms, not just paper titles.
- The honesty gate is solid: 0 hallucinated answers across out-of-coverage questions.

## Tracking targets for next sprints

If we run this same eval at the end of each sprint, watch:

- **answered_rate** ↑ (next sprint should beat 58.3%)
- **expected_yes_answered** ↑ (66.7% baseline; sparse retrieval / query rewriting should push this higher)
- **citation_validity_rate** ≥ 95% (don't regress; spec hard floor is 95%)
- **expected_no_refused** = 100% (don't regress into hallucinations)
- **latency_p95** ↓ towards 8s (probably hard without provider changes)
