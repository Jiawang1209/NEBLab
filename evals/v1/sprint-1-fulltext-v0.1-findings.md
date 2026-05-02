# Sprint 1 v0.1 Findings — Full-text REGRESSED Quality (2026-05-03)

Pilot run: 4 of 18 OA docs successfully fetched + parsed (others 403'd
behind publisher paywalls — needs Tier-2 TDM API per spec §3.4). Re-indexed
all 50 docs (4 with fulltext, 46 abstract-only): **120 chunks → 4,915
chunks (41× more material)**.

Re-ran the n=41 eval against the new index, judge enabled, all other
Sprint 2.5 settings unchanged. Result is **a clear regression** vs the
abstract-only baseline:

| Metric | Sprint 2.5 v1 (abstract) | Sprint 1 v0.1 (fulltext) | Δ |
|---|---|---|---|
| answered_rate | 52.5% | 46.3% | −6.2pp |
| expected_yes_answered | 65.5% | 48.3% | **−17.2pp** |
| expected_no_refused | 100% | **80%** | **−20pp (1 real hallucination)** |
| citation_supported | 46.6% | **38.9%** | **−7.7pp** |
| citation_partial | 38.2% | 42.7% | +4.5pp |
| citation_not_supported | 15.2% | 18.5% | +3.3pp |
| latency p95 | 34.0s | 24.6s | −9.4s ✅ (only the win) |

## What broke

**One real hallucination on `hard.en.china`.** The LLM cited "Toumma
National Nature and Cultural Reserve in 2007" — *which is in Niger* —
as if it were Chinese sand-control policy, then synthesized claims about
"China adopted UNCCD in 2000 with a NAP" that aren't in the corpus.

Two other "honesty fails" turned out to be the metric still missing
refusal phrasings ("文献中未提及", "无法回答您的问题", "未涉及"). Detector
widened in this commit; re-aggregating brought `expected_no_refused`
80% → **80% (still real)** with that one stubborn hard.en.china case.

## Why fulltext made things worse

The pilot pulled 4 fulltext docs of very uneven scale:

```
doc 19  Springer book "Land Degradation and Improvement"   695 pages   ~3300 chunks
doc 23  Springer chapter on monitoring                      42 pages    ~310 chunks
doc 47  another Springer paper                              ~?  pages   ~? chunks
doc 52  Nature paper on anthropogenic climate change        11 pages    ~120 chunks
```

doc 19 alone is **2/3 of the entire chunk pool** (3300 of ~4915). Books
cover huge breadth — economics, policy, regional case studies, indices,
acknowledgments. Many of these chunks are tangentially related to almost
any desertification query and get pulled into the top-30 dense candidate
pool. Citation distribution shows it: top-cited chunks now span Niger
nature reserves, biochar agronomics, and dust-precipitation feedback —
the corpus's effective focus blurred.

## What this means for Sprint 1's design

The spec's "5000 papers full text" target assumed the average paper, not
695-page reference books. Three concrete fixes for v0.2:

1. **Page-count cap on ingestion** — skip PDFs over ~50 pages, or chunk
   them differently (e.g. one chunk per section header, smaller k).
2. **Per-doc chunk cap in retriever** — limit max chunks-per-doc in
   top-K so one giant doc can't dominate every query. Standard pattern
   in production RAG.
3. **Section filtering** — strip references / acknowledgments / indices
   before chunking. PyMuPDF gives us section structure; we currently
   treat the whole text as one stream.

## What we keep from this pilot

- ✅ ParserProvider abstraction works; PyMuPDF runs reliably
- ✅ FullTextFetcher idempotency + per-doc error isolation work as designed
- ✅ Schema (fulltexts table) is right; ChunkIndexer prefer-fulltext logic is right
- ✅ The Qdrant timeout/batch fixes (60s + batch=50) handle large indexes
- ✅ Eval infra caught the regression cleanly — A/B comparison was the whole point
- ✅ Detector regex now catches more refusal phrasings (Sprint 1 byproduct)

## Recommendation

**Do not ship v0.1 fulltext as-is.** Either:

A. **Quick remediation**: drop doc 19 (and any future docs > 50 pages),
   re-index, re-test. ~10 min experiment to isolate whether the book IS
   the problem.

B. **Implement per-doc chunk cap in retrieval** and re-test. Bigger
   change but addresses the root cause regardless of corpus mix.

C. **Acknowledge + revert + plan v0.2 properly** — leave fulltext code
   in place but don't enable it in production until the 3 design fixes
   land.
