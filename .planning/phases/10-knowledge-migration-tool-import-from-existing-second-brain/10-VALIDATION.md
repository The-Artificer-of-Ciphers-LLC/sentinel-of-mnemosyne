---
phase: 10
slug: knowledge-migration-tool-import-from-existing-second-brain
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-11
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.23 |
| **Config file** | `sentinel-core/pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `cd sentinel-core && python -m pytest tests/test_obsidian_client.py tests/test_message.py -x` |
| **Full suite command** | `cd sentinel-core && python -m pytest tests/ -x && cd ../interfaces/discord && python -m pytest tests/ -x` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd sentinel-core && python -m pytest tests/test_obsidian_client.py tests/test_message.py -x`
- **After every plan wave:** Run `cd sentinel-core && python -m pytest tests/ -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 10-01-01 | 01 | 0 | 2B-01 | — | N/A | unit | `cd interfaces/discord && python -m pytest tests/test_subcommands.py -x` | ✅ | ✅ green |
| 10-01-02 | 01 | 0 | 2B-03 | — | N/A | unit | `cd interfaces/discord && python -m pytest tests/test_thread_persistence.py -x` | ✅ | ✅ green |
| 10-01-03 | 01 | 0 | MEM-02 | — | N/A | unit | `cd sentinel-core && python -m pytest tests/test_obsidian_client.py -x -k "user_context"` | ✅ | ✅ green |
| 10-01-04 | 01 | 0 | MEM-03 | — | N/A | unit | `cd sentinel-core && python -m pytest tests/test_message.py -x -k "session_summary"` | ✅ | ✅ green |
| 10-02-01 | 02 | 1 | MEM-02 | — | N/A | unit | `cd sentinel-core && python -m pytest tests/test_obsidian_client.py -x -k "user_context"` | ✅ | ✅ green |
| 10-02-02 | 02 | 1 | 2B-02 | — | N/A | unit | `cd sentinel-core && python -m pytest tests/test_obsidian_client.py -x -k "self_context"` | ✅ | ✅ green |
| 10-02-03 | 02 | 1 | MEM-03 | — | N/A | unit | `cd sentinel-core && python -m pytest tests/test_message.py -x -k "session_summary"` | ✅ | ✅ green |
| 10-03-01 | 03 | 2 | 2B-01 | — | N/A | unit | `cd interfaces/discord && python -m pytest tests/test_subcommands.py -x` | ✅ | ✅ green |
| 10-03-02 | 03 | 2 | 2B-03 | — | N/A | unit | `cd interfaces/discord && python -m pytest tests/test_thread_persistence.py -x` | ✅ | ✅ green |
| 10-03-03 | 03 | 2 | 2B-04 | — | N/A | unit | `cd interfaces/discord && python -m pytest tests/test_subcommands.py -x -k "check"` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `interfaces/discord/tests/test_subcommands.py` — stub tests covering 2B-01 (27-command routing), 2B-04 (`:check` validation)
- [x] `interfaces/discord/tests/test_thread_persistence.py` — stub tests covering 2B-03 (thread ID persistence)
- [x] Update `sentinel-core/tests/test_obsidian_client.py` — update mock paths: `core/users/` → `self/`, add stubs for 5-file parallel read (2B-02)
- [x] Update `sentinel-core/tests/test_message.py` — update path assertions: `core/sessions/` → `ops/sessions/`

*All Wave 0 items completed before Phase 10 shipped.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `:pipeline` runs full 6 Rs sequence end-to-end | 2B-01 | Requires live Discord, live Obsidian, live LM Studio | Send `:seed some content`, then `:pipeline`. Verify content appears in `notes/` via Obsidian UI. |
| Session-start self/ reads inject context into AI response | 2B-02 | Requires live Obsidian + LM Studio | Write content to `self/goals.md`, send a message, verify AI references the goal in its response. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** complete — Phase 10 shipped 2026-04-11, all 9/10 automated truths verified (vault directory gap logged as separate remediation item)
