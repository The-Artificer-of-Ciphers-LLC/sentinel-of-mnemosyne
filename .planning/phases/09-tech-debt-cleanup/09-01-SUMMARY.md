---
phase: 09-tech-debt-cleanup
plan: "01"
subsystem: sentinel-core
tags: [tech-debt, exception-handling, dead-code, pi-adapter]
dependency_graph:
  requires: []
  provides: [D-01-fix, D-03-fix]
  affects: [sentinel-core/app/routes/message.py, sentinel-core/app/clients/pi_adapter.py]
tech_stack:
  added: []
  patterns: [narrowed-except-clause, dead-code-removal]
key_files:
  modified:
    - sentinel-core/app/routes/message.py
    - sentinel-core/app/clients/pi_adapter.py
    - sentinel-core/tests/test_message.py
decisions:
  - "D-01: non-httpx exceptions from Pi call block propagate as 502 (not silently trigger AI fallback)"
  - "D-02: pre-verified in commit 2940af9 before Phase 09 defined — no code change required"
  - "D-03: send_prompt() had zero callers; deletion confirmed safe before removing"
metrics:
  duration: "~5 min"
  completed: "2026-04-11"
  tasks_completed: 3
  files_modified: 3
---

# Phase 09 Plan 01: Tech Debt Cleanup (D-01, D-02, D-03) Summary

**One-liner:** Narrowed bare `except Exception` at Pi call site to `(httpx.RequestError, httpx.HTTPStatusError)` with non-httpx errors surfacing as 502, and removed dead `send_prompt()` method with zero callers.

## What Was Built

### Task 1: Narrow bare except in message.py (D-01)

Replaced the bare `except Exception:` at the Pi harness call site (message.py line 149) with a two-clause handler:

1. `except (httpx.RequestError, httpx.HTTPStatusError) as exc:` — Pi connectivity/protocol failures fall through to AI provider fallback with a `logger.warning`
2. `except Exception as exc:` — Non-httpx protocol errors (e.g., `KeyError` on malformed Pi response) surface as HTTP 502 instead of silently triggering AI fallback

Added `import httpx` to message.py imports. Three new tests cover all three paths.

### Task 2: Verify D-02 pre-applied (no code change)

Confirmed `test_send_messages_hard_timeout_set` asserts `== 90.0` at test_pi_adapter.py:82 and passes. This fix was applied in commit `2940af9` before Phase 09 was defined. No code change required.

### Task 3: Delete dead send_prompt() (D-03)

Removed `send_prompt()` method (lines 27–40 of pi_adapter.py) after confirming zero callers across the entire sentinel-core codebase. The `@retry`-decorated `send_messages()` and `reset_session()` methods are intact. All 6 pi_adapter tests pass.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | c02e1fa | feat(09-01): narrow bare except in Pi call block (D-01) |
| 3 | b3c900a | feat(09-01): delete dead send_prompt() method from PiAdapterClient (D-03) |

Task 2 had no code change (pre-verified).

## Test Results

- `tests/test_message.py`: 28 passed (3 new tests added)
- `tests/test_pi_adapter.py`: 6 passed
- Full suite: 99 passed, 1 pre-existing warning (unrelated)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Added `except Exception as exc` catch for non-httpx Pi errors**
- **Found during:** Task 1 GREEN phase
- **Issue:** Plan specified KeyError should propagate as 502, but narrowing the except to httpx types alone meant KeyError would propagate unhandled to FastAPI (returning 500, not 502). The plan said "exception propagates to the outer except Exception handler and returns HTTP 502" — that outer handler needed to be added explicitly.
- **Fix:** Added `except Exception as exc` clause after the httpx clause, raising `HTTPException(status_code=502)` for any unexpected Pi protocol error.
- **Files modified:** sentinel-core/app/routes/message.py
- **Commit:** c02e1fa

**2. [Rule 3 - Blocking issue] Worktree had stale branch state**
- **Found during:** Task 1 commit
- **Issue:** The `worktree-agent-a940ad83` branch was at `3778e6f` (older commit) while the target base was `1fd9aebf`. Initial edits went to the main repo's files, not the worktree. Required `git reset --soft` on the worktree branch then re-applying all changes to worktree paths.
- **Fix:** Reset worktree branch to `1fd9aebf`, re-applied all changes to worktree-local file paths.
- **Commit:** resolved before commits

## Known Stubs

None.

## Threat Flags

None — changes narrow exception handling at an existing trust boundary. No new network endpoints, auth paths, or schema changes introduced.

## Self-Check: PASSED

- FOUND: sentinel-core/app/routes/message.py
- FOUND: sentinel-core/app/clients/pi_adapter.py
- FOUND: .planning/phases/09-tech-debt-cleanup/09-01-SUMMARY.md
- FOUND commit c02e1fa (D-01 narrow except)
- FOUND commit b3c900a (D-03 delete send_prompt)
