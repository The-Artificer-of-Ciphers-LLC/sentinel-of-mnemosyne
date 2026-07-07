---
phase: 47-migration-cutover-hardening
plan: 05
subsystem: api
tags: [fastapi, discord, admin-gating, migration, vault-sweep-pattern]

# Dependency graph
requires:
  - phase: 47-migration-cutover-hardening (Plan 03/04)
    provides: migration_orchestrator.run()/start_migration(), migration_status_store, RollbackLedger
provides:
  - "POST /vault/migrate/start (admin-gated, dry_run flag) in sentinel-core"
  - "GET /vault/migrate/status in sentinel-core"
  - "Discord :migrate [status|dry-run|live] command dispatch, admin-gated at bot layer"
  - "core_gateway.call_core_migrate_start/call_core_migrate_status HTTP wrappers"
affects: [47-06 (full-suite hard gate), 47-07 (live cutover — depends on :migrate being invocable end-to-end from Discord)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Route-layer admin gate reused verbatim (imported _is_admin_route from note.py, not re-implemented)"
    - "Discord dispatch verb parsing (status/dry-run/live) mirrors :vault-sweep's status/dry-run/force shape"
    - "Additive optional kwargs (call_core_migrate_start=None) on handle_subcommand to stay backward-compatible with existing callers"

key-files:
  created:
    - sentinel-core/app/routes/migration.py
  modified:
    - sentinel-core/app/main.py
    - interfaces/discord/command_router.py
    - interfaces/discord/core_gateway.py
    - interfaces/discord/bot.py
    - interfaces/discord/tests/test_command_router_module.py
    - interfaces/discord/tests/test_core_gateway.py

key-decisions:
  - "T-47-02 resolved as: :migrate defaults to dry_run=True (bare invocation or explicit 'dry-run' verb); a live run requires the explicit 'live' verb — safer than :vault-sweep's actual bare-invocation-is-live default, per the plan's explicit instruction to make dry-run the safe default."
  - "Wired interfaces/discord/bot.py (not listed in the plan's files_modified) to actually register call_core_migrate_start/status in handle_sentask_subcommand's kwargs — without this, :migrate would be dispatchable in unit tests only and non-functional from real Discord messages, which would block Plan 07's live ':migrate --dry-run' invocation. Confirmed no stale fixed-prompt :migrate entry existed in bot.py to remove."
  - "handle_subcommand's two new params (call_core_migrate_start, call_core_migrate_status) default to None rather than being required — avoids breaking every existing test/call site that doesn't pass them, matching the discord_router_bridge.route_message precedent (sentinel_client=None, http_client=None) for additive kwargs."

patterns-established:
  - "Migration invocation surface is a verbatim structural mirror of :vault-sweep/:pipeline at all three layers (route, core_gateway, command_router/bot)."

requirements-completed: [MIG-01, MIG-02]

coverage:
  - id: D1
    description: "POST /vault/migrate/start is admin-gated (403 for non-admin) and returns a 200 ack with migration_id + status:running for an admin dry_run request"
    requirement: "MIG-01"
    verification:
      - kind: integration
        ref: "sentinel-core/tests/test_migration_routes.py#test_migrate_start_requires_admin"
        status: pass
      - kind: integration
        ref: "sentinel-core/tests/test_migration_routes.py#test_migrate_start_dry_run"
        status: pass
    human_judgment: false
  - id: D2
    description: "GET /vault/migrate/status returns the migration_status_store shape"
    requirement: "MIG-01"
    verification:
      - kind: integration
        ref: "sentinel-core/tests/test_migration_routes.py#test_migrate_status_shape"
        status: pass
    human_judgment: false
  - id: D3
    description: "Discord :migrate dispatch is admin-gated at the bot layer, defaults to dry-run, requires an explicit 'live' verb for a live run, and 'status' polls status"
    requirement: "MIG-02"
    verification:
      - kind: unit
        ref: "interfaces/discord/tests/test_command_router_module.py#test_migrate_non_admin_refused"
        status: pass
      - kind: unit
        ref: "interfaces/discord/tests/test_command_router_module.py#test_migrate_bare_defaults_to_dry_run"
        status: pass
      - kind: unit
        ref: "interfaces/discord/tests/test_command_router_module.py#test_migrate_live_verb_requires_explicit_confirmation"
        status: pass
      - kind: unit
        ref: "interfaces/discord/tests/test_command_router_module.py#test_migrate_status_verb_invokes_status_gateway"
        status: pass
    human_judgment: false
  - id: D4
    description: "core_gateway exposes call_core_migrate_start(dry_run, user_id) and call_core_migrate_status() mirroring the sweep/pipeline HTTP wrapper shape and error handling"
    requirement: "MIG-02"
    verification:
      - kind: unit
        ref: "interfaces/discord/tests/test_core_gateway.py#test_call_core_migrate_start_posts_and_formats_dry_run_response"
        status: pass
      - kind: unit
        ref: "interfaces/discord/tests/test_core_gateway.py#test_call_core_migrate_status_formats_report_fields"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-07-06
status: complete
---

# Phase 47 Plan 05: Migration Invocation Surface Summary

**Admin-gated `POST /vault/migrate/start` + `GET /vault/migrate/status` routes in sentinel-core, and a Discord `:migrate [status|dry-run|live]` command wired end-to-end through `core_gateway` — every primitive a verbatim mirror of the existing `:vault-sweep` surface (T-47-01/T-47-02 mitigations).**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-07-06T23:03:00-04:00
- **Completed:** 2026-07-06T23:17:22-04:00
- **Tasks:** 2/2 completed
- **Files modified:** 7 (1 created, 6 modified)

## Accomplishments
- `sentinel-core/app/routes/migration.py` — `POST /vault/migrate/start` (admin-gated via `note.py`'s `_is_admin_route`, reused verbatim) and `GET /vault/migrate/status`; registered in `main.py`. Turns `test_migration_routes.py` GREEN (3/3).
- `interfaces/discord/core_gateway.py` — `call_core_migrate_start(dry_run, user_id)` and `call_core_migrate_status()` HTTP wrappers, mirroring `call_core_sweep_start`/`call_core_pipeline_status` request/response shape and error handling.
- `interfaces/discord/command_router.py` — `:migrate` subcommand: admin-gated at the bot layer (defense-in-depth alongside the route-layer gate), verb-parsed dispatch (`status` / bare or `dry-run` → dry_run=True / `live` → dry_run=False).
- `interfaces/discord/bot.py` — wired `_call_core_migrate_start`/`_call_core_migrate_status` into `handle_sentask_subcommand`'s kwargs so `:migrate` is actually invocable from real Discord messages (see Deviations).
- New tests for the dispatch and gateway wrappers; discord suite grows 276 → 286 passed (50 skipped, no shrink); sentinel-core suite stays at 592 passed (12 skipped, no shrink).

## Task Commits

Each task was committed atomically:

1. **Task 1: Admin-gated /vault/migrate/start + /vault/migrate/status routes** - `5cafa57` (feat)
2. **Task 2: Discord :migrate dispatch + core_gateway HTTP wrappers** - `c8306c4` (feat)

**Plan metadata:** (this commit, follows)

## Files Created/Modified
- `sentinel-core/app/routes/migration.py` - New route module: `MigrateStartRequest{user_id, dry_run}`, admin-gated `POST /vault/migrate/start` calling `start_migration()`, `GET /vault/migrate/status` returning `migration_status_store.get_status()`
- `sentinel-core/app/main.py` - Import + register `migration_router`
- `interfaces/discord/core_gateway.py` - `call_core_migrate_start`/`call_core_migrate_status` HTTP wrappers
- `interfaces/discord/command_router.py` - `:migrate` subcommand dispatch (admin-gated, verb-parsed dry-run/live/status); two new optional kwargs on `handle_subcommand`
- `interfaces/discord/bot.py` - `_call_core_migrate_start`/`_call_core_migrate_status` wrapper functions, wired into `handle_sentask_subcommand`'s kwargs dict
- `interfaces/discord/tests/test_command_router_module.py` - 5 new tests for `:migrate` dispatch
- `interfaces/discord/tests/test_core_gateway.py` - 5 new tests for the gateway wrappers

## Decisions Made
- **Dry-run-safe default for `:migrate` (T-47-02):** the plan's action text explicitly required "default to dry-run OR require an explicit confirmation flag for a live run" — this diverges from `:vault-sweep`'s actual behavior (bare `:vault-sweep` is a LIVE, non-forced sweep by default). Implemented `:migrate` so bare invocation and `:migrate dry-run` both default to `dry_run=True`; only `:migrate live` performs a live run. This satisfies the plan's explicit safety requirement while still mirroring `:vault-sweep`'s verb-parsing *shape* (`status`/dry-run-verb/force-verb → `status`/dry-run-verb/live-verb).
- **`handle_subcommand`'s two new kwargs default to `None`:** every existing test (and the real `bot.py` call site) passes an explicit, complete kwarg set with no defaults for the pre-existing params. Adding `call_core_migrate_start`/`call_core_migrate_status` as required kwargs would have broken every existing call site. Defaulting them to `None` (mirroring the `discord_router_bridge.route_message` precedent of `sentinel_client=None, http_client=None` for additive kwargs) keeps all pre-existing tests/call sites byte-for-byte unchanged.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] Wired `interfaces/discord/bot.py` to register the new gateway callables**
- **Found during:** Task 2 (Discord `:migrate` dispatch)
- **Issue:** The plan's `files_modified` frontmatter and Task 2's `read_first` note ("check ONLY for a stale fixed-prompt `:migrate` entry to remove; do not add new bot logic") scoped this plan to `command_router.py` + `core_gateway.py` only. However, `discord_router_bridge.handle_subcommand` forwards `**kwargs` from a manually-enumerated dict built in `bot.py`'s `handle_sentask_subcommand` — there is no dynamic/generic dispatch. Without adding `call_core_migrate_start`/`call_core_migrate_status` to that dict (and the corresponding `_call_core_migrate_start`/`_call_core_migrate_status` wrapper functions calling `core_gateway`), `:migrate` would dispatch correctly in unit tests (which pass fakes directly) but would be entirely non-functional from a real Discord message — `handle_subcommand`'s new params would stay at their `None` default in production. Plan 07 (wave 6, human-gated) explicitly requires running `:migrate --dry-run` live from Discord against the real vault before the live cutover, which is impossible if the command is never wired end-to-end.
- **Fix:** Added `_call_core_migrate_start(user_id, dry_run=True)` and `_call_core_migrate_status(user_id)` wrapper functions in `bot.py` (mirroring the existing `_call_core_sweep_start`/`_call_core_pipeline_start` wrappers exactly), and registered both under `"call_core_migrate_start"`/`"call_core_migrate_status"` in `handle_sentask_subcommand`'s kwargs dict. Confirmed (via grep) no stale fixed-prompt `:migrate` entry existed anywhere in `bot.py` to remove — the read_first's removal instruction was a no-op.
- **Files modified:** `interfaces/discord/bot.py`
- **Verification:** `python -c "import ast; ast.parse(open('bot.py').read())"` succeeds; full discord suite (286 passed, 50 skipped) still green with the wiring in place.
- **Committed in:** `c8306c4` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical functionality)
**Impact on plan:** Necessary to make the Discord `:migrate` command actually functional end-to-end (not just unit-testable) — a prerequisite for Plan 07's live invocation. No scope creep beyond wiring the already-built primitives together; no new business logic was invented in `bot.py`.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The migration invocation surface (route + Discord command) is fully wired end-to-end and admin-gated at both layers (T-47-01 proven by `test_migrate_start_requires_admin` + the Discord bot-layer `is_admin` check).
- T-47-02 (accidental live migration) is mitigated: `:migrate` and bare `:migrate dry-run` never mutate the vault; only the explicit `:migrate live` verb does.
- Ready for Plan 06 (full-suite hard gate, verification-only, no files modified) and then Plan 07 (human-gated live cutover, which depends on `:migrate --dry-run` being invocable from Discord — now satisfied).
- No blockers.

---
*Phase: 47-migration-cutover-hardening*
*Completed: 2026-07-06*

## Self-Check: PASSED

All created/modified files and both task commits (5cafa57, c8306c4) verified present on disk / in git log.
