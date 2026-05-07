---
phase: 37-pf2e-per-player-memory
plan: 12
subsystem: pathfinder/foundry-import
tags: [pathfinder, foundry, projection, idempotency, route, tdd-green]
requires:
  - 37-11 (project_foundry_chat_memory module)
  - 37-06 (player_identity_resolver)
  - 37-08 (npc_matcher)
provides:
  - app.foundry_chat_import._load_projection_state (re-export shim)
  - app.foundry_chat_import._save_state (multi-bucket state writer)
  - import_nedb_chatlogs_from_inbox(project_player_maps, project_npc_history, identity_resolver, npc_matcher)
  - FoundryImportRequest.project_player_maps / project_npc_history
  - POST /foundry/messages/import response.projection block
affects:
  - .foundry_chat_import_state.json (read-then-merge preserves projection arrays on importer writes)
tech-stack:
  added: []
  patterns:
    - re-export shim for cross-module symbol stability under TDD
    - read-then-merge state-file writes (importer + projector share one file)
    - closure-based seam wiring (identity_resolver + npc_matcher built per-request from singletons)
key-files:
  created:
    - modules/pathfinder/tests/test_foundry_routes.py
  modified:
    - modules/pathfinder/app/foundry_chat_import.py
    - modules/pathfinder/app/routes/foundry.py
decisions:
  - "Projection runs only when seams are provided AND at least one of the two flags is True. Function-level callers without seams (existing tests) keep legacy behavior."
  - "_save_dedupe_keys read-then-merges so the importer never trampling player_projection_keys / npc_projection_keys."
  - "Route closures fetch alias_map and foundry_alias_map per-request via the existing async loaders; npc_roster comes from app.routes.session.npc_roster_cache (already lifespan-populated)."
  - "Response includes `projection: null` when both flags are False (or seams missing); test asserts the null contract explicitly."
metrics:
  duration_minutes: 6
  completed: 2026-05-07
requirements: [FCM-04, FCM-05]
---

# Phase 37 Plan 12: Projection Wiring + Route Flags Summary

Wires the Wave-6 `project_foundry_chat_memory` module into the existing `POST /foundry/messages/import` flow, turns the last plan-37-03 RED test GREEN, and extends the import route with two boolean flags plus a `projection` metric block in the response.

## What Shipped

### `app.foundry_chat_import`

- **`_load_projection_state(path) -> dict[str, set[str]]`** — re-export shim that satisfies the plan-37-03 backcompat test. Returns three buckets (`imported_keys`, `player_projection_keys`, `npc_projection_keys`); handles legacy state files containing only `imported_keys` cleanly.
- **`_save_state(path, *, imported_keys, player_keys=None, npc_keys=None)`** — unified writer; emits the legacy single-array shape when projection keys are absent so plan-pre-37 readers keep working.
- **`_save_dedupe_keys`** is now a read-then-merge wrapper. It loads the existing projection arrays before writing so the importer never trampling projector data.
- **`import_nedb_chatlogs_from_inbox`** gains four new kwargs (all backward-compatible defaults):
  - `project_player_maps: bool = True`
  - `project_npc_history: bool = True`
  - `identity_resolver: Callable[[record], (kind, slug)] | None = None`
  - `npc_matcher: Callable[[alias], slug | None] | None = None`

  When seams are provided AND at least one flag is True AND the run is non-dry, the function calls `project_foundry_chat_memory` with the same record set and surfaces its metric block under `result["projection"]`. When seams are absent or both flags False, projection is skipped and `result["projection"]` is `None`.

### `app.routes.foundry`

- **`FoundryImportRequest`** gains `project_player_maps: bool = True` and `project_npc_history: bool = True`.
- **`POST /foundry/messages/import`** now builds an identity-resolver closure and an async NPC-matcher closure per request:
  - Loads `alias_map` and `foundry_alias_map` from Obsidian via the Phase-37-06 loaders.
  - Reads `npc_roster_cache` from `app.routes.session` (already lifespan-populated).
  - Wraps `resolve_foundry_speaker` in a closure that pulls `actor` from the record's `speaker.alias` so the projector's `_speaker(record)` semantics match.
  - Wraps `match_npc_speaker` in an async closure for defence-in-depth fallbacks.
- Response includes a `projection` field. With default flags it carries the FCM-05 metric shape; with both flags false it is `null`.

## How It Maps to Requirements

| Req    | Behavior                                                                            | Test |
| ------ | ----------------------------------------------------------------------------------- | ---- |
| FCM-04 | Projection wiring is idempotent end-to-end through the route                        | `test_foundry_import_response_includes_projection_metrics` (route-level shape); `test_projection_idempotent_on_rerun` (function-level, plan 37-11) |
| FCM-05 | dry-run flows through; metric shape verified at the route layer                     | `test_foundry_import_dry_run_projection_metrics`, `test_foundry_import_response_includes_projection_metrics` |
| FCM-04 | Pre-existing state files load cleanly (backward compat shim)                        | `test_state_file_backcompat_missing_projection_keys` (plan 37-03 RED → GREEN) |
| Wiring | Both flags False skip projection cleanly                                            | `test_foundry_import_skip_projection_when_flags_false` |

## Key Design Choices

**Local import for the projection module.** `project_foundry_chat_memory` imports `_message_key`/`_speaker`/`_strip_html` from `foundry_chat_import` at module load, so the importer must avoid a top-level reverse import. The projection call is wrapped in a function-scope import inside `import_nedb_chatlogs_from_inbox` to break the cycle without requiring any module-level reordering.

**Seams-required gate.** Projection only fires when the caller provides both `identity_resolver` and `npc_matcher`. This keeps the four pre-existing function-level tests in `test_foundry_chat_import.py` passing — they invoke the importer without seams, so projection is silently skipped, preserving the original return shape (with the additive `projection: None` key).

**Read-then-merge state writes.** `_save_dedupe_keys` now reads the existing state file before writing. If the projector has populated `player_projection_keys` or `npc_projection_keys`, those arrays survive the importer's write. This is what makes the in-place state-file extension safe for both writers to share without coordination.

**Route closure pattern over a fat resolver.** Building closures inside the route handler avoids a heavy module-level rewiring. The closures capture the per-request `alias_map`/`foundry_alias_map`/`npc_roster_cache` snapshot and pass exactly the kwargs `resolve_foundry_speaker` expects (`actor`, `alias_map`, `npc_roster`, `pc_character_names`). Note: the plan's illustrative snippet referenced an `onboarded_players` parameter that does not exist on `resolve_foundry_speaker` in the actual implementation; the wiring uses the real signature (Rule 3 – fixed during implementation).

## Verification

```
modules/pathfinder $ pytest tests/test_foundry_routes.py \
                            tests/test_foundry_chat_import.py \
                            tests/test_projection_idempotency.py \
                            tests/test_foundry_memory_projection.py
22 passed
```

- 3 new route tests GREEN.
- 5/5 `test_foundry_chat_import.py` tests GREEN — including the previously-RED `test_state_file_backcompat_missing_projection_keys` from plan 37-03.
- All 14 plan-37-11 projection tests still GREEN — schema extension fully backward-compatible.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 – Blocking] resolve_foundry_speaker signature mismatch**
- **Found during:** Task 2 wiring.
- **Issue:** The plan's illustrative closure called `resolve_foundry_speaker(...)` with an `onboarded_players={}` keyword, but the actual function (from plan 37-06) takes `actor`, `alias_map`, `npc_roster`, `pc_character_names`. There is no `onboarded_players` parameter.
- **Fix:** Used the real signature. Mapped `alias_map` (Discord-id → slug) into `pc_character_names` and `foundry_alias_map` (Foundry actor → Discord-id) into `alias_map`, matching the precedence the plan-37-11 module already documents.
- **Files modified:** `modules/pathfinder/app/routes/foundry.py`
- **Commit:** `037c055`

## Deferred Issues

`tests/test_foundry.py::{test_roll_event_accepted, test_notify_dispatched, test_llm_fallback}` fail with `NameError: name 'get_profile' is not defined` at `modules/pathfinder/app/routes/foundry.py:106`. Verified pre-existing on main via `git stash` round-trip — out of scope for plan 37-12. Logged in `.planning/phases/37-pf2e-per-player-memory/deferred-items.md` for separate operator follow-up.

## Commits

| Task | Description                                                                                  | Commit  |
| ---- | -------------------------------------------------------------------------------------------- | ------- |
| 1    | Wire projection hook + backcompat shim into foundry_chat_import.py                           | 1d9ae1e |
| 2    | Add projection flags + projection block to /foundry/messages/import; add route tests         | 037c055 |

## Self-Check: PASSED

- `modules/pathfinder/app/foundry_chat_import.py` — modified, FOUND
- `modules/pathfinder/app/routes/foundry.py` — modified, FOUND
- `modules/pathfinder/tests/test_foundry_routes.py` — created, FOUND
- Commit `1d9ae1e` — FOUND in git log
- Commit `037c055` — FOUND in git log
- `test_state_file_backcompat_missing_projection_keys` — GREEN
- 22/22 in-scope tests GREEN
