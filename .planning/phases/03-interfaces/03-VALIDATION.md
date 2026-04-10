---
phase: 03
slug: interfaces
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-10
---

# Phase 03 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio |
| **Config file** | `sentinel-core/pytest.ini` (or `pyproject.toml [tool.pytest.ini_options]`) |
| **Quick run command** | `cd sentinel-core && pytest tests/ -x -q` |
| **Full suite command** | `cd sentinel-core && pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd sentinel-core && pytest tests/ -x -q`
- **After every plan wave:** Run `cd sentinel-core && pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 0 | IFACE-04 | — | N/A | unit | `pytest tests/test_auth.py -x -q` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 1 | IFACE-04 | — | 401 on missing/wrong key; /health passes unauthenticated | unit | `pytest tests/test_auth.py -x -q` | ✅ | ⬜ pending |
| 03-01-03 | 01 | 1 | IFACE-05 | — | N/A | unit | `pytest tests/ -x -q` | ✅ | ⬜ pending |
| 03-02-01 | 02 | 1 | IFACE-02 | — | N/A | integration | manual: discord bot responds in thread | ✅ | ⬜ pending |
| 03-03-01 | 03 | 1 | IFACE-06 | — | N/A | integration | manual: bridge exits cleanly when IMESSAGE_ENABLED=false | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `sentinel-core/tests/test_auth.py` — stubs for IFACE-04 (auth middleware: 401 on bad key, 200 on good key, /health passes)
- [ ] `sentinel-core/tests/conftest.py` — update all existing fixtures to include `X-Sentinel-Key: test-key-for-pytest` header (31 existing tests)

*Existing pytest infrastructure covers the framework; Wave 0 only adds auth test stubs and updates fixtures.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Discord bot responds in thread within 3s | IFACE-03 | Requires live Discord connection and a real guild | Invite bot, run `/sentask hello`, verify thread created and response arrives within 3s |
| Apple Messages bridge receives and replies | IFACE-06 | Requires macOS Full Disk Access and a real iMessage conversation | Enable IMESSAGE_ENABLED=true, send iMessage from known number, verify AI response returned |
| iMessage bridge exits on IMESSAGE_ENABLED=false | IFACE-06 | Process startup behavior | Run `python bridge.py` with IMESSAGE_ENABLED=false; verify exit with clear log message |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
