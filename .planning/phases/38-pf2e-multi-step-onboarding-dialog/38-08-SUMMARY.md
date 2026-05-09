---
phase: 38-pf2e-multi-step-onboarding-dialog
plan: 08
subsystem: testing
tags: [pytest, asyncmock, integration, e2e, discord, pathfinder, onboarding]

requires:
  - phase: 38-pf2e-multi-step-onboarding-dialog
    provides: dialog_router, pathfinder_player_dialog, pathfinder_player_adapter no-args/cancel/reject branches, discord_router_bridge wired with pre-router gate
provides:
  - End-to-end behavioural acceptance suite covering SPEC checkboxes 1-9
  - FakeVault in-memory Obsidian REST stand-in (reusable for future Phase-38-adjacent tests)
  - Pipe-syntax vs dialog payload byte-for-byte equality assertion (regression lock)
affects: [38-09, future pathfinder verbs, regression suite]

tech-stack:
  added: []
  patterns:
    - "FakeVault: dict-backed Obsidian REST mock with directory-listing support for reject_if_draft_open and frontmatter round-trip"
    - "Behavioural assertions only: every test calls a real entrypoint (PathfinderRequest, dialog_router, discord_router_bridge) and asserts on observable side-effects"
    - "Booby-trap pattern: AssertionError side_effect on create_thread to lock the pipe-syntax regression at criterion 9"

key-files:
  created:
    - interfaces/discord/tests/test_phase38_integration.py
  modified: []

key-decisions:
  - "Criterion 5 implemented as parametrized test across all 7 verbs gated by reject_if_draft_open (note, ask, npc, recall, todo, style, canonize) — gives 7 case checks per parametric expansion instead of one verb sampled"
  - "Criterion 10 (Wave-0 RED ordering) deliberately NOT a test in this file — it is a property of git history; verified manually in 38-09 Task 3 via git log --diff-filter=A"
  - "Restart simulation uses SENTINEL_THREAD_IDS.clear() rather than process restart; vault is sole truth (D-06) so this is byte-equivalent to a real restart"
  - "Payload byte-for-byte equivalence (criterion 4) asserts dict equality, not just superset, so any future drift in either path fails CI"

patterns-established:
  - "FakeVault mock supports both single-file GET/PUT/DELETE and directory-listing GET (returning {'files': [...]} shape used by reject_if_draft_open)"
  - "Each acceptance test docstring leads with 'SPEC Acceptance N:' verbatim text so test failures map directly to SPEC checkboxes"

requirements-completed: [PVL-01]

duration: 8min
completed: 2026-05-09
---

# Phase 38 Plan 08: Wave 5 — End-to-End Acceptance Tests Summary

**One test per SPEC acceptance checkbox 1-9, exercising the full bridge → dialog_router → pathfinder_player_dialog → /player/onboard pipeline through an in-memory FakeVault.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-05-09T13:51Z
- **Completed:** 2026-05-09T13:59Z
- **Tasks:** 2 (merged into a single TDD-GREEN commit since the under-test code already shipped in Waves 1-4)
- **Files modified:** 1

## Accomplishments

- New test file `interfaces/discord/tests/test_phase38_integration.py` with 9 acceptance tests (15 test cases when criterion 5's parametrize is expanded across the 7 gated verbs).
- All 9 SPEC checkboxes 1-9 have explicit, behavioural coverage. Failures map directly to SPEC items via the docstring leads.
- Pipe-syntax regression locked: criterion 9 booby-traps `channel.create_thread` with an `AssertionError` side-effect, so any future drift that would spawn a thread on pipe-syntax fails CI.
- Restart-survival (criterion 3) explicit: `SENTINEL_THREAD_IDS.clear()` between answers proves the vault is the sole source of truth (D-06).
- Payload byte-for-byte equivalence (criterion 4) asserts strict dict equality between the dialog completion path and the pipe-syntax path.

## Task Commits

1. **Tasks 1+2: 9 acceptance tests (criteria 1-9)** — `90cadbc` (test)

_Note: Plan 38-08 is a tests-only plan against already-shipped Wave 1-4 code, so RED→GREEN collapses into a single `test(...)` commit. There is no `feat(...)` follow-up because the implementation under test was committed in 38-04..38-07._

## Files Created/Modified

- `interfaces/discord/tests/test_phase38_integration.py` — 9 acceptance tests + `FakeVault` + `_FakeThread` / `_FakeTextChannel` helpers; ~470 lines.

## Decisions Made

- **Criterion 5 parametrized over 7 verbs.** The SPEC checkbox names all of `note|ask|npc|recall|todo|style|canonize`; testing only one would leave 6 verbs uncovered for the rejection-template path. Parametrize expands the single criterion test into 7 cases with one rejection-template assertion each.
- **No git-log meta-test for criterion 10.** A `pytest --collect-only` substring grep on Wave-0 RED test names cannot verify commit ordering and is brittle to test renames. Criterion 10 is verified during `/gsd-verify-work` in 38-09 Task 3 via `git log --diff-filter=A --format='%H %s' -- 'interfaces/discord/tests/test_pathfinder_player_dialog.py' 'interfaces/discord/tests/test_dialog_router.py'`.
- **FakeVault returns `{"files": [...]}` directory shape.** Matches the object-shape branch the adapter parses (RESEARCH §Pitfall 5). Tests that hit `reject_if_draft_open` exercise the same listing-parser as production.

## Deviations from Plan

None — plan executed exactly as written. The Plan 38-08 frontmatter explicitly excluded a criterion-10 meta-test; this Summary preserves that exclusion.

## Issues Encountered

None. All 15 new test cases passed on the first run after creation.

## Self-Check: PASSED

- File `/Users/trekkie/projects/sentinel-of-mnemosyne/interfaces/discord/tests/test_phase38_integration.py` — FOUND
- Commit `90cadbc` — FOUND in `git log`
- Combined run of `tests/test_pathfinder_player_dialog.py tests/test_dialog_router.py tests/test_pathfinder_player_adapter.py tests/test_phase38_integration.py` — 84 passed (69 prior + 15 new), no regressions.
- Pre-existing failures in `tests/test_subcommands.py` are unchanged baseline (18 failures present before this plan), out of scope per Rule 4 SCOPE BOUNDARY.

## Next Phase Readiness

- **38-09 (final regression sweep + git-log criterion-10 check) is unblocked.** All implementation waves (38-04, 38-05, 38-06, 38-07) plus this acceptance suite are GREEN. 38-09 Task 3 should run `git log --diff-filter=A --format='%H %s' -- 'interfaces/discord/tests/test_pathfinder_player_dialog.py' 'interfaces/discord/tests/test_dialog_router.py'` to confirm those files were ADDED in commits *before* the implementation commits (38-04..38-07).
- No blockers for Phase 38 acceptance.

---
*Phase: 38-pf2e-multi-step-onboarding-dialog*
*Plan: 08*
*Completed: 2026-05-09*
