---
phase: 44-vault-namespace-taxonomy-foundation
plan: 03
subsystem: api
tags: [recall, vault, taxonomy, python, fastapi, dedup]

# Dependency graph
requires:
  - phase: 44-01
    provides: "D-03 PARA reroute (every topic resolves to ops/- or inbox/-prefixed destinations) and D-06 redirect retirement (pulled forward)"
provides:
  - "recall.py single-sources warm-tier exclusion prefixes from RecallConfig.exclude_prefixes only; the stale, inbox/-missing _WARM_TIER_EXCLUDE_PREFIXES duplicate is deleted"
  - "message_processing.py's dead re-export of _WARM_TIER_EXCLUDE_PREFIXES removed"
  - "Confirms (does not redo) that note_intake.py's searchable_only redirect and routes/message.py's _safe_file_chat_note guarantee were already retired upstream in 44-01 (D-06)"
affects: [44-04, 45, 46, 47]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Single-source warm-tier exclusion policy: only RecallConfig.exclude_prefixes; no module-level shadow constant"

key-files:
  created: []
  modified:
    - sentinel-core/app/services/recall.py
    - sentinel-core/app/services/message_processing.py
    - sentinel-core/tests/test_recall.py

key-decisions:
  - "Deleted _WARM_TIER_EXCLUDE_PREFIXES entirely (preferred remediation per 44-PATTERNS.md) rather than aliasing it, since no code path or test imported the symbol by name after note_intake.py's D-06-driven import removal in 44-01"
  - "Task 2 (D-06 redirect retirement) was verified as already fully satisfied by plan 44-01's pulled-forward deviation — not redone, per the plan's own upstream-context guidance"

requirements-completed: [VAULT-02, VAULT-04]

coverage:
  - id: D1
    description: "_WARM_TIER_EXCLUDE_PREFIXES (stale duplicate missing inbox/) deleted from recall.py; message_processing.py's dead re-export removed; single source of truth is RecallConfig.exclude_prefixes"
    requirement: "VAULT-04"
    verification:
      - kind: unit
        ref: "tests/test_recall.py::test_no_stale_warm_tier_exclude_prefixes_duplicate"
        status: pass
      - kind: unit
        ref: "tests/test_recall.py::test_inbox_gap_not_recalled"
        status: pass
    human_judgment: false
  - id: D2
    description: "D-06 chat-note redirect retirement (note_intake.classify_and_apply searchable_only guard removed; routes/message.py _safe_file_chat_note no longer promises warm-searchable redirect) — verified as already landed by plan 44-01, not redone"
    requirement: "VAULT-02"
    verification:
      - kind: unit
        ref: "tests/test_message.py::test_chat_note_path_passes_warm_tier_exclusion_filter"
        status: pass
      - kind: unit
        ref: "tests/test_message.py::test_observation_topic_chat_note_redirected_to_searchable_path"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-07-06
status: complete
---

# Phase 44 Plan 03: Warm-Tier Exclusion Reconciliation + D-06 Verification Summary

**Deleted the stale, inbox/-missing `_WARM_TIER_EXCLUDE_PREFIXES` duplicate from `recall.py` (and its dead re-export in `message_processing.py`), single-sourcing warm-tier exclusion on `RecallConfig.exclude_prefixes`; confirmed the D-06 chat-note redirect retirement (this plan's Task 2) was already fully and correctly landed by plan 44-01.**

## Performance

- **Duration:** ~15 min
- **Tasks:** 1 executed (Task 1, TDD) + 1 verified-not-redone (Task 2, upstream-satisfied)
- **Files modified:** 3 (2 source, 1 test)

## Accomplishments

- Closed the second dual-source-of-truth (D-03b) identified in research: `recall.py`'s module-level `_WARM_TIER_EXCLUDE_PREFIXES = ("ops/", "_trash/", "self/")` — missing `inbox/`, drifted from the canonical `RecallConfig.exclude_prefixes` — is deleted entirely (preferred remediation, not aliased, since nothing imports the bare symbol anymore).
- Removed `message_processing.py`'s now-dead re-export line for the same symbol; confirmed via grep that no source or test file references `_WARM_TIER_EXCLUDE_PREFIXES` by name anywhere in the codebase after this change.
- Added a RED-then-GREEN regression test (`test_no_stale_warm_tier_exclude_prefixes_duplicate`) that pins the "delete or value-equal to `RecallConfig().exclude_prefixes`" contract so this drift class cannot silently reappear.
- Verified — did not redo — Task 2 (D-06 redirect retirement): `note_intake.classify_and_apply`'s `searchable_only` journal-redirect branch is already gone (with an explicit D-06 comment explaining why), `routes/message.py`'s `_safe_file_chat_note` docstring already documents the retired "guaranteed searchable" promise, and both `test_message.py` tests already assert the classified-destination behavior. All landed in plan 44-01's pulled-forward deviation commit `f52cea4` / folded Task-1 commit `4d3368d`.

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: add failing test for stale _WARM_TIER_EXCLUDE_PREFIXES duplicate** - `832bdc0` (test)
2. **Task 1 GREEN: reconcile _WARM_TIER_EXCLUDE_PREFIXES with RecallConfig.exclude_prefixes** - `497257f` (feat)

Task 2 required no commit — verified as already satisfied by plan 44-01 (see Deviations below).

## Files Created/Modified

- `sentinel-core/app/services/recall.py` - Deleted the stale `_WARM_TIER_EXCLUDE_PREFIXES` module constant; replaced with an explanatory NOTE pointing to `RecallConfig.exclude_prefixes` as the single source of truth
- `sentinel-core/app/services/message_processing.py` - Removed the dead re-export of `_WARM_TIER_EXCLUDE_PREFIXES` from `recall.py` (nothing consumed it)
- `sentinel-core/tests/test_recall.py` - Added `test_no_stale_warm_tier_exclude_prefixes_duplicate` (RED before the fix, GREEN after)

## Decisions Made

- Deletion over aliasing: the plan allowed keeping a same-valued alias "if a named symbol must stay importable for external stability." A repo-wide grep confirmed zero remaining consumers of the bare `_WARM_TIER_EXCLUDE_PREFIXES` symbol (note_intake.py's import was already dropped in 44-01's D-06 deviation), so deletion — the plan's stated preference — was the correct, lower-surface-area choice.
- Task 2 verify-not-redo: per the upstream_context in this executor's brief and independent confirmation by reading the current committed state of `note_intake.py`, `routes/message.py`, and `tests/test_message.py`, D-06 is fully and correctly landed. Redoing it would have risked re-breaking an already-green path for zero benefit.

## Deviations from Plan

### Upstream-satisfied (not a fix — verification only)

**1. [Upstream-satisfied] Task 2 (D-06 redirect retirement) already landed by plan 44-01**
- **Found during:** Pre-execution verification (read `note_intake.py`, `routes/message.py`, `tests/test_message.py` before starting Task 1)
- **What was checked:** `note_intake.classify_and_apply`'s `searchable_only` journal-redirect branch, `routes/message.py`'s `_safe_file_chat_note` docstring/behavior, and both named `test_message.py` tests (`test_chat_note_path_passes_warm_tier_exclusion_filter`, `test_observation_topic_chat_note_redirected_to_searchable_path`)
- **Result:** All three are already correct and match this plan's Task 2 `<done>` criteria exactly, including the explicit D-06 rationale comments. No code change was made or needed.
- **Verification:** `pytest tests/test_message.py -q` — all green as part of the full-suite run below
- **Reference:** plan 44-01's commit `f52cea4` (deviation) and Task 1 commit `4d3368d` (note_intake.py half); documented in `44-01-SUMMARY.md`'s own Deviations section

---

**Total deviations:** 1 (upstream-satisfied verification, no code change)
**Impact on plan:** None — Task 2's real work was completed one plan early by 44-01's own deviation-rule discipline. This plan's genuine remaining scope (Task 1) was executed in full via TDD.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- VAULT-02 (D-06 redirect retirement, verified) and VAULT-04 (D-03b exclusion reconciliation) are both closed for this plan's scope.
- Full suite green: 467 passed, 12 skipped, 0 failed (479 collected) — baseline of 466/12 plus this plan's 1 new regression test, no new skips or failures.
- Plan 44-04 (wave 3, `depends_on: [44-03]`) can proceed — no known blockers from this plan's changes.

---
*Phase: 44-vault-namespace-taxonomy-foundation*
*Completed: 2026-07-06*

## Self-Check: PASSED

All modified/created files confirmed present on disk; both task commit hashes (`832bdc0`, `497257f`) confirmed in `git log`.
