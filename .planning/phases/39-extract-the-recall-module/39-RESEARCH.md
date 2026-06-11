# Phase 39: Extract the Recall Module - Research

**Researched:** 2026-06-11
**Domain:** Python service refactor — behavior-preserving extraction of retrieval policy into a `Recall` module
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Extract a deep `Recall` module that owns retrieval policy and sits *above* the Vault seam.
- **D-02:** `Recall` owns *what to remember*: Self namespace reads, recent Session summaries, Warm-tier vault search, the relevance threshold, the namespace exclusions, the recent-session window, and the per-tier selection budgets (the `0.15` / `0.10` split). These constants move into a `RecallConfig`.
- **D-03:** `Recall.assemble(request, budget)` returns a `RecalledContext` value — ranked, budget-trimmed memory items. It does NOT return chat messages.
- **D-04:** `MessageProcessor` keeps *how to present and defend*: the Sentinel persona read, `injection_filter.wrap_context()`, the "Understood." pairs, and the final whole-prompt `TokenBudget.check()`.
- **D-05:** `GET /context/{user_id}` delegates to `Recall` and serializes `RecalledContext`. The duplicated inline assembly is deleted.
- **D-06:** `Recall` depends on the `Vault` Protocol only. It does NOT move or modify `app/vault.py` (ADR-0002 stands).

### Claude's Discretion
- Internal structure of `RecallConfig` (dataclass vs pydantic), exact module/file layout under `app/`, naming of private helpers (`_warm_search`, etc.), and how raw Obsidian dicts are translated to `SearchResult` at Recall's edge — provided the leakage of raw dicts stops at that edge.
- Wiring/DI approach for injecting `Recall` into `MessageProcessor` and the `/context` route.

### Deferred Ideas (OUT OF SCOPE)
- Typed `SessionSummary` + `RetentionPolicy` → Phase 41.
- `RetrievalStrategy` seam + `SemanticRecall` adapter → Phase 40.
- Typing `find()` in the Vault Protocol → later step.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MEM-01 | The Sentinel assembles recalled memory for every message through a single Recall module, and the `/context/{user_id}` endpoint uses that same module (no duplicated assembly logic) | Section 2 (duplication map) + Section 6 (wiring) show the exact cut points |
| MEM-02 | Recall policy — relevance threshold, namespace exclusions (including `ops/`), and per-tier context budgets — is consolidated as explicit configuration rather than inline constants | Section 1 (inline constant inventory) gives every literal to extract |
</phase_requirements>

---

## Summary

Phase 39 is a **behavior-preserving extraction**: every piece of hot-tier and warm-tier assembly logic currently embedded in `MessageProcessor` moves into a new `Recall` module, with inline constants moving to `RecallConfig`. The primary source of truth is `sentinel-core/app/services/message_processing.py` — all extraction happens from this one file.

The current duplication is clean and bounded: `_append_hot_tier` and `_append_warm_tier` are private methods on `MessageProcessor`, and `GET /context/{user_id}` in `app/routes/status.py` hand-rolls only the self-context half of hot-tier assembly (not the persona swap, not warm-tier). After extraction, both paths call `Recall.assemble()` and the status route serializes the typed `RecalledContext` value rather than constructing its own dict.

The principal risk is behavioral drift. The planner must ensure `Recall.assemble()` reproduces the existing hot/warm assembly exactly — same path list, same exclusion prefixes, same budget arithmetic, same top-3 cap on warm results, same graceful-degrade behavior (empty results → no injection). The kept `test_message_processor.py` tests and `test_message.py` through-`/message` tests serve as the regression net.

**Primary recommendation:** Create `app/services/recall.py` containing `SearchResult`, `RecalledContext`, `RecallConfig`, and `Recall`. Wire `Recall` into `MessageProcessor` via constructor injection (same pattern as `vault`, `ai_provider`). Add `recall` field to `AppGraph` and `RouteContext`. The `/context` route reads `ctx.recall` and awaits `assemble()`.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Hot-tier self-context reads | Recall module | — | Recall owns *what to remember*; self namespace reads are recall policy (D-02) |
| Hot-tier session reads | Recall module | — | Session recency window is recall policy (D-02) |
| Warm-tier vault search + filter | Recall module | — | Relevance threshold and exclusion list are recall policy (D-02) |
| Persona system message swap | MessageProcessor | — | Persona is operator-curated identity, not recalled memory (D-04) |
| injection_filter wrapping | MessageProcessor | — | Presentation/defense layer (D-04) |
| "Understood." pairs | MessageProcessor | — | Presentation layer (D-04) |
| Final TokenBudget.check() | MessageProcessor | — | Whole-prompt guard (D-04) |
| /context/{user_id} serialization | Route handler | Recall (via delegation) | Route serializes RecalledContext; assembly logic lives in Recall (D-05) |
| RecallConfig constants | Recall module | — | Locality + single-place tuning (D-02) |

---

## Current Assembly Internals (the extraction map)

### `_append_hot_tier` — lines 195–234 of `message_processing.py` [VERIFIED: file read]

**Signature:** `async def _append_hot_tier(self, messages: list[dict], req: MessageRequest, budget: int) -> None`

**What it does (in order):**
1. Defines a hard-coded `self_paths` list of 6 paths + persona path (7 total reads via `asyncio.gather`):
   - `"self/identity.md"`, `"self/methodology.md"`, `"self/goals.md"`, `"self/relationships.md"`, `"ops/reminders.md"`, `"self/learning-areas.md"` — self-context paths
   - `"sentinel/persona.md"` — persona read (separate from self-context)
2. Calls `self._vault.read_self_context(p)` for each self path AND the persona path in one `asyncio.gather`.
3. Persona swap: if `persona_result` is a non-empty string, replaces `messages[0]` with `{"role": "system", "content": persona_result}`; otherwise logs WARNING and uses `_FALLBACK_PERSONA`.
4. Calls `self._vault.get_recent_sessions(req.user_id, limit=3)` — session window is **hard-coded as `limit=3`**.
5. Assembles `context_parts` — `"Personal context:\n..."` joined with `"\n\n---\n\n"`, then `"Recent session history:\n..."` joined with `"\n---\n"`.
6. If `context_parts` is empty, returns without appending anything.
7. Calls `self._budget.truncate(raw_context, budget)` to fit budget.
8. Calls `self._injection_filter.wrap_context(safe_context)`.
9. Appends `{"role": "user", "content": filtered_context}` + `{"role": "assistant", "content": "Understood."}` to messages.

**What moves to Recall vs stays in MessageProcessor:**
- Steps 1, 4: self_paths list, session limit → `RecallConfig`
- Steps 1–4 (the vault reads themselves): move to `Recall._hot_self()` + `Recall._hot_sessions()`
- Step 3 (persona swap): **stays in MessageProcessor** — it mutates `messages[0]`, which is presentation (D-04)
- Steps 7–9 (truncate + wrap + inject messages): **stay in MessageProcessor** — budget truncation and injection formatting are presentation (D-04)
- `Recall.assemble()` returns the raw content strings as `RecalledContext.self_context` and `RecalledContext.sessions`

**Critical note on persona:** The persona path `"sentinel/persona.md"` is currently gathered inside `_append_hot_tier`. In the extracted `Recall`, the persona read must **not** be part of `assemble()` — `RecalledContext` does not carry persona (D-03). `MessageProcessor` must continue to read the persona directly from vault OR receive it as a separate pre-step. The simplest split: `Recall.assemble()` reads only the 6 self paths + sessions; `MessageProcessor.process()` keeps its own `await self._vault.read_self_context("sentinel/persona.md")` call as a separate step (as it is today, just separated from the gather). [VERIFIED: file read]

### `_append_warm_tier` — lines 236–263 of `message_processing.py` [VERIFIED: file read]

**Signature:** `async def _append_warm_tier(self, messages: list[dict], req: MessageRequest, budget: int) -> None`

**What it does (in order):**
1. If `len(words) > _KEYWORD_SEARCH_THRESHOLD` (5), calls `_best_search_query(req.content)` → query; else uses `req.content` directly.
2. Calls `self._vault.find(query)` → raw `list[dict]`.
3. Filters: keeps results where `r.get("score", float("-inf")) >= SEARCH_SCORE_THRESHOLD` AND `not r.get("filename", "").startswith(_WARM_TIER_EXCLUDE_PREFIXES)`.
4. If empty after filter, returns early.
5. Takes top 3 results (hard-coded `[:3]`).
6. Reads full note bodies via `asyncio.gather(*[self._vault.read_note(p) for p in paths], return_exceptions=True)`.
7. Calls `self._format_search_results(top_results, paths, raw_contents)` to build the vault block string.
8. Calls `self._budget.truncate(vault_block, budget)`.
9. Calls `self._injection_filter.wrap_context(safe_vault)`.
10. Appends user/assistant pair to messages.

**What moves to Recall:**
- Steps 1–7: the vault search logic and `_format_search_results` — all move to `Recall._warm_search()` which returns `list[SearchResult]`
- Specifically: raw dict `→ SearchResult` translation happens at step 3/5 in `Recall._warm_search()`
- `_extract_keywords`, `_best_search_query`, `_SEARCH_STOPWORDS`, `_KEYWORD_SEARCH_THRESHOLD` — all move to `recall.py`
- `_format_search_results` — moves to `recall.py` or becomes a helper; Recall returns typed `SearchResult` and `MessageProcessor` formats for injection
- Steps 8–10 (truncate + wrap + inject): **stay in MessageProcessor**

**What `RecalledContext.warm` carries:** `list[SearchResult]` where `SearchResult` has `path: str`, `score: float`, `body: str` (full note text, snippet fallback if read fails). The serialization (joining into a "Relevant vault notes:" block) can stay in `MessageProcessor` or be a static helper on `Recall` — the ADR does not mandate either, so this is Claude's discretion.

### `_allocate_budgets` — lines 144–148 of `message_processing.py` [VERIFIED: file read]

**Signature:** `@classmethod def _allocate_budgets(cls, context_window: int) -> _ContextBudget`

**Behavior:** Returns `_ContextBudget(sessions_budget=int(context_window * 0.15), search_budget=int(context_window * 0.10))`.

This classmethod moves to `Recall` as `_allocate()` (or equivalent). `_ContextBudget` can be replaced by `RecallConfig` fields once the ratios are there. The `budget` parameter passed to `Recall.assemble()` is the total context window — `Recall._allocate()` recomputes the per-tier splits internally.

### Inline constants to move to `RecallConfig` [VERIFIED: file read]

All located in `sentinel-core/app/services/message_processing.py`:

| Constant | Line | Value | Type | Move to RecallConfig as |
|----------|------|-------|------|-------------------------|
| `SEARCH_SCORE_THRESHOLD` | 23 | `-200.0` | `float` | `relevance_threshold: float = -200.0` |
| `_WARM_TIER_EXCLUDE_PREFIXES` | 30 | `("ops/", "_trash/", "self/")` | `tuple[str, ...]` | `exclude_prefixes: tuple[str, ...] = ("ops/", "_trash/", "self/")` |
| `_SEARCH_STOPWORDS` | 37–44 | large frozenset | `frozenset[str]` | Can stay as module-level constant in `recall.py` (not a tunable config value) |
| `_KEYWORD_SEARCH_THRESHOLD` | 47 | `5` | `int` | `keyword_threshold: int = 5` (or leave as module constant — not a policy knob) |
| `MessageProcessor._SESSIONS_RATIO` | 133 | `0.15` | `float` | `sessions_ratio: float = 0.15` |
| `MessageProcessor._SEARCH_RATIO` | 134 | `0.10` | `float` | `search_ratio: float = 0.10` |
| Recent sessions `limit=3` (hard-coded in call) | 220 | `3` | `int` | `recent_session_limit: int = 3` |
| `self_paths` list | 196–203 | 6 paths | `list[str]` | `self_paths: list[str] = [...]` (or module constant) |
| Warm top-N cap | 250 | `[:3]` | `int` | `warm_top_n: int = 3` (or leave as constant) |

**MEM-02 mandate:** At minimum, `relevance_threshold`, `exclude_prefixes`, `sessions_ratio`, `search_ratio`, and `recent_session_limit` must appear in `RecallConfig`. The others are implementation constants and can stay as module-level literals.

**Note on `SEARCH_SCORE_THRESHOLD` export:** `app/routes/message.py` line 9 imports `SEARCH_SCORE_THRESHOLD` from `message_processing` and re-exports it (`_ = SEARCH_SCORE_THRESHOLD`). After extraction, this import must move to `recall.py` — or the `message.py` import can be updated/removed. [VERIFIED: file read]

---

## The Duplication: `GET /context/{user_id}` [VERIFIED: file read]

**Location:** `sentinel-core/app/routes/status.py`, lines 36–67

**What it currently does:**
```python
@router.get("/context/{user_id}")
async def debug_context(request, user_id):
    ctx = get_route_context(request)
    obsidian = ctx.vault
    self_paths = [
        "self/identity.md", "self/methodology.md", "self/goals.md",
        "self/relationships.md", "ops/reminders.md", "self/learning-areas.md",
    ]
    results = await asyncio.gather(
        *[obsidian.read_self_context(p) for p in self_paths],
        return_exceptions=True,
    )
    context_files = {
        path: text for path, text in zip(self_paths, results)
        if isinstance(text, str) and text
    }
    sessions = await obsidian.get_recent_sessions(user_id)
    return JSONResponse({
        "user_id": user_id,
        "context_files": context_files,
        "recent_sessions_count": len(sessions),
    })
```

**What this duplicates:** The self_paths list and `asyncio.gather` over `read_self_context` are byte-for-byte identical to `MessageProcessor._append_hot_tier` lines 196–210. It does NOT duplicate the warm-tier search.

**What must be deleted:** The `self_paths` list, the `asyncio.gather` call, and the `get_recent_sessions` call — all replaced by `await ctx.recall.assemble(...)`.

**What the new `/context` serializer must return:** After delegation, the response shape must preserve backward compatibility for any callers:
- `user_id` — kept
- `context_files` — currently `{path: text, ...}` for non-empty self files. After extraction, `RecalledContext.self_context` is `list[str]` (raw markdown). The serializer must reconstruct a compatible shape OR the existing tests must be updated. See test_status.py — existing tests only assert `user_id` and `recent_sessions_count`, so the serialization shape has latitude.
- `recent_sessions_count` — currently `len(sessions)`. After extraction, `RecalledContext.sessions` is `list[str]`, so `len(recalled.sessions)`.

**New serialization target:**
```python
@router.get("/context/{user_id}")
async def debug_context(request, user_id):
    ctx = get_route_context(request)
    # Build a synthetic MessageRequest for assemble()
    fake_req = MessageRequest(content="", user_id=user_id, ...)
    recalled = await ctx.recall.assemble(fake_req, budget=ctx.context_window)
    return JSONResponse({
        "user_id": user_id,
        "self_context": recalled.self_context,
        "sessions": recalled.sessions,
        "warm": [{"path": r.path, "score": r.score} for r in recalled.warm],
        "recent_sessions_count": len(recalled.sessions),
    })
```

Note: The `/context` route doesn't have a `content` to drive warm-tier search with. The planner must decide whether to call `assemble()` with `content=""` (warm search returns nothing meaningful for an empty query) or call a hot-tier-only variant. The simplest behavior-preserving choice: pass `content=""` — warm search degrades gracefully on empty queries because the empty query will match nothing or be below threshold. This is Claude's discretion.

---

## The Vault Seam [VERIFIED: file read]

**Location:** `sentinel-core/app/vault.py`

**Protocol surface `Recall` depends on** (subset of `Vault`):

| Method | Signature | Used by |
|--------|-----------|---------|
| `read_self_context` | `async def read_self_context(self, path: str) -> str` | Hot-tier self reads; returns `""` on 404/error (graceful degrade) |
| `get_recent_sessions` | `async def get_recent_sessions(self, user_id: str, limit: int = 3) -> list[str]` | Hot-tier session reads; returns `[]` on error (graceful degrade) |
| `find` | `async def find(self, query: str) -> list[dict]` | Warm-tier search; returns `[]` on error (graceful degrade) |
| `read_note` | `async def read_note(self, path: str) -> str` | Warm-tier note body fetch; returns `""` on 404/error |

**Raw dict shape from `Vault.find()`:** `list[dict]` where each dict has:
- `"filename"` — vault-relative path string (used for exclusion prefix check and for fetching the note)
- `"score"` — float (Obsidian BM25 negative value; relevant notes ~-120, noise ~-202)
- `"matches"` — `list[dict]` with `"context"` key — used as snippet fallback when `read_note` fails

**`SearchResult` translation point:** In `Recall._warm_search()`, after filtering and top-N selection, each raw dict is translated to `SearchResult(path=r["filename"], score=r["score"], body=<read_note result or snippet>)`. Raw dicts must not leak past the `_warm_search()` boundary — this is the ADR constraint.

**`Vault` is NOT modified by this phase.** `app/vault.py` has no changes. The Protocol already exposes the 4 methods Recall needs. `FakeVault` already implements all 4 with correct graceful-degrade semantics. [VERIFIED: file read, ADR-0002]

---

## The `RecalledContext` Value Type

**Proposed shape** (consistent with ADR-0003 interface sketch):

```python
@dataclass(frozen=True)
class SearchResult:
    path: str
    score: float   # Obsidian BM25 negative value — typed and named here
    body: str      # full note text, or snippet fallback

@dataclass(frozen=True)
class RecalledContext:
    self_context: list[str]    # raw markdown strings from self_paths, non-empty only
    sessions: list[str]        # raw markdown strings from get_recent_sessions
    warm: list[SearchResult]   # typed at Recall's edge; empty list if no results
```

**Half-typed by design:** `self_context` and `sessions` are `list[str]` (raw markdown). Typed `SessionSummary` arrives in Phase 41.

**What each consumer uses:**
- `MessageProcessor._append_hot_tier` (after refactor): joins `self_context` with `"\n\n---\n\n"`, joins `sessions` with `"\n---\n"`, truncates, wraps, injects.
- `MessageProcessor._append_warm_tier` (after refactor): formats `warm` list into "Relevant vault notes:" block, truncates, wraps, injects.
- `GET /context/{user_id}` serializer: `len(sessions)` → `recent_sessions_count`; `self_context`, `sessions`, `warm` → JSON fields.

---

## Test Surface [VERIFIED: file read]

### FakeVault construction

`FakeVault` (`sentinel-core/tests/fakes/vault.py`) is a pure dict-backed implementation of the full `Vault` Protocol:

```python
# Constructor
vault = FakeVault(
    notes={"self/identity.md": "# I am ...", "ops/sessions/2026-06-11/user-12-00-00.md": "..."},
    dirs={"": ["self/", "ops/"], "self": ["identity.md"]},
)

# Or mutate after construction:
vault.notes["self/goals.md"] = "My goals..."
```

**`FakeVault.find(query)`:** Returns `[{"filename": path, "score": 1.0}]` for any note whose body contains the query (case-insensitive). Score is always `1.0` — well above the `-200.0` threshold. The exclude-prefix filter in `Recall._warm_search()` must still be applied since FakeVault does not apply it.

**`FakeVault.get_recent_sessions(user_id, limit=3)`:** Returns bodies of notes at paths matching `ops/sessions/*/` where `f"{user_id}-" in filename`, sorted descending, up to `limit`. To seed: `vault.notes["ops/sessions/2026-06-11/trekkie-12-00-00.md"] = "session body"`.

### Existing tests to keep (Test-Rewrite Ban) [VERIFIED: file read]

| Test file | Coverage area | Must keep? |
|-----------|---------------|-----------|
| `test_message_processor.py` | `MessageProcessor.process()` behaviors (persona, fallback, error codes) | YES |
| `test_message.py` | Through-`POST /message` integration (hot-tier, warm-tier, auth) | YES |
| `test_status.py` | `GET /context/{user_id}` — currently tests `user_id`, `recent_sessions_count`, auth | YES — but the serializer shape may change; the 3 passing assertions are broad enough to survive |

### New test file: `test_recall.py`

**Location:** `sentinel-core/tests/test_recall.py`

**Pattern:** Construct `Recall(vault=FakeVault(...), config=RecallConfig(...))`, call `await recall.assemble(req, budget)`, assert on `RecalledContext` fields. No `MessageProcessor`, no AI provider, no `InjectionFilter`.

**Key test scenarios:**
1. `assemble()` returns `self_context` populated from seeded self notes
2. `assemble()` returns `sessions` populated from seeded session notes
3. Warm search: notes above threshold in non-excluded paths appear in `warm`
4. Warm search: notes with `ops/` or `self/` prefix excluded
5. Warm search: notes below threshold (`score < -200.0`) excluded
6. Empty vault → all lists empty (graceful degrade)
7. `RecallConfig` relevance_threshold and exclude_prefixes are respected

---

## DI Wiring [VERIFIED: file read]

### How `MessageProcessor` is constructed today

**In `app/composition.py` lines 307–313:**
```python
if message_processor is None:
    message_processor = MessageProcessor(
        vault=vault,
        ai_provider=ai_provider,
        injection_filter=injection_filter,
        output_scanner=output_scanner,
    )
```

**`MessageProcessor.__init__` signature** (line 136):
```python
def __init__(self, vault, ai_provider, injection_filter, output_scanner) -> None
```

### How `Recall` gets injected

**Option A (recommended — Claude's discretion):** Add `recall: Recall` as a constructor parameter to `MessageProcessor`:

```python
def __init__(self, vault, ai_provider, injection_filter, output_scanner, *, recall: Recall) -> None:
```

Then in `composition.py`, construct `recall = Recall(vault=vault)` before `MessageProcessor`, and pass it in:
```python
recall = Recall(vault=vault)
message_processor = MessageProcessor(vault=vault, ai_provider=ai_provider,
    injection_filter=injection_filter, output_scanner=output_scanner, recall=recall)
```

**RouteContext:** Add `recall: Recall` field to `RouteContext` in `app/state.py`. Pin it in `initialize_startup()` in `composition.py` alongside `processor`.

**AppGraph:** Add `recall: Recall` field to `AppGraph` in `composition.py`.

**`/context` route:** Reads `ctx.recall` directly from `RouteContext`.

### Test wiring impact

`test_message_processor.py` constructs `MessageProcessor` directly via `make_processor()`. After adding `recall` as a constructor parameter, `make_processor()` must either:
- Accept `recall=` kwarg defaulting to a `FakeRecall` or `Recall(FakeObsidian())`
- Or use `recall=Recall(vault=FakeObsidian())` as default

`test_message.py`'s `_LazyTestProcessor` constructs `MessageProcessor` with `app.state.*` fields. It must also supply a `recall` — either from `app.state.recall` or from a `FakeVault`.

---

## Common Pitfalls

### Pitfall 1: Persona path leaking into Recall
**What goes wrong:** If `"sentinel/persona.md"` is included in `Recall._hot_self()` reads, the persona string ends up in `RecalledContext.self_context` and is injected twice — once as `messages[0]["system"]` and once as a user-turn context block.
**Why it happens:** In the current code, the persona path is gathered alongside the self paths in the same `asyncio.gather`. It's easy to copy the whole gather.
**How to avoid:** `Recall._hot_self()` reads only the 6 self paths. `MessageProcessor.process()` reads `"sentinel/persona.md"` separately via its own `await self._vault.read_self_context("sentinel/persona.md")` call (just as it does today, extracted from the gather).

### Pitfall 2: Breaking the `ops/reminders.md` exception
**What goes wrong:** `ops/reminders.md` is currently in the hot-tier `self_paths` list (read as self-context) even though `ops/` is in `_WARM_TIER_EXCLUDE_PREFIXES`. This is intentional — reminders are explicitly injected as self-context via the hot tier, not via warm search.
**Why it happens:** The warm-tier exclusion of `ops/` only applies to `Vault.find()` results (warm search). The hot-tier self_paths list is a hard-coded allowlist that explicitly includes `ops/reminders.md`.
**How to avoid:** Keep `ops/reminders.md` in `RecallConfig.self_paths`. The exclusion in `RecallConfig.exclude_prefixes` applies only to warm search, not to the self_paths list.

### Pitfall 3: Budget arithmetic rounding
**What goes wrong:** `int(context_window * 0.15)` and `int(context_window * 0.10)` truncate (Python `int()` truncates toward zero). If the new code uses `round()` instead, budgets differ for some context window sizes.
**How to avoid:** Use `int()` (truncating division) to match the existing behavior exactly.

### Pitfall 4: FakeVault `find()` always returns score=1.0
**What goes wrong:** `FakeVault.find()` returns `{"filename": ..., "score": 1.0}` — always above the threshold. Tests that want to test threshold filtering must either: (a) use a negative score manually, or (b) confirm the `RecallConfig.relevance_threshold` is being applied (by seeding notes that would match the query and expecting them filtered when score is injected as below-threshold).
**How to avoid:** In `test_recall.py`, override the vault's `find()` return to include a result with score `-300.0` and assert it doesn't appear in `RecalledContext.warm`.

### Pitfall 5: Warm search exclusion check uses `str.startswith(tuple)`
**What goes wrong:** `r.get("filename", "").startswith(_WARM_TIER_EXCLUDE_PREFIXES)` works because Python's `str.startswith` accepts a tuple. If rewritten as `any(r["filename"].startswith(p) for p in exclude_prefixes)`, this is equivalent — but if rewritten with `in` it's wrong.
**How to avoid:** Preserve `str.startswith(tuple)` semantics. The `RecallConfig.exclude_prefixes` field type should be `tuple[str, ...]` (not `list`) to pass directly to `startswith`.

### Pitfall 6: `_format_search_results` ownership
**What goes wrong:** `_format_search_results` currently builds the "Relevant vault notes:" markdown string. If this logic moves to Recall entirely and Recall returns the formatted string, then `RecalledContext` leaks presentation concerns (D-03 violation). If it stays in `MessageProcessor` but `RecalledContext.warm` carries `list[SearchResult]`, the processor formats it — clean.
**How to avoid:** Keep `_format_search_results` in `MessageProcessor` (or make it a standalone helper in `message_processing.py`). `RecalledContext.warm` carries `list[SearchResult]`; the processor formats for injection.

### Pitfall 7: `test_status.py` serialization break
**What goes wrong:** The current `/context` response has `"context_files": {path: text, ...}`. If the new serializer emits `"self_context": [str, ...]` instead, the test `test_context_returns_user_id` still passes but any integration client expecting `context_files` would break.
**How to avoid:** Either keep a `context_files` key in the new response (reconstruct from `recalled.self_context` and the path list) or confirm no external callers depend on the current shape. The existing `test_status.py` only asserts `user_id` and `recent_sessions_count`, so the tests survive either way.

### Pitfall 8: Empty-content warm search in `/context` route
**What goes wrong:** The `/context` route has no user message content. Passing `content=""` to `assemble()` causes the warm-tier to search with `""` — the query hits `vault.find("")` which in `FakeVault` matches all notes (since `"" in body` is always True). In production `ObsidianVault`, an empty search may return unexpected results.
**How to avoid:** Design option A — `Recall.assemble()` returns empty `warm=[]` when `content` is empty (early return before calling `vault.find()`). Design option B — The `/context` route accepts an optional `?query=` parameter. Design option C — Accept and document that the `/context` route returns hot-tier-only context (warm requires a query). This is Claude's discretion; the ADR does not mandate the behavior.

---

## Architecture Patterns

### Recommended module location

Following ADR-0002's pattern (sibling top-level capability modules):
- **`sentinel-core/app/services/recall.py`** — `SearchResult`, `RecalledContext`, `RecallConfig`, `Recall` class

This keeps `app/vault.py` untouched (ADR-0002), does not require a new top-level module (Recall is a service, not a seam), and follows the existing `app/services/` convention where stateful services live (`message_processing.py`, `token_budget.py`).

### Recommended file structure change

```
sentinel-core/app/services/
├── message_processing.py    # trimmed: _append_hot_tier/_append_warm_tier/_allocate_budgets removed
├── recall.py                # NEW: SearchResult, RecalledContext, RecallConfig, Recall
├── token_budget.py          # unchanged
└── ... (all other services unchanged)
```

### ADR-0003 interface sketch (canonical reference) [VERIFIED: docs/adr/0003-recall-module.md]

```python
@dataclass(frozen=True)
class SearchResult:
    path: str
    score: float
    body: str

@dataclass(frozen=True)
class RecalledContext:
    self_context: list[str]
    sessions: list[str]
    warm: list[SearchResult]

class Recall:
    def __init__(self, vault: Vault, *, config: RecallConfig = DEFAULT) -> None: ...
    async def assemble(self, request: MessageRequest, budget: int) -> RecalledContext: ...
    # private: _hot_self() · _hot_sessions() · _warm_search() · _allocate()
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async parallel reads | Sequential awaits | `asyncio.gather(..., return_exceptions=True)` | Already the pattern in `_append_hot_tier`; preserves graceful degrade behavior |
| Token counting | Custom word count | `TokenBudget.truncate()` from `app.services.token_budget` | Already exists, used by MessageProcessor; Recall should pass raw content back and let MessageProcessor truncate |
| Vault search | Custom search impl | `Vault.find()` Protocol method | ADR-0002 owns this seam |

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.23 |
| Config file | `sentinel-core/pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `cd sentinel-core && uv run pytest tests/test_recall.py -x` |
| Full suite command | `cd sentinel-core && uv run pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MEM-01 | `Recall.assemble()` is sole entry point — `MessageProcessor` delegates | unit | `uv run pytest tests/test_recall.py tests/test_message_processor.py -x` | ❌ Wave 0 (test_recall.py) / ✅ (test_message_processor.py) |
| MEM-01 | `/context/{user_id}` uses same Recall (no duplicated logic) | integration | `uv run pytest tests/test_status.py -x` | ✅ |
| MEM-02 | Relevance threshold, exclusions, budgets readable from RecallConfig | unit | `uv run pytest tests/test_recall.py -x -k "config"` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_recall.py tests/test_message_processor.py tests/test_status.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_recall.py` — new test file; covers `Recall.assemble()` behavior against `FakeVault` for MEM-01 and MEM-02

*(All other test infrastructure already exists.)*

---

## Security Domain

This phase performs no authentication changes, no new external network connections, and no new user-facing input paths. It is a pure internal extraction refactor.

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | — |
| V3 Session Management | No | — |
| V4 Access Control | No | — |
| V5 Input Validation | No new inputs | Existing `InjectionFilter` stays in `MessageProcessor` (D-04) |
| V6 Cryptography | No | — |

No new threat surface is introduced. The `injection_filter.wrap_context()` wrapping of recalled content stays in `MessageProcessor` — `Recall` never calls `InjectionFilter`.

---

## Environment Availability

Step 2.6: SKIPPED — This phase installs no new packages and has no new external service dependencies. All required infrastructure (`uv`, `pytest`, `pytest-asyncio`) is already in `pyproject.toml` and verified by the existing test suite. [VERIFIED: sentinel-core/pyproject.toml]

---

## Package Legitimacy Audit

No new packages are installed in this phase. The extraction creates a new Python module (`app/services/recall.py`) using only the Python standard library (`dataclasses`, `asyncio`) and existing project dependencies. No `npm install` or `pip install` is required.

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The `/context` route has no existing external API callers that depend on the `context_files` dict shape in the response | Duplication section | If downstream callers (e.g., Discord bot) parse `context_files`, the response shape change would break them — add backward-compat alias |
| A2 | The warm search on empty content (`content=""`) in `/context` route is acceptable to degrade to no warm results | Common Pitfalls #8 | If the operator expects `/context` to return warm context, the route needs a `?query=` parameter |

**All other claims were verified by direct file read in this session.**

---

## Open Questions

1. **Persona path separation from hot-tier gather**
   - What we know: `"sentinel/persona.md"` is currently gathered inside `_append_hot_tier` alongside the 6 self_paths, but persona must NOT go into `RecalledContext.self_context`.
   - What's unclear: Whether `MessageProcessor.process()` should call `read_self_context("sentinel/persona.md")` as a separate await before calling `recall.assemble()`, or whether `Recall` could take an optional `include_persona=False` flag.
   - Recommendation: Separate await in `MessageProcessor.process()` — simplest, cleanest separation. Planner should document this split explicitly.

2. **Warm content formatting: stays in `MessageProcessor` or moves to `Recall`?**
   - What we know: `_format_search_results` currently lives in `MessageProcessor`. `RecalledContext.warm` carries `list[SearchResult]`.
   - What's unclear: Whether the "Relevant vault notes:" formatting belongs in Recall (as a utility) or in the processor (as presentation).
   - Recommendation: Keep in `MessageProcessor` — it formats for injection (presentation concern per D-04). `RecalledContext` carries typed data; formatting is the processor's responsibility.

---

## Sources

### Primary (HIGH confidence)
- `sentinel-core/app/services/message_processing.py` — direct file read; all inline constants, method signatures, and call order verified
- `sentinel-core/app/routes/status.py` — direct file read; `/context/{user_id}` duplication documented
- `sentinel-core/app/vault.py` — direct file read; Vault Protocol surface verified
- `sentinel-core/tests/fakes/vault.py` — direct file read; FakeVault construction API verified
- `docs/adr/0003-recall-module.md` — canonical design record; interface sketch verified
- `docs/adr/0002-vault-seam-location.md` — boundary constraints verified
- `sentinel-core/app/composition.py` — direct file read; DI wiring verified
- `sentinel-core/app/state.py` — direct file read; RouteContext fields verified
- `sentinel-core/tests/test_message_processor.py` — direct file read; kept-test surface verified
- `sentinel-core/tests/test_status.py` — direct file read; /context test assertions verified
- `sentinel-core/pyproject.toml` — direct file read; test framework config verified

### Secondary (MEDIUM confidence)
- `.planning/phases/39-extract-the-recall-module/39-CONTEXT.md` — locked decisions D-01..D-06
- `.planning/REQUIREMENTS.md` — MEM-01, MEM-02 requirements text

---

## Metadata

**Confidence breakdown:**
- Current assembly internals: HIGH — all constants, line numbers, and method bodies read directly from source
- Vault seam surface: HIGH — Protocol definition read directly from `app/vault.py`
- Test surface: HIGH — FakeVault and existing test files read directly
- DI wiring: HIGH — composition.py and state.py read directly
- Architectural patterns: HIGH — consistent with ADR-0003 interface sketch

**Research date:** 2026-06-11
**Valid until:** 2026-07-11 (stable codebase; re-verify if message_processing.py is modified before planning)
