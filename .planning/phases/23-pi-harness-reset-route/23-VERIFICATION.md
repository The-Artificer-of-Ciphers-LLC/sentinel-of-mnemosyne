---
phase: 23-pi-harness-reset-route
verified: 2026-04-11T14:16:30Z
re_verified: 2026-04-11T19:00:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
resolution: >
  reset_session() was present in pi_adapter.py as a duplicate definition (two versions in the same class).
  The graceful version (catches exceptions, logs warning, never raises) was correct and retained.
  The strict duplicate (raises on non-2xx) was removed. SC-3 is now fully satisfied.
---

# Phase 23: Pi Harness /reset Route Verification Report

**Phase Goal:** Add a `POST /reset` route to `bridge.ts` so that `pi_adapter.py`'s reset-after-exchange call succeeds (200) instead of silently returning 404. Without this, the Pi harness accumulates full session history across every exchange, risking LM Studio RAM exhaustion after approximately 5 calls.
**Verified:** 2026-04-11T14:16:30Z
**Re-verified:** 2026-04-11T19:00:00Z
**Status:** passed
**Re-verification:** Yes — SC-3 resolved by removing duplicate reset_session() definition

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | POST /reset returns HTTP 200 with `{ status: 'ok' }` | ✓ VERIFIED | `app.post('/reset', ...)` at bridge.ts:85 returns `{ status: 'ok' }`; vitest confirms 200 response |
| 2  | Pi subprocess receives `{"type":"new_session"}` on each reset call | ✓ VERIFIED | `sendReset()` at pi-adapter.ts:167-170 writes `JSON.stringify({ type: 'new_session' }) + '\n'` to `piProcess.stdin`; vitest asserts `sendReset` called exactly once per request |
| 3  | pi_adapter.py reset_session() confirmed calling correct URL | ✓ VERIFIED | `reset_session()` at pi_adapter.py:36 calls `f"{self._harness_url}/reset"`; duplicate strict definition removed; 6 pytest tests pass |
| 4  | configurable timeout_s restored with PI_TIMEOUT_S env var support | ✓ VERIFIED | `PI_TIMEOUT_S = float(os.getenv("PI_TIMEOUT_S", "190"))` at line 11; `timeout=PI_TIMEOUT_S` at line 31; hardcoded `timeout=190.0` is gone |
| 5  | Integration test for /reset passes | ✓ VERIFIED | vitest: `Tests 2 passed (2)` — bridge.test.ts covers POST /reset status code and sendReset() call count |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pi-harness/src/pi-adapter.ts` | sendReset() export | ✓ VERIFIED | `export function sendReset()` at line 167; no-op guard for null piProcess/stdin |
| `pi-harness/src/bridge.ts` | POST /reset route + buildApp() export | ✓ VERIFIED | `export function buildApp()` at line 41; `app.post('/reset', ...)` at line 85 |
| `pi-harness/src/bridge.test.ts` | vitest suite | ✓ VERIFIED | 2 tests passing — 200 status and sendReset call count |
| `pi-harness/vitest.config.ts` | vitest config with passWithNoTests | ✓ VERIFIED | Created as auto-fix for vitest 2.x exit-code-1 behavior |
| `sentinel-core/app/clients/pi_adapter.py` | PI_TIMEOUT_S module-level + no hardcoded 190.0 | ✓ VERIFIED | Line 11: `PI_TIMEOUT_S = float(os.getenv("PI_TIMEOUT_S", "190"))`. No `timeout=190.0` literal present. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| bridge.ts POST /reset | sendReset() | direct call | ✓ WIRED | `app.post('/reset', ...)` calls `sendReset()` |
| sendReset() | piProcess.stdin | `piProcess.stdin.write(...)` | ✓ WIRED | Writes `{"type":"new_session"}\n` |
| pi_adapter.py send_prompt() | PI_TIMEOUT_S | `timeout=PI_TIMEOUT_S` | ✓ WIRED | Module-level constant used in httpx timeout |
| pi_adapter.py reset_session() | bridge.ts /reset | `f"{self._harness_url}/reset"` | ✓ WIRED | `reset_session()` at line 36 calls `f"{self._harness_url}/reset"` |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| vitest suite green (2 tests) | `cd pi-harness && NODE_ENV=test npm test` | Tests 2 passed (2) | ✓ PASS |
| PI_TIMEOUT_S present (>= 2 matches) | `grep -n 'PI_TIMEOUT_S' pi_adapter.py` | 2 matches (line 11 + line 31) | ✓ PASS |
| No hardcoded timeout=190.0 | `grep 'timeout=190.0' pi_adapter.py` | 0 matches | ✓ PASS |
| os.getenv with default 190 | `grep 'os.getenv.*PI_TIMEOUT_S.*190'` | 1 match (line 11) | ✓ PASS |
| sendReset export exists | `grep 'export function sendReset'` | 1 match (line 167) | ✓ PASS |
| new_session RPC message | `grep 'new_session'` | 1 match (line 169) | ✓ PASS |
| POST /reset route registered | `grep "'/reset'" bridge.ts` | 1 match (line 85) | ✓ PASS |
| buildApp() exported | `grep 'export function buildApp'` | 1 match (line 41) | ✓ PASS |
| pi_adapter.py pi tests pass | `python3 -m pytest test_pi_adapter.py -x -q` | 6 passed | ✓ PASS |
| reset_session() URL correct | `grep 'harness_url.*reset'` | 1 match (line 46) | ✓ PASS |

### Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| CORE-07 | Pi session reset mechanism + Docker Compose include | ✓ SATISFIED | POST /reset returns 200; Pi receives new_session; vitest confirms; PI_TIMEOUT_S wired |

### Anti-Patterns Found

None detected. No TODOs, stubs, empty handlers, or hardcoded empty returns in modified files.

### Gaps Summary

None. All 5 success criteria verified. SC-3 was resolved by removing a duplicate `reset_session()` definition that had silently shadowed the correct graceful implementation. The method at line 36 calls `f"{self._harness_url}/reset"` as required.

---

_Verified: 2026-04-11T14:16:30Z_
_Re-verified: 2026-04-11T19:00:00Z — SC-3 resolved, duplicate reset_session() removed_
_Verifier: Claude (gsd-verifier / gsd-quick)_
