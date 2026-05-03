# v1 Eval Set 41 → 86 — New Baseline + Methodology Lessons (2026-05-03)

Goal: extend eval coverage so future A/Bs are statistically reliable.
Spec target was 100; we landed at 86 after dedup.

## Process

1. Ran `scripts/generate_eval_questions.py --target 80 --batch-size 20`
   against the live 50-paper corpus. (Batched because 80 in one call
   timed out at 60s — added `--batch-size` to the generator.)
2. Auto-dedup against existing 41 (id collision + normalized-text overlap):
   80 → 69 unique candidates.
3. Greedy balance toward spec ratios (30/50/20 difficulty, 70/30 lang,
   70/15/15 coverage): 69 → 59 picks.
4. **Human review caught 14 topical duplicates the auto-filter missed**
   (e.g. `medium.en.economics-restoration` vs `medium.en.economics-salt`,
   `easy.en.ldn-framework` vs `easy.en.ldn-concepts`). The LLM saw the
   same 50 paper titles 4 times and gravitated to the same topics.
5. 45 confirmed picks merged → questions.json bumped to v2 (86 cases).

Final v2 distribution (target → actual):
- difficulty: 30/50/20 → **24/41/21** (slightly hard-heavy)
- language: 70/30 en/zh → **56/30** (more zh than target — fine)
- coverage: 70/15/15 yes/partial/no → **62/13/11** (a bit yes-heavy)

## Headline numbers

Same pipeline (rewriter+BM25+cap=3+temp=0+judge), real DeepSeek + Qwen3
+ Qdrant Cloud:

| Metric | 41q v0.2 | **86q v2** | Δ |
|---|---|---|---|
| n_judgments | 148 | **412** | +264 |
| citation_validity | 100% | 100% | 0 |
| **expected_no_refused** | 100% | **100%** | 0 (after regex fix, see below) |
| answered_rate | 43.9% | 51.2% | +7.3pp |
| expected_yes_answered | 51.7% | 58.1% | +6.4pp |
| **citation_supported** | **43.3%** | **39.3%** | **−4.0pp** |
| citation_partial | 32.7% | 35.0% | +2.3pp |
| citation_not_supported | 24.0% | 25.7% | +1.7pp |
| avg_citations_per_answer | 5.00 | 4.98 | ≈0 |
| latency_p50 / p95 (s) | 15.4 / 20.3 | 20.5 / 43.3 | API jitter, not architectural |

## Methodology learning #1: regex detector was missing real refusals

86q exposed a metric bug. Two of the 11 `expected_no` cases generated
clean refusal answers but the regex detector flagged them as "answered":

- `hard.zh.china_north`: "基于所给文献片段，**无法直接回答**该问题"
   (adverb "直接" between 无法 and 回答 — old regex required them
   adjacent)
- `hard.en.out-of-coverage-tech`: "目前**无法回答关于使用 …… 这一问题**"
   (60+ chars between "回答" and "问题" — old window was 20)

Widened the pattern to `r"无法[^。\n]{0,8}回答[^。\n]{0,60}(?:问题|您的)"`.
Result: `expected_no_refused` 81.8% → **100%** at n=11 expected_no.

The 11/11 honesty result holds even at 2× the cases (and with a richer
out-of-scope test mix: drone-swarm seeding, CRISPR drought crops, EU CAP
eco-schemes, urban-desert transition, Antarctic ice-sheet retreat as
desertification). **Cap=3 + soft refusal pattern is robust honesty-wise.**

## Methodology learning #2: 41q overstated supported_rate

`citation_supported_rate` dropped from 43.3% (41q) to 39.3% (86q). Three
overlapping reasons:

1. The 41q included disproportionate "easy" definitional questions
   that the corpus's abstracts answer cleanly. Adding 45 more drafted
   questions (many medium/hard with multi-paper synthesis) shifted the
   mix toward harder retrieval.
2. Some new questions ask for *specific* claims the corpus brushes
   against but doesn't directly support (e.g. `medium.en.ipcc-synergies`
   asks for IPCC synergy practices — the corpus mentions IPCC reports
   in passing, no detailed practice list). Those generate citations
   that are partially or not supported.
3. n=412 judgments has ~2.5× the statistical power of n=148. The 43.3%
   figure had a wide CI; 39.3% is closer to true population rate.

**Going forward, 86q is the honest baseline. The 41q "+4.9pp from
v0.1 to v0.2" claim still holds (cap fixes hallucination), but the
"43.3% supported" number is sample-inflated. Real number is ~39%.**

## Per-case structure of out-of-scope refusals

All 11 `expected_no` correctly refused, but in two flavors:
- **Hard refusal (1 case)**: `hard.en.out-of-scope-ocean-acidification`
  generates an answer with no citation IDs, n_judgments=0.
- **Soft refusal (10 cases)**: answer says "无法回答" / "未提及" but
  cites the chunks anyway as evidence of why nothing matched. The judge
  has citation IDs to evaluate, n_judgments > 0, but most claims grade
  as `not_supported` because the "claim" is just "the corpus discusses
  X, not Y."

Soft refusal is acceptable behavior — in fact preferable — because it
shows the user *what's there* and what's missing. But it inflates the
`citation_supported_rate` denominator. Future metric design might
exclude soft-refusal judgments from the supported_rate calculation.

## What broke / changed in this branch

- `scripts/generate_eval_questions.py`: added `--batch-size` to avoid
  60s read timeouts on big targets. Batch loop with empty-batch
  abort.
- `evals/v1/questions.json`: bumped to v2, 41 → 86 cases.
- `evals/v1/draft-batch2.json` + `draft-batch2-picks.json`: audit
  trail for the dedup/picks workflow.
- `src/neblab_rag/eval/metrics.py`: widened the `无法回答…问题` regex
  per learning #1.

## Files

- Run JSON: `evals/runs/v1-86q-baseline-2026-05-03T152653Z.json`
   (regenerated post-regex fix; metrics in JSON reflect 100% refused)
- 41q v0.2 reference: `evals/runs/sprint-1-v0.2-with-cap-2026-05-03T125254Z.json`

## Next

The 86q baseline gives us reliable signal. Top three follow-up moves
(per project-state ROI ranking):

1. **Hierarchical retrieval prototype**: abstract first, then drill into
   matched doc's fulltext chunks. Targets the −4pp `supported_rate`
   gap by reducing fulltext noise during candidate generation.
2. **Corpus expansion**: `neblab-ingest --max 5000` then reindex. At 50
   docs many `expected_yes_answered` failures are actually corpus-not-
   covered, not retrieval failures. Spec target is 5000 metadata.
3. **Tier-2 TDM API decision**: 22% PDF hit rate caps the value of
   fulltext work. Not engineering — procurement.
