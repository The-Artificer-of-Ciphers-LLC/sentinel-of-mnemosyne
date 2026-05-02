---
quick_id: 260502-1zv
slug: codebase-improvements-from-diagnose-find
date: 2026-05-02
status: planned
---

# Codebase Improvements from `/diagnose` Findings

## Description

Apply four codebase improvements identified during a `/diagnose` session investigating
a LiteLLM `BadRequestError: No models loaded` from the LM Studio embeddings flow. The
proximate cause was operator-side (no embedding model loaded in LM Studio), but the
diagnose surfaced four codebase deficiencies that, if addressed, make the next
occurrence diagnosable in seconds rather than via curl. Items: (1) typed
`EmbeddingModelUnavailable` exception, (2) startup probe + `/health` surfacing for
embedding model state, (3) config-driven `embedding_model` setting (eliminates two
hardcoded SPOT violations), (4) chat model default updated to `gemma-4-e4b-it-mlx`.

## Decisions (locked)

All four items below are LOCKED per the operator brief. The diagnose session
established the findings; this plan implements them. No re-litigation.

- D-01 — Add `EmbeddingModelUnavailable` typed exception in `app/clients/embeddings.py`,
  modeled on the `ContextLengthError` precedent (commit `9fe7c82`). Vendor exception
  translation lives in `app/clients/`.
- D-02 — Add embedding-model startup probe to `app/services/model_selector.py`; surface
  through `app.state.embedding_model_loaded` and `/health` response. Graceful degrade
  on probe failure (mirror `sentinel/persona.md` probe pattern from commit `27d5ee9`).
- D-03 — Single source of truth for embedding model id: `Settings.embedding_model` in
  `app/config.py`. Provider prefix (`openai/`) added at LiteLLM call site, not stored.
- D-04 — Chat model default changes from `"local-model"` to `"gemma-4-e4b-it-mlx"`.
  Operator pre-authorized lockstep test assertion updates per CLAUDE.md
  Test-Rewrite Ban (this is a config-default change, not a shipped-feature regression).

## Files modified

### Edit

- `sentinel-core/app/config.py` — add `embedding_model` field; change `model_name`
  default to `"gemma-4-e4b-it-mlx"`.
- `sentinel-core/app/clients/embeddings.py` — add `EmbeddingModelUnavailable` class;
  wrap `litellm.aembedding` call to translate "No models loaded" `BadRequestError`;
  source default model id from settings (lazy lookup, not import-time).
- `sentinel-core/app/services/model_selector.py` — add
  `probe_embedding_model_loaded(http_client, base_url, configured_model) -> bool`.
- `sentinel-core/app/services/vault_sweeper.py` — replace module-level
  `EMBEDDING_MODEL` constant with `settings.embedding_model` (or pass-through via
  embedder fn signature, depending on what minimizes diff).
- `sentinel-core/app/main.py` — call probe in lifespan; pin to
  `app.state.embedding_model_loaded`; log INFO/WARNING; extend `/health` endpoint
  with `embedding_model: "loaded" | "not_loaded"`; update `_embedder_fn` to pass
  `model=f"openai/{settings.embedding_model}"`.
- `.env.example` — add `EMBEDDING_MODEL=text-embedding-nomic-embed-text-v1.5`
  documentation; update `LITELLM_MODEL` / `MODEL_NAME` comment to reflect gemma
  default.
- `sentinel-core/tests/test_model_selector_discovery.py` and/or
  `sentinel-core/tests/test_model_registry.py` — lockstep update if they assert on
  the old `"local-model"` default (only update assertions affected by D-04;
  document in commit message).

### Create (if missing)

- `sentinel-core/tests/test_embeddings.py` — house tests for D-01 + D-03 embedding
  model behavior.

### Test additions (in addition to lockstep updates above)

- D-01: `test_no_models_loaded_raises_typed_error`,
  `test_other_bad_request_passes_through` (in `tests/test_embeddings.py`).
- D-03: `test_embedding_model_uses_settings` (in `tests/test_embeddings.py`).
- D-02: `test_probe_embedding_loaded_true_when_state_loaded`,
  `test_probe_embedding_loaded_false_when_state_not_loaded`,
  `test_probe_embedding_loaded_false_on_http_error`,
  `test_health_endpoint_reports_embedding_status` (location: matching existing
  `test_model_selector*.py` and `test_health*.py` test files; create alongside
  if no obvious home).

## Tasks

Four atomic commits in this exact order. Each task must leave the test suite green
at its boundary.

### Task 1 — D-04: chat model default → `gemma-4-e4b-it-mlx`

<files>sentinel-core/app/config.py, .env.example, sentinel-core/tests/test_model_selector_discovery.py (lockstep, if asserting on old default), sentinel-core/tests/test_model_registry.py (lockstep, if asserting on old default)</files>

<action>
Change `model_name: str = "local-model"` to `model_name: str = "gemma-4-e4b-it-mlx"` in
`app/config.py` `Settings`. Update `.env.example` comment block surrounding
`LITELLM_MODEL` / `MODEL_NAME` so the documented default reflects gemma. Run the
suite; if any test asserts on `"local-model"` as the default value, update those
assertions in lockstep (this is a config-default change, not a behavioral
regression — operator pre-authorized per CLAUDE.md). Do NOT change the
provider-prefix-adding helpers; they continue to add `openai/` at call sites.
Mention the lockstep test updates explicitly in the commit message body.

This is the smallest, most mechanical change — it ships first to clear the way.
</action>

<verify>
<automated>cd sentinel-core && PYTHONPATH=$(pwd)/../shared .venv/bin/pytest -q</automated>
</verify>

<done>
Default chat model is `gemma-4-e4b-it-mlx`; `.env.example` reflects new default;
all tests pass; commit message documents any lockstep test updates.
</done>

### Task 2 — D-03: config-driven `embedding_model`

<files>sentinel-core/app/config.py, sentinel-core/app/clients/embeddings.py, sentinel-core/app/services/vault_sweeper.py, sentinel-core/app/main.py, .env.example, sentinel-core/tests/test_embeddings.py</files>

<behavior>
- Test: when `settings.embedding_model = "test-embed-model"`, calling the embedder
  via `app.state` invokes `litellm.aembedding` with `model="openai/test-embed-model"`.
- Test: vault_sweeper persists `embedding_model` frontmatter using the configured
  setting value (not the old hardcoded constant).
</behavior>

<action>
1. `app/config.py` — add `embedding_model: str = "text-embedding-nomic-embed-text-v1.5"`
   to `Settings` (no `openai/` prefix; provider tag added at call sites).
2. `app/clients/embeddings.py` — keep `EMBEDDING_MODEL_DEFAULT` for back-compat but
   source from settings via a helper function (lazy, not import-time, to avoid
   import-order tangles). Callers that pass `model=` explicitly continue to win.
3. `app/services/vault_sweeper.py` — remove the module-level
   `EMBEDDING_MODEL = "text-embedding-nomic-embed-text-v1.5"` constant (lines ~56).
   Replace usages with `settings.embedding_model` looked up at use site, OR plumb
   through the embedder function signature — pick whichever minimizes diff and
   keeps the existing frontmatter write semantics intact. The frontmatter
   `embedding_model` field must continue to record the configured id.
4. `app/main.py` `_embedder_fn` — pass `model=f"openai/{settings.embedding_model}"`,
   mirroring the existing `api_base` `/v1` suffix logic. The `openai/` prefix is
   added here, not stored in settings.
5. `.env.example` — add `EMBEDDING_MODEL=text-embedding-nomic-embed-text-v1.5`
   with a one-line comment explaining it's the LM Studio embedding model id
   (no provider prefix).
6. Add `test_embedding_model_uses_settings` to `sentinel-core/tests/test_embeddings.py`
   (create the file if it doesn't exist). Set `settings.embedding_model =
   "test-embed-model"`, exercise the embedder function, assert `litellm.aembedding`
   was called with `model="openai/test-embed-model"`. Behavioral test — call the
   function under test, assert on observable call shape.
7. Verify `rg "EMBEDDING_MODEL\s*=" sentinel-core/app/` returns 0 matches after
   this commit (consolidated into settings).
</action>

<verify>
<automated>cd sentinel-core && PYTHONPATH=$(pwd)/../shared .venv/bin/pytest -q && rg "EMBEDDING_MODEL\s*=" sentinel-core/app/ ; test $? -eq 1</automated>
</verify>

<done>
Single source of truth: `Settings.embedding_model`. No hardcoded embedding model
strings in `app/`. New `test_embedding_model_uses_settings` passes. All other
tests still pass. `.env.example` documents the var.
</done>

### Task 3 — D-01: typed `EmbeddingModelUnavailable` exception

<files>sentinel-core/app/clients/embeddings.py, sentinel-core/tests/test_embeddings.py</files>

<behavior>
- Test: `litellm.aembedding` raises `litellm.BadRequestError("No models loaded.
  Please load a model.")` → `embed_texts()` raises `EmbeddingModelUnavailable`
  whose message contains the configured model id.
- Test: `litellm.aembedding` raises a different `BadRequestError` (e.g. malformed
  request) → that exception propagates unwrapped.
</behavior>

<action>
1. Add `class EmbeddingModelUnavailable(Exception): pass` to
   `app/clients/embeddings.py` (top-level, near other module exception types
   if any).
2. In `embed_texts()`, wrap the `litellm.aembedding` call with
   `try/except litellm.BadRequestError as exc`. Sniff `str(exc)` for the literal
   substring `"No models loaded"` (case-insensitive: lower-case both sides). If
   matched, raise `EmbeddingModelUnavailable(f"No embedding model loaded on
   LM Studio. Configured: {model}. Load via `lms load {model}` or LM Studio UI.")`
   `from exc`. If not matched, `raise` (re-raise original unchanged).
3. Pattern matches `ContextLengthError` precedent in commit `9fe7c82` — vendor
   SDK import stays in `clients/`; vendor exception translation happens here.
4. Add two tests to `tests/test_embeddings.py`:
   - `test_no_models_loaded_raises_typed_error` — patch `litellm.aembedding` to
     raise `litellm.BadRequestError("No models loaded. Please load a model.")`.
     Call `embed_texts(["hello"], model="some-model-id")`. Assert
     `EmbeddingModelUnavailable` raised; assert `"some-model-id"` in
     `str(exc.value)`.
   - `test_other_bad_request_passes_through` — patch to raise
     `litellm.BadRequestError("malformed request")`. Assert that exact
     `BadRequestError` propagates (not wrapped).
   Both tests call `embed_texts()` directly and assert on observable raised
   exception type + message substring (behavioral-test compliant).
</action>

<verify>
<automated>cd sentinel-core && PYTHONPATH=$(pwd)/../shared .venv/bin/pytest -q tests/test_embeddings.py</automated>
</verify>

<done>
`EmbeddingModelUnavailable` exists; `embed_texts()` translates the
"No models loaded" `BadRequestError`; other `BadRequestError`s pass through;
two new tests pass; full suite green.
</done>

### Task 4 — D-02: startup probe + `/health` extension

<files>sentinel-core/app/services/model_selector.py, sentinel-core/app/main.py, sentinel-core/tests/ (new probe + health tests in matching existing test files)</files>

<behavior>
- Test: probe returns True iff `GET {base_url}/api/v0/models` response contains an
  entry with `state == "loaded"` AND `type == "embeddings"` AND `id == configured`
  (after stripping any `openai/` prefix).
- Test: probe returns False when state is `"not-loaded"`.
- Test: probe returns False on HTTP error (graceful degrade — never raises).
- Test: `GET /health` response includes `embedding_model: "loaded" | "not_loaded"`.
</behavior>

<action>
1. Add `probe_embedding_model_loaded(http_client, lmstudio_base_url,
   configured_embedding_model) -> bool` to `app/services/model_selector.py`. It:
   - Strips any leading `openai/` from `configured_embedding_model` for the
     comparison.
   - Issues `GET {base_url}/api/v0/models`.
   - Walks `response.json()["data"]`. Returns True if any entry has
     `state == "loaded"` AND `type == "embeddings"` AND `id == stripped_id`.
   - Catches all `httpx` / `JSONDecodeError` / `KeyError` exceptions and
     returns False (graceful degrade — never fails startup over a probe).
2. In `app/main.py` lifespan, after the existing model registry/discovery block,
   call the probe with the lifespan's existing http client + `settings.lmstudio_base_url`
   (or whichever attribute holds the LM Studio URL — read the file to confirm) +
   `settings.embedding_model`. Pin result to `app.state.embedding_model_loaded: bool`.
   Log:
   - `logger.info("Embedding model `%s` loaded ✓", settings.embedding_model)` if True.
   - `logger.warning("Embedding model `%s` NOT loaded on LM Studio — vault sweeper / "
     "note classifier will fail until you `lms load %s`.", settings.embedding_model,
     settings.embedding_model)` if False.
3. Extend `/health` endpoint (currently returns `{status, obsidian}`, around
   `app/main.py:271`). Re-run the probe on each `/health` call (one HTTP GET, parallel
   with the obsidian check via `asyncio.gather` if the existing pattern uses one;
   otherwise sequential is fine — match the existing style). Add field
   `"embedding_model": "loaded" if probe_result else "not_loaded"`.
4. Tests:
   - `test_probe_embedding_loaded_true_when_state_loaded` — mock httpx response
     with the configured embedding model entry having `state: "loaded"`,
     `type: "embeddings"`. Assert probe returns True.
   - `test_probe_embedding_loaded_false_when_state_not_loaded` — same fixture but
     `state: "not-loaded"`. Assert probe returns False.
   - `test_probe_embedding_loaded_false_on_http_error` — mock httpx client to
     raise `httpx.RequestError`. Assert probe returns False (does not raise).
   - `test_health_endpoint_reports_embedding_status` — exercise `GET /health`
     against the FastAPI test client with mocked obsidian + mocked embedding
     probe. Assert response JSON contains `"embedding_model"` key with value
     `"loaded"` or `"not_loaded"`. Assert backwards compat: `status` and
     `obsidian` fields still present.
   Place tests in matching existing test files (`test_model_selector*.py` for the
   probe; `test_health*.py` or equivalent for the endpoint test). If no obvious
   home exists, create `tests/test_embedding_probe.py`.
5. Graceful-degrade rule: probe failure must not crash startup or `/health`. If
   LM Studio is unreachable, the probe returns False and the existing
   error-handling for the obsidian check is mirrored.
</action>

<verify>
<automated>cd sentinel-core && PYTHONPATH=$(pwd)/../shared .venv/bin/pytest -q && cd sentinel-core && uvx ruff check .</automated>
</verify>

<done>
`probe_embedding_model_loaded` exists in `model_selector.py` with graceful-degrade
semantics; lifespan calls it and logs INFO/WARNING; `app.state.embedding_model_loaded`
is set; `/health` returns the new `embedding_model` field; four new tests pass;
full suite green; ruff clean.
</done>

## Verification

- `cd sentinel-core && PYTHONPATH=$(pwd)/../shared .venv/bin/pytest -q` — all pass
  (231 baseline + N new tests; 7 new tests expected: 1 from Task 2, 2 from Task 3,
  4 from Task 4 → ~238 total; confirm exact count after Task 4 lands).
- `cd sentinel-core && uvx ruff check .` — 0 errors.
- `rg "EMBEDDING_MODEL\s*=" sentinel-core/app/` — 0 matches (D-03 consolidation
  verified).
- Manual smoke: hit `GET /health` against running app, observe new
  `embedding_model` field reports `loaded` or `not_loaded` accurately.
- Manual smoke: with no embedding model loaded in LM Studio, trigger the vault
  sweeper or note classifier path, observe `EmbeddingModelUnavailable` raised
  with the configured model id in the message (instead of opaque
  `BadRequestError: No models loaded`).

## Guardrail call-outs

- **Spec-Conflict Guardrail.** Task 4 extends `/health` response by adding a
  *new* field (`embedding_model`); does not change existing `status` /
  `obsidian` fields. Backwards compatible. Task 1 (D-04) changes a config
  default; not a shipped-feature regression because operators set `MODEL_NAME`
  explicitly in production.
- **Test-Rewrite Ban.** Task 1 may require lockstep updates to discovery /
  registry tests if they assert on the old `"local-model"` default. Operator
  pre-authorized in-turn per the brief; document the lockstep update in the
  commit message body.
- **Behavioral-Test-Only Rule.** All new tests call the function under test
  directly and assert on observable results (raised exception type/message,
  call-shape via mock, response JSON shape). No source-grep, no `assert True`,
  no echo-chamber tests.
- **AI Deferral Ban.** Complete all four items. No TODOs, no skipped items,
  no "for future work".
- **Git workflow.** Commit directly to `main`; no feature branches, no PRs;
  one atomic commit per task; commit messages reference the diagnose finding
  and item id (D-01 / D-02 / D-03 / D-04).
