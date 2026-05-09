---
phase: 38-pf2e-multi-step-onboarding-dialog
plan: 02
subsystem: interfaces/discord
tags: [tdd, red, dialog-router, wave-0, phase-38]
requires: []
provides:
  - "RED test contract for interfaces/discord/dialog_router.maybe_consume_as_answer"
  - "Hit/miss matrix locking D-01, D-02 from 38-CONTEXT.md"
affects:
  - "Wave 2 implementation (38-05) — these tests must turn GREEN when dialog_router.py ships"
tech-stack:
  added: []
  patterns:
    - "Function-scope imports for RED-until-implemented (matches test_pathfinder_player_adapter.py)"
    - "monkeypatch discord.Thread to a real distinguishing class so isinstance discriminates against the conftest stub (Thread = object)"
    - "Real httpx.Response objects from AsyncMock so production code can call .status_code / .text / .raise_for_status without per-test plumbing"
key-files:
  created:
    - "interfaces/discord/tests/test_dialog_router.py (327 lines, 8 RED tests)"
  modified: []
decisions:
  - "Used a local _RealThread class + monkeypatch.setattr(discord, 'Thread', _RealThread) inside each test rather than relying on the conftest discord.Thread stub (which aliases to `object` and breaks isinstance discrimination)"
  - "Lazily ensure pathfinder_player_dialog exists in sys.modules so monkeypatch.setattr can install consume_as_answer regardless of import order — the canonical RED signal stays on dialog_router"
metrics:
  duration_seconds: 117
  task_count: 1
  test_count: 8
  file_count: 1
  completed: 2026-05-09
---

# Phase 38 Plan 02: RED Tests for dialog_router Hit/Miss Matrix Summary

**One-liner:** Wave 0 RED contract — 8 behavioral tests that fail with `ModuleNotFoundError: No module named 'dialog_router'` until Wave 2 (38-05) ships the pre-router gate.

## What Shipped

A single new file, `interfaces/discord/tests/test_dialog_router.py`, with 8 async tests pinned to the locked D-01/D-02 hit conditions:

| # | Test | Locks |
|---|------|-------|
| 1 | `test_miss_when_message_has_colon_prefix` | `":pf …"` is a command, never an answer (D-02 cond. 1) |
| 2 | `test_miss_when_message_has_leading_whitespace_then_colon` | Whitespace doesn't smuggle commands past the gate; aligns with `command_router.py:8-34` |
| 3 | `test_miss_when_channel_is_not_thread` | Non-Thread channel → return None **without** issuing the HTTP GET (D-02 ordering, blast-radius zero outside Sentinel threads) |
| 4 | `test_miss_when_draft_does_not_exist` | 404 on the draft path → miss; `consume_as_answer` not called |
| 5 | `test_hit_invokes_consume_as_answer` | All three hit conditions → forward kwargs `thread/user_id/message_text/sentinel_client/http_client` and return the dialog's response string verbatim |
| 6 | `test_hit_uses_thread_id_in_draft_path_lookup` | URL ends with `/vault/mnemosyne/pf2e/players/_drafts/{thread.id}-{user_id}.md` (canonical `(thread_id, user_id)` key from SPEC) |
| 7 | `test_empty_message_is_miss` | Embed-only / whitespace-only edits don't fire the gate |
| 8 | `test_obsidian_get_error_falls_through` | `httpx.RequestError` during the existence check → miss (gate is non-fatal); `command_router` still gets a chance |

## RED Proof

```text
$ cd interfaces/discord && python -m pytest tests/test_dialog_router.py
Pytest: 0 passed, 8 failed

1. [FAIL] test_miss_when_message_has_colon_prefix
   E   ModuleNotFoundError: No module named 'dialog_router'
2. [FAIL] test_miss_when_message_has_leading_whitespace_then_colon
   E   ModuleNotFoundError: No module named 'dialog_router'
3. [FAIL] test_miss_when_channel_is_not_thread
   E   ModuleNotFoundError: No module named 'dialog_router'
4. [FAIL] test_miss_when_draft_does_not_exist
   E   ModuleNotFoundError: No module named 'dialog_router'
5. [FAIL] test_hit_invokes_consume_as_answer
   E   ModuleNotFoundError: No module named 'dialog_router'
… +3 more (all ModuleNotFoundError on dialog_router)
```

All 8 tests collect cleanly and fail on the same import. RED state confirmed.

## Behavioral-Test-Only Compliance

Every assertion exercises observable behavior — return value (`None` vs `"next question"`), recorded mock call counts (`AsyncMock.await_count`), kwarg forwarding (`consume.await_args.kwargs["thread"] is channel`), or the literal URL passed to `http_client.get`. No source-grep, no `assert True`, no sole `assert_called`. The single `endswith` assertion on the draft URL is paired with a strict canonical path that would fail on any drift.

## Deviations from Plan

None — plan executed exactly as written. The plan offered two patterns for handling the lazy `pathfinder_player_dialog` import; the implemented helper (`_stub_consume_as_answer`) follows the second (recommended) pattern, registering a stub `pathfinder_player_dialog` module in `sys.modules` only if absent so `monkeypatch.setattr` succeeds regardless of which dependency is missing first. The canonical RED signal stays on `dialog_router`.

## What's Out of Scope (Deferred)

- Production `dialog_router.py` — Wave 2 (38-05).
- `pathfinder_player_dialog.py` (`consume_as_answer`, `start_dialog`, `cancel_dialog`) — Wave 1 (38-04).
- Bridge wiring in `discord_router_bridge.route_message` to call the new gate before `command_router` — Wave 2 (38-05/38-06).
- Pre-existing failures elsewhere in `interfaces/discord/tests/` (e.g. `pathfinder_harvest_adapter.py:22 NoneType` errors in `TestHarvestCommand`) — predate this plan, logged as out-of-scope per the executor scope boundary rule.

## Self-Check: PASSED

- `interfaces/discord/tests/test_dialog_router.py` — FOUND
- Commit `a65d417` — FOUND in `git log` (`test(38-02): RED tests for dialog_router hit/miss matrix`)
- 8 tests collected, 8 ImportError failures — verified via pytest output
- No production code added — `git status --short interfaces/` shows only the new test file
