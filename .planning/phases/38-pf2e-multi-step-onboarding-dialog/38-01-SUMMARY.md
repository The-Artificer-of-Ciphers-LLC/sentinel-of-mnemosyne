---
phase: 38
plan: 01
subsystem: interfaces/discord
tags: [tdd, red, pf2e, onboarding, dialog]
type: tdd
wave: 0
requires: []
provides:
  - "RED contract for pathfinder_player_dialog public surface"
affects:
  - interfaces/discord/tests/test_pathfinder_player_dialog.py
tech-stack:
  added: []
  patterns:
    - "function-scope import RED convention (mirrors test_pathfinder_player_adapter.py: 16 imports / 12 tests)"
    - "AsyncMock http_client + assertion via .call_args"
    - "Discord stubs from conftest.py (Phase 33-01 decision — no per-file stubs)"
key-files:
  created:
    - interfaces/discord/tests/test_pathfinder_player_dialog.py
  modified: []
decisions:
  - "Body-arg extraction is shape-defensive: tolerates positional, data=, or content= http.put kwarg (pre-locks Wave-1 freedom on httpx call shape)."
  - "discord.HTTPException raised in tests uses the conftest stub (mapped to plain Exception) — plan 38-04 must catch HTTPException specifically, but the test passes whatever the stub exposes."
metrics:
  duration: "<5min"
  tests-added: 23
  tests-failing-red: 23
  files-created: 1
  completed: 2026-05-09
---

# Phase 38 Plan 01: Wave 0 RED Tests for pathfinder_player_dialog Summary

23 RED behavioral tests for the not-yet-existing `interfaces/discord/pathfinder_player_dialog.py` module, locking the public contract before Wave 1 (plan 38-04) implementation lands.

## What Shipped

- `interfaces/discord/tests/test_pathfinder_player_dialog.py` — 23 `async def test_*` tests, asyncio_mode="auto", function-scope imports of every `pathfinder_player_dialog` symbol so collection succeeds and every test fails with `ModuleNotFoundError: No module named 'pathfinder_player_dialog'`.

## Test Inventory

| # | Test | Locks |
|---|------|-------|
| 1 | `test_steps_tuple_locked` | D-13 step ordering |
| 2 | `test_questions_dict_locked` | D-13 verbatim question text |
| 3 | `test_draft_path_format` | D-05 path scheme |
| 4 | `test_draft_path_coerces_user_id_to_str` | Pitfall 6 |
| 5 | `test_save_draft_puts_frontmatter_only_body` | save_draft contract |
| 6 | `test_load_draft_returns_frontmatter_dict` | load_draft happy path |
| 7 | `test_load_draft_404_returns_none` | Pitfall 4 |
| 8 | `test_delete_draft_calls_http_delete` | delete_draft contract |
| 9 | `test_start_dialog_creates_public_thread` | SPEC Req 1; Pitfall 1 |
| 10 | `test_start_dialog_thread_name_truncated_to_100_chars` | Discord 100-char cap |
| 11 | `test_start_dialog_registers_thread_id_in_sentinel_set` | D-11 inverse |
| 12 | `test_resume_dialog_reposts_current_step` | SPEC Req 7 |
| 13 | `test_resume_dialog_does_not_reset_existing_answers` | SPEC Req 7 acceptance |
| 14 | `test_consume_as_answer_first_step_advances_to_preferred_name` | SPEC Req 2 |
| 15 | `test_consume_as_answer_second_step_advances_to_style_preset` | answer preservation |
| 16 | `test_consume_as_answer_final_step_calls_onboard_route` | SPEC Req 4; D-09; D-11 |
| 17 | `test_consume_as_answer_style_preset_case_insensitive_normalised` | RESEARCH Q10 |
| 18 | `test_consume_as_answer_invalid_style_preset_reasks` | D-14 |
| 19 | `test_consume_as_answer_archive_swallows_already_archived` | Pitfall 2 |
| 20 | `test_consume_as_answer_does_not_invoke_ai` | SPEC Req 2 (AI-not-invoked) |
| 21 | `test_cancel_dialog_with_existing_draft_deletes_and_archives` | SPEC Req 6; D-10 |
| 22 | `test_cancel_dialog_with_no_draft_returns_no_progress_message` | SPEC Req 6 acceptance |
| 23 | `test_cancel_dialog_archive_swallows_http_exception` | Pitfall 2 (cancel side) |

## Requirements Coverage

| SPEC Requirement | Tests |
|------------------|-------|
| Req 1 (thread creation) | 9, 10, 11 |
| Req 2 (plain-text capture, no AI) | 14, 15, 20 |
| Req 3 (vault-backed draft) | 3, 4, 5, 6, 7, 8 |
| Req 4 (completion calls /player/onboard) | 16, 17 |
| Req 6 (cancel) | 21, 22, 23 |
| Req 7 (resume on restart-start) | 12, 13 |

Req 5 (mid-dialog rejection) lives in 38-02; pipe-syntax regression lives in 38-03.

PVL-01 traceability: Test 16 asserts the assembled four-field payload byte-for-byte against the existing `/player/onboard` schema — Phase-37 contract preserved.

## RED Verification

```text
cd interfaces/discord && python -m pytest tests/test_pathfinder_player_dialog.py
Pytest: 0 passed, 23 failed
ModuleNotFoundError: No module named 'pathfinder_player_dialog'  (×46 in tb=line output: 23 tests × 2 mentions per failure)
```

Sibling regression check: `python -m pytest tests/test_pathfinder_player_adapter.py` → `16 passed`. No existing test touched.

## Commits

- `dd027eb` — Task 1: 8 RED tests for constants + draft I/O contract
- `7977437` — Task 2: 5 RED tests for start_dialog + resume_dialog (SPEC Req 1, 7)
- `1f38f6f` — Task 3: 10 RED tests for consume_as_answer + cancel_dialog (SPEC Req 2, 4, 6)

## Deviations from Plan

None — plan executed exactly as written.

The plan's `_fake_resp` helper signature was implemented as specified; `_fake_draft_body(**fields)` mirrors the YAML-frontmatter shape `pathfinder_player_dialog._join_fm` is expected to emit (RESEARCH §"Frontmatter round-trip" — `yaml.safe_dump(... default_flow_style=False)` with `---\n…\n---\n` wrapper).

Body-extraction in three tests (`test_save_draft_puts_frontmatter_only_body`, `test_start_dialog_creates_public_thread`, `_put_body` helper) is shape-defensive over `http.put(url, body)` vs `http.put(url, data=body)` vs `http.put(url, content=body)` — the exact httpx kwarg is implementation choice for plan 38-04, the test asserts only that the body string lands and contains the required YAML lines. This preserves Wave-1 freedom without weakening any contract assertion.

## Out-of-Scope Findings (deferred — SCOPE BOUNDARY)

Running the full discord test suite shows 18 pre-existing failures unrelated to this plan (test_pathfinder_dispatch, test_pathfinder_rule_adapter, test_subcommands harvest/cartosia paths). None touch `pathfinder_player_*` modules; deferred per `<deviation_rules>` SCOPE BOUNDARY.

## Threat Flags

None — RED test file only; no production surface introduced.

## TDD Gate Compliance

This plan is the RED gate for the broader Phase 38 dialog module feature. GREEN gate ships in plan 38-04 (per the Phase 38 wave map in 38-RESEARCH §Q7).

## Self-Check: PASSED

- File `interfaces/discord/tests/test_pathfinder_player_dialog.py` exists (verified via `git log --stat`).
- Commits `dd027eb`, `7977437`, `1f38f6f` exist on main (verified via `git log --oneline -5`).
- All 23 tests fail with ModuleNotFoundError on the not-yet-existing module (verified via pytest run with `--tb=line` showing 46 ModuleNotFoundError lines = 23 tests × 2).
