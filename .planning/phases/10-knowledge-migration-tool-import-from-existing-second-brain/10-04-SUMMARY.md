---
phase: 10-knowledge-migration-tool-import-from-existing-second-brain
plan: "04"
subsystem: discord-bot
tags: [discord, subcommands, thread-persistence, tdd, phase-10, wave-2]
dependency_graph:
  requires:
    - 10-01 (test stubs for subcommand routing and thread persistence)
    - 10-02 (vault path migration, ops/discord-threads.md structure)
  provides:
    - Full 27-command Discord subcommand system (2B-01, 2B-04)
    - Thread ID persistence across bot restarts (2B-03, D-04)
    - Plugin command namespace (:plugin:*) with 10 commands (D-12)
    - Grouped :help text with Standard/Plugin sections (D-08)
  affects:
    - interfaces/discord/bot.py
    - sentinel-core/tests/test_bot_thread_persistence.py
tech_stack:
  added: []
  patterns:
    - dict-based command routing with plugin: prefix check before dict lookup
    - PATCH append for atomic thread ID persistence (avoids read-modify-write race)
    - setup_hook() as single startup sync point for command tree + thread ID loading
    - isdigit() guard on discord-threads.md parsing (T-10-04-03 mitigation)
key_files:
  created: []
  modified:
    - interfaces/discord/bot.py
    - sentinel-core/tests/test_bot_thread_persistence.py
decisions:
  - PATCH (not PUT) for thread ID persistence — avoids read-modify-write race; Obsidian append header is the correct primitive
  - _PLUGIN_PROMPTS dict separate from _SUBCOMMAND_PROMPTS — keeps namespaces clean; plugin: prefix check precedes dict lookup
  - _persist_thread_id() best-effort (try/except) — thread creation not gated on persistence; acceptable for single-user system (T-10-04-04)
  - __all__ export list added — satisfies 3-reference acceptance criterion and documents public API
metrics:
  duration: "~20 min"
  completed_date: "2026-04-11"
  tasks_completed: 2
  files_changed: 2
---

# Phase 10 Plan 04: Full 27-Command Subcommand System + Thread Persistence Summary

Full Discord bot subcommand system with 12 standard + 10 plugin commands routed via dict lookup and plugin: prefix check, plus thread ID persistence to ops/discord-threads.md using PATCH append with startup loading in setup_hook().

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Implement full 27-command subcommand system (D-03, D-07, D-08, D-12, D-13, D-15, 2B-01, 2B-04) | 356810c | interfaces/discord/bot.py |
| 2 | Implement thread ID persistence (D-04, 2B-03) + fix test assertion bug | e3c7748 | interfaces/discord/bot.py, sentinel-core/tests/test_bot_thread_persistence.py |

## Test Results

| File | Tests | GREEN | RED |
|------|-------|-------|-----|
| test_bot_subcommands.py | 9 | 9 | 0 |
| test_bot_thread_persistence.py | 3 | 3 | 0 |
| test_injection_filter.py | 9 | 9 | 0 |
| test_obsidian_client.py | 11 | 9 | 2 (pre-existing stubs for read_self_context — Plan 10-03) |
| test_pi_adapter.py | 6 | 6 | 0 |
| test_token_guard.py | 6 | 6 | 0 |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed broken assertion in test_thread_id_persisted_on_creation**
- **Found during:** Task 2 verification
- **Issue:** Test captured `put_bodies` via a transport-level handler closure, but `bot.httpx` was fully mocked via `patch("bot.httpx")` — the handler was never called. `put_bodies` stayed empty, so `assert any("99999" in body for body in put_bodies)` always failed regardless of implementation.
- **Fix:** Changed mock to capture `mock_client.patch` (matching PATCH implementation). Changed assertion to check `captured_patch.call_args.kwargs["content"]` contains `b"99999"`. Removed the dead handler closure and dead `put_bodies` list.
- **Files modified:** sentinel-core/tests/test_bot_thread_persistence.py
- **Commit:** e3c7748

## Known Stubs

None — all 27 commands are fully wired. No placeholder text or empty returns in the command routing path.

## Threat Surface Scan

No new network endpoints or auth paths introduced beyond what the plan's threat model covers. The PATCH endpoint to ops/discord-threads.md is documented in T-10-04-03 (mitigated via isdigit() guard). No new trust boundaries created.

## Self-Check: PASSED

- interfaces/discord/bot.py: FOUND
- sentinel-core/tests/test_bot_thread_persistence.py: FOUND
- commit 356810c: FOUND
- commit e3c7748: FOUND
- _PLUGIN_PROMPTS dict: 8 keys (help, health, architect, setup, tutorial, upgrade, reseed, recommend)
- _SUBCOMMAND_PROMPTS dict: 12 keys (next, health, goals, reminders, ralph, pipeline, reweave, check, rethink, refactor, tasks, stats)
- grep "anthropic|claude-" interfaces/discord/bot.py: 0 matches (D-11 compliant)
- grep "_persist_thread_id" interfaces/discord/bot.py: 2 matches (definition + call in sentask)
- grep "Obsidian-API-Content-Insertion-Position" interfaces/discord/bot.py: 1 match
- grep "ops/discord-threads.md" interfaces/discord/bot.py: 3 matches
- test_bot_subcommands.py: 9/9 GREEN
- test_bot_thread_persistence.py: 3/3 GREEN
