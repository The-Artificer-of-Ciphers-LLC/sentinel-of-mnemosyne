---
phase: 35-foundry-vtt-event-ingest
plan: "01"
subsystem: pathfinder-module + discord-interface
tags: [tdd, red-phase, foundry-vtt, testing]
dependency_graph:
  requires: []
  provides:
    - modules/pathfinder/tests/test_foundry.py (6 RED stubs for FVT-01/02)
    - interfaces/discord/tests/test_discord_foundry.py (2 RED stubs for FVT-03)
    - interfaces/discord/tests/conftest.py (gold() classmethod in _ColorStub)
  affects:
    - Wave 1 plan 35-02 (must turn test_foundry.py GREEN)
    - Wave 2 plan 35-03 (must turn test_discord_foundry.py GREEN)
tech_stack:
  added: []
  patterns:
    - Function-scope imports inside each test body (Phase 33/34 Wave 0 pattern)
    - asyncio_mode=auto — no @pytest.mark.asyncio decorator
    - L-5 rule: all discord stubs in conftest.py, never per-file
key_files:
  created:
    - modules/pathfinder/tests/test_foundry.py
    - interfaces/discord/tests/test_discord_foundry.py
  modified:
    - interfaces/discord/tests/conftest.py
decisions:
  - "RED failures on test_foundry.py are ModuleNotFoundError (rapidfuzz not installed locally — container dep). Same failure mode as all other pathfinder tests locally. Not a SyntaxError. Acceptable RED state."
  - "discord suite (50 tests) still passes after conftest.py gold() addition — no regressions"
metrics:
  duration: "~8 minutes"
  completed: "2026-04-25"
  tasks_completed: 3
  files_changed: 3
---

# Phase 35 Plan 01: Wave 0 RED Test Stubs Summary

**One-liner:** RED stubs for 8 Foundry VTT tests (6 route/LLM + 2 embed) plus gold() color classmethod for criticalSuccess embed.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Extend _ColorStub with gold() classmethod | 37daf84 | interfaces/discord/tests/conftest.py |
| 2 | Write RED stubs — test_foundry.py (FVT-01, FVT-02) | a015a72 | modules/pathfinder/tests/test_foundry.py |
| 3 | Write RED stubs — test_discord_foundry.py (FVT-03) | 345f8a8 | interfaces/discord/tests/test_discord_foundry.py |

## Verification Results

### RED Gate (all 8 tests fail, none pass)

**test_foundry.py (6 tests):**
- test_roll_event_accepted — FAILED: ModuleNotFoundError (rapidfuzz, container dep)
- test_auth_rejected — FAILED: ModuleNotFoundError (rapidfuzz, container dep)
- test_invalid_payload — FAILED: ModuleNotFoundError (rapidfuzz, container dep)
- test_notify_dispatched — FAILED: ModuleNotFoundError (rapidfuzz, container dep)
- test_llm_fallback — FAILED: ModuleNotFoundError (rapidfuzz, container dep)
- test_registration_payload — FAILED: ModuleNotFoundError (rapidfuzz, container dep)

**test_discord_foundry.py (2 tests):**
- test_embed_critical_success — FAILED: AttributeError: module 'bot' has no attribute 'build_foundry_roll_embed'
- test_embed_hidden_dc — FAILED: AttributeError: module 'bot' has no attribute 'build_foundry_roll_embed'

No SyntaxErrors. No collection failures.

### Regression Gate

- interfaces/discord test suite (--ignore=test_discord_foundry.py): 50 passed, 0 failed

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None — this plan IS the stub phase. All stubs are intentional RED tests. Implementation lands in Waves 1-2 (plans 35-02, 35-03).

## Threat Flags

None — test files introduce no new network endpoints, auth paths, or schema changes at trust boundaries. Test env vars use `setdefault` pattern (safe — never overwrite real env in container context).

## Self-Check: PASSED

- [x] interfaces/discord/tests/conftest.py — modified, gold() present (1 match)
- [x] modules/pathfinder/tests/test_foundry.py — created, 6 tests collected
- [x] interfaces/discord/tests/test_discord_foundry.py — created, 2 tests collected
- [x] Commit 37daf84 — conftest gold()
- [x] Commit a015a72 — test_foundry.py
- [x] Commit 345f8a8 — test_discord_foundry.py
