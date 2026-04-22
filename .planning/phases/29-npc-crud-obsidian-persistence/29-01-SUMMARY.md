---
phase: 29-npc-crud-obsidian-persistence
plan: "01"
subsystem: pathfinder-module
tags: [testing, tdd, npc, wave-0, nyquist]
dependency_graph:
  requires: []
  provides:
    - modules/pathfinder/tests/test_npc.py
    - interfaces/discord/tests/test_subcommands.py (extended)
  affects:
    - Wave 1 plans (29-02 through 29-05) — unblocked
    - Wave 1 bot dispatch plan (29-06) — unblocked
tech_stack:
  added: []
  patterns:
    - "xfail stub tests: pytest.mark.xfail allows collection without blocking CI"
    - "ASGITransport + AsyncClient: ASGI in-process testing without server startup"
    - "env vars before import: OBSIDIAN_BASE_URL set before any app.main import"
    - "patch app.routes.npc.*: module-level mocks for Obsidian client and LLM helpers"
key_files:
  created:
    - modules/pathfinder/tests/test_npc.py
  modified:
    - interfaces/discord/tests/test_subcommands.py
decisions:
  - "xfail on all Wave 0 stubs — tests are red by design; Wave 2 removes the marks as endpoints land"
  - "patch app.routes.npc.obsidian not app.main — routes module owns the client instance"
metrics:
  duration: "106 seconds"
  completed: "2026-04-22T02:42:47Z"
  tasks_completed: 2
  files_modified: 2
---

# Phase 29 Plan 01: Wave 0 NPC Test Scaffolding Summary

Wave 0 Nyquist compliance stubs — 9 xfail NPC endpoint tests and 2 xfail bot dispatch tests created before any implementation.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create test_npc.py with 9 stub tests (all red) | 32fc5e1 | modules/pathfinder/tests/test_npc.py |
| 2 | Extend test_subcommands.py with _pf_dispatch tests | 3967910 | interfaces/discord/tests/test_subcommands.py |

## Verification Results

**NPC tests:** 9 collected, 9 xfailed, 0 errors
```
============================== 9 xfailed in 0.49s ==============================
```

**Discord subcommand tests:** 9 passed, 2 xfailed, 0 errors
```
========================= 9 passed, 2 xfailed in 0.07s =========================
```

## Test Coverage

### modules/pathfinder/tests/test_npc.py (new)

| Test | Requirement | Behavior Covered |
|------|-------------|-----------------|
| test_npc_create_success | NPC-01 | POST /npc/create returns 200 + slug on new NPC |
| test_npc_create_collision | NPC-01 | POST /npc/create returns 409 when note exists |
| test_npc_update_identity_fields | NPC-02 | POST /npc/update reads/LLM-patches/puts note |
| test_npc_show_returns_fields | NPC-03 | POST /npc/show returns name, level, ancestry, class, slug |
| test_npc_show_not_found | NPC-03 | POST /npc/show returns 404 when absent |
| test_npc_relate_valid | NPC-04 | POST /npc/relate returns 200 for valid relation type |
| test_npc_relate_invalid_type | NPC-04 | POST /npc/relate returns 422 for "enemies-with" |
| test_npc_import_basic | NPC-05 | POST /npc/import returns imported_count=2 for 2 actors |
| test_npc_import_collision_skipped | NPC-05 | POST /npc/import skipped list populated on collision |

### interfaces/discord/tests/test_subcommands.py (extended)

| Test | Requirement | Behavior Covered |
|------|-------------|-----------------|
| test_pf_dispatch_create | NPC-01 (bot) | :pf npc create routes to post_to_module("npc/create", ...) |
| test_pf_dispatch_relate_invalid | NPC-04 (bot) | :pf npc relate enemies-with returns error without calling module |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

All 11 tests are intentional xfail stubs. The xfail markers are the deliverable for Wave 0 — they will be removed as Wave 1 and Wave 2 plans implement the endpoints.

## Self-Check: PASSED

- modules/pathfinder/tests/test_npc.py: FOUND
- interfaces/discord/tests/test_subcommands.py: contains test_pf_dispatch_create and test_pf_dispatch_relate_invalid
- Commit 32fc5e1: FOUND
- Commit 3967910: FOUND
