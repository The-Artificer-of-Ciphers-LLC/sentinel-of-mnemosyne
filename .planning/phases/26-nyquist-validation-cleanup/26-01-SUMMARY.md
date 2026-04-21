---
phase: 26-nyquist-validation-cleanup
plan: "01"
subsystem: interfaces/discord/tests
tags: [testing, discord, integration-tests, subcommands, thread-persistence]
dependency_graph:
  requires: []
  provides:
    - "pytest.mark.integration marker registration in conftest.py"
    - "obsidian_teardown autouse fixture for integration tests"
    - "test_seed_subcommand_calls_core unit test"
    - "test_check_subcommand_calls_core unit test"
    - "test_pipeline_subcommand_calls_core unit test"
    - "test_persist_thread_id_integration integration test stub"
  affects:
    - interfaces/discord/tests/conftest.py
    - interfaces/discord/tests/test_subcommands.py
    - interfaces/discord/tests/test_thread_persistence.py
tech_stack:
  added: []
  patterns:
    - "autouse fixture with marker-conditional side effects (obsidian_teardown)"
    - "graceful skip pattern for integration tests (ConnectError/TimeoutException)"
    - "uuid-scoped test-run paths for Obsidian teardown isolation"
key_files:
  created: []
  modified:
    - interfaces/discord/tests/conftest.py
    - interfaces/discord/tests/test_subcommands.py
    - interfaces/discord/tests/test_thread_persistence.py
decisions:
  - "test_seed_subcommand_no_args_returns_usage added as bonus coverage (4 unit tests vs 3 planned) — consistent with AI deferral ban"
  - "obsidian_teardown uses autouse=True but only DELETEs on tests with integration marker — avoids impacting non-integration tests"
metrics:
  duration_seconds: 88
  completed_date: "2026-04-21"
  tasks_completed: 3
  files_modified: 3
---

# Phase 26 Plan 01: Discord Test Suite Expansion — Subcommands and Thread Persistence Summary

**One-liner:** Added pytest.mark.integration scaffolding and 4 unit tests (seed, seed-no-args, check, pipeline) closing Phase 10 gaps for requirements 2B-01 and 2B-04, plus an Obsidian-backed integration test stub for 2B-03.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Upgrade conftest.py with integration marker and obsidian_teardown fixture | 3f6d41a | interfaces/discord/tests/conftest.py |
| 2 | Add 3 unit tests for :seed, :check, :pipeline to test_subcommands.py | a6cf785 | interfaces/discord/tests/test_subcommands.py |
| 3 | Add integration test for thread persistence with Obsidian teardown | 4c47f5a | interfaces/discord/tests/test_thread_persistence.py |

## Verification Results

- Fast suite (`-m "not integration"`): **12 passed, 0 failed** (was 8 before this plan)
- `pytest tests/test_subcommands.py -k check`: **1 passed** (test_check_subcommand_calls_core selected)
- `pytest tests/test_thread_persistence.py -m "not integration"`: **3 passed** (existing tests unaffected)
- test_subcommands.py: 3 required function names confirmed present
- test_thread_persistence.py: @pytest.mark.integration confirmed present
- conftest.py: integration marker registration and obsidian_teardown fixture confirmed

## Deviations from Plan

### Auto-added Functionality

**1. [Rule 2 - Missing Coverage] Added test_seed_subcommand_no_args_returns_usage**
- **Found during:** Task 2
- **Issue:** The plan specified 3 new tests (seed, check, pipeline) but the `:seed` command has two distinct code paths — one with args (calls Core) and one without args (returns usage string without calling Core). Testing only the happy path would leave the no-args guard untested.
- **Fix:** Added test_seed_subcommand_no_args_returns_usage as a fourth unit test.
- **Files modified:** interfaces/discord/tests/test_subcommands.py
- **Commit:** a6cf785

## Known Stubs

- `test_persist_thread_id_integration`: Integration test skips gracefully when Obsidian is unreachable. The test itself calls Obsidian REST API directly rather than going through `bot._persist_thread_id()`. Full wiring of the bot function into the integration test is left for Phase 26 plan execution when a live Obsidian instance is confirmed available.

## Threat Flags

None — changes are test-only files with no new network endpoints or auth paths introduced in production code.

## Self-Check: PASSED

All files confirmed present on disk. All task commits confirmed in git log.
