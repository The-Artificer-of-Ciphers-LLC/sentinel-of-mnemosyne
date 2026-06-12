---
phase: 40-semantic-recall
plan: "04"
subsystem: vault-sweeper / model-selector / composition / routes
tags: [security, safety, tdd, fail-closed, vault-sweeper, embedding-index, startup]
dependency_graph:
  requires: []
  provides:
    - vault_sweeper.rebuild_embedding_index
    - model_selector.probe_classifier_model_ready
    - run_sweep.safe_to_mutate_gate
    - _emit_embedding_index.stale_invariant
    - composition.startup_index_rebuild
    - note_sweep_runner.safe_to_mutate_forwarding
    - routes.note.fail_closed_admin_probe
  affects:
    - 40-07 (stale:true reader-side skip)
tech_stack:
  added:
    - probe_classifier_model_ready (model_selector.py)
    - rebuild_embedding_index (vault_sweeper.py)
    - stale:true index field (vault_sweeper._emit_embedding_index)
    - safe_to_mutate probe gate (run_sweep, start_sweep, vault_sweep_start)
  patterns:
    - Fail-closed safety probe: absent probe = unsafe (zero moves)
    - Per-move probe re-evaluation (not once-per-run)
    - Deterministic stale marker: new hash without fresh vector = stale:true
    - ProtectedPathError catch-and-continue in all three destructive branches
key_files:
  created:
    - sentinel-core/tests/test_model_selector.py
    - sentinel-core/tests/test_note_sweep_runner.py
  modified:
    - sentinel-core/app/services/vault_sweeper.py
    - sentinel-core/app/services/model_selector.py
    - sentinel-core/app/composition.py
    - sentinel-core/app/services/note_sweep_runner.py
    - sentinel-core/app/routes/note.py
    - sentinel-core/tests/test_vault_sweeper.py
    - sentinel-core/tests/test_composition.py
decisions:
  - "rebuild_embedding_index uses all walked paths as active_paths (not just survivors) so existing index entries for unsafe-skipped notes aren't pruned on degraded runs"
  - "stale:true rule chosen over (a) carry-old-hash-forward only — stale:true preserves the new content_hash so 40-07 can detect and skip, deterministic to avoid test flake"
  - "_ImmediateTaskRunner test helper avoids asyncio.sleep() timing in test_note_sweep_runner.py — TaskRunner injected via test_runner kwarg"
  - "probe_classifier_model_ready uses provided http_client directly (not get_loaded_models cache) so test fakes and production clients are both honored"
metrics:
  duration: 17min
  completed: "2026-06-11"
  tasks: 4
  files: 8
---

# Phase 40 Plan 04: Mandatory Fail-Closed Safe-to-Mutate Gate Summary

One-liner: Startup switched from destructive `run_sweep` to index-only `rebuild_embedding_index`, and `run_sweep` now requires a fail-closed per-move safety probe that is absent-means-unsafe — closing the UAT incident root cause and all three round-2/3 cross-AI review gaps.

## What Was Built

### Task 1: `rebuild_embedding_index()` — Index-only non-destructive startup rebuild

Added `async def rebuild_embedding_index(client, embedder, *, model_loaded=True, source_folder="")` to `vault_sweeper.py`. This routine:
- Walks the vault using `walk_vault`, reads note bodies, and embeds them with `NOMIC_DOCUMENT_PREFIX`
- Calls `_emit_embedding_index` to write the sidecar — reusing the existing helper
- Uses ONLY `list_under`, `read_note`, and `write_note` primitives — NEVER calls `relocate`, `move_to_trash`, `delete_note`, or the classifier
- Reuses the sweep lockfile (T-40-16: cannot race a concurrent `run_sweep`)
- When `model_loaded=False`: logs WARNING, sets `status="skipped"`, returns immediately without calling the embedder

**4 tests, all pass.**

### Task 2: `probe_classifier_model_ready()` — Fail-closed classifier readiness probe

Added `async def probe_classifier_model_ready(http_client, lmstudio_base_url, *, model_name, model_preferred=None)` to `model_selector.py`. This probe:
- Mirrors the exact selection path `_resolve_model_for_classification` uses
- Calls `select_model("structured", loaded, preferences=..., default=None)` — `default=None` prevents rules 3/5 (defaulted fallbacks) from firing
- Guards against rule-4 last-resort: `_score("structured", id) > 0` required — a bare `loaded[0]` with no function-calling scores 0 and is NOT reported ready
- Any HTTP/JSON/unexpected exception returns `False` (graceful degrade, never raises)

**6 tests, all pass.** The decisive round-2 case (loaded but non-scored = False) is explicitly tested.

### Task 3: Mandatory per-move safe-to-mutate gate, frontmatter suppression, degraded-index invariant, ProtectedPathError handling

**run_sweep changes:**
- Added `safe_to_mutate: Callable[[], Awaitable[bool]] | None = None` parameter
- Internal `_is_safe()` helper: returns `False` when `safe_to_mutate is None` (fail-closed by construction, round-3 HIGH)
- `_is_safe()` is re-evaluated IMMEDIATELY BEFORE each `relocate`/`move_to_trash` in all three branches (noise→trash, misplaced→relocate, dedup→trash) — per-move, not once per run
- Round-2 item C: classification frontmatter write-back suppressed on unsafe runs — note left byte-identical
- `ProtectedPathError` caught in all three branches; error recorded in `report.errors`; sweep continues
- Removed permissive `model_loaded: bool = True` from `run_sweep` signature — the bypass is closed by construction
- Pre-existing destructive tests updated to supply `safe_to_mutate=_true_probe`

**`_emit_embedding_index` degraded-index invariant (MEM-05 / T-40-23):**
- Deterministic `stale: true` rule: if body hash changed but no fresh vector available, write `{old_vector, new_content_hash, stale: True}` — never persist new hash with missing/stale vector
- All walked paths used as `active_paths` (not just survivors) to prevent existing entries from being pruned on degraded runs

**11 new tests + 8 updated pre-existing tests, all 39 sweeper tests pass.**

### Task 4: Startup rewire and admin sweep entrypoint wiring

**composition.py (`_startup_rebuild`):**
- Replaced `from app.services.vault_sweeper import run_sweep as _run_sweep` + call with `rebuild_embedding_index(graph.vault, graph.embeddings.embed, model_loaded=graph.embedding_model_loaded)`
- Updated comment documenting the UAT incident and why this is safe
- `run_sweep` is provably absent from composition.py (grep == 0)

**note_sweep_runner.start_sweep:**
- Added `safe_to_mutate` parameter; forwarded to live `run_sweep` call
- Dry-run path does NOT forward a probe

**routes/note.vault_sweep_start:**
- Imports `probe_embedding_model_loaded` and `probe_classifier_model_ready`
- Builds `_safe_to_mutate_probe` closure that ANDs both probes for live runs
- Dry-run passes `safe_to_mutate=None`

**14 tests across test_composition.py and test_note_sweep_runner.py (new file), all pass.**

## Success Criteria Verification

1. Startup rebuild: `grep run_sweep == 0` in composition.py + spy test — PASS
2. No permissive default: `grep "model_loaded: bool = True" in run_sweep == 0` + no-probe→zero-moves test — PASS
3. Per-move re-evaluation: flip-to-False test proves guard re-checked before each move — PASS
4. Real classifier readiness: non-scored-returns-False test + admin classifier-probe-False test — PASS
5. Frontmatter suppressed on unsafe run: byte-identical-note assertion under False probe — PASS
6. MEM-05 invariant: no index entry with new hash + missing/old vector — PASS
7. ProtectedPathError continues: concern-3 test across relocate branch — PASS
8. Admin entrypoint always supplies probe: live-path-non-None-probe test — PASS
9. Full suite green: 334 passed, 12 skipped — PASS

## TDD Gate Compliance

All 4 tasks followed RED → GREEN pattern:
- RED commits (test only, failing): c0d9094, 83dc62c, 2ac9754, d584e12
- GREEN commits (implementation): 49aa71c, d64c4e0, 416afec, 1e0fa8e

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] probe_classifier_model_ready used get_loaded_models (cached) instead of provided http_client**
- **Found during:** Task 2 GREEN run
- **Issue:** First implementation delegated to `get_loaded_models` which creates its own `httpx.AsyncClient` internally, ignoring the injected `http_client`. Tests using `MockTransport` saw no requests.
- **Fix:** Changed to call the HTTP endpoint directly via the provided `http_client`, matching `probe_embedding_model_loaded`'s pattern.
- **Files modified:** `sentinel-core/app/services/model_selector.py`
- **Commit:** d64c4e0

**2. [Rule 1 - Bug] Degraded-run index pruning: notes skipped by safe-to-mutate gate were evicted from index**
- **Found during:** Task 3 GREEN run
- **Issue:** `active_paths = {s[0] for s in survivors}` was empty on a degraded run (no survivors due to unsafe gate), causing all existing index entries to be pruned.
- **Fix:** Changed `active_paths` to use `set(paths)` (all walked paths) so existing entries for unsafe-skipped notes are preserved in the index.
- **Files modified:** `sentinel-core/app/services/vault_sweeper.py`
- **Commit:** 416afec

**3. [Rule 1 - Bug] test_note_sweep_runner.py timing: asyncio.sleep(0.05) unreliable for background task completion**
- **Found during:** Task 4 RED phase
- **Issue:** Tests using `asyncio.sleep(0.05)` were unreliable for background task completion with `AsyncioTaskRunner`.
- **Fix:** Added `_ImmediateTaskRunner` test helper that collects coroutines and runs them immediately via `await runner.run_all()`. Injected via `task_runner=runner` parameter.
- **Files modified:** `sentinel-core/tests/test_note_sweep_runner.py`
- **Commit:** d584e12

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes beyond what the plan specified. The `stale: true` field is a new index-schema field documented in the plan; its reader-side consumer is owned by 40-07.

## Self-Check: PASSED

All 9 key files verified present on disk. All 8 task commits verified in git log:

| Commit | Type | Description |
|--------|------|-------------|
| c0d9094 | RED  | test(40-04): add failing tests for rebuild_embedding_index |
| 49aa71c | GREEN | feat(40-04): add rebuild_embedding_index() index-only routine |
| 83dc62c | RED  | test(40-04): add failing tests for probe_classifier_model_ready |
| d64c4e0 | GREEN | feat(40-04): add probe_classifier_model_ready() fail-closed probe |
| 2ac9754 | RED  | test(40-04): add failing tests for mandatory safe-to-mutate gate |
| 416afec | GREEN | feat(40-04): mandatory fail-closed safe-to-mutate gate + invariants |
| d584e12 | RED  | test(40-04): add failing tests for startup rewire + admin probe wiring |
| 1e0fa8e | GREEN | feat(40-04): rewire startup + wire admin sweep to fail-closed probe |
