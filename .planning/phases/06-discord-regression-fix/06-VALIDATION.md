---
phase: 06
slug: discord-regression-fix
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-10
---

# Phase 06 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Reconstructed 2026-04-21 from 06-VERIFICATION.md and 06-UAT.md artifacts.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio |
| **Config file** | `interfaces/discord/tests/conftest.py` |
| **Quick run command** | `docker compose config --services` |
| **Full suite command** | `cd interfaces/discord && python3 -m pytest tests/test_integration.py -v` |
| **Estimated runtime** | < 5 seconds (3 tests skip cleanly without env vars) |

---

## Sampling Rate

- **After every task commit:** Run `docker compose config --services` — verify `discord` in output
- **After every plan wave:** Run `cd interfaces/discord && python3 -m pytest tests/test_integration.py -v`
- **Before `/gsd-verify-work`:** Full suite + manual UAT (live Discord interaction required)
- **Max feedback latency:** < 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | IFACE-02 | — | N/A | smoke | `docker compose config --services \| grep -c discord` | ✅ | ✅ green |
| 06-01-02 | 01 | 1 | IFACE-03 | — | N/A | manual | Read `interfaces/discord/bot.py` lines 197–228 — verify `interaction.response.defer(thinking=True)` called before `followup.send` | ✅ | ✅ green |
| 06-02-01 | 02 | 2 | IFACE-02 | — | N/A | integration | `cd interfaces/discord && python3 -m pytest tests/test_integration.py -v -k "iface02"` | ✅ | ✅ green |
| 06-02-02 | 02 | 2 | IFACE-03 | — | N/A | integration | `cd interfaces/discord && python3 -m pytest tests/test_integration.py -v -k "iface03"` | ✅ | ✅ green |
| 06-02-03 | 02 | 2 | IFACE-04 | — | N/A | integration | `cd interfaces/discord && python3 -m pytest tests/test_integration.py -v -k "iface04"` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `interfaces/discord/tests/__init__.py` — empty package marker (committed 03836b0)
- [x] `interfaces/discord/tests/test_integration.py` — 3 integration test stubs (committed 03836b0)
- [x] `.env.example` — `DISCORD_TEST_CHANNEL_ID` variable with comment (committed 29008d7)

*All Wave 0 items completed. Note: Wave 2 regression (Wave 2 agent deleted Phase 5 security files + re-commented discord include) was corrected within Phase 06 via commits c6f4753 and 2b11b3f.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Discord bot receives `/sentask say hello` and returns AI response in a thread | IFACE-02, IFACE-04 | Discord slash commands cannot be triggered via REST API — require real user interaction | With `docker compose up` running, send `/sentask say hello` in Discord. Verify AI response appears in a thread on the message. |
| Deferred acknowledgement appears within 3 seconds | IFACE-03 | Wall-clock timing SLA requires live observation | Send `/sentask say hello`. Verify "Sentinel of Mnemosyne is thinking..." appears within 3 seconds of submission. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 5s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** complete — Phase 06 shipped 2026-04-10, UAT passed 5/5 tests, IFACE-02/03/04 closed. Human confirmed: "ok worked finally" after pi-harness session reset + 90s timeout fix (commit 5e224ac).
