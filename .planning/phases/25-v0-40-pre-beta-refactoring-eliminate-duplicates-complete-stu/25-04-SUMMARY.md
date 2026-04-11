---
phase: 25-v0-40-pre-beta-refactoring-eliminate-duplicates-complete-stu
plan: "04"
subsystem: sentinel-core/clients, interfaces/imessage, interfaces/discord
tags: [refactor, tdd, retry-config, obsidian-client, imessage, discord, test-migration]
dependency_graph:
  requires: []
  provides:
    - retry_config.py shared retry constants (RETRY_STOP, RETRY_WAIT, RETRY_ATTEMPTS, HARD_TIMEOUT_SECONDS)
    - ObsidianClient._safe_request() graceful-failure helper
    - iMessage attributedBody decode + Full Disk Access guard
    - interfaces/discord/tests/ and interfaces/imessage/tests/ with passing test suites
  affects:
    - sentinel-core/app/clients/pi_adapter.py
    - sentinel-core/app/clients/litellm_provider.py
    - sentinel-core/app/clients/obsidian.py
    - interfaces/imessage/bridge.py
tech_stack:
  added:
    - plistlib (stdlib) for NSKeyedArchiver attributedBody decoding
  patterns:
    - _safe_request() coroutine wrapper pattern for graceful degradation
    - Centralized retry constants imported by all HTTP clients
    - Interface-level test directories with conftest.py asyncio_mode=auto
key_files:
  created:
    - sentinel-core/app/clients/retry_config.py
    - sentinel-core/tests/test_retry_config.py
    - interfaces/imessage/tests/conftest.py
    - interfaces/imessage/tests/test_bridge.py
    - interfaces/discord/tests/conftest.py
    - interfaces/discord/tests/test_thread_persistence.py
    - interfaces/discord/tests/test_subcommands.py
  modified:
    - sentinel-core/app/clients/pi_adapter.py
    - sentinel-core/app/clients/litellm_provider.py
    - sentinel-core/app/clients/obsidian.py
    - interfaces/imessage/bridge.py
  deleted:
    - sentinel-core/tests/test_bot_thread_persistence.py (moved to interfaces/discord/tests/)
decisions:
  - conftest.py-based asyncio_mode=auto preferred over __init__.py packages for interface tests — avoids pytest package name collision when both discord/tests and imessage/tests are collected together
  - _safe_request uses inner async helper functions rather than lambdas for coroutine capture — cleaner, avoids late-binding issues
  - __init__.py omitted from interface test directories — rootdir-relative collection avoids tests.conftest name collision between two independent test suites
metrics:
  duration: "~25 minutes"
  completed: "2026-04-11"
  tasks_completed: 3
  files_created: 7
  files_modified: 4
  files_deleted: 1
requirements_closed: [PROV-03, IFACE-05, MEM-01, 2B-03, 2B-04]
---

# Phase 25 Plan 04: Cluster A Small Refactors Summary

Centralized retry configuration, extracted ObsidianClient._safe_request() helper, fixed iMessage attributedBody decoding with Full Disk Access guard, and migrated misplaced Discord thread tests to their correct interface directory.

## Tasks Completed

| Task | Name | Commit | Status |
|------|------|--------|--------|
| 25-04-01 | Create retry_config.py; update pi_adapter + litellm_provider imports | 7cb5c61 | GREEN |
| 25-04-02 | Extract ObsidianClient._safe_request; refactor 5 graceful methods | 0e63407 | GREEN |
| 25-04-03 | Fix iMessage attributedBody decoding + Full Disk Access guard; move thread tests | 1a324f7 | GREEN |

## Test Results

- sentinel-core pytest: **121 passed**, 1 warning (0 failures, 0 regressions)
- interfaces/discord/tests/: **8 passed** (3 thread persistence + 5 subcommand routing)
- interfaces/imessage/tests/: **4 passed** (attributedBody decode tests)
- Total new tests: **17** (6 retry_config + 5 _safe_request + 4 bridge + behavior preserved in existing suites)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] pytest package name collision for interface tests**
- **Found during:** Task 3 — when running `interfaces/discord/tests/` and `interfaces/imessage/tests/` together
- **Issue:** Both test directories had `__init__.py`, making them packages named `tests`. pytest's `ImportPathMismatchError` prevented collecting both directories in a single run.
- **Fix:** Removed `__init__.py` from both interface test directories (rootdir-relative collection); added `conftest.py` to each with `asyncio_mode=auto` for async test support.
- **Files modified:** Deleted `interfaces/discord/tests/__init__.py`, `interfaces/imessage/tests/__init__.py`; added `conftest.py` to each.
- **Commit:** 1a324f7

## TDD Gate Compliance

All three tasks followed RED → GREEN → REFACTOR sequence:

1. `test(25-04)` gate: tests written and confirmed FAILING before implementation
2. `feat(25-04)` gate: implementation written and tests confirmed PASSING
3. Full sentinel-core suite confirmed GREEN after each task

Note: commits use `feat(25-04)` rather than separate `test(25-04)` prefixes because TDD was inline (RED run confirmed, then implementation committed atomically per task). RED confirmation is documented in execution log above.

## Success Criteria Verification

- [x] retry_config.py exports RETRY_STOP, RETRY_WAIT, HARD_TIMEOUT_SECONDS, RETRY_ATTEMPTS with correct values
- [x] pi_adapter.py and litellm_provider.py use RETRY_STOP/RETRY_WAIT from retry_config — no literal `stop_after_attempt(3)` in either file
- [x] ObsidianClient has `_safe_request()`; all 5 graceful-failure methods delegate to it; write_session_summary() still raises
- [x] `_decode_attributed_body()` in bridge.py uses plistlib per D-04 (no imessage_reader dependency)
- [x] Full Disk Access guard present in bridge.py run_bridge() per D-05
- [x] poll_new_messages() falls back to attributedBody when text column is NULL
- [x] interfaces/discord/tests/test_thread_persistence.py, test_subcommands.py all pass GREEN
- [x] interfaces/imessage/tests/test_bridge.py all pass GREEN
- [x] sentinel-core/tests/test_bot_thread_persistence.py deleted
- [x] sentinel-core pytest suite exits 0 (121 passed, no regressions)
- [x] DUP-02, DUP-03, STUB-04, STUB-05 resolved

## Known Stubs

None. All implementations are complete and wired. No placeholder values or TODO comments introduced.

## Threat Flags

No new security-relevant surface introduced. All changes are refactors within existing trust boundaries.
- retry_config.py: constants only, no network surface
- _safe_request: swallows exceptions by design (T-25-04-02 accepted disposition)
- attributedBody decoding: plistlib.loads() wrapped in try/except per T-25-04-03 mitigate disposition
- Full Disk Access guard: fail-closed on PermissionError per T-25-04-04 mitigate disposition

## Self-Check: PASSED

| Item | Status |
|------|--------|
| sentinel-core/app/clients/retry_config.py | FOUND |
| sentinel-core/tests/test_retry_config.py | FOUND |
| sentinel-core/app/clients/obsidian.py | FOUND |
| interfaces/imessage/bridge.py | FOUND |
| interfaces/imessage/tests/test_bridge.py | FOUND |
| interfaces/discord/tests/test_thread_persistence.py | FOUND |
| interfaces/discord/tests/test_subcommands.py | FOUND |
| sentinel-core/tests/test_bot_thread_persistence.py | DELETED (correct) |
| commit 7cb5c61 | FOUND |
| commit 0e63407 | FOUND |
| commit 1a324f7 | FOUND |
