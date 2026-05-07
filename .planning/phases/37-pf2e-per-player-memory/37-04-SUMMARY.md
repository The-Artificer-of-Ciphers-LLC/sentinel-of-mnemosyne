---
phase: 37-pf2e-per-player-memory
plan: "04"
subsystem: discord/pathfinder-player-adapter
tags: [tdd, red, discord, adapter, player-vault, pvl]
type: tdd
wave: 0
requires:
  - interfaces/discord/pathfinder_types (PathfinderRequest/Command/Response)
  - interfaces/discord/tests/conftest.py (centralised discord stubs)
provides:
  - RED contract tests for Wave 7 interfaces/discord/pathfinder_player_adapter.py
  - Behavioural pin on payload shape + module route path for all 7 :pf player verbs
  - Pitfall-4 guard: user_id forwarded as str, never coerced
affects:
  - interfaces/discord/tests/
tech-stack:
  added: []
  patterns:
    - function-scope ImportError gate (RED until Wave 7 lands the adapter)
    - AsyncMock + call_args[0] inspection for route-path + payload assertions
    - asyncio_mode = "auto" — async tests carry no @pytest.mark.asyncio decorator
key-files:
  created:
    - interfaces/discord/tests/test_pathfinder_player_adapter.py
  modified: []
decisions:
  - "RED tests import command classes at function scope so the file collects cleanly even though the adapter module does not exist"
  - "Discord stubs are NOT redeclared per-file — conftest.py centralises them (Phase 33-01 collection-order race fix)"
  - "Recall (no query) test tolerates either {user_id, query=''} or {user_id} — leaves the empty-query encoding to Wave 7 while still pinning user_id"
  - "Type-drift guard uses user_id='123' so a regression coerces to int 123 and the assertion fails loudly"
metrics:
  duration: ~2 min
  completed: 2026-05-07
  tests_added: 14
---

# Phase 37 Plan 04: Wave 0 RED Tests for Discord Pathfinder Player Adapter Summary

**One-liner:** 14 RED tests pinning the Discord adapter contract for all 7 `:pf player` verbs (start, note, ask, npc, recall, todo, style list/set, canonize) before Wave 7 implements `pathfinder_player_adapter.py`.

## Objective Recap

Wave 0 RED tests for the Discord adapter classes that will dispatch `:pf player <verb>` to the pathfinder module's `/player/*` routes. Every command-class contract — route path, payload keys, usage-hint short-circuits, `user_id` type — is locked in before any implementation code lands. RED state proves there is no accidental green-on-stub.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | RED tests for pathfinder_player_adapter command classes | `27b0328` | `interfaces/discord/tests/test_pathfinder_player_adapter.py` |

## What's In the Test File

14 async test functions (asyncio_mode=auto, no decorator):

1. `test_player_start_posts_to_onboard_route` — start → `modules/pathfinder/player/onboard`, user_id is str
2. `test_player_note_payload_shape` — `{user_id, text}` exactly, route `/player/note`
3. `test_player_note_empty_returns_usage` — empty rest → "Usage:" text response, no post
4. `test_player_ask_payload_shape` — `{user_id, question}`, route `/player/ask`
5. `test_player_npc_parses_npc_name_and_note` — first whitespace token is npc_name; rest is note
6. `test_player_npc_missing_note_returns_usage` — single-token rest → usage hint, no post
7. `test_player_recall_no_query` — empty rest; user_id present + str; query='' if encoded
8. `test_player_recall_with_query` — query forwarded as full rest string
9. `test_player_todo_payload_shape` — `{user_id, text}`, route `/player/todo`
10. `test_player_style_list` — `{user_id, action='list'}` and response surfaces all 4 preset names
11. `test_player_style_set_with_preset` — `{user_id, action='set', preset='Tactician'}`
12. `test_player_style_set_missing_preset_returns_usage` — `set` with no preset → usage hint
13. `test_player_canonize_payload_shape` — `{user_id, outcome, question_id, rule_text}`, route `/player/canonize`
14. `test_user_id_is_forwarded_as_str` — Pitfall 4: user_id="123" stays "123", never int 123

## Verification

```
$ pytest interfaces/discord/tests/test_pathfinder_player_adapter.py
collected 14 items
... 14 failed (all ModuleNotFoundError on 'pathfinder_player_adapter') ...
14 failed in 0.06s
```

All 14 fail at the function-scope `from pathfinder_player_adapter import ...` line — the desired RED state until Wave 7 lands the adapter module.

Existing Discord tests unrelated to this plan were spot-checked; failures observed in `test_pathfinder_dispatch.py::TestHarvestCommand`, `test_pathfinder_harvest_adapter.py`, `test_pathfinder_session_adapter.py`, and `test_subcommands.py` are pre-existing (HarvestCommand/`request.parts` `NoneType` regression and others) and are NOT introduced by this plan. Logged as out-of-scope — see "Deferred Issues" below.

## Behavioural-Test Compliance

Every test calls `cmd.handle(request)` and asserts on observable effects:

- `client.post_to_module.call_args[0]` for route path + payload (positional args inspection)
- `client.post_to_module.await_count` for the no-post short-circuit cases
- `response.kind` and `response.content` substring for usage hints

No source-grep, no `assert True`, no tautologies, no echo-chamber tests.

## Deviations from Plan

### Auto-fixed Issues

None — plan executed as written.

### Plan Wording vs. Final Count

- Plan body lists 14 distinct test cases but the success-criteria summary said "13 RED tests + user_id type guard." Final file contains 14 tests (the type-drift guard counted as the 14th). This matches the enumerated cases in the plan body verbatim — no scope deviation, just clearer counting.

## Deferred Issues

Pre-existing unrelated test failures observed in `interfaces/discord/tests/`:

- `test_pathfinder_dispatch.py::TestHarvestCommand::*` — `HarvestCommand.handle` calls `len(request.parts)` but `parts=None` in test fixtures → `TypeError`
- `test_pathfinder_harvest_adapter.py::*` — same root cause
- `test_pathfinder_session_adapter.py::test_handle_session_show_uses_placeholder_edit`
- `test_subcommands.py::test_pf_rule_*` and `test_pf_dispatch_cartosia_*` / `test_pf_dispatch_ingest_*`

These are out of scope for plan 37-04 (Wave 0 RED tests for player adapter). They are logged here for visibility; left untouched per the executor scope-boundary rule.

## TDD Gate Compliance

- RED gate: `27b0328 test(37-04): RED tests for Discord pathfinder_player_adapter` ✅
- GREEN gate: pending (Wave 7 plan — `interfaces/discord/pathfinder_player_adapter.py` implementation)
- REFACTOR gate: pending (Wave 7+)

## Self-Check

- File created: `[ -f interfaces/discord/tests/test_pathfinder_player_adapter.py ]` → FOUND
- Commit exists: `27b0328` → FOUND in `git log`
- Tests collect: 14 items collected by pytest
- Tests RED: 14 failed with ModuleNotFoundError as expected

## Self-Check: PASSED
