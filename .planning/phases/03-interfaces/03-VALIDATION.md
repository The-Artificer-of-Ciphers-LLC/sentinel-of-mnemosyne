---
phase: 03
slug: interfaces
status: draft
nyquist_compliant: true
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

## Nyquist Test Matrix

> Added retroactively (Phase 08 docs repair). All tests confirmed present in codebase as of 2026-04-11.
> Manual verifications reference evidence from 03-VERIFICATION.md (verified 2026-04-10).
> Note: Per-Task Verification Map above has a mapping error (03-01-01/02 labels say IFACE-04 but
> implement IFACE-06 auth). This matrix uses 03-VERIFICATION.md as ground truth.

| Requirement | Description | Test Type | Test File / Command | Status |
|-------------|-------------|-----------|---------------------|--------|
| IFACE-01 | Standard Message Envelope defined as Pydantic v2 model | unit | `sentinel-core/tests/test_message.py` (envelope shape asserted in `test_post_message_returns_response_envelope`) | ✅ automated |
| IFACE-02 | Discord bot container operational, discord.py v2.7.x | manual | `docker compose up discord && /sentask hello` — see 03-VERIFICATION.md §Human Verification #1 | ✅ manual-verified |
| IFACE-03 | Discord slash commands use deferred responses (3s SLA) | manual | `interaction.response.defer(thinking=True)` confirmed in bot.py line 77; timing SLA requires live Discord — see 03-VERIFICATION.md §Human Verification #1 | ✅ manual-verified |
| IFACE-04 | Discord multi-turn conversations use threads | manual | `channel.create_thread()` confirmed in bot.py line 84; requires live Discord — see 03-VERIFICATION.md §Human Verification #1 | ✅ manual-verified |
| IFACE-05 | Apple Messages bridge operational as feature-flagged tier-2 | manual | IMESSAGE_ENABLED=false exit confirmed by live execution; full path requires macOS — see 03-VERIFICATION.md §Human Verification #2 | ✅ manual-verified |
| IFACE-06 | All non-health Core endpoints require X-Sentinel-Key | unit | `sentinel-core/tests/test_auth.py::test_auth_rejects_missing_key`, `::test_auth_rejects_wrong_key`, `::test_health_bypasses_auth`, `::test_auth_accepts_valid_key` | ✅ automated |

**Test count:** 6 requirements → 2 automated (unit) + 4 manual-verified (live hardware required)
**Suite command:** `pytest sentinel-core/tests/test_auth.py -x -q`

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

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** retroactive — 2026-04-11 (Phase 08 docs repair)
