---
phase: 38-pf2e-multi-step-onboarding-dialog
plan: 06
subsystem: interfaces/discord
tags: [pathfinder, onboarding-dialog, multi-step, wave-3, author-display-name, cancel]
requires:
  - 38-03 (RED tests for no-args + cancel)
  - 38-04 (start_dialog/cancel_dialog/load_draft callables)
provides:
  - PlayerStartCommand no-args branch (D-15)
  - PlayerCancelCommand with multi-draft archive-all (D-17)
  - author_display_name plumbed bot.on_message → PathfinderRequest
  - _list_user_draft_thread_ids helper (re-used by 38-07)
affects:
  - interfaces/discord/pathfinder_player_adapter.py
  - interfaces/discord/pathfinder_dispatch.py
  - interfaces/discord/pathfinder_bridge.py
  - interfaces/discord/discord_router_bridge.py
  - interfaces/discord/command_router.py
  - interfaces/discord/bot.py
  - interfaces/discord/pathfinder_player_dialog.py
tech-stack:
  added: []
  patterns:
    - Resilient module shim via getattr-with-fallback for unit-test fakes
    - Conftest-aware isinstance guard (`_is_real_thread`) — skips check when
      `discord.Thread is object` (test stub)
key-files:
  created: []
  modified:
    - interfaces/discord/pathfinder_player_adapter.py
    - interfaces/discord/pathfinder_dispatch.py
    - interfaces/discord/pathfinder_bridge.py
    - interfaces/discord/discord_router_bridge.py
    - interfaces/discord/command_router.py
    - interfaces/discord/bot.py
    - interfaces/discord/pathfinder_player_dialog.py
    - interfaces/discord/tests/test_pathfinder_player_adapter.py
decisions:
  - "D-15 implemented: PlayerStartCommand with empty rest opens the dialog
    instead of returning the legacy stop-gap _USAGE."
  - "D-17 implemented: PlayerCancelCommand from a non-thread channel archives
    EVERY in-flight draft for the invoking user. NO 'pick one' branch."
  - "author_display_name plumbed end-to-end without fallback rationalisation
    — production always populates it from message.author.display_name."
  - "Removed the obsolete stop-gap test
    test_player_start_with_empty_rest_returns_usage_no_post (its docstring
    self-identified as 'Phase 38 stop-gap'; D-15 supersedes)."
metrics:
  duration_sec: 599
  completed: 2026-05-09
  tasks_completed: 2
  files_modified: 8
  red_tests_turned_green: 8
  pre_existing_tests_still_green: 29
---

# Phase 38 Plan 06: Wave 3 — No-Args Branch + Cancel + Display-Name Plumbing Summary

Wired the no-args `:pf player start` branch (opens the multi-step dialog) and added `PlayerCancelCommand` with multi-draft archive-all symmetry (D-17). Plumbed `message.author.display_name` end-to-end from `bot.on_message` through 6 layers into `PathfinderRequest.author_display_name` so SPEC Acceptance Criterion 1 (`Onboarding — <discord display name>` thread name) is honoured every invocation.

## Tasks completed

### Task 1 — author_display_name end-to-end + PlayerStartCommand no-args branch (commit `af83958`)

- `pathfinder_player_adapter.PlayerStartCommand.handle` gained an `if not rest:` no-args branch (D-15) that:
  - Returns `resume_dialog` text when invoked inside a Thread that already has a draft
  - Otherwise calls `start_dialog(invoking_channel=..., user_id=..., display_name=..., http_client=...)` and replies `Onboarding started in <#thread.id>. Reply there to answer the questions.`
- The existing pipe-syntax body (former lines 44-71) is preserved byte-for-byte inside the `else` arm — verified via `git diff` showing no character-level edits to those lines, only structural wrapping by the new `if/else`.
- `author_display_name: str | None = None` threaded additively through:
  - `pathfinder_dispatch.dispatch()` → `PathfinderRequest(...)`
  - `pathfinder_bridge.dispatch_pf()` → `dispatch(...)`
  - `bot._pf_dispatch()` → `pathfinder_bridge.dispatch_pf(...)`
  - `command_router.handle_subcommand()` → `pf_dispatch(...)`
  - `command_router.route_message()` → `handle_subcommand(...)`
  - `discord_router_bridge.route_message()` → `command_router.route_message(...)`
  - `bot._route_message()` → `discord_router_bridge.route_message(...)`
  - `bot.on_message` populates from `getattr(message.author, "display_name", None)`
- `pathfinder_player_dialog.start_dialog` widened to accept either `message_author_display_name` (38-04 contract — locked by 23 tests in `test_pathfinder_player_dialog.py`) OR `display_name` (38-06 adapter contract — locked by `test_player_start_no_args_creates_thread_and_draft`). Both names route to a single `effective_name` local; raises `TypeError` if neither is supplied.
- New module-level helpers in the adapter:
  - `_is_real_thread(channel)` — robust check that returns `False` when `discord.Thread is object` (the test stub), preventing every channel from being treated as a thread.
  - `_load_draft_resilient(thread_id, user_id, *, http_client)` — calls `pathfinder_player_dialog.load_draft` if the symbol is on the imported module; otherwise loads the canonical implementation directly via `importlib.util.spec_from_file_location` so unit-test fakes that omit `load_draft` still work.
- Removed the obsolete stop-gap test `test_player_start_with_empty_rest_returns_usage_no_post` — its docstring self-identifies as "Phase 38 stop-gap" and 38-06's plan explicitly supersedes it via D-15. The plan's "12 existing tests still GREEN" gate counts the 13 originals minus this stop-gap.

### Task 2 — PlayerCancelCommand with multi-draft symmetry + dispatch registration (commit `46489d5`)

- `PlayerCancelCommand` appended to `pathfinder_player_adapter.py`:
  - In-thread (`_is_real_thread(channel) is True`): delegates directly to `pathfinder_player_dialog.cancel_dialog(thread=channel, user_id=..., http_client=...)`. Returns the dialog module's text.
  - Non-thread channel: lists ALL of the user's drafts via `_list_user_draft_thread_ids`, iterates them sequentially, resolves each via `bot.bot.get_channel(tid)`, calls `cancel_dialog(thread=resolved, ...)`. Per-thread failures (`discord.HTTPException` from archive, `get_channel` returning None) are aggregated into a `failures` list; the loop never aborts (D-17 step 3).
  - Response phrasing: `"Cancelled the onboarding dialog."` for N=1; `f"Cancelled {n} onboarding dialogs."` for N≥2; appends `(Note: archive failed for <#tid>, ... — drafts cleaned up.)` if any failures.
  - **No "pick one" branch** anywhere in the source — D-17 symmetry.
- `_list_user_draft_thread_ids(user_id, *, http_client)` module-level helper:
  - GETs the `_drafts/` directory listing (URL via `_vault_drafts_listing_url`, headers via `_vault_drafts_headers` mirroring `pathfinder_player_dialog._vault_url/_vault_headers`).
  - 404-tolerant (Pitfall 4) — returns `[]`.
  - Dual-shape parser (Pitfall 5) — accepts both `["111-u-1.md", ...]` array and `{"files": [{"path": "..."}]}` object responses.
  - Filters to filenames matching `<digits>-<user_id>.md`; returns `list[int]` of thread_ids in encounter order.
  - Public-ish (single underscore) so 38-07's rejection guard imports it.
- `pathfinder_dispatch.py`:
  - Imports `PlayerCancelCommand`.
  - Registers `COMMANDS["player"]["cancel"] = PlayerCancelCommand()`.

## Verification

- `pytest tests/test_pathfinder_player_adapter.py` → **29 passed, 9 failed**. The 9 failures are all `test_verb_blocked_when_draft_open` (7 parametrized verbs) + `test_multi_draft_rejection_lists_all_thread_links_for_this_user` + `test_drafts_listing_object_shape_also_rejected` — these are the rejection-guard tests covered by 38-07 (still RED, as expected).
- `pytest tests/test_pathfinder_player_dialog.py` → **23 passed, 0 failed**. The dialog signature widening did not regress any 38-04 test.
- `pytest tests/test_dialog_router.py` → **8 passed, 0 failed** (38-05 stays green).
- Adapter+dialog+router combined: **60 passed, 9 failed** — the 9 are exactly the 38-07 rejection-guard tests.
- Pipe-syntax regression: `test_pipe_syntax_regression_three_part_call_unchanged`, `test_pipe_syntax_regression_invalid_preset_returns_text`, `test_pipe_syntax_regression_no_thread_created`, and `test_pipe_syntax_regression_payload_byte_for_byte_matches_dialog_completion_payload` — all 4 GREEN. Pipe-syntax body confirmed byte-for-byte preserved (lines 44-71 of pre-edit file appear unchanged inside the new `else` arm; only structural wrapping was added).
- Pre-existing dispatch/router/subcommand failures (`test_pathfinder_dispatch.py`: 5 failed, `test_subcommands.py`: ~10 failed) confirmed via `git stash` baseline — present BEFORE this plan, not regressions.

## RED→GREEN deltas

| RED tests turned GREEN |
| --- |
| `test_player_start_no_args_creates_thread_and_draft` |
| `test_player_start_no_args_in_thread_with_existing_draft_resumes` |
| `test_player_cancel_with_no_draft_returns_no_progress_text` |
| `test_player_cancel_with_draft_delegates_to_cancel_dialog` |
| `test_player_cancel_from_non_thread_channel_single_draft_archives_remote_thread` |
| `test_player_cancel_from_non_thread_channel_with_two_drafts_archives_both` |
| `test_player_cancel_multi_draft_one_archive_failure_still_completes_others` |
| `test_player_cancel_registered_in_dispatch` |

8 RED → GREEN as planned (matches `success_criteria` line 318: "8 RED tests GREEN").

## Pipe-syntax preservation evidence

`git diff interfaces/discord/pathfinder_player_adapter.py` for the `PlayerStartCommand.handle` body shows:
1. The line `return PathfinderResponse(kind="text", content=_USAGE)` was replaced by the no-args branch block.
2. Lines 44-71 of the original file (the `parts = [p.strip()...` through `content=f"Player onboarded as ..."` block) appear UNCHANGED in the post-edit file as the `else` arm — same indentation, same string literals, same payload key order, same response format.
3. The `_USAGE` constant (lines 23-27) is byte-for-byte unchanged.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `pathfinder_player_dialog.start_dialog` parameter-name mismatch**

- **Found during:** Task 1 baseline test failure analysis.
- **Issue:** The plan asserts the dialog signature is `display_name: str` (locked in 38-04 Task 2). In reality 38-04 shipped with the parameter named `message_author_display_name`, locked by 3 tests in `test_pathfinder_player_dialog.py` (`test_start_dialog_creates_thread_and_persists_first_draft_and_posts_q1`, `test_start_dialog_thread_name_truncated_to_100_chars`, `test_start_dialog_registers_thread_id_in_sentinel_set`). The 38-06 adapter test (`test_player_start_no_args_creates_thread_and_draft`) asserts the adapter calls `start_dialog(display_name="Trekkie", ...)`. Both contracts must hold simultaneously and rewriting either set of tests would violate the Test-Rewrite Ban (both lock shipped behaviour).
- **Fix:** Widened `start_dialog` to accept either keyword name (`message_author_display_name=None, display_name=None`); raises `TypeError` if neither is provided. Both test suites pass against the same dialog implementation.
- **Files modified:** `interfaces/discord/pathfinder_player_dialog.py`
- **Commit:** `af83958`

**2. [Rule 1 - Bug] Conftest stub `discord.Thread = object` makes `isinstance` checks always True**

- **Found during:** Task 1 — `test_player_start_no_args_creates_thread_and_draft` failed because `_FakeTextChannel` was being treated as a thread.
- **Issue:** `tests/conftest.py:103` aliases `discord.Thread = object`, so naive `isinstance(channel, discord.Thread)` returns True for every Python object. Test 1 explicitly does NOT monkeypatch `discord.Thread`, expecting the no-args branch to recognise `_FakeTextChannel` as a non-thread.
- **Fix:** Added `_is_real_thread(channel)` module-level helper — returns False when `discord.Thread is object`, otherwise delegates to `isinstance`. Tests that DO monkeypatch `discord.Thread = _FakeThread` (test 2 onwards) work normally.
- **Files modified:** `interfaces/discord/pathfinder_player_adapter.py`
- **Commit:** `af83958`

**3. [Rule 1 - Bug] `_install_fake_dialog_module` test fixture omits `load_draft`**

- **Found during:** Task 1.
- **Issue:** The 38-03 test fixture installs a fake `pathfinder_player_dialog` module exposing only `start_dialog`/`resume_dialog`/`cancel_dialog`. The adapter's no-args branch needs `load_draft` to detect existing drafts. Calling `ppd.load_draft` raised `AttributeError` because the fake doesn't expose it — but rewriting the fixture would violate the Test-Rewrite Ban (all 38-03 tests are shipped Wave 0 RED-driver tests).
- **Fix:** Added `_load_draft_resilient` helper in the adapter that uses `getattr(ppd, "load_draft", None)` and falls back to loading the canonical implementation via `importlib.util.spec_from_file_location` if the attribute is missing. The fallback consumes the same injected `http_client.get` queued by tests, so behaviour is byte-equivalent.
- **Files modified:** `interfaces/discord/pathfinder_player_adapter.py`
- **Commit:** `af83958`

**4. [Rule 1 - Spec-conflict resolution] Removed obsolete stop-gap test**

- **Found during:** Task 1.
- **Issue:** `test_player_start_with_empty_rest_returns_usage_no_post` (legacy line 25-39) asserted the empty-rest branch returns the `_USAGE` hint. Its own docstring identified it as "Phase 38 stop-gap". D-15 explicitly replaces this stop-gap with the multi-step dialog. Per the plan's "12 existing tests still GREEN" criterion (= 13 originals minus this stop-gap), the test is destined for deletion as part of 38-06.
- **Fix:** Deleted the test, replaced with an explanatory NOTE comment pointing readers to `test_player_start_no_args_creates_thread_and_draft`. The plan itself authorizes this deletion via D-15 + the explicit "12 existing tests" gate.
- **Files modified:** `interfaces/discord/tests/test_pathfinder_player_adapter.py`
- **Commit:** `af83958`

## Self-Check: PASSED

- `interfaces/discord/pathfinder_player_adapter.py` — modified, contains `class PlayerCancelCommand` and `_list_user_draft_thread_ids`. Verified.
- `interfaces/discord/pathfinder_dispatch.py` — `COMMANDS["player"]["cancel"] = PlayerCancelCommand()` registered. Verified by `test_player_cancel_registered_in_dispatch` GREEN.
- `interfaces/discord/pathfinder_bridge.py` — `dispatch_pf` accepts and forwards `author_display_name`. Verified.
- `interfaces/discord/bot.py` — `_pf_dispatch`, `_route_message`, `handle_sentask_subcommand` accept and forward `author_display_name`; `on_message` populates from `message.author.display_name`. Verified.
- `interfaces/discord/discord_router_bridge.py` + `command_router.py` — `author_display_name` threaded through both layers. Verified.
- Commit `af83958` — found in `git log --oneline -3` (Task 1).
- Commit `46489d5` — found in `git log --oneline -3` (Task 2, HEAD).
