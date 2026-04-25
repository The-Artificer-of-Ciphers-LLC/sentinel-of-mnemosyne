---
phase: 35
slug: foundry-vtt-event-ingest
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-25
---

# Phase 35 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (asyncio_mode = "auto") |
| **Config file** | `modules/pathfinder/pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `cd modules/pathfinder && python -m pytest tests/test_foundry.py -x` |
| **Full suite command** | `cd modules/pathfinder && python -m pytest tests/ -x && cd ../../interfaces/discord && python -m pytest tests/ -x` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd modules/pathfinder && python -m pytest tests/test_foundry.py -x`
- **After every plan wave:** Run `cd modules/pathfinder && python -m pytest tests/ -x && cd ../../interfaces/discord && python -m pytest tests/ -x`
- **Before `/gsd:verify-work`:** Both test suites must be green
- **Max feedback latency:** ~30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 35-01-01 | 01 | 0 | FVT-01 | — | N/A | unit stub | `pytest tests/test_foundry.py -x` | ❌ W0 | ⬜ pending |
| 35-01-02 | 01 | 0 | FVT-03 | — | N/A | unit stub | `pytest tests/test_discord_foundry.py -x` | ❌ W0 | ⬜ pending |
| 35-02-01 | 02 | 1 | FVT-01 | — | auth check rejects missing/wrong key → 401 | unit | `pytest tests/test_foundry.py::test_roll_event_accepted tests/test_foundry.py::test_auth_rejected -x` | ✅ W0 | ⬜ pending |
| 35-02-02 | 02 | 1 | FVT-02 | — | LLM failure → fallback text, embed still sent | unit | `pytest tests/test_foundry.py::test_llm_fallback tests/test_foundry.py::test_notify_dispatched -x` | ✅ W0 | ⬜ pending |
| 35-03-01 | 03 | 2 | FVT-03 | — | embed title/footer correct; dc_hidden → "DC: [hidden]" | unit | `pytest tests/test_discord_foundry.py::test_embed_critical_success tests/test_discord_foundry.py::test_embed_hidden_dc -x` | ✅ W0 | ⬜ pending |
| 35-04-01 | 04 | 3 | FVT-01..03 | — | `/foundry/event` appears in REGISTRATION_PAYLOAD | unit | `pytest tests/test_foundry.py::test_registration_payload -x` | ✅ W0 | ⬜ pending |
| 35-03-02 | 03 | 1 | FVT-02 | T-35-03-01 | aiohttp server starts in setup_hook; bot.py imports cleanly | manual | manual — requires live asyncio + discord.py event loop | ✅ W0 | ⬜ pending |
| 35-04-02 | 04 | 3 | FVT-01..03 | — | compose.yml DISCORD_BOT_INTERNAL_URL present; .env.example has Foundry section | manual | `grep -v '^#' modules/pathfinder/compose.yml | grep -c DISCORD_BOT_INTERNAL_URL` returns 1 | ✅ | ⬜ pending |
| 35-05-01 | 05 | 4 | FVT-01 | T-35-05-04 | package.sh produces zip with sentinel-connector/ subdirectory at root | automated | `cd modules/pathfinder/foundry-client && bash package.sh && unzip -l sentinel-connector.zip | grep -c sentinel-connector/module.json` | ✅ | ⬜ pending |
| 35-05-02 | 05 | 4 | FVT-01..03 | — | UAT script passes all 9 automated steps against live stack | automated | `bash scripts/uat_phase35.sh` | ✅ | ⬜ pending |
| 35-06-A | 06 | 5 | FVT-01..03 | T-35-06-01..05 | discordWebhookUrl/sentinelBaseUrl settings registered; postEvent() has AbortController + no-cors fallback; _postRollEvent/_postChatEvent removed | automated | `grep -c 'discordWebhookUrl' modules/pathfinder/foundry-client/sentinel-connector.js && grep -c 'AbortController' modules/pathfinder/foundry-client/sentinel-connector.js && grep -c "mode: 'no-cors'" modules/pathfinder/foundry-client/sentinel-connector.js` | ✅ | ⬜ pending |
| 35-06-B | 06 | 5 | FVT-01..03 | T-35-06-03..04 | PNACORSMiddleware defined and registered; all pathfinder tests still pass | automated | `grep -c 'class PNACORSMiddleware' modules/pathfinder/app/main.py && cd modules/pathfinder && python -m pytest tests/ -x -q 2>&1 | tail -1` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `modules/pathfinder/tests/test_foundry.py` — RED stubs for FVT-01, FVT-02 (route, auth, LLM fallback, notify dispatch, REGISTRATION_PAYLOAD)
- [ ] `interfaces/discord/tests/test_discord_foundry.py` — RED stubs for FVT-03 (embed builder: criticalSuccess title/footer, dc_hidden, all four outcome types)

*Framework already installed — no additional pytest setup needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Foundry module installs from zip without console errors | FVT-01 (SC-1) | Requires live Foundry VTT v14 browser environment | Install zip via manifest URL; check browser DevTools console for errors |
| `X-Sentinel-Key` world setting visible in GM module settings panel | FVT-01 (SC-4) | Requires Foundry UI | Open Manage Modules > Sentinel Connector settings; confirm 3 fields visible (URL, Key, Prefix) |
| Roll in PF2e triggers Discord embed in DM channel | FVT-03 (SC-3) | Requires Foundry + live stack | Make an attack roll; verify Discord receives embed within 5s |
| aiohttp internal server starts and bot.py accepts POST /internal/notify | FVT-02 | Requires docker compose up | `curl -X POST http://discord-bot:8001/internal/notify -H "X-Sentinel-Key: ..." -d '{...}'` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
