---
phase: 27-architecture-pivot
plan: "07"
subsystem: test-infrastructure
tags: [pytest, asyncio, pytest-asyncio, discord, gap-closure]
dependency_graph:
  requires: [27-01, 27-02, 27-03, 27-04, 27-05]
  provides: [asyncio_mode_discord_fixed]
  affects: [interfaces/discord/tests, sentinel-core/tests]
tech_stack:
  added: []
  patterns: [pytest-asyncio asyncio_mode=auto via pyproject.toml ini options]
key_files:
  created:
    - interfaces/discord/pyproject.toml
  modified:
    - interfaces/discord/tests/conftest.py
decisions:
  - "asyncio_mode must be set via [tool.pytest.ini_options] in pyproject.toml — config.option assignment in conftest.py fires after pytest-asyncio initializes and has no effect"
metrics:
  duration: "~8 minutes"
  completed: "2026-04-20"
  tasks_completed: 2
  tasks_total: 2
---

# Phase 27 Plan 07: asyncio_mode Gap Closure Summary

**One-liner:** Created `interfaces/discord/pyproject.toml` with `asyncio_mode = "auto"` in `[tool.pytest.ini_options]` and removed the ineffective `config.option.asyncio_mode` assignment from conftest.py — both pytest suites now execute async tests for real (13 discord tests collected, 12 passed 1 skipped; 131 sentinel-core tests all passed).

## What Was Built

The `interfaces/discord` package had no `pyproject.toml`. Its `conftest.py` attempted to configure `asyncio_mode` via `config.option.asyncio_mode = "auto"` inside `pytest_configure`, which fires *after* pytest-asyncio has already initialized its mode. The result: every async test in the discord interface was collected as a coroutine object and reported "passed" without ever being awaited.

This plan:
1. Created `interfaces/discord/pyproject.toml` with `[tool.pytest.ini_options] asyncio_mode = "auto"` — the correct mechanism, matching the pattern already used in `sentinel-core/pyproject.toml`.
2. Removed the ineffective `config.option.asyncio_mode = "auto"` line from `conftest.py`, keeping only the integration marker registration.

## Test Results

### sentinel-core
```
tests/test_modules.py — 5 passed in 5.38s
Full suite — 131 passed, 1 warning in 21.40s
```

The 1 warning is a pre-existing bug in `app/services/output_scanner.py:99` (`coroutine 'OutputScanner._classify' was never awaited`). This is a production code bug, not a test infrastructure issue. It is out of scope for this plan.

### interfaces/discord
```
tests/test_subcommands.py — 9 passed
tests/test_thread_persistence.py — 3 passed, 1 skipped (integration test correctly skipped)
Total: 12 passed, 1 skipped in 0.18s
```

No coroutine warnings. No `PytestUnraisableExceptionWarning`. async test functions are being awaited correctly.

## Commits

| Task | Description | Commit |
|------|-------------|--------|
| 1 | Create interfaces/discord/pyproject.toml + fix conftest.py | 1055e72 |

## Deviations from Plan

### Auto-fixed Issues

None. Plan executed exactly as written.

### Out-of-Scope Discovery

**Pre-existing coroutine bug in output_scanner.py** (sentinel-core full suite, 1 warning):
- `app/services/output_scanner.py:99`: `coroutine 'OutputScanner._classify' was never awaited`
- This is a production code bug, not a test infrastructure issue
- Not caused by this plan's changes
- Logged to deferred-items.md scope for a future fix

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced.

## Self-Check: PASSED

- [x] `interfaces/discord/pyproject.toml` exists with `asyncio_mode = "auto"`
- [x] `interfaces/discord/tests/conftest.py` has 0 occurrences of `config.option.asyncio_mode`
- [x] sentinel-core: `tests/test_modules.py` 5/5 PASSED
- [x] sentinel-core full suite: 131/131 PASSED (exits 0)
- [x] discord: 12 PASSED, 1 SKIPPED (no failures, no coroutine warnings)
- [x] Commit 1055e72 verified in git log
