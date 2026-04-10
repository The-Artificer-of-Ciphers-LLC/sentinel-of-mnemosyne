---
phase: 1
slug: core-loop
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-10
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (latest) |
| **Config file** | `sentinel-core/pyproject.toml` (`[tool.pytest.ini_options]`) — Wave 0 gap |
| **Quick run command** | `pytest sentinel-core/tests/ -x -q` |
| **Full suite command** | `pytest sentinel-core/tests/ -v` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest sentinel-core/tests/ -x -q`
- **After every plan wave:** Run `pytest sentinel-core/tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 0 | CORE-01 | — | N/A | smoke | `curl -s -X POST http://localhost:3000/prompt -d '{"message":"hello"}'` | ❌ W0 | ⬜ pending |
| 1-01-02 | 01 | 0 | CORE-02 | — | N/A | unit (file assert) | `grep '"@mariozechner/pi-coding-agent": "0.66.1"' pi-harness/package.json` | ❌ W0 | ⬜ pending |
| 1-01-03 | 01 | 1 | CORE-03 | — | N/A | unit | `pytest sentinel-core/tests/test_message.py -x` | ❌ W0 | ⬜ pending |
| 1-01-04 | 01 | 1 | CORE-04 | — | N/A | integration | `pytest sentinel-core/tests/test_lmstudio_client.py -x` | ❌ W0 | ⬜ pending |
| 1-01-05 | 01 | 1 | CORE-05 | T-1-01 | Token guard rejects oversized messages before LM Studio call | unit | `pytest sentinel-core/tests/test_token_guard.py::test_rejects_oversized -x` | ❌ W0 | ⬜ pending |
| 1-01-06 | 01 | 1 | CORE-05 | — | N/A | unit | `pytest sentinel-core/tests/test_token_guard.py::test_permits_normal -x` | ❌ W0 | ⬜ pending |
| 1-01-07 | 01 | 1 | CORE-06 | — | N/A | smoke (manual) | `docker compose up -d && docker compose ps` | ❌ W0 | ⬜ pending |
| 1-01-08 | 01 | 1 | CORE-07 | — | N/A | unit (file assert) | `grep -q "^include:" docker-compose.yml` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `sentinel-core/pyproject.toml` — pytest + pytest-asyncio config (`[tool.pytest.ini_options]`)
- [ ] `sentinel-core/tests/conftest.py` — shared fixtures (TestClient, mock LM Studio via httpx MockTransport)
- [ ] `sentinel-core/tests/test_message.py` — stub covering CORE-03
- [ ] `sentinel-core/tests/test_token_guard.py` — stubs for CORE-05 (rejects oversized, permits normal)
- [ ] `sentinel-core/tests/test_lmstudio_client.py` — stub covering CORE-04 (mocked LM Studio response)
- [ ] Framework install: `pip install pytest pytest-asyncio httpx`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `docker compose up` starts both services cleanly | CORE-06 | Docker container orchestration cannot be reliably automated in CI without Docker-in-Docker | 1. Run `docker compose up -d`; 2. `docker compose ps` — both `sentinel-core` and `pi-harness` show `running`; 3. `curl -s http://localhost:8000/health` returns `{"status": "ok"}` |
| Pi harness bridge smoke test | CORE-01 | Requires LM Studio running with a model loaded | 1. `curl -X POST http://localhost:3000/prompt -H "Content-Type: application/json" -d '{"message":"hello"}'`; 2. Response is JSON with `content` field |
| End-to-end message flow | Phase goal | Requires full stack up | `curl -X POST http://localhost:8000/message -H "Content-Type: application/json" -d '{"content":"hello","user_id":"test"}' -s | jq .content` — response is non-empty string |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
