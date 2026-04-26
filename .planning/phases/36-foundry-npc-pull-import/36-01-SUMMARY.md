---
phase: 36-foundry-npc-pull-import
plan: 01
subsystem: pathfinder-module
tags: [tdd, red-phase, npcs, foundry-vtt, fvt-04]
dependency_graph:
  requires:
    - modules/pathfinder/tests/test_foundry.py  # env setup + ASGITransport pattern
    - modules/pathfinder/tests/test_npc.py      # obsidian mock pattern
    - modules/pathfinder/pyproject.toml         # asyncio_mode = auto confirmed
    - modules/pathfinder/app/main.py            # REGISTRATION_PAYLOAD structure
  provides:
    - modules/pathfinder/tests/test_npcs.py     # 7 RED test stubs for FVT-04a..f
  affects: []
tech_stack:
  added: []
  patterns:
    - function-scope app import (collection safe before Wave 1 routes exist)
    - app.routes.npcs.obsidian patch target (plural module, distinct from npc.py)
    - AsyncMock side_effect list for sequential Obsidian reads
key_files:
  created:
    - modules/pathfinder/tests/test_npcs.py
  modified: []
decisions:
  - Function-scope imports used so pytest collection passes before app.routes.npcs exists (Phase 33-01 pattern reused)
  - path-traversal test uses raw "../" path rather than percent-encoded form — httpx normalizes URLs; the route guard must handle both forms
  - test_list_npcs_obsidian_down is structurally identical to test_list_npcs_empty — the distinction exists at the mock level to document the 200-not-503 contract explicitly
metrics:
  duration: "~5 minutes"
  completed: "2026-04-26T13:15:56Z"
  tasks_completed: 1
  files_created: 1
  files_modified: 0
---

# Phase 36 Plan 01: Wave 0 RED TDD Stubs for FVT-04 Summary

**One-liner:** 7 RED test stubs locking GET /npcs/ list endpoint and GET /npcs/{slug}/foundry-actor actor export contract before implementation.

## What Was Built

Created `modules/pathfinder/tests/test_npcs.py` with 7 failing test functions covering the full FVT-04 requirement set:

| Test | FVT ID | Contract |
|------|--------|----------|
| `test_list_npcs_success` | FVT-04a | 200 + list of 2 NPC dicts with slug/name/level/ancestry |
| `test_list_npcs_empty` | FVT-04b | 200 + empty list when vault is empty |
| `test_list_npcs_obsidian_down` | FVT-04c | 200 + empty list (NOT 503) when Obsidian unreachable |
| `test_get_foundry_actor_success` | FVT-04d | 200 + Foundry actor JSON with name/system/type="npc" |
| `test_get_foundry_actor_not_found` | FVT-04e | 404 when slug not in vault |
| `test_get_foundry_actor_invalid_slug` | FVT-04f | 400 on path-traversal slug |
| `test_registration_payload` | FVT-04 | npcs/ and npcs/{slug}/foundry-actor in REGISTRATION_PAYLOAD |

## RED Gate Verification

All 7 tests fail at runtime (ModuleNotFoundError: app.routes.npcs does not exist). Pytest collects all 7 without collection errors — function-scope imports prevent collection-time failure.

```
0 passed, 7 failed
```

## Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Write 7 RED test stubs for FVT-04a..f | a677685 | modules/pathfinder/tests/test_npcs.py |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — this is a test-only plan. No production stubs exist.

## Threat Flags

None — test file only; no new network endpoints, auth paths, or schema changes introduced.

## Self-Check: PASSED

- `modules/pathfinder/tests/test_npcs.py` exists: FOUND
- Commit `a677685` exists: FOUND
- 7 test functions: CONFIRMED (grep -c "def test_" = 7)
- All 7 fail RED: CONFIRMED (0 passed, 7 failed)
- Collection succeeds: CONFIRMED (no collection errors)
