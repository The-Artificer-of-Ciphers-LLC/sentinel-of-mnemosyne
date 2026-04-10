---
phase: 02
slug: memory-layer
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-10
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (asyncio_mode=auto) |
| **Config file** | `sentinel-core/pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `docker compose exec sentinel-core pytest sentinel-core/tests/ -x -q` |
| **Full suite command** | `docker compose exec sentinel-core pytest sentinel-core/tests/ -v` |
| **Estimated runtime** | ~10 seconds (httpx MockTransport, no real Obsidian/Pi needed) |

---

## Sampling Rate

- **After every task commit:** Run quick run command
- **After every plan wave:** Run full suite command
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|--------|
| 02-01-01 | 01 | 1 | MEM-01 | — | Obsidian unavailable → 200 returned (not 503) | unit | `pytest tests/test_obsidian_client.py -x -q` | ⬜ pending |
| 02-01-02 | 01 | 1 | MEM-02 | T-2-02 | user_id path traversal rejected at model validation | unit | `pytest tests/test_message.py::test_invalid_user_id -x -q` | ⬜ pending |
| 02-01-03 | 01 | 1 | MEM-02 | — | Context injected as 3-message array before token guard | unit | `pytest tests/test_message.py::test_context_injected -x -q` | ⬜ pending |
| 02-01-04 | 01 | 1 | MEM-03 | — | Session summary written via BackgroundTasks | unit | `pytest tests/test_message.py::test_summary_written -x -q` | ⬜ pending |
| 02-01-05 | 01 | 1 | MEM-07 | — | Token guard fires on context-inflated message array | unit | `pytest tests/test_token_guard.py::test_multi_message_budget -x -q` | ⬜ pending |
| 02-02-01 | 02 | 2 | MEM-04 | — | Second message includes prior session content in context | integration | manual (live Obsidian + pi) | ⬜ pending |
| 02-02-02 | 02 | 2 | MEM-05 | — | Hot tier: last 3 sessions loaded for user_id | unit | `pytest tests/test_obsidian_client.py::test_hot_tier -x -q` | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `sentinel-core/tests/test_obsidian_client.py` — stubs for MEM-01, MEM-05 (get_user_context, get_recent_sessions, write_session_summary)
- [ ] `sentinel-core/tests/test_message.py` — extend existing file with stubs for MEM-02, MEM-03, MEM-07

*Existing `conftest.py` covers shared fixtures — no new conftest changes required.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Cross-session memory demo | MEM-04 | Requires live Obsidian + two real conversations | Send message 1 with unique detail. Send message 2 asking about it. Verify AI references detail from session 1. |
| Obsidian graceful degradation | MEM-01 | Requires stopping Obsidian desktop app | Stop Obsidian. Send message. Verify 200 response with no crash. Check logs for warning. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
