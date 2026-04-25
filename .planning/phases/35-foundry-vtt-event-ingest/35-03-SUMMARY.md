---
phase: 35-foundry-vtt-event-ingest
plan: "03"
subsystem: discord-bot
tags: [discord, foundry-vtt, aiohttp, embed, fvt-02, fvt-03]
dependency_graph:
  requires: [35-01]
  provides: [build_foundry_roll_embed, SentinelBot._handle_internal_notify, SentinelBot.close]
  affects: [interfaces/discord/bot.py]
tech_stack:
  added: [aiohttp.web (AppRunner, TCPSite)]
  patterns: [module-level pure embed builder, aiohttp-in-discord-bot internal HTTP listener]
key_files:
  modified:
    - interfaces/discord/bot.py
    - interfaces/discord/tests/test_thread_persistence.py
decisions:
  - "Use aiohttp AppRunner (not FastAPI sub-app) for internal HTTP listener — discord.py event loop compatible; confirmed by 35-RESEARCH.md Pattern 4"
  - "close() override calls runner.cleanup() before super().close() to prevent aiohttp socket leak (Pitfall 5)"
  - "ALLOWED_CHANNEL_IDS first-iter channel selection for notify dispatch — same channel as all other pf2e commands (D-15)"
metrics:
  duration: "~12 minutes"
  completed: "2026-04-25T14:33:00Z"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 2
---

# Phase 35 Plan 03: Discord Bot Foundry Embed and Internal Listener Summary

**One-liner:** aiohttp internal HTTP listener on port 8001 + `build_foundry_roll_embed()` with outcome emoji/color maps for Foundry VTT roll notifications to Discord.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add build_foundry_roll_embed() — turn test_discord_foundry.py GREEN | 2f644f6 | interfaces/discord/bot.py |
| 2 | Add aiohttp internal listener to SentinelBot | 78198ed | interfaces/discord/bot.py, tests/test_thread_persistence.py |

## What Was Built

**Task 1 — `build_foundry_roll_embed()`** (module-level pure function, lines ~365-420 in bot.py):

- `OUTCOME_EMOJIS`: criticalSuccess→"🎯", success→"✅", failure→"❌", criticalFailure→"💀"
- `OUTCOME_LABELS`: criticalSuccess→"Critical Hit!", success→"Success", failure→"Failure", criticalFailure→"Critical Failure!"
- `OUTCOME_COLORS`: criticalSuccess→`discord.Color.gold()`, success→`discord.Color.green()`, failure→`discord.Color.orange()`, criticalFailure→`discord.Color.red()`
- Title: `{emoji} {label} | {actor} vs {target}` or `{emoji} {label} | {actor} ({roll_type})` when no target
- Description: `narrative[:4000]` if present, else `None`
- Footer: `Roll: {total} | DC/AC: {dc} | {item_name}` or `DC: [hidden]` when `dc_hidden=True`
- All 2 `test_discord_foundry.py` tests pass GREEN

**Task 2 — SentinelBot aiohttp listener** (3 additions + 1 override):

- `from aiohttp import web` — top-level import after `httpx`
- `SentinelBot.__init__`: `self._internal_runner: "web.AppRunner | None" = None`
- `SentinelBot.setup_hook()`: starts aiohttp `TCPSite` on `DISCORD_BOT_INTERNAL_PORT` (default 8001) after existing thread ID load block
- `SentinelBot._handle_internal_notify()`: validates `X-Sentinel-Key`, parses JSON, sends `build_foundry_roll_embed(data)` to first `ALLOWED_CHANNEL_IDS` channel; returns 401/400/500 on error, 200 on success
- `SentinelBot.close()`: calls `self._internal_runner.cleanup()` before `super().close()` (D-14, Pitfall 5 mitigation, T-35-03-03)

## Test Results

- 2 new `test_discord_foundry.py` tests: PASS (GREEN)
- 50 pre-existing discord tests: PASS (no regression)
- Total: **52 tests pass**

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] setup_hook tests broke when aiohttp startup was added**

- **Found during:** Task 2 verification
- **Issue:** `test_setup_hook_loads_threads_on_start` and `test_setup_hook_graceful_on_404` in `test_thread_persistence.py` call `setup_hook()` without patching `bot.web`. After Task 2 added `web.Application()` / `web.AppRunner()` / `web.TCPSite()` calls to `setup_hook()`, these tests raised `NameError: name 'web' is not defined` (the real aiohttp was imported but the test's `patch("bot.httpx")` context didn't cover the aiohttp code path in that test's execution environment).
- **Fix:** Added `patch("bot.web", mock_web)` alongside the existing `patch("bot.httpx")` in both affected tests. Created `mock_runner` (AsyncMock) and `mock_site` (AsyncMock) with the correct method names (`setup`, `cleanup`, `start`).
- **Files modified:** `interfaces/discord/tests/test_thread_persistence.py`
- **Commit:** 78198ed

## Threat Surface Scan

All mitigations from plan threat register applied:

| Threat | Mitigation | Status |
|--------|-----------|--------|
| T-35-03-01 (Spoofing) | X-Sentinel-Key validated; 401 on mismatch | Applied in `_handle_internal_notify` |
| T-35-03-02 (Tampering) | `narrative[:4000]` truncation | Applied in `build_foundry_roll_embed` |
| T-35-03-03 (DoS/socket leak) | `close()` calls `runner.cleanup()` | Applied |
| T-35-03-04 (Info disclosure) | Accepted — internal Docker network only | No action needed |

No new threat surface introduced beyond what the plan's threat model covers.

## Known Stubs

None. `build_foundry_roll_embed()` and `_handle_internal_notify()` are fully wired. The internal server starts on `setup_hook()` and cleans up on `close()`. No placeholder values flow to UI rendering.

## Self-Check

Files exist:
- `interfaces/discord/bot.py` — FOUND (modified)
- `interfaces/discord/tests/test_thread_persistence.py` — FOUND (modified)

Commits exist:
- `2f644f6` — feat(35-03): add build_foundry_roll_embed()
- `78198ed` — feat(35-03): add aiohttp internal listener

## Self-Check: PASSED
