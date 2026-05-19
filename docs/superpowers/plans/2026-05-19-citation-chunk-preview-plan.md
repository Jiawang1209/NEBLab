# Citation Chunk Preview (Sprint 3 v0.3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the citations side panel show each cited chunk's full text on demand. Clicking `[N]` in the answer auto-expands that card's text; manual chevron toggles each card independently.

**Architecture:** Pure additive change — `Citation.chunk_text` is plumbed from `RetrievedChunk.text` (already in memory after retrieval) through `generator._citations()` → `CitationOut` → SSE `"citations"` event → front-end `Citation` TS type → `CitationsPanel`. Page-level `expandedCites: Set<number>` state, reset on session switch / panel close. Backward compatible: TS type makes `chunk_text` optional so legacy saved sessions degrade to v0.2 layout.

**Tech Stack:** Python (pydantic, FastAPI, pytest, ruff, pyright) on the backend; TypeScript / React / Next.js 16 / Tailwind / `lucide-react` on the front-end. Run env is `mamba activate NEBLab` (or `PATH="$HOME/miniforge3/envs/NEBLab/bin:$PATH"` prefix).

**Spec:** `docs/superpowers/specs/2026-05-19-citation-chunk-preview-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/neblab_rag/rag/generator.py` | Modify `Citation` model + `_citations()` | Source of truth: Citation model. Add `chunk_text: str` field. |
| `src/neblab_rag/rag/handlers.py` | Modify `_citations_payload()` | SSE wire format for streaming endpoint. Add `chunk_text` to JSON. |
| `src/neblab_rag/api/routes/query.py` | Modify `CitationOut` | Wire format for non-streaming POST /query. Add `chunk_text: str`. |
| `tests/unit/rag/test_generator.py` | Add assertions | Confirm `Citation.chunk_text` is populated from chunk text. |
| `tests/unit/rag/test_handlers.py` | Add assertions | Confirm SSE `"citations"` payload includes `chunk_text`. |
| `tests/unit/api/test_query.py` | Add assertions | Confirm `/query` JSON response surfaces `chunk_text`. |
| `web/src/lib/types.ts` | Modify `Citation` interface | Add optional `chunk_text?: string` (back-compat for stored sessions). |
| `web/src/hooks/use-stream-query.ts` | No code change | `parseCitations` already passes unknown fields through; verify and document. |
| `web/src/components/citations-panel.tsx` | Modify | Accept `expandedCites` + `onToggleExpand` props; render chevron + chunk region per card. |
| `web/src/app/page.tsx` | Modify | Hoist `expandedCites` to page scope; reset on session switch + panel close; pipe through to panel and to `onCitationClick`. |

---

### Task 0: Verify branch + clean state + baseline tests pass

**Files:** (no edits — environment sanity)

- [ ] **Step 1: Confirm branch and working tree**

Run:
```bash
git branch --show-current
git status --short
```
Expected: branch `feature/sprint3-ui-v03-citation-preview`, working tree clean (only the freshly-committed spec `docs/superpowers/specs/2026-05-19-citation-chunk-preview-design.md` should already be in the tree as a tracked file).

- [ ] **Step 2: Confirm baseline backend tests pass**

Run:
```bash
make test
```
Expected: all unit tests pass (integration suite is auto-skipped without `LLM_API_KEY`). If any failure pre-exists, stop and report — do not start the implementation on top of a broken tree.

- [ ] **Step 3: Confirm lint, format, typecheck pass**

Run:
```bash
make lint && PATH="$HOME/miniforge3/envs/NEBLab/bin:$PATH" ruff format --check . && make typecheck
```
Expected: all three green. Same rule — do not start on red.

- [ ] **Step 4: Confirm the Next.js dev server boots**

Run (in another terminal or `&`):
```bash
cd web && npm install >/dev/null 2>&1 && npm run dev
```
Visit `http://localhost:3000` to confirm v0.2 renders. Then stop the dev server (Ctrl-C). This is sanity only — we'll re-run it in Task 7 for manual verification.

(No commit at this task.)

---

### Task 1: Add `chunk_text` to backend `Citation` model

**Files:**
- Modify: `src/neblab_rag/rag/generator.py:22-26` (the `Citation` BaseModel) and `:195-204` (the `_citations()` constructor)
- Test: `tests/unit/rag/test_generator.py`

- [ ] **Step 1: Read the current `Citation` and `_citations()` to lock the Edit baseline**

Run:
```bash
sed -n '22,26p;195,204p' src/neblab_rag/rag/generator.py
```
Expected: the `Citation` BaseModel with four fields `number / doc_id / openalex_id / title`, and the `_citations(self, chunks)` method returning a list comprehension over `enumerate(chunks, 1)`.

- [ ] **Step 2: Add a failing test in `tests/unit/rag/test_generator.py`**

Find an existing test that constructs `RetrievedChunk` (e.g. a test that exercises `_citations` directly or `generate()`). Pattern an explicit chunk_text assertion test after it. Add this test:

```python
def test_citations_carries_chunk_text():
    """Sprint 3 v0.3: Citation must expose the underlying chunk.text so
    the UI can preview the cited passage without a follow-up RPC."""
    from neblab_rag.rag.generator import AnswerGenerator
    from neblab_rag.rag.retriever import RetrievedChunk

    chunks = [
        RetrievedChunk(
            chunk_id=1,
            doc_id=42,
            chunk_index=0,
            openalex_id="W123",
            title="Sand Storm Atlas",
            text="We observed that shelterbelt mass transport reduced by 40-60%.",
            score=0.9,
        ),
    ]
    # Class-method tested directly — no LLM needed
    cits = AnswerGenerator._citations(None, chunks)  # type: ignore[arg-type]
    assert cits[0].chunk_text == (
        "We observed that shelterbelt mass transport reduced by 40-60%."
    )
```

If `RetrievedChunk` has different field names (e.g. content vs text), use the actual fields — `grep -n "class RetrievedChunk" src/neblab_rag/rag/retriever.py` first.

- [ ] **Step 3: Run to confirm the test fails**

```bash
PATH="$HOME/miniforge3/envs/NEBLab/bin:$PATH" pytest tests/unit/rag/test_generator.py::test_citations_carries_chunk_text -v
```
Expected: FAIL with `AttributeError: 'Citation' object has no attribute 'chunk_text'` (or an equivalent pydantic validation error).

- [ ] **Step 4: Add `chunk_text` to the `Citation` model**

Use Edit on `src/neblab_rag/rag/generator.py`:

`old_string`:
```python
class Citation(BaseModel):
    number: int
    doc_id: int
    openalex_id: str | None
    title: str
```

`new_string`:
```python
class Citation(BaseModel):
    number: int
    doc_id: int
    openalex_id: str | None
    title: str
    chunk_text: str
```

- [ ] **Step 5: Populate `chunk_text` in `_citations()`**

Use Edit on `src/neblab_rag/rag/generator.py`:

`old_string`:
```python
    def _citations(self, chunks: list[RetrievedChunk]) -> list[Citation]:
        return [
            Citation(
                number=i,
                doc_id=c.doc_id,
                openalex_id=c.openalex_id,
                title=c.title,
            )
            for i, c in enumerate(chunks, 1)
        ]
```

`new_string`:
```python
    def _citations(self, chunks: list[RetrievedChunk]) -> list[Citation]:
        return [
            Citation(
                number=i,
                doc_id=c.doc_id,
                openalex_id=c.openalex_id,
                title=c.title,
                chunk_text=c.text,
            )
            for i, c in enumerate(chunks, 1)
        ]
```

- [ ] **Step 6: Run the new test plus all existing generator tests**

```bash
PATH="$HOME/miniforge3/envs/NEBLab/bin:$PATH" pytest tests/unit/rag/test_generator.py -v
```
Expected: new test PASSES; existing tests still PASS (they don't assert prompt-equality and the Citation model just gained one field).

- [ ] **Step 7: Lint + format + typecheck**

```bash
make lint && PATH="$HOME/miniforge3/envs/NEBLab/bin:$PATH" ruff format --check . && make typecheck
```
Expected: all green. If `ruff format --check` flags formatting, run `make format` and re-check.

- [ ] **Step 8: Commit**

```bash
git add src/neblab_rag/rag/generator.py tests/unit/rag/test_generator.py
git commit -m "$(cat <<'EOF'
feat(rag): Citation carries chunk_text (Sprint 3 v0.3 backend 1/3)

Citation BaseModel grows a `chunk_text: str` field, populated from
the RetrievedChunk.text already in memory after retrieval (Qdrant
payload). _citations() pipes it through. Zero new DB or vector
queries.

Spec: docs/superpowers/specs/2026-05-19-citation-chunk-preview-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Add `chunk_text` to SSE `_citations_payload`

**Files:**
- Modify: `src/neblab_rag/rag/handlers.py:63-74`
- Test: `tests/unit/rag/test_handlers.py`

The SSE streaming endpoint emits a `"citations"` event whose payload is built by `_citations_payload()`, independent of the `Citation` BaseModel above. This second source of truth also needs `chunk_text`.

- [ ] **Step 1: Read the current `_citations_payload`**

Run:
```bash
sed -n '63,74p' src/neblab_rag/rag/handlers.py
```
Expected: a `json.dumps` over a list-comp with `number / doc_id / openalex_id / title`.

- [ ] **Step 2: Add a failing test**

Open `tests/unit/rag/test_handlers.py` (or create it if absent — `grep -l _citations_payload tests/` to check; if no test file exists, create the file with the standard import pattern from other handler tests). Add:

```python
def test_citations_payload_includes_chunk_text():
    """Sprint 3 v0.3: SSE 'citations' event must include chunk_text
    so the UI can render chunk previews from the streaming path."""
    import json
    from neblab_rag.rag.handlers import _citations_payload
    from neblab_rag.rag.retriever import RetrievedChunk

    chunks = [
        RetrievedChunk(
            chunk_id=11,
            doc_id=42,
            chunk_index=0,
            openalex_id="W123",
            title="Sand Storm Atlas",
            text="We observed that shelterbelt mass transport reduced by 40-60%.",
            score=0.9,
        ),
    ]
    payload = json.loads(_citations_payload(chunks))
    assert payload[0]["chunk_text"] == (
        "We observed that shelterbelt mass transport reduced by 40-60%."
    )
    # existing fields untouched
    assert payload[0]["number"] == 1
    assert payload[0]["doc_id"] == 42
    assert payload[0]["title"] == "Sand Storm Atlas"
```

- [ ] **Step 3: Run to confirm the test fails**

```bash
PATH="$HOME/miniforge3/envs/NEBLab/bin:$PATH" pytest tests/unit/rag/test_handlers.py::test_citations_payload_includes_chunk_text -v
```
Expected: FAIL with `KeyError: 'chunk_text'`.

- [ ] **Step 4: Add `chunk_text` to the payload**

Use Edit on `src/neblab_rag/rag/handlers.py`:

`old_string`:
```python
def _citations_payload(chunks: list[RetrievedChunk]) -> str:
    return json.dumps(
        [
            {
                "number": i + 1,
                "doc_id": c.doc_id,
                "openalex_id": c.openalex_id,
                "title": c.title,
            }
            for i, c in enumerate(chunks)
        ]
    )
```

`new_string`:
```python
def _citations_payload(chunks: list[RetrievedChunk]) -> str:
    return json.dumps(
        [
            {
                "number": i + 1,
                "doc_id": c.doc_id,
                "openalex_id": c.openalex_id,
                "title": c.title,
                "chunk_text": c.text,
            }
            for i, c in enumerate(chunks)
        ]
    )
```

- [ ] **Step 5: Run the test + full handler tests + full backend tests**

```bash
PATH="$HOME/miniforge3/envs/NEBLab/bin:$PATH" pytest tests/unit/rag/test_handlers.py -v
make test
```
Expected: new test PASSES; everything else still PASSES.

- [ ] **Step 6: Lint + format + typecheck**

```bash
make lint && PATH="$HOME/miniforge3/envs/NEBLab/bin:$PATH" ruff format --check . && make typecheck
```

- [ ] **Step 7: Commit**

```bash
git add src/neblab_rag/rag/handlers.py tests/unit/rag/test_handlers.py
git commit -m "$(cat <<'EOF'
feat(api): SSE citations payload carries chunk_text (Sprint 3 v0.3 backend 2/3)

_citations_payload now emits chunk_text alongside number/doc_id/title.
This is the streaming path's wire format (independent of Citation
BaseModel — see prior commit).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Add `chunk_text` to `CitationOut` for non-streaming POST /query

**Files:**
- Modify: `src/neblab_rag/api/routes/query.py:51-56`
- Test: `tests/unit/api/test_query.py`

- [ ] **Step 1: Locate the existing query test pattern**

Run:
```bash
grep -n "CitationOut\|/query\|citations" tests/unit/api/test_query.py
```
Note the closest existing test that exercises the non-streaming POST `/query` endpoint and checks the citations field. We'll model the new assertion on it.

- [ ] **Step 2: Add a failing test**

Append to `tests/unit/api/test_query.py`:

```python
def test_query_endpoint_returns_chunk_text(client, fake_pipeline):
    """Sprint 3 v0.3: POST /query must include chunk_text per citation
    so non-streaming clients also see the preview text."""
    # fake_pipeline fixture is what the existing test_query_endpoint
    # tests use — re-use it. The fixture returns a result whose
    # answer.citations include the new chunk_text field.
    resp = client.post("/query", json={"messages": [{"role": "user", "content": "test"}], "top_k": 3})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["citations"]) >= 1
    assert "chunk_text" in data["citations"][0]
    assert data["citations"][0]["chunk_text"]  # non-empty
```

If the `fake_pipeline` fixture is currently constructing `Citation` objects that lack `chunk_text`, Task 1's model change will have already made those constructions invalid — so the fixture itself needs to be updated to pass `chunk_text="..."`. Find the fixture (likely in `tests/unit/api/conftest.py` or inline) and add `chunk_text="fake chunk text"` (or similar) to every `Citation(...)` constructor in test fixtures.

Search command to identify all such call sites:
```bash
grep -rn "Citation(" tests/ src/
```
For every match in `tests/`, add `chunk_text="…"`. For every match in `src/`, it should already be fixed by Task 1.

- [ ] **Step 3: Run to confirm the test fails**

```bash
PATH="$HOME/miniforge3/envs/NEBLab/bin:$PATH" pytest tests/unit/api/test_query.py::test_query_endpoint_returns_chunk_text -v
```
Expected: FAIL because `CitationOut` does not yet declare `chunk_text` and pydantic strips it from the response.

- [ ] **Step 4: Add `chunk_text` to `CitationOut`**

Use Edit on `src/neblab_rag/api/routes/query.py`:

`old_string`:
```python
class CitationOut(BaseModel):
    number: int
    doc_id: int
    openalex_id: str | None
    title: str
```

`new_string`:
```python
class CitationOut(BaseModel):
    number: int
    doc_id: int
    openalex_id: str | None
    title: str
    chunk_text: str
```

(The `CitationOut(**c.model_dump())` call below already splats every field, so no other line needs editing.)

- [ ] **Step 5: Run the full test suite**

```bash
make test
```
Expected: every test passes. If any older test that constructs `Citation` is now red because of the new required field, fix the test fixture to pass `chunk_text="…"`.

- [ ] **Step 6: Lint + format + typecheck**

```bash
make lint && PATH="$HOME/miniforge3/envs/NEBLab/bin:$PATH" ruff format --check . && make typecheck
```

- [ ] **Step 7: Commit**

```bash
git add src/neblab_rag/api/routes/query.py tests/
git commit -m "$(cat <<'EOF'
feat(api): CitationOut carries chunk_text (Sprint 3 v0.3 backend 3/3)

Non-streaming POST /query response now exposes chunk_text per
citation. Streaming SSE path emitted in prior commit. Closing the
backend half of v0.3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Frontend types + SSE parser

**Files:**
- Modify: `web/src/lib/types.ts`
- Verify: `web/src/hooks/use-stream-query.ts` (likely no code change; just confirm parser is permissive)

- [ ] **Step 1: Add `chunk_text` to the TS Citation interface**

Use Edit on `web/src/lib/types.ts`:

`old_string`:
```typescript
export interface Citation {
  number: number;
  doc_id: number;
  openalex_id: string | null;
  title: string;
}
```

`new_string`:
```typescript
export interface Citation {
  number: number;
  doc_id: number;
  openalex_id: string | null;
  title: string;
  /** Sprint 3 v0.3: full chunk text for inline preview. Optional so
   * legacy sessions persisted in localStorage before v0.3 (which
   * carry only title) degrade to the v0.2 card layout without errors. */
  chunk_text?: string;
}
```

- [ ] **Step 2: Inspect `parseCitations` to confirm it passes unknown fields through**

Run:
```bash
grep -n "parseCitations\|function parseCitations\|const parseCitations" web/src/hooks/use-stream-query.ts
```
Then `sed -n '<line-range>p'` to print the body. Confirm it's `JSON.parse(data) as Citation[]` (or a permissive `as`/`unknown` cast). If it's already a passthrough JSON.parse, **no code change needed** — the new `chunk_text` field will flow through automatically.

If `parseCitations` uses explicit field mapping (e.g. `{ number: x.number, title: x.title, ... }`), add `chunk_text: x.chunk_text` to the mapping.

- [ ] **Step 3: Run typecheck on the frontend**

Run:
```bash
cd web && npx tsc --noEmit
```
Expected: zero errors. (If the project uses `pnpm` instead of `npx`, run `cd web && pnpm tsc --noEmit`; check `web/package.json` for the script name.)

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/types.ts web/src/hooks/use-stream-query.ts
git commit -m "$(cat <<'EOF'
feat(web): Citation TS type gains optional chunk_text (Sprint 3 v0.3 1/3)

Adds chunk_text?: string to the Citation interface. Optional keeps
back-compat for ChatSessions persisted to localStorage before v0.3.
parseCitations is already a passthrough JSON.parse so SSE values
flow through unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: CitationsPanel — chevron + expandable chunk region

**Files:**
- Modify: `web/src/components/citations-panel.tsx`

- [ ] **Step 1: Update the `CitationsPanelProps` interface**

Use Edit on `web/src/components/citations-panel.tsx`:

`old_string`:
```typescript
interface CitationsPanelProps {
  citations: readonly Citation[];
  open: boolean;
  onToggle: () => void;
}
```

`new_string`:
```typescript
interface CitationsPanelProps {
  citations: readonly Citation[];
  open: boolean;
  onToggle: () => void;
  /** Sprint 3 v0.3: set of citation numbers whose chunk_text is
   * currently expanded in-card. Owned by the page so the [N] click
   * handler in the answer can also toggle entries here. */
  expandedCites: ReadonlySet<number>;
  onToggleExpand: (n: number) => void;
}
```

- [ ] **Step 2: Update the function signature and add chevron + chunk region**

Use Edit on `web/src/components/citations-panel.tsx`:

`old_string`:
```typescript
import { ChevronRight, BookOpen } from "lucide-react";
```

`new_string`:
```typescript
import { ChevronRight, BookOpen, ChevronDown, ChevronUp } from "lucide-react";
```

Then Edit the component body. `old_string`:
```typescript
export function CitationsPanel({
  citations,
  open,
  onToggle,
}: CitationsPanelProps) {
```

`new_string`:
```typescript
export function CitationsPanel({
  citations,
  open,
  onToggle,
  expandedCites,
  onToggleExpand,
}: CitationsPanelProps) {
```

- [ ] **Step 3: Replace the per-card `<li>` body to include chevron + chunk_text region**

Use Edit on `web/src/components/citations-panel.tsx`:

`old_string`:
```typescript
            {citations.map((c) => {
              const href = c.openalex_id
                ? `https://openalex.org/${c.openalex_id}`
                : null;
              return (
                <li
                  key={c.number}
                  id={`cite-${c.number}`}
                  className="scroll-mt-4 rounded-md p-2 -mx-2 transition-colors target:bg-accent"
                >
                  <div className="flex gap-2.5">
                    <span className="w-5 shrink-0 text-right tabular-nums text-muted-foreground">
                      {c.number}
                    </span>
                    <span className="flex-1">
                      {href ? (
                        <a
                          href={href}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-foreground decoration-foreground/20 underline-offset-4 hover:underline"
                        >
                          {c.title}
                        </a>
                      ) : (
                        <span className="text-foreground">{c.title}</span>
                      )}
                      {c.openalex_id && (
                        <span className="mt-1 block font-mono text-[0.7rem] tracking-tight text-muted-foreground">
                          {c.openalex_id}
                        </span>
                      )}
                    </span>
                  </div>
                </li>
              );
            })}
```

`new_string`:
```typescript
            {citations.map((c) => {
              const href = c.openalex_id
                ? `https://openalex.org/${c.openalex_id}`
                : null;
              const hasChunkText = !!c.chunk_text;
              const isExpanded = expandedCites.has(c.number);
              return (
                <li
                  key={c.number}
                  id={`cite-${c.number}`}
                  className="scroll-mt-4 rounded-md p-2 -mx-2 transition-colors target:bg-accent"
                >
                  <div className="flex gap-2.5">
                    <span className="w-5 shrink-0 text-right tabular-nums text-muted-foreground">
                      {c.number}
                    </span>
                    <span className="flex-1">
                      {href ? (
                        <a
                          href={href}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-foreground decoration-foreground/20 underline-offset-4 hover:underline"
                        >
                          {c.title}
                        </a>
                      ) : (
                        <span className="text-foreground">{c.title}</span>
                      )}
                      {c.openalex_id && (
                        <span className="mt-1 block font-mono text-[0.7rem] tracking-tight text-muted-foreground">
                          {c.openalex_id}
                        </span>
                      )}
                      {hasChunkText && (
                        <>
                          <button
                            type="button"
                            onClick={() => onToggleExpand(c.number)}
                            className="mt-2 flex items-center gap-1 text-[0.7rem] text-muted-foreground hover:text-foreground"
                            aria-expanded={isExpanded}
                            aria-controls={`cite-${c.number}-chunk`}
                          >
                            {isExpanded ? (
                              <ChevronUp className="size-3" />
                            ) : (
                              <ChevronDown className="size-3" />
                            )}
                            {isExpanded ? "隐藏 chunk 正文" : "显示 chunk 正文"}
                          </button>
                          {isExpanded && (
                            <div
                              id={`cite-${c.number}-chunk`}
                              className="mt-2 whitespace-pre-wrap border-t border-border/40 pt-2 text-[0.8rem] leading-6 text-muted-foreground"
                            >
                              {c.chunk_text}
                            </div>
                          )}
                        </>
                      )}
                    </span>
                  </div>
                </li>
              );
            })}
```

- [ ] **Step 4: Typecheck the frontend**

```bash
cd web && npx tsc --noEmit
```
Expected: zero errors. The component's caller (page.tsx) is not yet updated, so TypeScript will flag the missing props at the call site. Continue to Task 6.

If the only error is "Property 'expandedCites' is missing in type" / similar at page.tsx, that's expected — Task 6 fixes it.

- [ ] **Step 5: Hold the commit until Task 6 lands**

This task leaves the tree red. Don't commit yet — Task 6's page.tsx changes are what make the tree green again. We'll commit Task 5 + Task 6 together.

---

### Task 6: page.tsx — hoist `expandedCites` and wire it through

**Files:**
- Modify: `web/src/app/page.tsx`

- [ ] **Step 1: Read `page.tsx` to find the current `onCitationClick` handler and `CitationsPanel` usage**

Run:
```bash
grep -n "onCitationClick\|CitationsPanel\|expandedCites\|setActiveSessionId\|panelOpen" web/src/app/page.tsx
```
Note:
1. The line where `onCitationClick` is defined / passed to `AssistantBubble`
2. The line where `<CitationsPanel ... />` is rendered
3. The state where the active session is tracked (we'll piggyback the reset onto session changes)
4. The state controlling panel open/close (we'll piggyback the reset onto panel close)

- [ ] **Step 2: Add the `expandedCites` state**

In `page.tsx`, near the other `useState` calls at the top of the component, add:

```typescript
const [expandedCites, setExpandedCites] = useState<Set<number>>(new Set());

const toggleExpandedCite = useCallback((n: number) => {
  setExpandedCites((prev) => {
    const next = new Set(prev);
    if (next.has(n)) next.delete(n);
    else next.add(n);
    return next;
  });
}, []);

const expandCite = useCallback((n: number) => {
  setExpandedCites((prev) => {
    if (prev.has(n)) return prev;
    const next = new Set(prev);
    next.add(n);
    return next;
  });
}, []);

const clearExpandedCites = useCallback(() => {
  setExpandedCites((prev) => (prev.size === 0 ? prev : new Set()));
}, []);
```

Make sure `useCallback` is in the React import line at the top of the file. Example: change `import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";` to include `useCallback`.

- [ ] **Step 3: Wire `onCitationClick` to also call `expandCite`**

Find the existing `onCitationClick` handler in `page.tsx` (it scrolls the anchor element into view). After the scroll-into-view call, add `expandCite(num)`. Example pattern (use the exact existing handler — don't blindly copy):

```typescript
const handleCitationClick = useCallback(
  (num: number) => {
    const el = document.getElementById(`cite-${num}`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
    expandCite(num);
    setCitationsPanelOpen(true); // if panel-open state already exists; use its setter name
  },
  [expandCite],
);
```

(Existing handler may already open the panel — preserve that logic verbatim and only add `expandCite(num)`.)

- [ ] **Step 4: Wire `<CitationsPanel>` with the new props**

Find the `<CitationsPanel ... />` JSX. Add `expandedCites={expandedCites}` and `onToggleExpand={toggleExpandedCite}` props alongside the existing ones.

- [ ] **Step 5: Reset `expandedCites` on session switch + on panel close**

Find where the active session id is set (e.g. `setActiveSessionId(id)` calls). Locate the user-action paths that switch sessions: clicking sidebar item, "new chat", deleting current session. In each path, also call `clearExpandedCites()`.

Similarly, find the existing panel-close path. The cleanest place is the function that the panel's `onToggle` prop currently calls — wrap it so that when transitioning open=true→false it also calls `clearExpandedCites()`. Example:

```typescript
const handleTogglePanel = useCallback(() => {
  setCitationsPanelOpen((open) => {
    if (open) clearExpandedCites();
    return !open;
  });
}, [clearExpandedCites]);
```

Replace the current inline panel-toggle (likely passed directly to `<CitationsPanel onToggle={...} />`) with `handleTogglePanel`.

- [ ] **Step 6: Typecheck and verify the tree is green**

```bash
cd web && npx tsc --noEmit
```
Expected: zero errors. If there are still errors, fix them inline before continuing.

- [ ] **Step 7: Lint the front-end if there's a script**

Run:
```bash
cd web && npm run lint 2>/dev/null || echo "no lint script — skipping"
```

- [ ] **Step 8: Commit Tasks 5 + 6 together**

```bash
git add web/src/components/citations-panel.tsx web/src/app/page.tsx
git commit -m "$(cat <<'EOF'
feat(web): citation [N] expands chunk text in side panel (Sprint 3 v0.3 2/3)

CitationsPanel grows a per-card chevron + collapsible chunk_text
region (text-muted-foreground, whitespace-pre-wrap, no truncation).
page.tsx hoists expandedCites: Set<number>; onCitationClick now
scrolls *and* auto-expands the target card; closing the panel and
switching sessions both clear the set so cards return to the v0.2
collapsed state on next open.

chunk_text absent (legacy persisted sessions) → chevron hidden,
card falls back to v0.2 layout (title + openalex_id only).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Manual end-to-end verification + final commit

**Files:** (none — this is a smoke gate before declaring v0.3 done)

- [ ] **Step 1: Boot the backend**

In one terminal:
```bash
make dev
```
Wait for `Application startup complete.`

- [ ] **Step 2: Boot the frontend**

In another terminal:
```bash
cd web && npm run dev
```
Visit `http://localhost:3000`.

- [ ] **Step 3: Walk the happy path**

In the chat input, type: `为什么过度放牧会加速荒漠化？`

Submit; wait for the streaming answer to complete. Observe:
1. Right-side citations panel populates with cards numbered `1..N`
2. Each card shows title + openalex_id (v0.2 behaviour) PLUS a new "显示 chunk 正文" chevron
3. Click the first `[N]` (e.g. `[1]`) in the answer body → page scrolls to card 1 AND card 1's chunk text auto-expands
4. The displayed chunk text matches what would be in the Qdrant payload (roughly 500-1200 chars, no truncation)
5. Click the same `[1]` again → still expanded (no toggle from the answer-body click; only chevron toggles)
6. Click card 1's chevron → collapses; click again → expands

- [ ] **Step 4: Walk the reset paths**

- Click the panel's close button (right arrow at top-right of panel) → panel becomes narrow bar; click again → re-expands with all chunks collapsed (set was cleared)
- In the sidebar, click "新对话" / start a new chat → previous chat's expansion state does not leak; new chat's citations all start collapsed
- Switch back to the prior session via sidebar → its citations re-render with all chunks collapsed (set is cleared on switch)

- [ ] **Step 5: Walk the back-compat path**

- Refresh the page (the old session loads from localStorage)
- If the session was saved *before* this v0.3 deploy, citations will have `chunk_text === undefined`. The chevron should be **hidden** and the card should look exactly like v0.2
- If the session was saved *after* this v0.3 deploy, the chevron is visible and the chunk text works

To force the legacy state for testing: open DevTools → Application → Local Storage → edit a chat session entry → delete `chunk_text` from one citation → reload. That citation's card should drop the chevron.

- [ ] **Step 6: Walk the empty / error paths**

- Submit a query that returns no chunks (the chat handles it via `eval_case_error` path — try something very out-of-scope like `2026 World Cup winner`). Confirm: assistant says "无法回答" / similar, citations panel is empty, no chevrons rendered, no JS errors in console
- Stop the backend mid-stream (`Ctrl-C` `make dev`) and submit again. UI should show the existing "连接后端失败" toast. No new bugs.

- [ ] **Step 7: Quick lighthouse-ish sanity check**

In Chrome DevTools console, after a successful query, verify there are zero `Warning:` / `Error:` lines from React. If there are, fix before committing.

- [ ] **Step 8: Add a brief findings note**

Create `evals/v1/sprint-3-v03-citation-preview-findings.md` (brief — this is not a paid eval, just a record of what shipped):

```markdown
# Sprint 3 v0.3 — Citation Chunk Preview Findings (2026-05-19)

## Shipped

- Citation panel cards expose chunk_text on demand
- Click [N] in answer → side panel auto-expands that card's chunk
- Chevron toggle per card; closing panel / switching session clears expansion state
- Back-compat: legacy stored sessions without chunk_text fall back to v0.2 layout

## Verification

- Backend tests: `make test` PASS
- Lint/format/typecheck: PASS
- Manual smoke: walked happy path, reset paths, back-compat path, empty/error paths
- Browser console clean (no React warnings)

## Decision

SHIP. Next UI candidate: v0.4 multi-turn deepening or answer-export-to-Markdown
(see spec §2.2). No new infra dependencies.

## Files

- Backend: `src/neblab_rag/rag/generator.py`, `handlers.py`, `api/routes/query.py` (+ tests)
- Frontend: `web/src/lib/types.ts`, `components/citations-panel.tsx`, `app/page.tsx`
- Spec: `docs/superpowers/specs/2026-05-19-citation-chunk-preview-design.md`
- Plan: `docs/superpowers/plans/2026-05-19-citation-chunk-preview-plan.md`
```

- [ ] **Step 9: Commit the findings**

```bash
git add evals/v1/sprint-3-v03-citation-preview-findings.md
git commit -m "$(cat <<'EOF'
docs(sprint3-v03): chunk preview findings — SHIP

Manual smoke pass on happy / reset / back-compat / empty paths.
Closes Sprint 3 v0.3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 10: Surface the merge command (do NOT execute)**

Per CLAUDE.md, the operator runs the merge / push themselves. Print:

```
Ready to merge feature/sprint3-ui-v03-citation-preview. Run manually:
  git checkout feature/sprint3-ui-v01 && git merge --no-ff feature/sprint3-ui-v03-citation-preview
  # or, if v0.1 has been merged to main already:
  git checkout main && git merge --no-ff feature/sprint3-ui-v03-citation-preview
  git push origin <target-branch>   # USER MUST RUN — per project convention
```

---

## Self-Review

Checked the plan against the spec along the four required axes:

1. **Spec coverage**
   - Spec §3.2 v0.3 dataflow (Citation → CitationOut → SSE → TS type) → Tasks 1, 2, 3, 4
   - Spec §4.1 v0.3 card structure (title + chevron + chunk) → Task 5
   - Spec §4.2 interaction table (click [N] auto-expand; chevron toggle; close-panel reset; session-switch reset) → Tasks 5 + 6
   - Spec §4.3 default folded state → Task 5 default `isExpanded = false`
   - Spec §4.4 visual (muted-foreground, whitespace-pre-wrap, lucide chevrons, border-t/40 divider) → Task 5 Step 3
   - Spec §5.1 backend file list → Tasks 1, 2, 3 (note: spec mentioned only generator + routes, but handlers.py is also a citation emission point that the implementation discovered — Task 2 added; not a deviation, just a more-complete plan than the spec snapshot)
   - Spec §5.2 frontend file list → Tasks 4, 5, 6
   - Spec §5.3 validation → Task 0 + Task 7
   - Spec §6 risk (chunk_text special chars, 7-chunk panel length, Next.js 16 boundary, fixture updates, SSE size) → all addressed in tasks or noted

2. **Placeholder scan**
   - No "TBD" / "TODO" / "fill in" / "similar to Task N" anywhere.
   - All code blocks are concrete and self-contained.
   - Task 6 Step 3 says "Use the existing handler — don't blindly copy" because we can't show code we haven't read yet; this is a *read instruction*, not a placeholder.

3. **Type consistency**
   - `chunk_text` (snake_case) on the backend; `chunk_text` (snake_case) on the TS type — matches because the backend's JSON shape is what the frontend consumes. Confirmed stable across Tasks 1/2/3/4.
   - `expandedCites: ReadonlySet<number>` (panel prop) vs `Set<number>` (state) — these are compatible (Set is assignable to ReadonlySet). Stable across Tasks 5 and 6.
   - `onToggleExpand: (n: number) => void` — same signature in both files. Stable.
   - `expandCite` / `toggleExpandedCite` / `clearExpandedCites` — named consistently within Task 6.

4. **Ambiguity check**
   - Task 3 Step 2 explicitly handles the fixture-update path (every Citation(...) call site in tests needs chunk_text="…"). This is the most likely source of test regressions; pre-flagged.
   - Task 6 Steps 3/5 acknowledge that page.tsx's exact prior structure isn't quoted in the plan (because it depends on reading the live file); the *instructions* are unambiguous about what to add and where.
   - Task 5 vs Task 6 commit timing is explicit (Task 5 leaves tree red; commit at end of Task 6).

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-19-citation-chunk-preview-plan.md`.**
