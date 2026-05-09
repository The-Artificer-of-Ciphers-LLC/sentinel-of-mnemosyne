---
phase: 38-pf2e-multi-step-onboarding-dialog
plan: 03
subsystem: discord-pathfinder
tags: [tdd, red-tests, wave-0, adapter, regression-locks]
requires: []
provides: ["adapter-test-contracts"]
affects: ["38-06", "38-07"]
tech-stack:
  added: []
  patterns: ["function-scope imports for RED isolation", "fake module injection via sys.modules", "monkeypatch discord.Thread to a real class for isinstance branching"]
key-files:
  created: []
  modified:
    - "interfaces/discord/tests/test_pathfinder_player_adapter.py"
decisions:
  - "Adopt fake-module pattern (`_install_fake_dialog_module`) instead of importing pathfinder_player_dialog (does not yet exist) — keeps Task 2 commit independent of Task 6 ordering"
  - "Use a real `_FakeThread` class via `monkeypatch.setattr('discord.Thread', _FakeThread)` so isinstance(channel, Thread) returns the right answer (conftest's `Thread = object` makes everything True)"
  - "Added one extra dual-shape rejection test (object-shape `_drafts/` listing) — locks RESEARCH §Pitfall 5 explicitly; brings new test count to 23 vs the planned 22"
metrics:
  duration: "~25 min"
  completed: "2026-05-09"
---

# Phase 38 Plan 03: Wave 0 RED tests for adapter no-args / cancel / rejection (+ pipe-syntax regression locks) Summary

Wave 0 TDD: 23 new tests appended to `test_pathfinder_player_adapter.py` — 6 GREEN-on-day-zero regression contracts pin the existing pipe-syntax path so any future change to `PlayerStartCommand` that breaks `Aria | Ari | Tactician` semantics fails CI; 17 RED tests assert the contract that 38-06 and 38-07 must satisfy (no-args branch, `PlayerCancelCommand`, multi-draft cancel symmetry per D-17, mid-dialog rejection guard for all 7 non-start/non-cancel verbs incl. dual-shape `_drafts/` listing).

## What Shipped

| Category | Tests | State on commit |
|---|---|---|
| PlayerStartCommand no-args branch (D-15) | 2 | RED — TypeError on missing `author_display_name` field (38-04) |
| Pipe-syntax regression locks (SPEC Constraint) | 4 | GREEN |
| PlayerCancelCommand single-draft + dispatch (D-16) | 3 | RED — ImportError on `PlayerCancelCommand` |
| PlayerCancelCommand multi-draft symmetry (D-17) | 3 | RED — ImportError |
| Mid-dialog rejection guard, parametrised across 7 verbs (SPEC Req 5, D-05/07/08) | 7 | RED — `post_to_module` still called |
| Multi-draft rejection lists every link, filter by user (D-08, PVL-07) | 1 | RED |
| `_drafts/` 404 pass-through (Pitfall 4) | 1 | GREEN |
| Other-user-only draft pass-through (PVL-07) | 1 | GREEN |
| Object-shape `_drafts/` listing (Pitfall 5) | 1 | RED |
| **Total new** | **23** | **6 GREEN, 17 RED** |

## Test Categories — exact pytest breakdown

```
Pre-existing (untouched):                  16 PASS
New GREEN (regression / pass-through):      6 PASS
New RED (38-04 / 38-06 / 38-07):           17 FAIL
                                          ----
Total:                                     22 pass, 17 fail (39 collected)
```

## RED-failure modes (intentional, documented for the verifier)

1. **`author_display_name` TypeError** — 2 tests fail at request construction. Resolves when 38-04 adds the field to `PathfinderRequest`.
2. **ImportError on `PlayerCancelCommand`** — 6 tests. Resolves when 38-06 lands the class + dispatch registration.
3. **Rejection-guard absence** — 9 tests. The current handlers call `post_to_module` unconditionally; the new guard `reject_if_draft_open` short-circuits this path. Resolves when 38-07 lands.

## Pre-existing tests still pass

```
$ python -m pytest tests/test_pathfinder_player_adapter.py -k "not (no_args or pipe_syntax_regression or player_cancel or blocked_when_draft or multi_draft_rejection or no_draft_passes or drafts_dir_404 or drafts_listing_object)"
16 passed
```

## CLAUDE.md compliance

- **Test-Rewrite Ban:** all 16 existing tests are byte-for-byte unchanged — diff is purely additive (verified by `git diff --stat`: `1 file changed, 708 insertions(+)`).
- **Behavioral-Test-Only Rule:** every assertion either checks an observable side-effect (`post_to_module.await_count`, `http_client.delete` URL substring, `thread.edit(archived=True)`) or a returned `PathfinderResponse.content` substring against a SPEC-defined phrase. No source greps, no `assert True`, no mock-only call-shape echo.
- **Spec-Conflict Guardrail:** the four pipe-syntax regression locks explicitly preserve the validated v0.x behaviour (PROJECT.md "Core Value", PVL-01 contract); the no-args branch tests assert the new dialog flow ADDS to (does not replace) that path.

## Deviations from Plan

**Additive only — 1 extra test.** Plan called for 22 new tests (6+6+10). I shipped 23: the extra is `test_drafts_listing_object_shape_also_rejected`, which the plan body explicitly mandated ("write at least one test where the response is the array shape ... and one where it's `{"files": [{"path": "111-u-1.md"}]}` to lock both shapes are handled"). The plan's task-level count (10 in Task 3) didn't match its prose; the prose won.

No bug-fixes auto-applied (Rule 1-3) — Wave 0 is pure RED tests, no production code touched.

## Commits

- `c6fca2d` — test(38-03): RED tests for adapter no-args/cancel/rejection + pipe-syntax regression locks

## Self-Check: PASSED

- [x] `interfaces/discord/tests/test_pathfinder_player_adapter.py` exists and contains 39 collected tests.
- [x] Commit `c6fca2d` exists in `git log --oneline -1`.
- [x] All 16 pre-existing tests pass (`pytest -k "not (no_args ...)"` returns 16 passed).
- [x] 4 pipe-syntax regression contracts pass GREEN.
- [x] 17 RED tests fail with expected error modes (TypeError / ImportError / assertion on `post_to_module` count).
