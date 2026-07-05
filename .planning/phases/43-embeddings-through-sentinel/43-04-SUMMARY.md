---
phase: 43-embeddings-through-sentinel
plan: 04
subsystem: sentinel-core semantic recall / vault sweeper
tags: [embeddings, dimension-guard, D-08, D-09, EMB-04, defense-in-depth]
dependency-graph:
  requires: [43-01]
  provides: [D-08-persisted-dim-guard, D-09-restart-is-cutover-doc]
  affects: [SemanticRecall.search, vault_sweeper.rebuild_embedding_index, vault_sweeper.run_sweep]
tech-stack:
  added: []
  patterns:
    - "persisted-dim fast-path guard mirroring the existing embedding_model read-and-compare pattern"
    - "batch-level dimension resolved from produced vectors (len(embeddings[0])), never from config"
key-files:
  created: []
  modified:
    - sentinel-core/app/services/embedding_sidecar_index.py
    - sentinel-core/app/services/vault_sweeper.py
    - sentinel-core/tests/test_embedding_sidecar_index.py
    - sentinel-core/tests/test_vault_sweeper.py
decisions:
  - "D-08 badged and extended: eligible_entries() reads an optional persisted entry.embedding_dim and hard-skips before decode when it differs from the live query_dim; entries lacking the field fall back unchanged to the existing decode-time len(raw) != query_dim check"
  - "D-09 documented in-code: the existing non-blocking startup rebuild_embedding_index (wired via composition.initialize_startup's _startup_rebuild) plus a container restart IS the cutover mechanism — no new trigger, route, or CLI was added"
  - "embedding_dim resolved from the PRODUCED vectors (len(embeddings[0])), never from settings/config, so the guard also catches a same-embedding_model-string/different-dimension cutover (Matryoshka truncation change scenario)"
metrics:
  duration: "~15 min"
  completed: 2026-07-05
status: complete
---

# Phase 43 Plan 04: Dimension-Mismatch Guard Hardening (D-08) + Restart-Is-Cutover Documentation (D-09) Summary

Extended the existing D-08 dimension-mismatch guard in `eligible_entries()` with a cheap persisted-`embedding_dim` fast path (skip-before-decode), and taught the vault sweeper to persist that dimension on every written sidecar entry — closing the defense-in-depth gap where a same-named embedding model could silently change output dimension across the exo→LM Studio cutover.

## What Was Built

**Task 1 — `eligible_entries()` persisted-dimension fast path (D-08/EMB-04):**
- Added a cheap fast-path check: if a sidecar entry carries `entry.get("embedding_dim")` as a positive int that differs from `query_dim`, the entry is skipped (logged, `continue`) *before* `decode_embedding()` runs.
- Entries without `embedding_dim` fall through unchanged to the pre-existing decode-time `len(raw) != query_dim` check — fully backward compatible with indexes written before this plan.
- Badged the existing decode-time check with an explicit D-08/EMB-04 comment identifying it as the single source of truth for this invariant (no duplicate guard added in `recall.py` or elsewhere).
- New tests cover: (a) the cutover case — `embedding_model` matches but persisted `embedding_dim` differs (768 vs query 3), caught before decode even though the decoded vector's own length happens to match `query_dim`; (b) no `embedding_dim` field present, decode-time fallback still catches a mismatch; (c) matching-model/matching-persisted-dim entry is retained (positive control).

**Task 2 — persisted `embedding_dim` written by the sweeper + D-09 doc:**
- `fresh_entry()` and `stale_entry()` (`embedding_sidecar_index.py`) now accept and persist an `embedding_dim` keyword. `fresh_entry` falls back to `len(embedding)` when no batch-level dimension is threaded in; `stale_entry` carries forward the existing entry's `embedding_dim` (mirrors the existing `embedding_model` fallback pattern).
- `build_embedding_index()` gained an `active_embedding_dim: int | None = None` parameter (default `None`, backward compatible with existing callers/tests), threaded into every `fresh_entry`/`stale_entry` call it makes.
- New `_resolve_embedding_dim()` helper in `vault_sweeper.py` (mirrors `_embedding_model_id()`) derives the dimension from the produced vectors (`len(embeddings[0])`) — never from settings — so the guard reacts to what the backend actually returned, not what config claims.
- `_emit_embedding_index()` now passes `active_embedding_dim=_resolve_embedding_dim(embeddings)` into `build_embedding_index()`, so both `run_sweep` and `rebuild_embedding_index` (both funnel through `_emit_embedding_index`) persist the dimension.
- `rebuild_embedding_index()` docstring extended with the D-09 note: the existing non-blocking startup rebuild + `docker compose restart sentinel-core` (after the 43-01 `base_url` fix) IS the cutover mechanism. No new re-sweep trigger, ops route, or CLI was introduced. pf2e's rules index rebuild is separately triggered at its own startup and out of scope.
- `model_loaded=False` skip gate in `rebuild_embedding_index` is unchanged — still short-circuits to `status="skipped"` before any embedding_dim work runs.

## Verification

- `pytest tests/test_embedding_sidecar_index.py` — 19 passed (4 new cases covering the cutover, fallback, and positive-control scenarios).
- `pytest tests/test_vault_sweeper.py` — 39 passed (extended `test_rebuild_embedding_index_writes_index_with_all_fields` to assert `embedding_dim` is a positive int equal to the fake embedder's produced vector length).
- `pytest tests/test_embedding_sidecar_index.py tests/test_vault_sweeper.py tests/test_recall.py` — 108 passed.
- Full `sentinel-core` suite: `pytest` — 458 passed, 12 skipped, no failures, no warnings.

## TDD Gate Compliance

Both tasks followed RED → GREEN:
- Task 1: `test(43-04): add failing tests for D-08 persisted embedding_dim fast-path guard` (1f1ee24, confirmed failing before implementation) → `feat(43-04): badge D-08 dimension guard and add persisted embedding_dim fast path` (b95c31d).
- Task 2: `test(43-04): add failing assertion for persisted embedding_dim in sweeper index` (56fed45, confirmed failing before implementation) → `feat(43-04): persist embedding_dim in sweeper-written index; document D-09 restart-is-cutover` (9bf307e).

## Deviations from Plan

None — plan executed exactly as written. The optional `_embedding_dim()`-style helper mentioned as "acceptable" in the plan's Task 2 action was implemented as `_resolve_embedding_dim()` in `vault_sweeper.py`, mirroring `_embedding_model_id()` as suggested.

## Known Stubs

None.

## Threat Flags

None — this plan hardens an existing mitigation (T-43-04-01, `eligible_entries` dimension guard) and adds a persisted field to an existing sidecar index; no new network endpoint, auth path, or trust-boundary-crossing surface was introduced.

## Self-Check: PASSED

- `sentinel-core/app/services/embedding_sidecar_index.py` — FOUND, contains `embedding_dim` persisted-fast-path logic.
- `sentinel-core/app/services/vault_sweeper.py` — FOUND, contains `_resolve_embedding_dim` and D-09 docstring note.
- `sentinel-core/tests/test_embedding_sidecar_index.py` — FOUND, 3 new test functions present.
- `sentinel-core/tests/test_vault_sweeper.py` — FOUND, extended assertion present.
- Commits `1f1ee24`, `b95c31d`, `56fed45`, `9bf307e` — all FOUND in `git log --oneline --all`.
