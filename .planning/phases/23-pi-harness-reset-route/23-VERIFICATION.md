---
phase: 23-pi-harness-reset-route
verified: 2026-04-11T14:16:30Z
status: human_needed
score: 4/5 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Confirm pi_adapter.py has a reset_session() method (or equivalent) that calls {harness_url}/reset"
    expected: "Method exists and constructs URL as f\"{self._harness_url}/reset\""
    why_human: "reset_session() is absent from pi_adapter.py on this branch. The SUMMARY documents this as a known deviation: the method was removed in a prior phase. However, SC-3 ('pi_adapter.py reset_session() confirmed calling correct URL') requires this to be confirmed. A human must decide whether this SC is satisfied by the bridge.ts /reset route alone, or whether pi_adapter.py still needs a reset_session() caller."
---

# Phase 23: Pi Harness /reset Route Verification Report

**Phase Goal:** Add a `POST /reset` route to `bridge.ts` so that `pi_adapter.py`'s reset-after-exchange call succeeds (200) instead of silently returning 404. Without this, the Pi harness accumulates full session history across every exchange, risking LM Studio RAM exhaustion after approximately 5 calls.
**Verified:** 2026-04-11T14:16:30Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | POST /reset returns HTTP 200 with `{ status: 'ok' }` | ✓ VERIFIED | `app.post('/reset', ...)` at bridge.ts:85 returns `{ status: 'ok' }`; vitest confirms 200 response |
| 2  | Pi subprocess receives `{"type":"new_session"}` on each reset call | ✓ VERIFIED | `sendReset()` at pi-adapter.ts:167-170 writes `JSON.stringify({ type: 'new_session' }) + '\n'` to `piProcess.stdin`; vitest asserts `sendReset` called exactly once per request |
| 3  | pi_adapter.py reset_session() confirmed calling correct URL | ? UNCERTAIN | `reset_session()` method is absent from `pi_adapter.py`. Method was removed in a prior phase. `_harness_url` is present but no reset path is constructed anywhere in the file. Requires human decision. |
| 4  | configurable timeout_s restored with PI_TIMEOUT_S env var support | ✓ VERIFIED | `PI_TIMEOUT_S = float(os.getenv("PI_TIMEOUT_S", "190"))` at line 11; `timeout=PI_TIMEOUT_S` at line 31; hardcoded `timeout=190.0` is gone |
| 5  | Integration test for /reset passes | ✓ VERIFIED | vitest: `Tests 2 passed (2)` — bridge.test.ts covers POST /reset status code and sendReset() call count |

**Score:** 4/5 truths verified (1 requires human confirmation)

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
| pi_adapter.py reset_session() | bridge.ts /reset | `f"{self._harness_url}/reset"` | ? ABSENT | Method does not exist in current file |

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
| reset_session() URL correct | `grep 'harness_url.*reset'` | 0 matches | ✗ FAIL (method absent) |

### Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| CORE-07 | Pi session reset mechanism + Docker Compose include | ✓ SATISFIED | POST /reset returns 200; Pi receives new_session; vitest confirms; PI_TIMEOUT_S wired |

### Anti-Patterns Found

None detected. No TODOs, stubs, empty handlers, or hardcoded empty returns in modified files.

### Human Verification Required

#### 1. SC-3: pi_adapter.py reset_session() calling correct URL

**Test:** Open `sentinel-core/app/clients/pi_adapter.py` and confirm whether `reset_session()` exists or whether the intent is that it will be re-added.

**Expected:** Either (a) `reset_session()` exists with URL `f"{self._harness_url}/reset"`, OR (b) a deliberate decision exists that pi_adapter.py does not need a reset_session() method at all (because reset is triggered differently).

**Why human:** The method is absent. The SUMMARY says "the method was removed in a prior phase" and notes "no code change needed." But SC-3 from the ROADMAP contract explicitly says "pi_adapter.py reset_session() confirmed calling correct URL." This cannot be verified programmatically — a human must confirm whether SC-3 is satisfied by the bridge.ts /reset route alone, or whether pi_adapter.py needs the reset_session() caller re-added.

**To accept the deviation and close SC-3 as satisfied, add to VERIFICATION.md frontmatter:**

```yaml
overrides:
  - must_have: "pi_adapter.py reset_session() confirmed calling correct URL"
    reason: "reset_session() was removed in a prior phase; POST /reset route is ready in bridge.ts for when the caller is re-added or called via another code path"
    accepted_by: "<your-name>"
    accepted_at: "<ISO timestamp>"
```

### Gaps Summary

One success criterion from the ROADMAP contract cannot be confirmed programmatically:

SC-3 requires `pi_adapter.py reset_session()` to be present and calling `{harness_url}/reset`. The method does not exist in the current file. The SUMMARY documents this as an expected condition (removed in a prior phase) and asserts no code change is needed. The question for the human: is this phase's job to add the `/reset` route to bridge.ts only (done), or to also ensure the Python caller exists (not done)?

All other 4 success criteria are fully verified.

---

_Verified: 2026-04-11T14:16:30Z_
_Verifier: Claude (gsd-verifier)_
