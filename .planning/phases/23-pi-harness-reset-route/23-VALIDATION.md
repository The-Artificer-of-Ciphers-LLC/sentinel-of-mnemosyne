---
phase: 23
slug: pi-harness-reset-route
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-11
---

# Phase 23 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | vitest 2.1.9 (installed in Wave 0) |
| **Config file** | none — Wave 0 installs; zero-config vitest 2.x |
| **Quick run command** | `cd pi-harness && npm test` |
| **Full suite command** | `cd pi-harness && npm test` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd pi-harness && npm test`
- **After every plan wave:** Run `cd pi-harness && npm test`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 23-01-01 | 01 | 0 | CORE-07 | — | N/A | setup | `cd pi-harness && npm install && npm test -- --reporter=verbose 2>&1 \| grep -E "passed\|failed\|no test"` | ❌ W0 | ⬜ pending |
| 23-01-02 | 01 | 1 | CORE-07 | — | sendReset no-ops safely when Pi not alive | unit | `cd pi-harness && npm test` | ❌ W0 | ⬜ pending |
| 23-01-03 | 01 | 1 | CORE-07 | — | POST /reset returns 200 + {status:ok} | integration | `cd pi-harness && npm test` | ❌ W0 | ⬜ pending |
| 23-01-04 | 01 | 2 | CORE-07 | — | PI_TIMEOUT_S env var controls send_prompt timeout | manual | Check pi_adapter.py contains `PI_TIMEOUT_S` and `os.getenv("PI_TIMEOUT_S", "190")` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `cd pi-harness && npm install --save-dev vitest@2.1.9` — install test framework
- [ ] `pi-harness/package.json` — add `"test": "vitest run"` script
- [ ] `pi-harness/src/bridge.test.ts` — create test file stub with vi.mock('./pi-adapter') factory
- [ ] bridge.ts testability: add `export { app }` + `if (process.env.NODE_ENV !== 'test') start()` guard OR extract `buildApp()` function

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| PI_TIMEOUT_S default = 190 | CORE-07 | env var read at module load; no runtime assertion | `grep "PI_TIMEOUT_S" sentinel-core/app/clients/pi_adapter.py` must show `os.getenv("PI_TIMEOUT_S", "190")` |
| reset_session() URL is correct | CORE-07 | Verified by reading code, not running | `grep "reset" sentinel-core/app/clients/pi_adapter.py` must show `{self._harness_url}/reset` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
