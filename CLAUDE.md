# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project context

NEBLab RAG is the knowledge-base subsystem (v1) of the Northern Ecological
Barrier Lab — a Chinese national ecology / desertification-control research
project. This repo only owns the RAG subsystem; sibling subsystems live
elsewhere. Sprint 0 (foundation + abstract-level RAG) shipped to `main`;
follow-on sprints land on feature branches.

## Environment

The project lives inside a mamba env named `NEBLab`. **All `python`,
`pytest`, `ruff`, `pyright`, `alembic`, `uvicorn`, and `neblab-ingest`
calls must use that env's binaries.** The Makefile assumes `mamba activate
NEBLab` is already done. From a non-activated shell (e.g. when issuing
commands programmatically), prefix with the env path:

```bash
PATH="$HOME/miniforge3/envs/NEBLab/bin:$PATH" <command>
```

Postgres must be **version 16** (pinned for both local and cloud). Local
runs as a Homebrew service: `make pg-start` / `make pg-stop`.

`.env.local` holds real DeepSeek/Qwen3 endpoint URLs + API keys + Qdrant
Cloud creds + `OPENALEX_EMAIL`. The file is gitignored. Tests inject
dummy env values via `tests/conftest.py` so `pytest` runs without it.

## Common commands

```bash
make test          # all unit tests (excludes 'integration' marker)
make lint          # ruff check
make format        # ruff format (writes)
make typecheck     # pyright on src only (CI runs same)
make migrate       # alembic upgrade head
make dev           # uvicorn --factory --reload :8000
make ingest        # neblab-ingest CLI

# single test file or test
pytest tests/unit/rag/test_pipeline.py -v
pytest tests/unit/rag/test_pipeline.py::test_answer_orchestrates_retriever_and_generator -v

# integration tests (need real Postgres + Qdrant + API keys; auto-skipped without)
pytest tests/integration -m integration -v

# end-to-end smoke against real APIs
bash scripts/smoke_run.sh

# corpus ingest (OpenAlex → Postgres)
neblab-ingest ingest --topic desertification --language en --max 500

# eval harness (real APIs, writes evals/runs/<label>-<ts>.json)
python -m neblab_rag.eval --label some-label
python -m neblab_rag.eval --label X --judge                    # + LLM-as-judge
python -m neblab_rag.eval --label X --judge --no-rewriter      # disable zh→en
python -m neblab_rag.eval --label X --judge --no-bm25          # disable BM25
```

## Architecture (big picture)

### Two pipelines that meet at Qdrant

```
INGEST (offline)                              QUERY (online)
───────────────                               ──────────────
OpenAlex API                                  user question
    ↓                                              ↓
DocumentRepository (Postgres docs)            QueryRewriter (zh→en, optional)
    ↓                                              ↓
ChunkIndexer:                                 HybridRetriever:
  chunk_text() → N chunks per doc               EmbeddingProvider → Qdrant search
  ChunkRepository.replace_for_document          BM25Index over chunks (optional, RRF merge)
  EmbeddingProvider.embed (per chunk)           RerankerProvider → top-K
  QdrantRepo.upsert_points                         ↓
    ↓                                          AnswerGenerator (LLMProvider, temp=0)
status=FULLTEXT_INDEXED                            ↓
                                              CitationValidation → RAGResult
```

### Provider abstraction layer (the most important architectural rule)

`src/neblab_rag/providers/` defines four abstract interfaces:
`LLMProvider`, `EmbeddingProvider`, `RerankerProvider`, and the implicit
`QdrantRepo`. **Only `src/neblab_rag/providers/factory.py` imports
concrete provider classes** (DeepSeek, Qwen3, Qdrant). Business code
depends on the abstract interfaces. Swapping a vendor = changing one
function in factory.py, no other module is touched.

When adding a new vendor: implement the abstract base class in
`providers/<kind>/<vendor>.py`, register it in `providers/<kind>/__init__.py`,
and have `factory.build_<kind>_provider()` decide which to return based on
Settings.

### Three layers in `src/neblab_rag/`

- `corpus/` — OpenAlex ingestion (CLI + service + client wrapper)
- `rag/` — chunker, indexer, retriever, query_rewriter, generator,
  citation, pipeline. The query-time pipeline is composed in `pipeline.py`
  via `RAGPipeline`. Components are wired by `api/routes/query.py` and
  `eval/__main__.py` (the only two entry points that build a full pipeline).
- `eval/` — evaluation harness. Independent of the API layer; talks
  directly to a `RAGPipeline`. Outputs JSON reports to `evals/runs/`.

### Schema invariants

- `documents.id` is `int` (Postgres serial). It's used as the doc-level
  identifier everywhere downstream.
- `chunks.id` is `int`; **the chunk's int PK IS the Qdrant point id**.
  We don't store a separate `qdrant_point_id` column — that was removed
  in Sprint 2 to avoid drift between two sources of truth.
- Qdrant point IDs **must be unsigned int or UUID**, never plain strings.
  `VectorPoint.id: int` enforces this at the type level (a Sprint-0 bug
  exposed at smoke time was passing `str(d.id)`).
- Qdrant payload shape (set by `ChunkIndexer`):
  `{chunk_id, doc_id, chunk_index, openalex_id, title, text, year, topic, language}`.
  The retriever reads `text` for chunk content and `title` for fallback.

## Conventions

### pyright
CI runs `pyright src` only (not tests). Errors from third-party packages
without stubs (fastapi, sse_starlette, qdrant_client, pyalex, structlog)
are ignored at the file level via `# pyright: reportUnknownVariableType=false`
etc. Same pattern in `corpus/openalex_client.py`, `api/routes/query.py`.
Don't try to fix these by adding stubs.

### ruff
- Line length is delegated to the formatter (`E501` ignored).
- `RUF001/002/003` (ambiguous-unicode) ignored — CJK full-width punctuation
  is intentional in prompts and docstrings.
- Both `ruff check` and `ruff format --check` must pass — CI runs both.

### Tests
- `asyncio_mode = "auto"` — async tests don't need `@pytest.mark.asyncio`,
  but existing files use it for explicitness; either works.
- Integration tests are marked `@pytest.mark.integration` and auto-skip
  when `LLM_API_KEY` is missing or still the dummy `"test"` value.
- `tests/conftest.py` injects dummy env vars at import time so `Settings()`
  construction works without `.env.local`.

### Eval reports
- One JSON file per run, written to `evals/runs/<label>-<timestamp>.json`.
- Committed alongside human-readable findings docs (`evals/v1/*-findings.md`).
- The eval is non-deterministic enough at n=12 that subtle prompt A/Bs
  need to be re-run several times before drawing conclusions. Read
  `evals/v1/sprint-2.5-final-findings.md` for the methodology lesson
  (denominator artifact when refusal rate changes).

### git operations
- **Never run `git push`** in any form — the user reserves that action
  for themselves. Surface the command, don't execute it.
- Sprint branches off main. Sprint N+0.5 (incremental fixes) branches
  off the parent sprint, not main, until the parent merges.

## Common gotchas

- **localhost API debugging on macOS**: there's a `http_proxy=http://127.0.0.1:7897`
  in the user's environment. `curl http://localhost:8000/...` will return
  502 Bad Gateway via that proxy. Use `curl --noproxy '*' ...` to bypass.
- **After schema changes**, existing data in Postgres is left intact but
  may need status reset before re-running indexers. Pattern is
  `session.query(Document).update({Document.status: IndexStatus.METADATA_ONLY})`
  followed by re-running `ChunkIndexer.index_pending()`.
- **Reranker / BM25 IDF on tiny test corpora**: BM25's IDF goes to 0 or
  negative for terms appearing in too many small-corpus documents.
  Tests need 4+ documents with sparse term distribution.

## Where to look

- High-level project state, sprint status, what's where right now: the
  user's auto-memory at
  `~/.claude/projects/-Users-liuyue-Desktop-Github-repos-NEBLab/memory/`
  (specifically `project_neblab_state.md`).
- Spec: `docs/superpowers/specs/2026-05-01-rag-v1-design.md`
- Sprint 0 implementation plan (frozen):
  `docs/superpowers/plans/2026-05-01-rag-v1-plan-01-foundation.md`
- Quick-start + data-flow diagram: `README.md`
