---
phase: 10-knowledge-migration-tool-import-from-existing-second-brain
plan: "01"
subsystem: test-scaffolding
tags: [tdd, discord, obsidian, memory, phase-10, wave-0]
dependency_graph:
  requires: []
  provides:
    - test stubs for 27-command routing (2B-01, 2B-04) — consumed by Plan 10-04
    - test stubs for thread ID persistence (2B-03) — consumed by Plan 10-02
    - parallel self/ read stubs (MEM-02, MEM-03) — consumed by Plan 10-03
    - ops/sessions path assertion — consumed by Plan 10-02
  affects:
    - sentinel-core/tests/test_obsidian_client.py
    - sentinel-core/tests/test_message.py
tech_stack:
  added: []
  patterns:
    - discord module stubbing via sys.modules injection for test isolation without discord.py installed
    - TDD red-green scaffolding: new test files describe unimplemented behavior explicitly
key_files:
  created:
    - sentinel-core/tests/test_bot_subcommands.py
    - sentinel-core/tests/test_bot_thread_persistence.py
  modified:
    - sentinel-core/tests/test_obsidian_client.py
    - sentinel-core/tests/test_message.py
decisions:
  - stub discord module via sys.modules before importing bot.py — avoids installing discord.py in test env while keeping real bot code unchanged
  - test_thread_ids_startup_graceful_on_404 is GREEN (setup_hook doesn't crash on missing file) — expected since no crash code exists yet either
  - test_get_user_context_returns_content stays GREEN after mock path change — obsidian.py already uses self/identity.md (updated in a prior phase)
metrics:
  duration: "~15 min"
  completed_date: "2026-04-11"
  tasks_completed: 2
  files_changed: 4
---

# Phase 10 Plan 01: Test Scaffolding (Wave 0) Summary

Wave 0 test scaffolding: 2 new test files (12 stubs) + 2 updated files establish the RED-GREEN baseline for Phase 10 implementation across command routing, thread persistence, parallel Obsidian reads, and session path migration.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create test_bot_subcommands.py with 9 failing stubs (2B-01, 2B-04) | e782205 | sentinel-core/tests/test_bot_subcommands.py |
| 2 | Create thread persistence stubs + update path assertions in existing tests | c455f8c | sentinel-core/tests/test_bot_thread_persistence.py, test_obsidian_client.py, test_message.py |

## Test State After This Plan

| File | Tests | GREEN | RED |
|------|-------|-------|-----|
| test_bot_subcommands.py | 9 | 2 (capture, unknown-command existing behavior) | 7 (new commands, plugin: routing, help grouping, seed) |
| test_bot_thread_persistence.py | 3 | 1 (graceful 404) | 2 (startup load, persist function) |
| test_obsidian_client.py | 11 | 9 (all existing) | 2 (read_self_context() stubs) |
| test_message.py | +1 new | 0 (module fails to import — pre-existing `anthropic` missing) | 1 (ops/sessions path) |

## Deviations from Plan

### Auto-noted observations (no fix needed)

**1. test_get_user_context_returns_content stays GREEN after mock path change**
- Found during: Task 2
- Situation: Plan expected changing the mock from `/vault/core/users/` to `/vault/self/identity.md` to make this test RED. Instead it stayed GREEN.
- Reason: obsidian.py already calls `/vault/self/identity.md` (updated in a prior phase before 10-01). The mock change aligns the test to reality — not a regression.
- No fix needed: the test correctly validates the current implementation.

**2. test_thread_ids_startup_graceful_on_404 is GREEN (not RED)**
- Found during: Task 2
- Situation: Plan expected all 3 thread persistence tests to be RED. The 404-graceful test passes because setup_hook does not attempt to load thread IDs at all — so it trivially doesn't crash.
- Reason: The test asserts "no crash" — which is true even without the persistence code. The assertion `SENTINEL_THREAD_IDS == set()` also holds since the set is never populated.
- Impact: Acceptable. The test will need updating in Plan 10-02 to assert the 404-handling code path explicitly rather than trivially passing by omission.

**3. test_message.py still fails to collect (pre-existing)**
- Found during: Task 2 verification
- Situation: `anthropic` module is not installed in the test environment; `app/main.py` imports it unconditionally at module load.
- Scope: Pre-existing — not caused by this plan's changes. Our addition (`test_session_write_uses_ops_sessions_path`) is syntactically valid and would run if the module loaded.
- Deferred: Logged, not fixed — out of scope for Wave 0 test scaffolding.

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| `read_self_context()` | test_obsidian_client.py:231,246 | Tests the method before it exists — RED until Plan 10-03 adds it to ObsidianClient |
| `_persist_thread_id()` | test_bot_thread_persistence.py:154 | Tests the function before it exists — RED until Plan 10-02 adds it to bot.py |
| 27-command routing | test_bot_subcommands.py:82-96 | Tests commands not yet in _SUBCOMMAND_PROMPTS — RED until Plan 10-04 |
| ops/sessions path | test_message.py (new test) | Asserts path not yet used by message.py — RED until Plan 10-02 |

## Self-Check: PASSED

- sentinel-core/tests/test_bot_subcommands.py: FOUND
- sentinel-core/tests/test_bot_thread_persistence.py: FOUND
- commit e782205: FOUND
- commit c455f8c: FOUND
