---
phase: 45-note-quality-schema-graph-analysis
plan: 01
subsystem: testing
tags: [pytest, importorskip, characterization-testing, graph-analysis, moc-maintenance]

# Dependency graph
requires:
  - phase: 44-vault-namespace-taxonomy-foundation
    provides: PARA taxonomy routing table (note_classifier.TOPIC_VAULT_PATH) this plan characterizes
provides:
  - "sentinel-core/tests/test_p45_invariants.py — three cross-cutting Wave 0 invariant tests"
  - "Live characterizing test locking D-02 inspect-only premise (note_classifier routes learning/reference to inbox/, never notes/)"
  - "importorskip fixture pinning wikilink -> path filename-stem resolution rule (research Open Question 2), ready to auto-activate at Plan 45-03"
  - "importorskip fixture pinning trailing _schema block preservation on hub-member append (RESEARCH Pitfall 1), ready to auto-activate at Plan 45-05"
affects: [45-03-graph-analysis, 45-05-moc-maintenance, 45-06-graph-routes]

# Tech tracking
tech-stack:
  added: []
  patterns: ["pytest.importorskip fixture guard for feature-dependent Wave 0 tests (visible SKIP, never silent pass)"]

key-files:
  created: [sentinel-core/tests/test_p45_invariants.py]
  modified: []

key-decisions:
  - "Trailing-block fixture matches the inserted member wikilink loosely (regex on the member-two substring, case/format-insensitive) rather than asserting an exact display-text format, since Plan 45-05 owns the slug-to-wikilink-text transformation and that exact format is not specified in CONTEXT.md/RESEARCH.md."

patterns-established:
  - "Wave 0 cross-cutting invariant tests use pytest.importorskip at the top of the test body (not module-level) so pytest collection always succeeds and the suite stays green with a visible SKIP count, never a collection error."

requirements-completed: [NOTE-01, NOTE-02, NOTE-03]

coverage:
  - id: D1
    description: "Live characterizing test locks the D-02 no-notes/-write-path premise: note_classifier.TOPIC_VAULT_PATH routes learning and reference to inbox/, and no topic maps to a notes/ root"
    requirement: "NOTE-01"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_p45_invariants.py#test_classifier_routes_learning_and_reference_to_inbox_not_notes"
        status: pass
    human_judgment: false
  - id: D2
    description: "importorskip fixture pins the wikilink -> path filename-stem resolution rule (research Open Question 2); SKIPS until Plan 45-03 lands graph_analysis.resolve_wikilink, then auto-activates"
    requirement: "NOTE-03"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_p45_invariants.py#test_wikilink_resolves_to_flat_notes_path_by_filename_stem"
        status: pass
    human_judgment: false
  - id: D3
    description: "importorskip fixture pins the trailing _schema block preservation invariant on hub-member append (RESEARCH Pitfall 1); SKIPS until Plan 45-05 lands moc_maintenance.attach_to_hub, then auto-activates"
    requirement: "NOTE-02"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_p45_invariants.py#test_attach_to_hub_preserves_trailing_schema_block_position"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-07-06
status: complete
---

# Phase 45 Plan 01: Wave 0 Cross-Cutting Invariants Summary

**Three Wave 0 pytest invariants — one live characterizing test (D-02 no-notes/-write-path) plus two `importorskip` fixtures pinning the wikilink filename-stem resolution rule and the trailing `_schema`-block preservation invariant — landed ahead of any Phase 45 feature module, keeping the 473/12 baseline green with two new visible skips.**

## Performance

- **Duration:** ~15 min
- **Tasks:** 3
- **Files modified:** 1 created

## Accomplishments

- Live test asserts `note_classifier.TOPIC_VAULT_PATH["learning"]` and `["reference"]` both resolve to `"inbox"`, and no topic in the map points at a `notes/` root — locking the premise that makes Phase 45's inspect-only enforcement point correct rather than an oversight.
- `pytest.importorskip("app.services.graph_analysis")`-guarded fixture asserts `resolve_wikilink("Member One", note_paths)` resolves to the flat-notes path whose filename stem matches (`notes/member-one.md`), and returns `None` on no match — pins research Open Question 2 ahead of Plan 45-03.
- `pytest.importorskip("app.services.moc_maintenance")`-guarded async fixture seeds a `FakeVault` hub note ending in a fenced `` ```_schema `` block, calls `attach_to_hub(vault, hub_path, "member-two")`, and asserts the resulting body still ends (after rstrip) with the fence close and the member wikilink appears exactly once — pins the phase's single highest-risk behavior (RESEARCH Pitfall 1: never `patch_append` a hub note) ahead of Plan 45-05.

## Task Commits

Each task was committed atomically:

1. **Task 1: Characterizing test — note_classifier keeps learning/reference in inbox/** - `4cc2a45` (test)
2. **Task 2: Fixture test — wikilink -> path resolution rule is filename-stem** - `c0a7217` (test)
3. **Task 3: Fixture test — attaching a 2nd hub member preserves the trailing _schema block position** - `1922f50` (test)

_Note: no `feat`/`refactor` commits — this plan is test-scaffold-only per its objective (Wave 0 must precede any feature module)._

## Files Created/Modified

- `sentinel-core/tests/test_p45_invariants.py` - Three Phase 45 cross-cutting invariant tests (1 live + 2 importorskip fixtures)

## Decisions Made

- The trailing-block fixture (Task 3) matches the inserted member wikilink with a loose case/format-insensitive regex (`\[\[[^\]]*member[ -]two[^\]]*\]\]`) rather than a hardcoded exact string. CONTEXT.md/RESEARCH.md/45-05-PLAN.md specify `attach_to_hub(vault, hub_path, member_slug)`'s contract (never `patch_append`, block stays terminal, member appears once) but not the exact slug-to-wikilink-display-text transformation — that's Plan 45-05's implementation detail. A loose match lets the fixture activate correctly regardless of whether Plan 45-05 renders `[[member-two]]` or `[[Member Two]]`, while still proving append-never-duplicate.

## Deviations from Plan

None - plan executed exactly as written. All three tasks' `<verify>` commands (`-k classifier`, `-k wikilink`, `-k trailing`) pass individually, and the full suite reports 474 passed / 14 skipped (473/12 baseline + 1 new live test + 2 new importorskip skips), matching the plan's `<verification>` block exactly with zero collection errors.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `graph_analysis.py` (Plan 45-03) can now be built with a live regression guard: once `resolve_wikilink(target, note_paths)` exists with the documented signature, the wikilink fixture auto-activates and must pass.
- `moc_maintenance.py` (Plan 45-05) can now be built with a live regression guard: once `attach_to_hub(vault, hub_path, member_slug)` exists, the trailing-block fixture auto-activates and must pass — catching the exact Pitfall 1 corruption class (blind `patch_append` pushing content after the terminal `_schema` block) within ~60s of introduction.
- No blockers. Full suite green at 474 passed / 14 skipped, ready for Wave 1 (Plan 45-02: `note_schema.py`).

---
*Phase: 45-note-quality-schema-graph-analysis*
*Completed: 2026-07-06*

## Self-Check: PASSED

- FOUND: sentinel-core/tests/test_p45_invariants.py
- FOUND: .planning/phases/45-note-quality-schema-graph-analysis/45-01-SUMMARY.md
- FOUND: 4cc2a45 (Task 1 commit)
- FOUND: c0a7217 (Task 2 commit)
- FOUND: 1922f50 (Task 3 commit)
