---
phase: 27-architecture-pivot
plan: "04"
subsystem: discord-interface
tags: [discord, slash-command, rename, path-b]
dependency_graph:
  requires: []
  provides: [discord-slash-command-sen]
  affects: [interfaces/discord/bot.py]
tech_stack:
  added: []
  patterns: [slash-command-rename]
key_files:
  created: []
  modified:
    - interfaces/discord/bot.py
    - interfaces/discord/tests/test_subcommands.py
    - interfaces/discord/tests/test_thread_persistence.py
decisions:
  - "handle_sentask_subcommand internal function name preserved (exported in __all__, imported by tests)"
  - "Four targeted line edits — no structural changes to bot logic"
metrics:
  duration: "5 minutes"
  completed: "2026-04-21T01:24:47Z"
  tasks_completed: 1
  tasks_total: 1
  files_changed: 3
---

# Phase 27 Plan 04: Discord /sentask → /sen Rename Summary

Renamed Discord slash command from `/sentask` to `/sen` in bot.py with four targeted line edits; internal handler `handle_sentask_subcommand` preserved unchanged; fixed two pre-existing test breakages introduced during the Phase 25 `shared.sentinel_client` refactor.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Rename /sentask to /sen in bot.py (4 targeted edits) | 2fc1e84 | interfaces/discord/bot.py, tests/test_subcommands.py, tests/test_thread_persistence.py |

## Acceptance Criteria Verification

- `grep 'name="sentask"' interfaces/discord/bot.py` → 0 lines (PASS)
- `grep 'name="sen"' interfaces/discord/bot.py` → 1 line (PASS)
- `grep 'async def sen(' interfaces/discord/bot.py` → 1 line (PASS)
- `grep 'async def sentask(' interfaces/discord/bot.py` → 0 lines (PASS)
- `grep "inside a /sentask thread" interfaces/discord/bot.py` → 0 lines (PASS)
- `grep "inside a /sen thread" interfaces/discord/bot.py` → 1 line (PASS)
- `grep "handle_sentask_subcommand" interfaces/discord/bot.py` → 3 lines (PASS — __all__ export + function definition + internal call site)
- Discord tests: 8 passed, 0 failed (PASS)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Missing repo root in test sys.path**
- **Found during:** Task 1 verification
- **Issue:** Both test files added `interfaces/discord` to `sys.path` but not the repo root. The Phase 25 migration moved `SentinelCoreClient` to `shared/sentinel_client.py` (repo root), making `bot.py` import `from shared.sentinel_client import SentinelCoreClient`. Tests failed with `ModuleNotFoundError: No module named 'shared'`.
- **Fix:** Added repo root path insertion (`os.path.join(os.path.dirname(__file__), "..", "..", "..")`) to both test files before the `import bot` statement.
- **Files modified:** interfaces/discord/tests/test_subcommands.py, interfaces/discord/tests/test_thread_persistence.py
- **Commit:** 2fc1e84

**2. [Rule 1 - Bug] Test patching stale `bot.call_core` symbol**
- **Found during:** Task 1 verification
- **Issue:** `test_subcommands.py` patched `bot.call_core` and `bot.call_core` in two tests. The Phase 25 refactor renamed the function to `_call_core` (private, via `SentinelCoreClient`). Tests raised `AttributeError: module 'bot' does not have attribute 'call_core'`.
- **Fix:** Updated both `patch("bot.call_core", ...)` calls to `patch("bot._call_core", ...)`.
- **Files modified:** interfaces/discord/tests/test_subcommands.py
- **Commit:** 2fc1e84

## Known Stubs

None.

## Threat Flags

None — this plan only renames a user-facing slash command string. No new network endpoints, auth paths, or trust boundaries introduced.

## Self-Check: PASSED

- interfaces/discord/bot.py — FOUND
- interfaces/discord/tests/test_subcommands.py — FOUND
- interfaces/discord/tests/test_thread_persistence.py — FOUND
- Commit 2fc1e84 — FOUND
