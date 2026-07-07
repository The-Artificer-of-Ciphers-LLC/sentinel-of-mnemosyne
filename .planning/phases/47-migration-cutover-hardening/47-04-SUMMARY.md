---
phase: 47-migration-cutover-hardening
plan: 04
subsystem: migration
tags: [migration-orchestrator, notes-bound-backfill, rollback-ledger, backlink-rewrite, graph-orphan-diff, tdd-green]

requires:
  - phase: 47-migration-cutover-hardening
    plan: 03
    provides: "migration_orchestrator's run() skeleton (shared-lock/try-finally/dry-run/background-task) plus Track A (ops-bound direct move); ledger_backlinks bookkeeping this plan consumes"
  - phase: 47-migration-cutover-hardening
    plan: 02
    provides: "RollbackLedger.record_ops_move/record_restore_original/record_inbox_write/record_backlink_rewrite + replay(), which this plan wires end-to-end for the first time and extends for byte-exact ops-move restoration"
provides:
  - "migration_orchestrator._enqueue_notes_bound/_ensure_embedded -- Track B (notes-bound backfill) reusing pipeline_orchestrator.run(mode='pipeline') verbatim, with embed-on-Reduce"
  - "migration_orchestrator._graph_orphan_diff/_build_rewrite_mapping/_rewrite_backlinks_after_reduce/_should_rollback -- the D-03 active backlink rewrite, the D-03a graph orphan-diff hard backstop, and the locked rollback-trigger predicate"
  - "migration_rollback_ledger.RollbackLedger.record_ops_move(original_body=...) -- byte-exact ops-move restoration, fixing a real frontmatter-pollution bug in the reused relocate()-based inverse"
affects: [47-05, 47-06, 47-07]

tech-stack:
  added: []
  patterns:
    - "Release-then-reacquire the shared sweep lock around any reused subsystem call that itself acquires the SAME lock (pipeline_orchestrator.run(), links_sidecar_index.rebuild_links_index) -- holding it across such a call is a guaranteed self-deadlock, not a genuine conflict"
    - "Rollback-trigger predicate: capture the live-run exception into a local variable instead of letting it propagate, so run() always returns a MigrationReport describing the outcome (rolled_back/status/errors) rather than raising"
    - "Best-effort old-title -> new-claim-title correspondence backstopped by a hard graph-orphan-diff gate, when the reused subsystem's report carries no exact per-entry mapping and modifying it is out of scope"

key-files:
  created: []
  modified:
    - sentinel-core/app/services/migration_orchestrator.py
    - sentinel-core/tests/test_migration_orchestrator.py
    - sentinel-core/app/services/migration_rollback_ledger.py

key-decisions:
  - "migration_orchestrator.run() releases its own shared sweep lock before calling pipeline_orchestrator.run(mode='pipeline') (Track B) and before any _graph_orphan_diff call that might trigger a links-index rebuild, then re-acquires it afterward -- both reused subsystems acquire the SAME shared lock internally, so holding migration's own lock across either call is a guaranteed nested-lock deadlock (Rule 1 bug fix, load-bearing: without this, Track B could never execute at all)."
  - "run() no longer re-raises a live-run failure: it captures the exception into raised_exc, evaluates the locked rollback-trigger predicate, and always returns a MigrationReport. Only the very initial pre-try lock-acquisition failure ('a vault operation is already in progress') still raises, unchanged from Plan 03."
  - "RollbackLedger.record_ops_move gained an optional original_body parameter (backward compatible, default None) so _OpsMove replay can write the exact pre-move body back directly instead of calling relocate() a second time -- ObsidianVault.relocate() unconditionally overwrites original_path/topic_moved_at frontmatter on every call, so a naive 'relocate back' inverse left stray provenance fields the pre-migration note never had, breaking the D-02a byte-identical restoration contract that test_hard_failure_triggers_atomic_rollback asserts."
  - "test_verify_failed_entry_does_not_rollback's fixture claim_title changed from a 5-word title to a single word: six_rs.reflect.find_and_attach_hub unconditionally writes a [[hub]] backlink into every Reduced note (both the cosine-match and the LLM-naming-fallback path -- the documented Phase 46 UAT-bug fix), so a Reduce result whose body merely lacks a wikilink can never organically fail Verify's has_wikilink check; a single-word title fails has_claim_title instead, independent of Reflect's injection, preserving the test's stated intent of a genuine non-mocked-internals dead-letter."
  - "Old-title -> new-claim-title backlink-rewrite mapping is a best-effort approximation (reversed enqueue order paired against the notes/ path-set diff), not an exact per-entry trace -- the reused PipelineReport carries no such mapping and deriving one exactly would require modifying Phase 46 code (out of scope, 'reused verbatim'). The D-03a graph orphan-diff is the designed hard backstop for any mispairing."

patterns-established:
  - "Both migration tracks (A: ops-bound direct move: Plan 03; B: notes-bound Reduce backfill: this plan) are fully wired; the locked rollback-trigger predicate distinguishes a designed pipeline dead-letter (accepted, reported) from a genuine hard failure (full atomic rollback) exactly per CONTEXT.md's Locked Decision"

requirements-completed: [MIG-01, MIG-02]

coverage:
  - id: D1
    description: "Track B: learning/reference(s) legacy files enqueued via inbox.append_entry() + one batched write_note(), originals deleted only after the write succeeds, then pipeline_orchestrator.run(mode='pipeline') reused verbatim to produce born-compliant notes/{claim-slug}.md; no note is grandfathered or left in inbox/"
    requirement: "MIG-01"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_migration_orchestrator.py::test_full_backfill_no_grandfathering"
        status: pass
    human_judgment: false
  - id: D2
    description: "Embed-on-Reduce: a targeted single-note embed per freshly-filed notes/ path when an embedder is supplied (the reused pipeline never persists an embedding-sidecar entry itself)"
    requirement: "MIG-01"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_migration_orchestrator.py::test_full_backfill_no_grandfathering"
        status: pass
    human_judgment: false
  - id: D3
    description: "Locked rollback-trigger predicate: a hard exception (including a mid-body shared-lock conflict) triggers full atomic ledger replay, restoring the vault byte-identical"
    requirement: "MIG-02"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_migration_orchestrator.py::test_hard_failure_triggers_atomic_rollback"
        status: pass
    human_judgment: false
  - id: D4
    description: "A pipeline dead-letter (Verify-fail, no new orphans) does NOT trigger rollback -- already-successful ops-bound moves are retained"
    requirement: "MIG-02"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_migration_orchestrator.py::test_verify_failed_entry_does_not_rollback"
        status: pass
    human_judgment: false

duration: 30min
completed: 2026-07-07
status: complete
---

# Phase 47 Plan 04: Track B (Notes-Bound Reduce Backfill) + Backlink Rewrite + Rollback Trigger Summary

**Notes-bound `learning/`/`reference(s)/` content now backfills into born-compliant `notes/{claim-slug}.md` by reusing `pipeline_orchestrator.run(mode="pipeline")` verbatim, gated by a locked rollback-trigger predicate (hard exception OR new `:graph` orphan OR unrepaired ops-bound backlink shortfall) that atomically replays the ledger — while a designed pipeline dead-letter is reported, never rolled back.**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-07-07T02:36:44Z
- **Completed:** 2026-07-07T03:06:00Z
- **Tasks:** 2
- **Files modified:** 3 (2 declared in the plan + 1 out-of-declared-scope fix, documented below)

## Accomplishments

- `_enqueue_notes_bound()` implements Track B (D-01/Pattern 1): reads each notes-bound legacy file's body, `inbox.append_entry()`s it with `ClassificationResult(topic=..., confidence=1.0, title_slug="", reasoning="Phase 47 backfill migration")`, records `rollback.record_restore_original`/`record_inbox_write`, writes `INBOX_PATH` once (batched), deletes the originals only after that write succeeds, then calls `pipeline_orchestrator.run(vault, mode="pipeline")` UNMODIFIED. `test_full_backfill_no_grandfathering` is GREEN: every flat-7 notes-bound original is gone, `notes/{claim-slug}.md` exists with a `_schema` block + wikilink for each, and no legacy filename survives under `inbox/` (Pitfall A absent).
- `_ensure_embedded()` closes the embed-on-Reduce gap: the reused pipeline's Reflect stage computes a transient vector for cosine hub-matching only and never persists a sidecar entry (confirmed by reading `pipeline_orchestrator.py` in full — it never imports `encode_index_body`). When migration is given an `embedder`, one targeted single-note embed per freshly-filed `notes/` path is triggered directly, since waiting for the ordinary sweep is not an option here (the note briefly lived in `inbox/`, which is `SWEEP_SKIP_PREFIXES`).
- **Load-bearing Rule 1 fix**: `pipeline_orchestrator.run()` acquires the SAME shared sweep lock `migration_orchestrator.run()` already holds from Track A. Without releasing it first, every Track B call would immediately raise `SweepInProgressError` with zero work done — a guaranteed self-deadlock, not a genuine failure. `run()` now explicitly releases the lock before Track B (and before any `_graph_orphan_diff` call that might trigger a links-index rebuild) and re-acquires it afterward.
- `_graph_orphan_diff()` captures the `notes/`-scoped orphan set via the exact code path `GET /vault/graph` uses (`rebuild_links_index_if_stale` + `routes.graph`'s own `_notes_map_from_index`/`_hub_paths` helpers + `graph_analysis.build_graph_report`) — the D-03a hard backstop for the Reduce track (Pattern 3: `:graph` is structurally blind to `ops/`, which is why Track A uses the separate `scan_for_title_refs` instead).
- `_build_rewrite_mapping()`/`_rewrite_backlinks_after_reduce()` implement the D-03 active backlink rewrite: a best-effort old-title → new-claim-title correspondence (the reused `PipelineReport` carries no per-entry mapping) drives a vault-wide `[[old-title]]` search-and-rewrite, with every edit recorded via `rollback.record_backlink_rewrite` for undo.
- `_should_rollback()` implements the CONTEXT.md Locked Decision exactly: full atomic rollback iff a hard exception escaped (including a mid-body lock conflict), the D-03a orphan diff found ≥1 new orphan, or an ops-bound backlink shortfall could not be repaired — a pipeline dead-letter alone is explicitly NOT a trigger.
- `run()`'s exception handling was restructured so a live-run failure is captured (not re-raised): `test_hard_failure_triggers_atomic_rollback` (an injected `relocate()` failure) replays the ledger and restores the vault byte-identical (`report.rolled_back is True`); `test_verify_failed_entry_does_not_rollback` (a genuine Verify dead-letter) leaves already-successful ops-bound moves intact (`report.rolled_back is False`, `report.verify_failed >= 1`).
- Full `migration_orchestrator` suite (5/5) and the full sentinel-core suite (589 passed, 12 skipped) both GREEN — no collateral breakage.

## Task Commits

Each task was committed atomically:

1. **Task 1: Track B — inbox enqueue + reuse pipeline_orchestrator.run + no-grandfathering** - `a444635` (feat)
2. **Task 2: Active backlink rewrite (D-03) + :graph orphan-diff gate + locked rollback trigger** - `be3046b` (feat)

**Plan metadata:** (this commit)

## Files Created/Modified

- `sentinel-core/app/services/migration_orchestrator.py` — `_enqueue_notes_bound`/`_ensure_embedded` (Track B); `_graph_orphan_diff`/`_build_rewrite_mapping`/`_rewrite_backlinks_after_reduce`/`_should_rollback` (D-03/D-03a + rollback trigger); `run()` restructured to release/reacquire the shared lock around Track B and to capture (never re-raise) a live-run failure.
- `sentinel-core/tests/test_migration_orchestrator.py` — `test_verify_failed_entry_does_not_rollback`'s `ReduceResult.claim_title` fixture changed from a 5-word title to a single word (Rule 1, see Deviations).
- `sentinel-core/app/services/migration_rollback_ledger.py` — `RollbackLedger.record_ops_move`/`_OpsMove` gained an optional `original_body` parameter for byte-exact restoration (Rule 1, out-of-declared-scope fix, see Deviations).

## Decisions Made

See `key-decisions` in the frontmatter above — summarized: (1) release/reacquire the shared lock around any reused subsystem call that acquires it internally; (2) `run()` never re-raises a live-run failure, always returning a `MigrationReport`; (3) `RollbackLedger.record_ops_move` gained an optional `original_body` for byte-exact restore; (4) the verify-failed test fixture was changed to a mechanism (`has_claim_title`) immune to Reflect's unconditional backlink injection; (5) the backlink-rewrite mapping is a documented best-effort approximation backstopped by the graph orphan-diff gate.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Nested shared-lock deadlock between migration_orchestrator and the reused pipeline_orchestrator/links_sidecar_index**
- **Found during:** Task 1 (Track B wiring)
- **Issue:** `migration_orchestrator.run()` acquires the shared sweep lock at the top of a live run and (per the plan's own diagram) was expected to hold it through Track B. But `pipeline_orchestrator.run()` (Track B) and `links_sidecar_index.rebuild_links_index` (called transitively via the D-03a graph-diff) both acquire this SAME shared lock internally. Holding migration's own lock across either call would make every Track B invocation immediately raise `SweepInProgressError` with zero work done — Track B could never succeed at all, contradicting `test_full_backfill_no_grandfathering`'s requirement that it does.
- **Fix:** `run()` explicitly releases its own lock immediately before Track B and any graph-diff call, then re-acquires it afterward (treating a failed re-acquisition as a mid-body lock conflict, one of the Locked Decision's own listed hard-exception categories).
- **Files modified:** `sentinel-core/app/services/migration_orchestrator.py`
- **Verification:** `test_full_backfill_no_grandfathering` passes; confirmed against `pipeline_orchestrator.run():505-506` and `links_sidecar_index.rebuild_links_index:118-119`.
- **Committed in:** `a444635` (Task 1), restructured further in `be3046b` (Task 2)

**2. [Rule 1 - Bug] `RollbackLedger`'s ops-move inverse left stray frontmatter after restore**
- **Found during:** Task 2 (`test_hard_failure_triggers_atomic_rollback`)
- **Issue:** `_OpsMove` replay called `vault.relocate(dst, src)` to undo a forward move, but `ObsidianVault.relocate()` unconditionally overwrites `fm["original_path"]`/`fm["topic_moved_at"]` on every call it makes — including the inverse call. A round-trip relocate therefore left the restored note with `original_path`/`topic_moved_at` fields the pre-migration original never had, failing the test's `vault.notes == pre_snapshot` byte-identical assertion. This bug was latent in Plan 02's `migration_rollback_ledger.py` but only became observable once this plan's test actually exercised a real hard-failure rollback end-to-end against the real `ObsidianVault.relocate()` (Plan 02's own ledger tests use a trivial stub `relocate()` that doesn't mutate frontmatter, so they never hit this).
- **Fix:** `RollbackLedger.record_ops_move` gained an optional `original_body` parameter (default `None`, fully backward compatible); when supplied, replay restores it via a direct `write_note` + `delete_note(dst)` instead of a second `relocate()` call. `migration_orchestrator._move_ops_bound` now passes the captured pre-move body.
- **Files modified:** `sentinel-core/app/services/migration_rollback_ledger.py`, `sentinel-core/app/services/migration_orchestrator.py`
- **Verification:** `test_hard_failure_triggers_atomic_rollback` passes (`vault.notes == pre_snapshot`); `test_migration_rollback_ledger.py`'s 3 existing tests (which don't pass `original_body`) remain green, unaffected by the new optional parameter.
- **Committed in:** `be3046b` (Task 2)

**3. [Rule 1 - Bug] Test fixture couldn't organically produce its own documented Verify failure**
- **Found during:** Task 2 (`test_verify_failed_entry_does_not_rollback`)
- **Issue:** The test's mocked `ReduceResult` had a 5-word `claim_title` and a body with no wikilink, intending (per its own docstring) to drive a genuine `has_wikilink` Verify failure without mocking `verify_note`/`find_and_attach_hub`. But `six_rs.reflect.find_and_attach_hub` unconditionally calls `add_hub_backlink_to_member` on BOTH its cosine-match and its LLM-naming-fallback path (the documented Phase 46 UAT-bug fix — "so no note could ever pass compliance" without it) — so Reflect always writes a `[[hub]]` backlink into the note body BEFORE Verify runs, regardless of what Reduce produced. An actual pytest run confirmed `report.verify_failed == 0` with the original fixture.
- **Fix:** Changed the fixture's `claim_title` to a single word ("Untitled"), which fails `has_claim_title` (requires >1 word) independent of Reflect's wikilink injection — a genuine, organic Verify failure with no additional mocking, preserving the test's stated intent.
- **Files modified:** `sentinel-core/tests/test_migration_orchestrator.py`
- **Verification:** `test_verify_failed_entry_does_not_rollback` passes (`report.verify_failed >= 1`, `report.rolled_back is False`).
- **Committed in:** `be3046b` (Task 2)

---

**Total deviations:** 3 auto-fixed (all Rule 1 — bugs found while making the plan's own required tests pass; two are latent bugs in already-committed Plan 02/03 code that only became observable once this plan's rollback logic was actually exercised end-to-end, one is a test-fixture premise contradicted by already-shipped, already-tested Phase 46 behavior).
**Impact on plan:** All three fixes were required for the plan's own specified verification commands (`pytest tests/test_migration_orchestrator.py::test_full_backfill_no_grandfathering` and `pytest tests/test_migration_orchestrator.py -x -q`) to pass. No scope creep — the full `migration_orchestrator` suite and the full sentinel-core suite (589 passed, 12 skipped) are green.

## Known Stubs

None — the notes-bound old-title → new-claim-title backlink-rewrite mapping (`_build_rewrite_mapping`) is a documented best-effort approximation (not an exact per-entry trace), but it is not a stub: it is backed by the D-03a graph orphan-diff hard gate, which is the plan's own designed backstop for exactly this case ("this is the hard backstop that forces rollback even if a rewrite was missed" — plan Task 2 action text). No automated test in this plan exercises the exact-mapping fidelity directly; this is called out here for the verifier's awareness, not hidden.

## Issues Encountered

- `tests/test_migration_routes.py` still fails to collect (`ModuleNotFoundError: No module named 'app.routes.migration'`) when running the full `tests/` suite without an `--ignore`. This is the same pre-existing Wave-0 RED scaffolding gap noted in Plan 03's SUMMARY (route wiring is a separate, later plan's scope per 47-PATTERNS.md's file assignment) — not something this plan touches. Running with `--ignore=tests/test_migration_routes.py` shows 589 passed / 12 skipped, no collateral breakage from this plan's changes.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Both migration tracks are fully wired and GREEN: Track A (ops-bound direct move, Plan 03) and Track B (notes-bound Reduce backfill, this plan), with the D-03 active backlink rewrite, the D-03a `:graph` zero-new-orphans hard gate, and the locked rollback-trigger predicate distinguishing hard failures from designed pipeline dead-letters.
- `migration_orchestrator.run()`'s live-run path never raises — callers (e.g. the future `/vault/migrate/start` route, `start_migration`) always receive a `MigrationReport` describing the outcome.
- `test_migration_routes.py`'s route-wiring gap remains open for whichever later plan owns `app/routes/migration.py` (per 47-PATTERNS.md's file assignment table) — no blocker introduced by this plan.
- No blockers for Plan 05.

---
*Phase: 47-migration-cutover-hardening*
*Completed: 2026-07-07*

## Self-Check: PASSED

All 3 modified files verified present on disk (`migration_orchestrator.py`, `migration_rollback_ledger.py`, `test_migration_orchestrator.py`) plus this SUMMARY.md; both task commits (`a444635`, `be3046b`) verified present in `git log`.
