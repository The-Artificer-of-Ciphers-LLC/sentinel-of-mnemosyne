---
phase: 44-vault-namespace-taxonomy-foundation
plan: 02
subsystem: vault
tags: [obsidian, vault-sweeper, embeddings, recall, inbox, para-taxonomy]

# Dependency graph
requires:
  - phase: 44-01
    provides: PARA taxonomy reroute (topic_dir_for routing table), is_in_topic_dir family fix
provides:
  - inbox/ removed from both sweep skip-prefix sets — sweeper walks and embeds inbox/ content
  - D-07 relocation guard for underscore-prefixed inbox control files (inbox/_pending-classification.md)
  - templates/ added to PROTECTED_NAMESPACES / config.protected_namespaces
affects: [phase-45-note-quality-schema-graph-analysis, phase-46-6rs-pipeline-orchestrator]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dual-maintenance pattern: any skip/protected set must be edited in BOTH the module constant AND the settings default — the settings tuple overrides the constant at runtime via _active_*() helpers"
    - "Path/pattern-based relocation guards (not is_in_topic_dir-dependent) for control files that aren't ordinary notes"

key-files:
  created: []
  modified:
    - sentinel-core/app/services/vault_sweeper.py
    - sentinel-core/app/config.py
    - sentinel-core/app/vault.py
    - sentinel-core/tests/test_vault_sweeper.py
    - sentinel-core/tests/test_obsidian_vault.py

key-decisions:
  - "inbox/ dropped from SWEEP_SKIP_PREFIXES and config.sweep_skip_prefixes in the same commit — settings tuple overrides the module constant at runtime, so editing only one would leave settings-present/absent paths divergent"
  - "RecallConfig.exclude_prefixes untouched — inbox/ stays there, so embedded-but-excluded is the D-02 end state; both KeywordRecall and SemanticRecall.eligible_entries apply exclude_prefixes"
  - "D-07 guard is path/pattern based (inbox/ prefix + leading-underscore filename), not is_in_topic_dir dependent, so future inbox/_* control files are covered without further code changes"
  - "templates/ added to PROTECTED_NAMESPACES additively (segment-boundary matching guarantees it cannot weaken sentinel/self/security/ protection)"

patterns-established:
  - "Dual-maintenance skip/protected-set edits: module constant + settings default must change together"

requirements-completed: [VAULT-04, VAULT-01]

coverage:
  - id: D1
    description: "inbox/ removed from SWEEP_SKIP_PREFIXES and config.sweep_skip_prefixes — sweeper walks and embeds inbox/ notes"
    requirement: "VAULT-04"
    verification:
      - kind: unit
        ref: "tests/test_vault_sweeper.py#test_sweep_skip_prefixes_constant"
        status: pass
      - kind: unit
        ref: "tests/test_vault_sweeper.py#test_should_skip_prefixes"
        status: pass
      - kind: unit
        ref: "tests/test_vault_sweeper.py#test_walk_vault_includes_inbox_notes"
        status: pass
      - kind: unit
        ref: "tests/test_recall.py#test_inbox_gap_not_recalled"
        status: pass
    human_judgment: false
  - id: D2
    description: "D-07 relocation guard: underscore-prefixed inbox control files are never proposed for a topic-move, even when classified into an ops-bound topic; ordinary inbox/ notes are unaffected"
    requirement: "VAULT-04"
    verification:
      - kind: unit
        ref: "tests/test_vault_sweeper.py#test_sweep_never_relocates_pending_classification_file"
        status: pass
    human_judgment: false
  - id: D3
    description: "templates/ added to the protected-namespace guard (additive; sentinel/self/security/ protection intact)"
    requirement: "VAULT-01"
    verification:
      - kind: unit
        ref: "tests/test_obsidian_vault.py#test_is_protected_path_templates_namespace"
        status: pass
      - kind: unit
        ref: "tests/test_obsidian_vault.py#test_is_protected_path_parametrized_from_literal"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-07-06
status: complete
---

# Phase 44 Plan 02: inbox/ embedding gap closure + control-file relocation guard Summary

**inbox/ dropped from the sweeper's skip-prefix denylist so staged captures get embedded (still excluded from warm recall), a path-based guard now protects the merged inbox/_pending-classification.md queue from topic-move relocation, and templates/ joins the protected-namespace set.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-07-06
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- Closed VAULT-04: `inbox/` is no longer wholesale-skipped by the vault sweeper — it is walked, classified, and embedded like any other subtree, while `RecallConfig.exclude_prefixes` (unchanged) keeps embedded `inbox/` vectors out of both warm-recall tiers (KeywordRecall filename filter and SemanticRecall's `eligible_entries`).
- Implemented D-07: a narrow, path-based guard (`_is_inbox_control_file`) stops `run_sweep` from ever proposing a topic-move relocation for underscore-prefixed `inbox/` control files (e.g. the merged `inbox/_pending-classification.md` "unsure" queue), while embedding of that same path — and of ordinary `inbox/` notes — proceeds unaffected.
- Added the discretionary `templates/` protected-namespace guard (VAULT-01 partial) — additive, segment-boundary-matched, verified not to weaken `sentinel/`, `self/`, `security/` protection.

## Task Commits

Each task was committed atomically:

1. **Task 1: Remove inbox/ from the sweep skip set (module constant + settings)** - `e906970` (feat)
2. **Task 2: Relocation guard for underscore-prefixed inbox control files (D-07)** - `75c35ca` (feat)
3. **Task 3: Add templates/ to the protected-namespace set (VAULT-01)** - `3fb056a` (feat)

_All three tasks followed RED→GREEN TDD: failing assertions/tests were written and confirmed to fail against the pre-change code before each implementation edit landed._

## Files Created/Modified

- `sentinel-core/app/services/vault_sweeper.py` - `inbox/` removed from `SWEEP_SKIP_PREFIXES` (with a D-02 comment guarding against re-adding "for symmetry"); new `_is_inbox_control_file(path)` helper; `run_sweep`'s topic-move construction now skips control files
- `sentinel-core/app/config.py` - `inbox/` removed from `sweep_skip_prefixes` default; `templates/` added to `protected_namespaces` default
- `sentinel-core/app/vault.py` - `templates/` added to `PROTECTED_NAMESPACES`
- `sentinel-core/tests/test_vault_sweeper.py` - flipped `test_sweep_skip_prefixes_constant` and `test_should_skip_prefixes` inbox assertions; added `test_walk_vault_includes_inbox_notes` and `test_sweep_never_relocates_pending_classification_file`
- `sentinel-core/tests/test_obsidian_vault.py` - added `test_is_protected_path_templates_namespace`

## Decisions Made

- inbox/ removal applied to BOTH `vault_sweeper.SWEEP_SKIP_PREFIXES` and `config.sweep_skip_prefixes` in the same commit (Task 1) — the settings tuple overrides the module constant at runtime via `_active_skip_prefixes()`, so editing only one would leave the settings-present and settings-absent code paths divergent.
- `RecallConfig.exclude_prefixes` was deliberately left untouched — it is the mechanism that keeps newly-embedded `inbox/` content out of warm recall (D-02 embed-but-exclude split); `test_inbox_gap_not_recalled` was re-run at the plan boundary and stays green.
- D-07 guard implemented as a standalone path/pattern check (`inbox/` prefix + leading-underscore filename) rather than extending `is_in_topic_dir`, so any future `inbox/_*` control file is covered without further code changes — a queue is not a note, and relocating it would corrupt it.
- `templates/` protected-namespace addition applied to both `vault.PROTECTED_NAMESPACES` and `config.protected_namespaces` for the same dual-maintenance reason as inbox/'s skip-prefix removal.

## Deviations from Plan

None - plan executed exactly as written. One test-authoring adjustment surfaced during Task 2's RED phase (documented below) was a pure test-fixture fix, not a code deviation.

### Auto-fixed Issues

**1. [Rule 1 - Bug in test fixture] Test embedder returning identical vectors triggered the dedup pass**
- **Found during:** Task 2 (writing `test_sweep_never_relocates_pending_classification_file`)
- **Issue:** The first draft of the new test's fake embedder returned the same vector `[1.0, 0.0, 0.0]` for every text. With two notes in the sweep batch, this made them cosine-identical (≥0.92), so the dedup pass additionally trashed one of them — confounding the test's relocation-only assertions with an unrelated dedup side-effect.
- **Fix:** Changed the fake embedder to return distinct, orthogonal vectors per text (`[1,0,0]` / `[0,1,0]`), isolating the assertions to the relocation guard under test.
- **Files modified:** `sentinel-core/tests/test_vault_sweeper.py` (test body only, before the implementation commit)
- **Verification:** `test_sweep_never_relocates_pending_classification_file` passes deterministically
- **Committed in:** `75c35ca` (part of Task 2 commit — the fixture fix and the guard implementation landed together since the fixture was authored in the same RED→GREEN cycle)

---

**Total deviations:** 1 auto-fixed (test-fixture bug, not a plan/code deviation)
**Impact on plan:** No scope creep — this was a self-correction inside the plan's own new test before it was committed.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- VAULT-04 closed: `inbox/` is now an embedded-but-not-yet-recalled staging area, ready for Phase 46's Reduce pipeline to eventually promote content out of `inbox/` into canonical topic directories.
- D-07's control-file relocation guard protects the merged `inbox/_pending-classification.md` queue against corruption now that `inbox/` is walked by the sweeper — no outstanding risk for Phase 45/46 to inherit.
- `templates/` protected-namespace guard is additive and low-risk; no blockers.
- Full suite green: 466 passed, 12 skipped (baseline was 463 passed, 12 skipped — +3 new tests, 0 regressions). `test_inbox_gap_not_recalled` reconfirmed green at the plan boundary.

---
*Phase: 44-vault-namespace-taxonomy-foundation*
*Completed: 2026-07-06*

## Self-Check: PASSED

All 3 task commits (e906970, 75c35ca, 3fb056a) and all 5 modified source/test files confirmed present on disk / in git history.
