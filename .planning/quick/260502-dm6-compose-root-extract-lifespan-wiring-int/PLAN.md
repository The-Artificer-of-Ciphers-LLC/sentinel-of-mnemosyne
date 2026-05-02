---
quick_id: 260502-dm6
slug: compose-root-extract-lifespan-wiring-int
date: 2026-05-02
status: planned
---

# Compose Root: Extract Lifespan Wiring into `app/composition.py`

## Description

Sentinel Core's `app/main.py:lifespan()` carries ~220 LOC of construction logic (model discovery, provider selection, vault probe, security stack, message processor, modules, embedding closure, classifier closure). It is untestable in isolation: tests can only exercise the wired-up app via `app.state` mutation. This quick task extracts that wiring into a stateless compose root at `app/composition.py`, replaces the two closures (`_embedder_fn`, `_secondary_classifier`) with proper module dependencies, and produces a flat `AppGraph` dataclass that tests can construct with fakes via `build_application(settings, http_client, *, vault=..., ai_provider=..., ...)` (explicit kwargs — no `**fakes` bag). Lifespan shrinks to ~30 LOC; existing call sites continue to read `app.state.X` (Q4 back-compat), so no test or route migration is required outside the two constructor-signature changes (Q3(b)).

This is round 3 of `/improve-codebase-architecture`. Decisions are LOCKED — do not redesign during execution.

## Decisions (locked)

| Q | Pick | Meaning |
|---|------|---------|
| Q1 | (a) Two free functions | `build_provider_router(settings, http_client)` and `build_application(settings, http_client, *, vault=None, ai_provider=None, …)`. Stateless. Explicit kwargs (W1). |
| Q2 | (a) Flat AppGraph | One frozen dataclass, ~15 fields, no nested sub-graphs. |
| Q3 | (b) Push deps into consumers | `OutputScanner(ai_provider, classifier_system=...)` not `(secondary_classifier=callable)`. Embedding closure becomes `Embeddings` adapter class. |
| Q4 | (a) Pin individual fields | `app.state.X = graph.X` for each field. Routes/tests untouched. |

### Spec-Conflict surface (CRITICAL — preserve byte-identical)

**SEC-02 OutputScanner fail-open contract** must be preserved end-to-end:

- Regex match → secondary classifier called
- Classifier returns "LEAK" → block (False, reason)
- Classifier returns "SAFE" → allow (True, None)
- Classifier `asyncio.wait_for` TimeoutError → fail open (True, None) + warn
- Classifier raises any exception → fail open (True, None) + warn
- No classifier configured → fail open (True, None) + warn

Under Q3(b), the constructor signature changes but observable behavior is byte-identical. The `asyncio.wait_for(self._classify(...), timeout=SECONDARY_TIMEOUT_S)` wrapper in `scan()` stays unchanged. The fix-rigor test from commit `9187cfe` (patches `SECONDARY_TIMEOUT_S` to 0.01, uses slow classifier) MUST pass after the migration with `mock_ai_provider.complete = slow_async_fn`.

**ADR-0001 startup contract** unaffected — vault-up + persona 404 still raises `RuntimeError` from lifespan; `VaultUnreachableError` still tolerated. The probe stays in `lifespan` (it's a startup failure decision, not graph construction).

**ADR-0002 Vault seam location** unaffected.

**Test-Rewrite Ban — operator consent recorded in this turn (Q3(b)).** Tests in `tests/test_output_scanner.py` migrate constructor-call shape only; assertion semantics preserved.

## Files modified

### Create
- `sentinel-core/app/composition.py` — `AppGraph` dataclass, `build_provider_router`, `build_application`
- `sentinel-core/tests/test_composition.py` — behavioral tests for the new seam

### Edit
- `sentinel-core/app/main.py` — lifespan reduced from ~220 LOC to ~30 LOC; persona probe stays; **`_ORIGINAL_PREFIXES` at line 52 deleted entirely** (no replacement import — call site at line 85 moves into `composition.py`)
- `sentinel-core/app/services/output_scanner.py` — constructor signature: `(ai_provider: ProviderRouter | None = None, classifier_system: str = _CLASSIFIER_SYSTEM)`; `_classify` builds messages internally; `SecondaryClassifier` type alias deleted; unused `Callable, Awaitable` imports deleted
- `sentinel-core/app/services/model_selector.py` — house the canonical `_ORIGINAL_PREFIXES` alongside `_LITELLM_PROVIDER_PREFIXES`
- `sentinel-core/app/services/model_registry.py` — replace local `_ORIGINAL_PREFIXES` (line 31) with `from app.services.model_selector import _ORIGINAL_PREFIXES`
- `sentinel-core/app/clients/embeddings.py` — add `class Embeddings` adapter
- `sentinel-core/app/services/vault_sweeper.py` — accept embedder via `Embeddings` (or its bound `.embed`); whichever is the smaller diff for `run_sweep`'s call sites
- `sentinel-core/tests/test_output_scanner.py` — constructor-call shape migration only at the 8 sites enumerated in Task 3; assertions preserved
- Any other test that constructs `OutputScanner` or supplies `note_embedder_fn` directly — update test-double shape in lockstep with the constructor change in the same commit

### Delete
- No files deleted.

## Tasks

### Task 1 — Create `app/composition.py` with frozen `AppGraph` dataclass

**Files:** `sentinel-core/app/composition.py` (new)

**Action:** Create the new module containing only:
- Imports for the typed fields (`Settings`, `httpx.AsyncClient`, `ProviderRouter`, `Vault`, `InjectionFilter`, `OutputScanner`, `MessageProcessor`, `Embeddings` — note: `Embeddings` does not yet exist; either forward-reference with `TYPE_CHECKING` or temporarily type as `object` and tighten in Task 4. Pick the path that doesn't break import.)
- `@dataclass(frozen=True)` definition with the 15 fields specified in the brief: `settings`, `http_client`, `model_registry`, `context_window`, `lmstudio_stop_sequences`, `ai_provider`, `ai_provider_name`, `vault`, `embedding_model_loaded`, `injection_filter`, `output_scanner`, `message_processor`, `module_registry`, `embeddings`, `note_classifier_fn`

No `build_*` functions yet. No call sites yet. Module imports cleanly. Zero behavior change.

**Verify:**
- `cd sentinel-core && .venv/bin/python -c "from app.composition import AppGraph; print(AppGraph.__dataclass_fields__.keys())"` lists all 15 fields
- `cd sentinel-core && PYTHONPATH=$(pwd)/../shared .venv/bin/pytest -q` passes (no regressions; new module is unused)
- `cd sentinel-core && uvx ruff check app/composition.py` → 0 errors

**Done:** New file committed; tree green; `AppGraph` importable.

---

### Task 2 — Extract `build_provider_router(settings, http_client) -> ProviderRouter`

**Files:**
- `sentinel-core/app/composition.py` (edit)
- `sentinel-core/app/main.py` (edit — delete `_ORIGINAL_PREFIXES` entirely from line 52)
- `sentinel-core/app/services/model_selector.py` (edit — add canonical `_ORIGINAL_PREFIXES`)
- `sentinel-core/app/services/model_registry.py` (edit — import the canonical version)

**Action:**
1. In `model_selector.py`, add `_ORIGINAL_PREFIXES` (the 3-prefix tuple currently duplicated). Place it alongside `_LITELLM_PROVIDER_PREFIXES`. Export it. This becomes the canonical home.
2. In `model_registry.py:31`, replace the local `_ORIGINAL_PREFIXES` definition with `from app.services.model_selector import _ORIGINAL_PREFIXES`.
3. In `main.py`, **delete** `_ORIGINAL_PREFIXES` from line 52 entirely. Do **not** replace with an import. The line-85 call site moves into `composition.py` as part of step 4 below, so `main.py` retains zero references to `_ORIGINAL_PREFIXES`.
4. Move lifespan lines ~78-177 (model discovery + context-window lookup + stop-sequence profile + provider-map construction + fallback selection) into a new `async def build_provider_router(settings: Settings, http_client: httpx.AsyncClient) -> ProviderRouter` in `composition.py`. The relocated code uses `from app.services.model_selector import _ORIGINAL_PREFIXES`.
5. The function returns a fully constructed `ProviderRouter` with primary + fallback wired. Lifespan now calls `provider_router = await build_provider_router(settings, http_client)` and continues to pin `app.state.ai_provider = provider_router` (and `ai_provider_name`, `model_registry`, `context_window`, `lmstudio_stop_sequences` — fields not yet on the graph; lifespan keeps direct pinning until Task 5).

**Verify:**
- `cd sentinel-core && PYTHONPATH=$(pwd)/../shared .venv/bin/pytest -q` passes
- `rg -n "_ORIGINAL_PREFIXES\s*=" sentinel-core/app/` → exactly 1 definition (in `model_selector.py`)
- `rg -n "_ORIGINAL_PREFIXES" sentinel-core/app/main.py` → 0 matches (deleted entirely)
- `cd sentinel-core && uvx ruff check .` → 0 errors

**Done:** Provider router construction lives in `composition.py`; lifespan delegates; `_ORIGINAL_PREFIXES` consolidated in `model_selector.py`; `main.py` no longer references it; tree green.

---

### Task 3 — Refactor `OutputScanner` constructor and migrate tests in lockstep

**Files:**
- `sentinel-core/app/services/output_scanner.py` (edit)
- `sentinel-core/app/main.py` (edit — drop the `_secondary_classifier` closure)
- `sentinel-core/tests/test_output_scanner.py` (edit — 8 constructor-call sites)
- Any other test file that constructs `OutputScanner(...)` directly (grep first; update in same commit)

**Baseline (verified in source as of 2026-05-02):**
- Current signature: `def __init__(self, classifier: SecondaryClassifier | None)` — positional, parameter named `classifier` (not `secondary_classifier`).
- Internal attribute: `self._classifier`.
- `SecondaryClassifier` is a type alias defined at the top of `app/services/output_scanner.py` (imports `Callable, Awaitable` from `collections.abc` to support it).
- The closure `_secondary_classifier` exists in `main.py` as the variable holding the constructed classifier callable that is then passed positionally to `OutputScanner(...)`.
- Test sites in `tests/test_output_scanner.py` constructing `OutputScanner`: lines **16, 40, 49, 85, 93, 100, 116, 138** (8 sites total). Most pass a callback fixture; line 100 (`test_no_classifier_degrades_gracefully`) passes `None`.

**Action:**
1. Change `OutputScanner.__init__` signature to `(self, ai_provider: ProviderRouter | None = None, classifier_system: str = _CLASSIFIER_SYSTEM)`. Store `self._ai_provider` and `self._classifier_system`. **Delete** the `SecondaryClassifier` type alias and the now-unused `from collections.abc import Callable, Awaitable` import in the same edit (otherwise ruff F401 fails the verify gate).
2. Default-None choice (W1 sub-decision recorded): the new constructor accepts `ai_provider: ProviderRouter | None = None` and falls open when `None`. This preserves the existing fail-open posture for "infrastructure not present" and keeps `test_no_classifier_degrades_gracefully` (line 100) intact with the same contract — only the parameter name changes (`None` → `ai_provider=None`).
3. Replace the `_classify` body with the spec from the brief:
   ```python
   async def _classify(self, response, fired_patterns):
       if self._ai_provider is None:
           # No classifier configured → fail open path handled in scan() via raise/return.
           # Preserve current "no classifier configured" semantics byte-identical.
           ...  # match existing behavior exactly
       excerpt = self._extract_excerpt(response, fired_patterns)
       messages = [
           {"role": "system", "content": self._classifier_system},
           {"role": "user", "content": f"Triggered patterns: {fired_patterns}\n\nText excerpt:\n{excerpt}"},
       ]
       return await self._ai_provider.complete(messages)
   ```
4. The `asyncio.wait_for(self._classify(...), timeout=SECONDARY_TIMEOUT_S)` wrapper in `scan()` stays UNCHANGED. Fail-open on TimeoutError, fail-open on Exception, fail-open on no-classifier — all preserved byte-identical.
5. In `main.py` lifespan: delete the `_secondary_classifier` closure entirely; construct `OutputScanner(ai_provider=app.state.ai_provider)` directly.
6. In `tests/test_output_scanner.py`, migrate exactly these 8 call sites: **lines 16, 40, 49, 85, 93, 100, 116, 138**. Each `OutputScanner(callback_fixture)` becomes `OutputScanner(ai_provider=mock_ai_provider)` where:
   ```python
   mock_ai_provider = AsyncMock()
   mock_ai_provider.complete = AsyncMock(return_value="LEAK")  # or "SAFE"
   ```
   For the timeout test, `mock_ai_provider.complete = slow_async_fn`. For line 100 (`test_no_classifier_degrades_gracefully`), `OutputScanner(None)` becomes `OutputScanner(ai_provider=None)` — contract preserved, behavior identical (fail-open). Existing assertions preserved verbatim across all 8 sites.
7. The fix-rigor timeout test from commit `9187cfe` migrates the same way — slow path becomes `mock_ai_provider.complete = slow_async_fn`.
8. Grep for any remaining `secondary_classifier` or `SecondaryClassifier` references and update or remove. Document in commit body: "Test-Rewrite Ban — operator consent recorded in plan turn 2026-05-02 (Q3(b)). Constructor signature change on shipped SEC-02 feature; assertion semantics preserved end-to-end; fail-open contract byte-identical."

**Verify:**
- `cd sentinel-core && PYTHONPATH=$(pwd)/../shared .venv/bin/pytest -q tests/test_output_scanner.py` passes (including the 9187cfe timeout test and the line-100 `None` test)
- Full suite: `cd sentinel-core && PYTHONPATH=$(pwd)/../shared .venv/bin/pytest -q` passes
- `rg -n "SecondaryClassifier|secondary_classifier" sentinel-core/` → 0 matches (after rename + closure deletion)
- `rg -n "from collections.abc import.*Callable.*Awaitable" sentinel-core/app/services/output_scanner.py` → 0 matches (unused import deleted)
- `cd sentinel-core && uvx ruff check .` → 0 errors

**Done:** OutputScanner takes `ai_provider`; tests migrated in lockstep at all 8 sites; SEC-02 fail-open contract intact; type alias and unused imports cleaned up; tree green.

---

### Task 4 — Replace `_embedder_fn` closure with `Embeddings` adapter class

**Files:**
- `sentinel-core/app/clients/embeddings.py` (edit — add class)
- `sentinel-core/app/main.py` (edit — drop closure)
- `sentinel-core/app/services/vault_sweeper.py` (edit — accept new shape if and only if smaller diff than bound-method pin; see step 3)
- Any test that supplies `note_embedder_fn` (edit in lockstep — see "Verified compatible" subsection below)

**Action:**
1. In `app/clients/embeddings.py`, add the `Embeddings` class with the shape from the brief: `__init__(http_client, base_url, model)`, `async def embed(texts)` that performs the `/v1` suffix normalization and calls the existing `embed_texts` helper. Keep the existing `embed_texts` function — `Embeddings.embed` is a thin wrapper.
2. In lifespan, replace the `_embedder_fn` closure with:
   ```python
   embeddings = Embeddings(http_client, settings.lmstudio_base_url or DEFAULT_BASE_URL, settings.embedding_model)
   app.state.note_embedder_fn = embeddings.embed
   ```
   (Pinning `embeddings.embed` keeps the call sites in `vault_sweeper` and the note route byte-identical: same `await fn(texts)` shape.)
3. If `vault_sweeper.run_sweep` accepts `note_embedder_fn` as a callable, no signature change is needed — bound method satisfies the contract. If a structural change to `run_sweep`'s signature would be smaller, take that path instead. Decide based on the actual call-site count: pick the smaller diff.
4. Tests that previously passed `note_embedder_fn=AsyncMock(...)` continue to pass an async callable (either the AsyncMock or a `FakeEmbeddings` 3-line class with `.embed`). Lockstep update — same commit.
5. Tighten `composition.py` `AppGraph.embeddings` type annotation from `object`/forward-ref to `Embeddings` now that it exists.

**Verified compatible (no edit needed):**

The bound-method pin (`app.state.note_embedder_fn = graph.embeddings.embed`) preserves the existing `await fn(texts)` call shape. The following sites were verified during plan-checking and require **zero source changes**:

- **Production:** `app/routes/note.py:284` reads `app.state.note_embedder_fn`, calls `await embedder(texts)`. Bound method satisfies the callable contract. No edit.
- **Tests:** `tests/test_note_routes.py:268` and `tests/test_note_routes.py:289` assign `app.state.note_embedder_fn` to async callables. No edit.

Listed here so a future reader doesn't re-discover the analysis.

**Verify:**
- `cd sentinel-core && PYTHONPATH=$(pwd)/../shared .venv/bin/pytest -q` passes
- `rg -n "_embedder_fn" sentinel-core/app/main.py` → 0 matches (closure gone)
- `rg -n "class Embeddings" sentinel-core/app/clients/embeddings.py` → 1 match
- `cd sentinel-core && uvx ruff check .` → 0 errors

**Done:** Closure replaced by `Embeddings`; vault_sweeper unchanged in semantics; note route + note-route tests verified compatible without edit; tree green.

---

### Task 5 — Add `build_application` and migrate lifespan to use it

**Files:**
- `sentinel-core/app/composition.py` (edit — add `build_application`)
- `sentinel-core/app/main.py` (edit — lifespan shrinks to ~30 LOC)

**Action:**
1. Add `build_application` to `composition.py` with the **explicit-kwargs** signature (W1 decision):
   ```python
   async def build_application(
       settings: Settings,
       http_client: httpx.AsyncClient,
       *,
       vault: Vault | None = None,
       ai_provider: ProviderRouter | None = None,
       injection_filter: InjectionFilter | None = None,
       output_scanner: OutputScanner | None = None,
       embeddings: Embeddings | None = None,
       message_processor: MessageProcessor | None = None,
   ) -> AppGraph:
       """Build the full application graph.

       For each keyword-only dependency: if None (default), construct the production
       implementation; otherwise use the supplied fake. This is the test seam — call
       sites pass explicit kwargs (e.g. `build_application(settings, http_client, vault=FakeVault())`).
       The signature intentionally avoids a `**fakes` bag so that typos like
       `build_application(..., vualt=...)` are caught at type-check / runtime rather
       than silently swallowed.
       """
       ai_provider = ai_provider or await build_provider_router(settings, http_client)
       vault = vault or ObsidianVault(http_client, settings.obsidian_base_url, settings.obsidian_api_key)
       injection_filter = injection_filter or InjectionFilter()
       output_scanner = output_scanner or OutputScanner(ai_provider=ai_provider)
       embeddings = embeddings or Embeddings(http_client, settings.lmstudio_base_url or DEFAULT, settings.embedding_model)
       message_processor = message_processor or MessageProcessor(...)
       # Non-overridable in this iteration (build defaults; can be promoted to kwargs later if needed):
       note_classifier_fn = default_note_classifier
       module_registry = load_module_registry(...)
       embedding_model_loaded = probe_embedding_model(...)
       # context_window, lmstudio_stop_sequences, ai_provider_name, model_registry come from
       # build_provider_router result; expose via the result tuple/dataclass.
       return AppGraph(settings=settings, http_client=http_client, ...)
   ```
   (Implementer note: if `build_provider_router` only returns `ProviderRouter`, return a small NamedTuple/dataclass from it that includes `model_registry`, `context_window`, `lmstudio_stop_sequences`, `ai_provider_name` — or call separate helpers. Pick whichever produces the cleanest seam. The constraint: `build_application` must produce a fully populated `AppGraph` with all 15 fields.)

2. Lifespan becomes ~30 LOC. **Persona probe stays in lifespan after `build_application` returns** (ADR-0001 contract analysis unchanged):
   ```python
   @asynccontextmanager
   async def lifespan(app: FastAPI):
       settings = get_settings()
       http_client = httpx.AsyncClient(...)
       graph = await build_application(settings, http_client)
       # Pin all 15 fields onto app.state for back-compat (Q4(a))
       app.state.settings = graph.settings
       app.state.ai_provider = graph.ai_provider
       app.state.vault = graph.vault
       app.state.injection_filter = graph.injection_filter
       app.state.output_scanner = graph.output_scanner
       app.state.message_processor = graph.message_processor
       app.state.module_registry = graph.module_registry
       app.state.note_embedder_fn = graph.embeddings.embed
       app.state.note_classifier_fn = graph.note_classifier_fn
       app.state.model_registry = graph.model_registry
       app.state.context_window = graph.context_window
       app.state.lmstudio_stop_sequences = graph.lmstudio_stop_sequences
       app.state.ai_provider_name = graph.ai_provider_name
       app.state.embedding_model_loaded = graph.embedding_model_loaded
       # Persona probe stays in lifespan — startup-failure decision, not construction
       try:
           await graph.vault.read_persona()
       except VaultUnreachableError:
           logger.warning(...)
       except FileNotFoundError:
           raise RuntimeError("vault up but persona missing — aborting startup") from None
       try:
           yield
       finally:
           await http_client.aclose()
   ```

3. ADR-0001 startup contract preserved: vault-up + 404 → `RuntimeError`; `VaultUnreachableError` tolerated.

**Verify:**
- `cd sentinel-core && PYTHONPATH=$(pwd)/../shared .venv/bin/pytest -q` passes (full app boots through `build_application`)
- `wc -l sentinel-core/app/main.py` → roughly half of the 344 baseline (lifespan went from 220 → ~30 LOC; total file ~150-180 LOC)
- `cd sentinel-core && uvx ruff check .` → 0 errors
- Boot the app locally if a smoke target exists; otherwise the test suite covers it

**Done:** Lifespan delegates entirely to `build_application` (explicit-kwargs signature); all `app.state` fields pinned for back-compat; ADR-0001 probe semantics intact.

---

### Task 6 — Add behavioral tests proving the new seam

**Files:** `sentinel-core/tests/test_composition.py` (new)

**Action:** Write at least 3 behavioral tests that exercise `build_application` / `build_provider_router` directly. **Use explicit kwargs** (e.g. `build_application(settings, http_client, vault=FakeVault())`) — **not** the unsafe `**fakes` form. All tests CALL the function under test and assert observable graph state — no source-grep, no tautologies, no mock-only assertions (Behavioral-Test-Only Rule).

Tests:
1. `test_build_application_uses_provided_vault_fake` — call `build_application(settings, http_client, vault=fake_vault)`; assert `graph.vault is fake_vault`. Use a tiny in-memory `FakeVault` implementing the `Vault` protocol.
2. `test_build_application_constructs_default_provider_when_not_overridden` — call with no `ai_provider` kwarg; assert `isinstance(graph.ai_provider, ProviderRouter)` and `graph.ai_provider_name` matches `settings.ai_provider`. Use a fake `httpx.AsyncClient` (e.g. `httpx.MockTransport`) so model discovery returns deterministic responses.
3. `test_build_provider_router_picks_primary_from_settings` — drive `build_provider_router` with two distinct settings configurations; assert the resulting `ProviderRouter.primary` (or equivalent observable attribute) reflects the configured backend.

No existing test files migrate to the new seam in this commit — that's a separate follow-up. The point is to PROVE the seam works end-to-end via observable behavior.

**Verify:**
- `cd sentinel-core && PYTHONPATH=$(pwd)/../shared .venv/bin/pytest -q tests/test_composition.py` → 3+ tests pass
- Full suite: `cd sentinel-core && PYTHONPATH=$(pwd)/../shared .venv/bin/pytest -q` → 250 baseline + 3 new = ~253 (or higher if other tasks added incidental coverage)
- `cd sentinel-core && uvx ruff check tests/test_composition.py` → 0 errors

**Done:** New test file proves `build_application` + `build_provider_router` are independently testable with fakes via explicit kwargs; tree green.

---

## Verification (overall)

Run after Task 6:

- `cd sentinel-core && PYTHONPATH=$(pwd)/../shared .venv/bin/pytest -q` → all pass (~253-255 tests; 250 baseline + new composition tests; SEC-02 fix-rigor test from 9187cfe still passing)
- `cd sentinel-core && uvx ruff check .` → 0 errors
- `rg -n "_ORIGINAL_PREFIXES\s*=" sentinel-core/app/` → exactly 1 definition site (`model_selector.py`)
- `rg -n "_ORIGINAL_PREFIXES" sentinel-core/app/main.py` → 0 matches (deleted entirely, not re-imported)
- `rg -n "SecondaryClassifier|secondary_classifier" sentinel-core/` → 0 matches
- `rg -n "_embedder_fn|_secondary_classifier" sentinel-core/app/main.py` → 0 matches
- `wc -l sentinel-core/app/main.py` → roughly half of 344 baseline
- 6 atomic commits on `main`, each with green pytest at HEAD

## Guardrail call-outs

- **Spec-Conflict Guardrail.** SEC-02 OutputScanner fail-open contract preserved byte-identical end-to-end. ADR-0001 startup contract (persona probe) preserved — probe stays in lifespan because it's a startup-failure decision, not graph construction. ADR-0002 vault seam location unaffected.
- **Test-Rewrite Ban.** Task 3 changes the `OutputScanner` constructor signature on a shipped feature. Operator consent recorded in this plan turn (Q3(b)). All test assertions preserved verbatim across the 8 enumerated sites; only constructor-call shape changes (callback fixture → `mock_ai_provider` with `.complete` AsyncMock; `None` → `ai_provider=None`). Document explicitly in Task 3's commit body.
- **Behavioral-Test-Only Rule.** Task 6 tests must call `build_application` / `build_provider_router` and assert observable graph state. No source-grep tests. No `assert True`. No mock-call-shape-only assertions. Tests use explicit kwargs (W1) — not `**fakes`.
- **AI Deferral Ban.** Complete all 6 tasks. No partial migration. No `# TODO` left in `composition.py` or `main.py`.
- **Atomic green commits.** Each task = one commit. Each commit must leave `pytest -q` passing. Tasks 3 and 4 update tests in the same commit as the constructor/closure change so the tree stays green.
- **Git workflow.** Commit directly to `main`. No feature branch. No PR.
