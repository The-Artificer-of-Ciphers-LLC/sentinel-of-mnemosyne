---
phase: 38-pf2e-multi-step-onboarding-dialog
plan: 07
subsystem: interfaces/discord
tags: [pathfinder, player, dialog, rejection-guard, discord]
requires: [38-06]
provides:
  - reject_if_draft_open module-level helper in pathfinder_player_adapter
  - mid-dialog short-circuit on 7 non-start/non-cancel :pf player verbs
affects:
  - PlayerNoteCommand, PlayerAskCommand, PlayerNpcCommand, PlayerRecallCommand,
    PlayerTodoCommand, PlayerStyleCommand, PlayerCanonizeCommand
tech-stack:
  added: []
  patterns:
    - "Reuse-the-primitive: helper composes _list_user_draft_thread_ids from 38-06 instead of re-parsing the listing."
    - "Single-line guard at top of each handler -- additive, no behavior change for users without an open draft."
key-files:
  modified:
    - interfaces/discord/pathfinder_player_adapter.py
  created: []
decisions:
  - "Guard runs BEFORE usage-string short-circuits so a player with a draft can never trigger a usage hint and miss the redirect (D-05)."
  - "Singular vs multi-draft phrasing diverged per D-08: 'an onboarding dialog open in <#tid>' vs 'onboarding dialogs open in <#a>, <#b>'."
  - "404 on _drafts/ pass-through preserved (Pitfall 4) -- absence of the dir means no rejection."
metrics:
  duration_minutes: 4
  tasks_completed: 2
  files_changed: 1
  insertions: 53
  deletions: 0
  completed: 2026-05-09
requirements: [PVL-01]
---

# Phase 38 Plan 07: Mid-Dialog Rejection Guard Summary

Adds the `reject_if_draft_open` helper plus single-line invocations on all seven non-start/non-cancel `:pf player <verb>` handlers, turning the remaining 9 RED tests in `test_pathfinder_player_adapter.py` GREEN.

## What Shipped

**`reject_if_draft_open(request) -> PathfinderResponse | None`** — module-level async helper appended to `interfaces/discord/pathfinder_player_adapter.py` (just above `PlayerCancelCommand`). Returns `None` when the user has no open draft (or when `_drafts/` 404s); returns a `PathfinderResponse(kind="text", ...)` carrying clickable Discord channel-mention links to every open dialog thread otherwise.

The helper composes `_list_user_draft_thread_ids` from 38-06, so dual-shape Obsidian directory parsing (array of strings vs `{"files": [{"path": "..."}]}`) and 404 tolerance are inherited — no new code paths were needed for either.

**Verb wiring** — each of the seven handlers gained a three-line block at the top of its `handle()` method:

```python
rejection = await reject_if_draft_open(request)
if rejection is not None:
    return rejection
```

| Verb       | Class                  | Pre-existing entry line       |
| ---------- | ---------------------- | ----------------------------- |
| note       | `PlayerNoteCommand`    | `text = request.rest.strip()` |
| ask        | `PlayerAskCommand`     | `text = request.rest.strip()` |
| npc        | `PlayerNpcCommand`     | `rest = request.rest.strip()` |
| recall     | `PlayerRecallCommand`  | `query = request.rest.strip()`|
| todo       | `PlayerTodoCommand`    | `text = request.rest.strip()` |
| style      | `PlayerStyleCommand`   | `rest = request.rest.strip()` |
| canonize   | `PlayerCanonizeCommand`| `rest = request.rest.strip()` |

`PlayerStartCommand` and `PlayerCancelCommand` are intentionally NOT gated — start has its own resume-vs-create branching from 38-06, and cancel is the documented escape hatch.

## Test Delta

| Test File                                | Before 38-07 | After 38-07 |
| ---------------------------------------- | ------------ | ----------- |
| `test_pathfinder_player_adapter.py`      | 27 pass / pytest stops at first parametrized RED | 38 pass |
| `test_pathfinder_player_dialog.py`       | 23 pass      | 23 pass     |
| `test_dialog_router.py`                  | 8 pass       | 8 pass      |

The nine RED tests turned GREEN by this plan:
- `test_verb_blocked_when_draft_open` (7 parametrized cases — note, ask, npc, recall, todo, style, canonize)
- `test_multi_draft_rejection_lists_all_thread_links_for_this_user`
- `test_drafts_listing_object_shape_also_rejected`

The PVL-07 isolation tests (`test_no_draft_passes_through_to_normal_verb`, `test_drafts_dir_404_passes_through`) were already green courtesy of 38-06's filename suffix filter and 404 handling — confirmed still green here.

## Deviations from Plan

None — plan executed as written. The plan's Task 1 action mentioned "verify `_list_user_draft_thread_ids` handles the dual-shape response and 404; if 38-06's implementation only handled one shape, fix it here." Inspection of `_parse_draft_filenames` in `pathfinder_player_adapter.py` confirms 38-06 already covers both shapes (`isinstance(payload, list)` branch plus `isinstance(payload, dict)` + `payload.get("files")` branch with per-entry dict/str handling); no fix was needed.

## Spec-Conflict Guardrail Check

Rejection text contains the locked components from the 38-03 RED contract:
- Discord channel-mention syntax `<#{thread_id}>` for every open thread (D-07)
- Literal substring `:pf player cancel` (D-05)
- Literal substring `onboarding` (case-insensitive match)
- Multi-draft case enumerates every `<#tid>`, never just the first (D-08)

No validated v0.x behavior altered. The seven verbs still post to their existing `modules/pathfinder/player/<verb>` routes when the user has no open draft — the no-draft path is unchanged.

## Commits

- `8058250` — feat(38-07): add reject_if_draft_open guard for the 7 non-start/non-cancel verbs

## Out-of-Scope Discoveries

`tests/test_pathfinder_dispatch.py` has pre-existing failures (~30) unrelated to this plan; verified with `git stash` that they fail identically before this commit lands. Logged here, not addressed (Rule: scope discipline).

## Self-Check: PASSED

- File `interfaces/discord/pathfinder_player_adapter.py`: FOUND (modified, +53 lines)
- Commit `8058250`: FOUND on main
- `reject_if_draft_open` helper: present at module level above `PlayerCancelCommand`
- 7 verb handlers all start with the rejection guard: verified by inspection
- Test counts: 38 / 23 / 8 — all GREEN
