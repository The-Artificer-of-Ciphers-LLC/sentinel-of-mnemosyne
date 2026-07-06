---
phase: 44-vault-namespace-taxonomy-foundation
plan: 01
subsystem: api
tags: [taxonomy, vault, recall, para, obsidian, python, fastapi]

# Dependency graph
requires: []
provides:
  - "TOPIC_VAULT_PATH rerouted to the D-03 PARA AFTER table (learning/reference -> inbox/, journal -> ops/journal, accomplishment -> ops/accomplishments, observation unchanged)"
  - "topic_dir_for and note_intake._topic_target_path both derive the journal path from the dict base (Pitfall 1 closed, both call sites)"
  - "vault_sweep_plan.is_in_topic_dir taxonomy-aware family-root fix (Pitfall 2 closed)"
  - "recall.py carrier-namespace recency allowlist removed; recency weighting is Session-summary-only (MEM-09 end state)"
  - "message.py/note_intake.py D-06 redirect retirement (pulled forward from 44-03)"
  - ".planning/v0.6.0-REGRESSION-LEDGER.md standing MEM-01..09 + D-05 contract"
affects: [44-02, 44-03, 44-04, 45, 46, 47]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "topic_dir_for is the single source of truth for topic->vault-directory routing; consumers derive from it, never hardcode a literal segment"
    - "is_in_topic_dir family-root derivation special-cases the nested-date journal family; every other topic dir matches on its full path, not just the first segment"

key-files:
  created:
    - .planning/v0.6.0-REGRESSION-LEDGER.md
  modified:
    - sentinel-core/app/services/note_classifier.py
    - sentinel-core/app/services/note_intake.py
    - sentinel-core/app/services/vault_sweep_plan.py
    - sentinel-core/app/services/recall.py
    - sentinel-core/app/routes/message.py
    - sentinel-core/tests/test_note_classifier.py
    - sentinel-core/tests/test_vault_sweep_plan.py
    - sentinel-core/tests/test_vault_sweeper.py
    - sentinel-core/tests/test_note_routes.py
    - sentinel-core/tests/test_recall.py
    - sentinel-core/tests/test_message.py

key-decisions:
  - "D-03 PARA reroute and its two hardcoded journal-literal fixes land in the same commit (Pitfall 1 discipline) — editing the dict alone was a proven no-op"
  - "is_in_topic_dir special-cases the nested-date ops/journal/ family; every other topic dir (ops/accomplishments, ops/observations, inbox) matches on its full path"
  - "D-01 carrier-namespace allowlist removed entirely; recency_weight() itself is kept (still used by _hot_sessions, MEM-09 place a)"
  - "D-06 (_safe_file_chat_note redirect retirement) pulled forward from plan 44-03 into this plan — the full-suite-green gate could not otherwise be met at this plan's boundary"

patterns-established:
  - "Regression ledger (.planning/v0.6.0-REGRESSION-LEDGER.md) as the append-only, standing MEM-0x + full-suite-baseline contract for the rest of the v0.6.0 milestone"

requirements-completed: [VAULT-02, VAULT-03]

coverage:
  - id: D1
    description: "TOPIC_VAULT_PATH rerouted to D-03 AFTER table; both journal-literal call sites derive from the dict base"
    requirement: "VAULT-02"
    verification:
      - kind: unit
        ref: "tests/test_note_classifier.py::test_topic_dir_for_journal_derives_from_dict"
        status: pass
      - kind: unit
        ref: "tests/test_note_classifier.py::test_topic_dir_for_para_reroute"
        status: pass
    human_judgment: false
  - id: D2
    description: "is_in_topic_dir taxonomy-aware family-root fix closes the ops/ collapse bug"
    requirement: "VAULT-02"
    verification:
      - kind: unit
        ref: "tests/test_vault_sweep_plan.py::test_is_in_topic_dir_does_not_conflate_ops_subdirs"
        status: pass
    human_judgment: false
  - id: D3
    description: "Carrier-namespace recency allowlist removed from recall.py; recency weighting is Session-summary-only"
    requirement: "VAULT-03"
    verification:
      - kind: unit
        ref: "tests/test_recall.py::test_recency_applies_only_to_session_summaries"
        status: pass
      - kind: unit
        ref: "tests/test_recall.py::test_recency_order_hot"
        status: pass
    human_judgment: false
  - id: D4
    description: "v0.6.0 regression ledger established with MEM-01..09 contract and D-05 accepted transient"
    verification:
      - kind: other
        ref: "test -f .planning/v0.6.0-REGRESSION-LEDGER.md && grep -q MEM-09 && grep -q D-05"
        status: pass
    human_judgment: false

duration: 45min
completed: 2026-07-06
status: complete
---

# Phase 44 Plan 01: PARA Taxonomy Reroute + Carrier-Allowlist Removal Summary

**PARA taxonomy reroute (learning/reference -> inbox/, journal/accomplishment -> ops/) landed atomically with its two hazard fixes (hardcoded journal literals, is_in_topic_dir family collapse) and the matching recall carrier-allowlist removal, closing VAULT-02 + VAULT-03 as one trap-and-fix unit.**

## Performance

- **Duration:** ~45 min
- **Tasks:** 3 planned + 1 deviation task (D-06 retirement)
- **Files modified:** 11 (4 source in the planned scope, 4 test files for direct-consequence fixes, 1 new doc, 2 additional source+test files for the D-06 deviation)

## Accomplishments

- `TOPIC_VAULT_PATH` rerouted to the D-03 AFTER table: `learning`/`reference` -> `inbox` (queued pending Reduce), `journal` -> `ops/journal`, `accomplishment` -> `ops/accomplishments`, `observation`/`noise`/`unsure` unchanged.
- Both hardcoded `journal/` literals (`note_classifier.topic_dir_for`, `note_intake._topic_target_path`) now derive their per-day path from the dict's fetched `base` value — closes Pitfall 1's silent no-op hazard.
- `vault_sweep_plan.is_in_topic_dir`'s family-root derivation is now taxonomy-aware: the nested-date `ops/journal/` family is special-cased; every other topic dir matches on its full path instead of collapsing to the shared `ops/` first segment — closes Pitfall 2.
- `recall.py`'s carrier-namespace recency allowlist (`_CARRIER_NAMESPACE_PREFIXES`, `_path_date`) and its warm-tier reweight loop are removed entirely; recency weighting is now Session-summary-only (MEM-09 end state). `recency_weight()` itself is preserved (still used by `_hot_sessions`).
- `.planning/v0.6.0-REGRESSION-LEDGER.md` established as the standing MEM-01..09 + full-suite-baseline regression contract for the rest of the v0.6.0 milestone, recording the D-05 accepted transient.
- (Deviation) D-06's `_safe_file_chat_note` searchable-only redirect retirement pulled forward from plan 44-03 to keep the full suite green at this plan's boundary.

## Task Commits

Each task was committed atomically:

1. **Task 1: PARA reroute table + both journal literals + is_in_topic_dir family fix** - `4d3368d` (feat) — also folds in the D-06 note_intake.py edit (see Deviations) and the necessary test_vault_sweeper.py / test_note_routes.py path-literal updates
2. **Task 2: Remove the carrier-namespace recency allowlist from recall** - `7f1bf8d` (feat)
3. **Task 3: Establish the v0.6.0 regression ledger** - `ac63122` (docs)
4. **Deviation: Retire _safe_file_chat_note searchable-only redirect (D-06)** - `f52cea4` (fix)

_No plan-metadata commit was made separately — see "Final commit" note below._

## Files Created/Modified

- `sentinel-core/app/services/note_classifier.py` - TOPIC_VAULT_PATH rerouted; topic_dir_for's journal branch derives from `base`
- `sentinel-core/app/services/note_intake.py` - _topic_target_path's journal branch derives from `base`; searchable_only redirect block removed (D-06); unused `_WARM_TIER_EXCLUDE_PREFIXES` import dropped
- `sentinel-core/app/services/vault_sweep_plan.py` - is_in_topic_dir taxonomy-aware family-root fix
- `sentinel-core/app/services/recall.py` - _CARRIER_NAMESPACE_PREFIXES + _path_date + warm-tier reweight loop removed
- `sentinel-core/app/routes/message.py` - _safe_file_chat_note's "guaranteed searchable" docstring/behavior retired (D-06)
- `sentinel-core/tests/test_note_classifier.py` - 2 new tests (journal-derive, PARA reroute table)
- `sentinel-core/tests/test_vault_sweep_plan.py` - 2 tests rewritten for ops/-prefixed destinations + 1 new family-root regression test
- `sentinel-core/tests/test_vault_sweeper.py` - 10 tests updated for the new taxonomy (path literals + a multi-level-directory fix to the shared `_make_classifiable_note_vault` test helper)
- `sentinel-core/tests/test_note_routes.py` - 3 tests updated for inbox/-prefixed learning/reference destinations
- `sentinel-core/tests/test_recall.py` - 3 tests rewritten around Session-summary recency (D-01 invalidated their carrier premises) + 1 new positive-invariant test
- `sentinel-core/tests/test_message.py` - 3 tests updated for the D-06 retired-redirect behavior
- `.planning/v0.6.0-REGRESSION-LEDGER.md` - new standing regression contract

## Decisions Made

- D-03 PARA reroute and its two journal-literal fixes landed in the same commit (Pitfall 1 discipline) — editing the dict alone is a proven no-op.
- `is_in_topic_dir` special-cases only the nested-date `ops/journal/` family; every other topic dir matches on its full path (not the first `/`-segment) to avoid collapsing distinct `ops/`-nested topics.
- D-01 carrier-namespace allowlist removed entirely rather than repointed to dead paths; `recency_weight()` itself is kept for `_hot_sessions`.
- D-06 (`_safe_file_chat_note` redirect retirement, originally scoped to plan 44-03) was pulled forward into this plan — see Deviations below for the full rationale.
- `RecallConfig.exclude_prefixes` and `_WARM_TIER_EXCLUDE_PREFIXES` were deliberately left untouched (per the plan's own Task 2 boundary and the D-06 deviation) — that reconciliation still belongs to plan 44-03 Task 1.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated test_vault_sweeper.py and test_note_routes.py path-literal expectations**
- **Found during:** Task 1 verification (full-suite run after the TOPIC_VAULT_PATH reroute)
- **Issue:** 13 tests across these two files encoded path literals for the OLD taxonomy (`learning/`, `references/`, `accomplishments/` as the expected destination/canonical directory for their respective topics). The D-03 reroute intentionally changes these destinations, so the tests broke as a direct, immediate consequence of Task 1's edit. Neither file is in this plan's declared `files_modified` list, but the plan's own SC-5 gate ("full suite stays green at 471 collected") requires them fixed here.
- **Fix:** Updated path-literal assertions to the new destinations (`inbox/...` for learning/reference, `ops/accomplishments/...` for accomplishment). For the embedding-index tests that relied on a note already being "at home" (no relocation) to isolate index-emission/incremental-carry-forward/pruning behavior from the sweeper's relocation logic, switched the fixture topic from `reference` to `observation` (whose canonical directory, `ops/observations`, is genuinely unchanged by D-03) rather than using `inbox/` — `inbox/` is still in `SWEEP_SKIP_PREFIXES` until plan 44-02 lands D-02, so a note placed directly under `inbox/` would never be walked/classified at all in this plan's state.
- **Files modified:** sentinel-core/tests/test_vault_sweeper.py, sentinel-core/tests/test_note_routes.py
- **Verification:** `pytest tests/test_vault_sweeper.py tests/test_note_routes.py -q` — all green
- **Committed in:** `4d3368d` (Task 1 commit)

**2. [Rule 1 - Bug] Fixed the shared `_make_classifiable_note_vault` test helper for multi-level topic directories**
- **Found during:** Task 1 verification (same pass as #1)
- **Issue:** The helper only built a top-level directory listing plus the immediate-parent directory listing, which worked for the old single-segment topic dirs (`references/`, `learning/`) but silently broke walk_vault's BFS discovery for the new two-level `ops/observations/` topic dir (the intermediate `ops` -> `["observations/"]` listing was never registered, so `walk_vault` never descended past `ops/`).
- **Fix:** Rewrote the helper to build every intermediate directory level generically (not just top + immediate-parent), so arbitrary-depth topic dirs are correctly discoverable.
- **Files modified:** sentinel-core/tests/test_vault_sweeper.py
- **Verification:** `pytest tests/test_vault_sweeper.py -q` — all 39 tests green
- **Committed in:** `4d3368d` (Task 1 commit)

**3. [Rule 1 - Bug, pulled forward from plan 44-03] Retired `_safe_file_chat_note`'s searchable-only redirect (D-06)**
- **Found during:** Full-suite run after Tasks 1-3 completed
- **Issue:** After the D-03 reroute, every classifier topic (including the former `journal` redirect target itself) resolves to an `ops/`- or `inbox/`-prefixed destination. `note_intake.classify_and_apply`'s `searchable_only` guard — which redirects a warm-tier-excluded destination to a `journal` path to "guarantee searchability" — became structurally unsatisfiable, since the redirect target is now excluded too. This is D-06, a locked CONTEXT.md decision already scoped to plan 44-03 (wave 2, `depends_on: [44-01]`). Three test_message.py tests were red at this plan's SC-5 full-suite-green boundary: `test_substantive_chat_content_filed_as_vault_note`, `test_chat_note_path_passes_warm_tier_exclusion_filter`, and `test_observation_topic_chat_note_redirected_to_searchable_path`. The first of these was not even on plan 44-03's radar (its hardcoded exclusion-tuple check breaks purely from the D-03 reroute itself, independent of the redirect logic) — a genuine gap neither 44-RESEARCH.md nor 44-03-PLAN.md anticipated.
- **Fix:** Removed the `searchable_only` redirect block in `note_intake.classify_and_apply` and the now-unused `_WARM_TIER_EXCLUDE_PREFIXES` import; retired the "guaranteed searchable" promise in `routes/message.py`'s `_safe_file_chat_note` docstring/call (dropped the now-inert `searchable_only=True` argument). Updated all three affected test_message.py tests to assert the real, current behavior (note files to its classified destination; no redirect).
- **Files modified:** sentinel-core/app/services/note_intake.py (folded into the Task 1 commit), sentinel-core/app/routes/message.py, sentinel-core/tests/test_message.py
- **Verification:** `pytest tests/test_message.py -q` — 38/38 green; full suite green (463 passed, 12 skipped)
- **Committed in:** `f52cea4` (separate deviation commit) — the `note_intake.py` half of this edit landed in `4d3368d` since it's the same file as Task 1's journal-literal fix
- **Scope note:** `RecallConfig.exclude_prefixes` / `_WARM_TIER_EXCLUDE_PREFIXES` reconciliation (44-03 Task 1) was deliberately NOT done here — still belongs to plan 44-03. When 44-03 executes, its Task 2 (the redirect retirement) should find the work already done and can proceed straight to its Task 1 reconciliation.

---

**Total deviations:** 3 auto-fixed (all Rule 1 — bugs/breakage directly and immediately caused by this plan's own Task 1/Task 2 edits)
**Impact on plan:** All three were necessary to satisfy the plan's own SC-5 full-suite-green gate. The D-06 pull-forward duplicates work planned for 44-03; that plan's executor should verify-not-redo when it runs.

## Issues Encountered

- The plan's declared `files_modified` list (4 source + 3 test files + the ledger) undercounted the taxonomy reroute's real blast radius. `test_vault_sweeper.py`, `test_note_routes.py`, and `test_message.py` all encode path assumptions tied to the OLD taxonomy and broke as a direct consequence of Task 1's `TOPIC_VAULT_PATH` edit. Resolved by fixing all of them within this plan per the deviation rules and the plan's own hard full-suite gate (see Deviations above).
- Wave-1 plan 44-02 (parallel/independent, `depends_on: []`) still needs to land D-02 (remove `inbox/` from `SWEEP_SKIP_PREFIXES`) and D-07 (underscore-prefixed inbox control-file relocation guard) — neither is touched by this plan.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- VAULT-02 and VAULT-03 are both closed; the full suite is green (475 collected: 463 passed, 12 skipped, 0 failed).
- Plan 44-02 (wave 1, parallel) can proceed independently — no dependency on this plan's changes.
- Plan 44-03 (wave 2, `depends_on: [44-01]`) should verify its Task 2 (D-06 retirement) is already satisfied by this plan and proceed directly to its Task 1 (`_WARM_TIER_EXCLUDE_PREFIXES` reconciliation with `RecallConfig.exclude_prefixes`).
- Plan 44-04 (wave 3, `depends_on: [44-03]`) is unaffected by this plan's scope.

---
*Phase: 44-vault-namespace-taxonomy-foundation*
*Completed: 2026-07-06*

## Self-Check: PASSED

All created/modified files confirmed present on disk; all 4 task commit hashes (`4d3368d`, `7f1bf8d`, `ac63122`, `f52cea4`) confirmed in `git log`.
