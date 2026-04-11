---
phase: 09
slug: tech-debt-cleanup
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-11
---

# Phase 09 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio |
| **Config file** | `sentinel-core/pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `cd sentinel-core && .venv/bin/python -m pytest tests/ -x -q` |
| **Full suite command** | `cd sentinel-core && .venv/bin/python -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd sentinel-core && .venv/bin/python -m pytest tests/ -x -q`
- **After every plan wave:** Run `cd sentinel-core && .venv/bin/python -m pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~15 seconds

---

## Per-Task Verification Map

| Task ID | Decision | Wave | Req | Threat Ref | Test Type | Automated Command | File Exists | Status |
|---------|----------|------|-----|------------|-----------|-------------------|-------------|--------|
| 09-D01 | Narrow except Exception: in message.py | 1 | — | — | grep assert | `grep -c "except Exception:" sentinel-core/app/routes/message.py` → expect 0 in pi block | ✅ | ⬜ pending |
| 09-D01 | httpx exceptions caught, non-httpx propagates | 1 | — | — | unit | `cd sentinel-core && .venv/bin/python -m pytest tests/ -x -q` | ✅ | ⬜ pending |
| 09-D02 | timeout assertion already 90.0 (pre-verified) | 1 | PROV-03 | — | unit | `cd sentinel-core && .venv/bin/python -m pytest tests/test_pi_adapter.py::test_send_messages_hard_timeout_set -v` | ✅ | ⬜ pending |
| 09-D03 | send_prompt() absent from pi_adapter.py | 1 | — | — | grep assert | `grep -c "def send_prompt" sentinel-core/app/clients/pi_adapter.py` → expect 0 | ✅ | ⬜ pending |
| 09-D03 | send_messages() still present and tests pass | 1 | — | — | unit | `cd sentinel-core && .venv/bin/python -m pytest tests/test_pi_adapter.py -x -q` | ✅ | ⬜ pending |
| 09-D04 | Four new JSON patterns in DISCLOSURE_RED_FLAGS | 1 | — | — | grep assert | `grep -c '"name.*arguments' security/pentest-agent/pentest.py` → expect 4 | ✅ | ⬜ pending |
| 09-D04 | New json_tool_schema_probe in TEST_VECTORS | 1 | — | — | grep assert | `grep -c "json_tool_schema_probe" security/pentest-agent/pentest.py` → expect 1 | ✅ | ⬜ pending |
| 09-D04 | Python syntax valid after changes | 1 | — | — | syntax check | `python3 -m py_compile security/pentest-agent/pentest.py && echo OK` | ✅ | ⬜ pending |
| 09-D05 | 04-VALIDATION.md file exists | 1 | PROV-01..05 | — | file assert | `ls .planning/phases/04-ai-provider-multi-provider-support-retry-logic-fallback/04-VALIDATION.md` | ❌ create | ⬜ pending |
| 09-D05 | nyquist_compliant: true in frontmatter | 1 | PROV-01..05 | — | grep assert | `grep "nyquist_compliant: true" .planning/phases/04-ai-provider-multi-provider-support-retry-logic-fallback/04-VALIDATION.md` | ❌ create | ⬜ pending |
| 09-D05 | All 5 PROV requirements mapped | 1 | PROV-01..05 | — | grep assert | `grep -c "PROV-0[1-5]" .planning/phases/04-ai-provider-multi-provider-support-retry-logic-fallback/04-VALIDATION.md` → expect ≥5 | ❌ create | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. No new test files or fixtures needed.
- D-01, D-02, D-03 are covered by existing `sentinel-core/tests/` suite (62 tests total).
- D-04 verified by grep + Python syntax check (no new test file required for pentest.py changes).
- D-05 produces a documentation file — verified by file existence and grep assertions.

---

## Manual-Only Verifications

All phase behaviors have automated verification (grep assertions + existing test suite).

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (none needed)
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-04-11
