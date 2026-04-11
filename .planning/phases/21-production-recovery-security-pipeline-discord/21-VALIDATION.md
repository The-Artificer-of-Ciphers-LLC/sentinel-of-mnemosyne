---
phase: 21
slug: production-recovery-security-pipeline-discord
status: ready
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-11
plan_count: 1
---

# Phase 21 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (asyncio_mode = "auto") |
| **Config file** | `sentinel-core/pyproject.toml` |
| **Quick run command** | `cd sentinel-core && python -m pytest tests/ -x -q` |
| **Full suite command** | `cd sentinel-core && python -m pytest tests/ -v` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd sentinel-core && python -m pytest tests/ -x -q`
- **After every plan wave:** Run `cd sentinel-core && python -m pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 21-01-01 | 01 | 1 | SEC-01 | T-21-01 | InjectionFilter strips injection attempts | unit | `cd sentinel-core && python -m pytest tests/test_injection_filter.py -v` | Wave 0 restore | ⬜ pending |
| 21-01-02 | 01 | 1 | SEC-02 | T-21-01 | OutputScanner blocks leaked credentials/PII | unit | `cd sentinel-core && python -m pytest tests/test_output_scanner.py -v` | Wave 0 restore | ⬜ pending |
| 21-01-03 | 01 | 1 | CORE-03 | T-21-03 | POST /message returns ResponseEnvelope without AttributeError | unit | `cd sentinel-core && python -m pytest tests/test_message.py -v` | ✅ | ⬜ pending |
| 21-01-04 | 01 | 1 | IFACE-02 | T-21-05 | Docker Compose includes Discord container | grep | `grep "path: interfaces/discord/compose.yml" docker-compose.yml` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Wave 0 is handled within Task 1 of Plan 01 — the test files are restored from git before
any other task runs. No separate Wave 0 plan is needed.

- [ ] `sentinel-core/tests/test_injection_filter.py` — restored in Task 1 from git history (c6f4753), covers SEC-01
- [ ] `sentinel-core/tests/test_output_scanner.py` — restored in Task 1 from git history (c6f4753), covers SEC-02

*Existing conftest.py infrastructure is sufficient — no new fixtures needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Discord container starts on `docker compose up` | IFACE-02 | Requires Docker daemon + running stack | Run `docker compose up discord` and verify container reaches healthy state |

---

## Nyquist Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 restore in Task 1
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (restored in Task 1)
- [x] No watch-mode flags
- [x] Feedback latency < 15s (pytest suite ~10s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** ready
