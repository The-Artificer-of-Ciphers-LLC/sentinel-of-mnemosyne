---
quick_id: 260502-g8c
slug: pure-helper-extraction-cross-package-spo
date: 2026-05-02
status: planned
revision: 1
---

# Pure-Helper Extraction + Cross-Package SPOT

Round-4 architecture deepening from `/improve-codebase-architecture`. Closes the cross-package SPOT violation between sentinel-core and pathfinder (same `cosine_similarity` name, **different signatures**). Extracts pure utility math out of `services/vault_sweeper.py` and consolidates ALL frontmatter/codec copies repo-wide.

## Locked decisions

| Q | Pick | Meaning |
|---|------|---------|
| Q1 | (a) Overloaded cosine | One `cosine_similarity(a, b)` — auto-detects 1D vs 2D via `np.atleast_2d`. Returns float if both 1D, ndarray otherwise. NumPy-idiomatic. |
| Q2 | App top-level | `app/markdown_frontmatter.py` (sentinel-core only — pathfinder doesn't parse markdown frontmatter). Matches `vault.py` / `composition.py` placement. |
| Q3 | (a) Full pathfinder migration | Pathfinder's codecs in BOTH `app/rules.py` AND `app/routes/rule.py` migrate to imports. Calibration scripts + `tests/test_rules.py` update in lockstep. |
| Q4 | (b) Wrap-at-call-site | Shared `decode_embedding(s) -> list[float]` is the single API. `routes/rule.py` callers wrap: `np.asarray(decode_embedding(s), dtype=np.float32)`. |
| Q5 | (a) Migrate ALL 3 frontmatter copies | `vault_sweeper.py`, `inbox.py`, AND `vault.py` all migrate in Task 3. Real SPOT closure. |

## Spec-conflict surface

**Pathfinder's `cosine_similarity(matrix, vec) -> ndarray`** (`modules/pathfinder/app/rules.py:171`) is shipped behavior. Used by:
- `modules/pathfinder/scripts/calibrate_reuse_threshold.py`
- `modules/pathfinder/scripts/calibrate_retrieval_threshold.py`
- `modules/pathfinder/tests/test_rules.py:201,204,212`
- pathfinder's runtime retrieval path

**Pathfinder's `_decode_query_embedding`** (`modules/pathfinder/app/routes/rule.py:194`) returns `np.ndarray` (float32). Per Q4-b, the shared `decode_embedding` returns `list[float]`; call sites at `routes/rule.py:349,423` wrap with `np.asarray(..., dtype=np.float32)` to preserve the ndarray contract at the consumer boundary.

**Sentinel-core's `cosine_similarity(a, b) -> float`** (`vault_sweeper.py:177`) — vec×vec preserved.

**Frontmatter behavior divergence (audit during Task 3):** `sentinel-core/app/vault.py:57-63`'s `_join_frontmatter` short-circuits when `fm` is empty (returns `rest`); the `inbox.py` and `vault_sweeper.py` copies do not. Canonical public `join_frontmatter` MUST preserve the always-emit-block behavior of `inbox.py`/`vault_sweeper.py` (the dominant pattern) — `vault.py`'s short-circuit is a local optimization; verify no `vault.py` caller depends on it before migrating. If a caller does depend on it, surface in Task 3 commit body and either keep the optimization at the call site or expand the public API. Default plan: migrate `vault.py` to canonical behavior; if any test breaks, STOP per Spec-Conflict Guardrail.

## Module specs

### `sentinel_shared/embedding_codec.py`
```python
def encode_embedding(vec: list[float] | np.ndarray | str) -> str: ...
def decode_embedding(s: str | list | np.ndarray) -> list[float]: ...
```
Verbatim move from `sentinel-core/app/services/vault_sweeper.py:148-172`. Pathfinder's two private codec pairs (`app/rules.py` and `app/routes/rule.py`) replace with imports. `routes/rule.py` callers wrap return value with `np.asarray(..., dtype=np.float32)` (Q4-b).

### `sentinel_shared/similarity.py`
```python
def cosine_similarity(a: np.ndarray | list, b: np.ndarray | list) -> float | np.ndarray: ...
def find_dup_clusters(matrix: np.ndarray, threshold: float = 0.92) -> list[list[int]]: ...
```
Overloaded via `np.atleast_2d`; collapses to float when both inputs were 1D. Zero-norm safe.

### `sentinel-core/app/markdown_frontmatter.py`
```python
_FRONTMATTER_RE: re.Pattern  # module-private (single SPOT for the regex)
def split_frontmatter(body: str) -> tuple[dict, str]: ...
def join_frontmatter(fm: dict, rest: str) -> str: ...
```
Verbatim semantics from `vault_sweeper.py:122-144` / `inbox.py:64-87` (always emits frontmatter block).

## Files modified

### Create
- `shared/sentinel_shared/embedding_codec.py` (~25 LOC)
- `shared/sentinel_shared/similarity.py` (~50 LOC)
- `shared/tests/test_embedding_codec.py` (~20 LOC)
- `shared/tests/test_similarity.py` (~40 LOC)
- `sentinel-core/app/markdown_frontmatter.py` (~30 LOC)
- `sentinel-core/tests/test_markdown_frontmatter.py` (~25 LOC)

### Edit
- `shared/pyproject.toml` — add `[tool.pytest.ini_options]` with `pythonpath = ["."]` if `shared/conftest.py` does not already wire it. (`shared/conftest.py` exists; verify in Task 1 — ADD config only if missing.)
- `sentinel-core/app/services/vault_sweeper.py` — delete codec + similarity + frontmatter helpers; import from new homes. 589 → ~430 LOC.
- `sentinel-core/app/services/inbox.py` — delete `_FRONTMATTER_RE`, `_split_frontmatter`, `_join_frontmatter`; import `split_frontmatter`, `join_frontmatter` from `app.markdown_frontmatter`. Update internal call sites (`_split_frontmatter(...)` → `split_frontmatter(...)`).
- `sentinel-core/app/vault.py` — same treatment as inbox.py. Verify behavior parity (see audit note above).
- `sentinel-core/tests/test_vault_sweeper.py` — update imports.
- (any inbox/vault tests) — update imports if they reference the private helpers.
- `modules/pathfinder/app/rules.py` — delete `_encode_query_embedding`, `_decode_query_embedding`, `cosine_similarity`; import from `sentinel_shared`. Update internal call sites.
- `modules/pathfinder/app/routes/rule.py` — delete `_encode_query_embedding`, `_decode_query_embedding`. Replace caller `_encode_query_embedding(...)` → `encode_embedding(...)`. Replace caller `_decode_query_embedding(s)` → `np.asarray(decode_embedding(s), dtype=np.float32)` at lines 349, 423 (Q4-b wrap-at-call-site).
- `modules/pathfinder/scripts/calibrate_reuse_threshold.py` — update import.
- `modules/pathfinder/scripts/calibrate_retrieval_threshold.py` — update import.
- `modules/pathfinder/tests/test_rules.py` — update imports.
- `modules/pathfinder/pyproject.toml` — add `sentinel-shared` as a path dependency (durable wiring; doesn't depend on env). Likely under `[tool.uv.sources]`: `sentinel-shared = { path = "../../shared", editable = true }` plus listing `sentinel-shared` in `dependencies`. Confirm exact syntax against pathfinder's existing pyproject conventions.

## Tasks (atomic commits, in order)

### Task 1 — `sentinel_shared` extractions

Create `embedding_codec.py` + `similarity.py` + their tests.

Pre-step: `cat shared/conftest.py` — if it does not set `sys.path`, add `[tool.pytest.ini_options]` block with `pythonpath = ["."]` to `shared/pyproject.toml`.

Tests:
- `test_encode_decode_round_trip` — encode then decode returns original to float32 precision.
- `test_encode_accepts_list_or_ndarray_or_passthrough_str`.
- `test_decode_accepts_list_ndarray_or_b64_str` — return type is `list[float]`.
- `test_cosine_similarity_1d_returns_float`.
- `test_cosine_similarity_2d_returns_ndarray_shape` — `(N,D)` × `(D,)` → `(N,)`.
- `test_cosine_similarity_zero_norm_returns_zero` — both shapes — no NaN.
- `test_find_dup_clusters_detects_pairs_above_threshold`.

Verify: `cd shared && pytest -q` → all pass. New code only; no existing files touched. Tree green.

### Task 2 — Migrate sentinel-core to `sentinel_shared` (codec + similarity)

Edit `vault_sweeper.py`: delete `encode_embedding`, `decode_embedding`, `cosine_similarity`, `find_dup_clusters`. Add imports from `sentinel_shared.embedding_codec` and `sentinel_shared.similarity`. Edit `tests/test_vault_sweeper.py` imports.

Verify: `cd sentinel-core && PYTHONPATH=$(pwd)/../shared .venv/bin/pytest -q` → all pass. Grep gate: `rg "^def cosine_similarity|^def encode_embedding|^def decode_embedding|^def find_dup_clusters" sentinel-core/app/` → 0 matches.

### Task 3 — Extract `markdown_frontmatter`; migrate ALL 3 sentinel-core copies

Create `app/markdown_frontmatter.py` (canonical: always emits frontmatter block — matches `inbox.py`/`vault_sweeper.py` semantics) + `tests/test_markdown_frontmatter.py`.

Migrate in one atomic commit:
1. `sentinel-core/app/services/vault_sweeper.py:41-63` — delete `_FRONTMATTER_RE`, `_split_frontmatter`, `_join_frontmatter`. Import public versions. Update internal call sites.
2. `sentinel-core/app/services/inbox.py:64-87` — same treatment. Update internal call sites within `inbox.py`.
3. `sentinel-core/app/vault.py:41-63` — same treatment. **Audit first** for the `if not fm: return rest` divergence — if any vault.py caller relies on it, STOP and surface per Spec-Conflict Guardrail before editing.

Update test file imports for any test that imported the private helpers.

Commit body MUST note: which files were migrated, the `vault.py` divergence audit outcome, and that canonical `join_frontmatter` always emits the block.

Verify: `cd sentinel-core && PYTHONPATH=$(pwd)/../shared .venv/bin/pytest -q` → all pass. Strengthened gate: `rg "^def _?(split|join)_frontmatter|^_?FRONTMATTER_RE" sentinel-core/app/` → only `sentinel-core/app/markdown_frontmatter.py` matches (the public defs and module-local `_FRONTMATTER_RE`). 0 matches in `services/` or `vault.py`.

### Task 4 — Migrate pathfinder to `sentinel_shared`

Pre-step: `cat modules/pathfinder/pyproject.toml` to confirm exact `[tool.uv.sources]` / dependency syntax. Add `sentinel-shared` as an editable path dependency pointing at `../../shared`. Run `cd modules/pathfinder && uv sync` (or equivalent) so the import resolves.

Edits:
1. `modules/pathfinder/app/rules.py` — delete `_encode_query_embedding`, `_decode_query_embedding`, `cosine_similarity`. Import from `sentinel_shared`. Update internal call sites: `_encode_query_embedding(...)` → `encode_embedding(...)`, `_decode_query_embedding(s)` → wrap call sites if they expect ndarray (audit before changing) — most likely they consume `np.ndarray`, so wrap with `np.asarray(decode_embedding(s), dtype=np.float32)`.
2. `modules/pathfinder/app/routes/rule.py` — delete `_encode_query_embedding`, `_decode_query_embedding`. Update caller at line 349 (`_encode_query_embedding(...)` → `encode_embedding(...)`) and the decode call site (line 423 region) to `np.asarray(decode_embedding(s), dtype=np.float32)` (Q4-b wrap-at-call-site).
3. `modules/pathfinder/scripts/calibrate_reuse_threshold.py` — update import to pull `cosine_similarity` from `sentinel_shared.similarity`.
4. `modules/pathfinder/scripts/calibrate_retrieval_threshold.py` — same.
5. `modules/pathfinder/tests/test_rules.py` — update imports. Assertions unchanged.

Commit body MUST include: "shared `decode_embedding` returns `list[float]`; pathfinder `routes/rule.py` callers wrap with `np.asarray(..., dtype=np.float32)` to preserve the ndarray contract at the call site (Q4-b)."

Verify: `cd modules/pathfinder && uv run pytest -q` → all pass. Grep gate: `rg "^def cosine_similarity|^def _encode_query_embedding|^def _decode_query_embedding" modules/pathfinder/` → 0 matches.

**Split fallback (planner discretion at execute-time):** if Task 4's diff is too dense to keep tree green at boundaries, split:
- 4a: Add `sentinel-shared` path dep; verify pathfinder pytest still passes (no functional change).
- 4b: Migrate `app/rules.py` + `app/routes/rule.py` codecs/cosine.
- 4c: Migrate scripts + tests.

### Task 5 — Final SPOT verification + cross-package gate

Strengthened repo-wide grep audit (catches underscore-prefixed copies):

```
rg "^def _?(split|join)_frontmatter|^def _?(encode|decode)_(query_)?embedding|^_?FRONTMATTER_RE|^def cosine_similarity|^def find_dup_clusters" sentinel-core modules shared
```

Expected results — only:
- `sentinel_shared/embedding_codec.py` — `encode_embedding`, `decode_embedding`
- `sentinel_shared/similarity.py` — `cosine_similarity`, `find_dup_clusters`
- `sentinel-core/app/markdown_frontmatter.py` — `split_frontmatter`, `join_frontmatter`, module-local `_FRONTMATTER_RE`

Anywhere else: 0 matches.

If gates auto-pass with no code change, fold task 5 into task 4's commit body as a verification block; otherwise stand alone as a no-code audit commit.

## Verification (overall)

- `cd sentinel-core && PYTHONPATH=$(pwd)/../shared .venv/bin/pytest -q` → all pass (257 baseline + ~7 new = 264).
- `cd sentinel-core && uvx ruff check .` → 0 errors.
- `cd modules/pathfinder && uv run pytest -q` → all pass (now resolves `sentinel_shared` via path dep).
- `cd shared && pytest -q` → all pass (runner exists; `testpaths = ["tests"]` already configured).
- Strengthened grep gate from task 5 clean.
- `wc -l sentinel-core/app/services/vault_sweeper.py` → ≤ 430 LOC (down from 589).

## Guardrails

- **Spec-Conflict Guardrail.** Pathfinder's `cosine_similarity(matrix, vec) -> ndarray` and `_decode_query_embedding -> ndarray` are shipped behavior. Overloaded fn + call-site wrap (Q4-b) preserve identical observable shapes. `vault.py`'s `join_frontmatter` empty-fm short-circuit is shipped behavior — audit + STOP if any caller depends on it before migrating.
- **Test-Rewrite Ban.** All test edits are import-only fixture-wiring refactors. Assertions preserved. Allowed without explicit consent per the ban's allowed list.
- **Behavioral-Test-Only Rule.** New tests in tasks 1+3 must call the function and assert observable result.
- **AI Deferral Ban.** Complete all 5 tasks. Q5-a forbids partial frontmatter migration.
- **Atomic green commits.** Each commit must leave sentinel-core's pytest, pathfinder's pytest, AND shared's pytest green.

Direct to main per project override.
