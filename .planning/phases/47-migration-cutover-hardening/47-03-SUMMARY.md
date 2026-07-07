---
phase: 47-migration-cutover-hardening
plan: 03
subsystem: migration
tags: [migration-orchestrator, ops-bound-relocate, embedding-sidecar, backlink-scan, tdd-green]

requires:
  - phase: 47-migration-cutover-hardening
    plan: 02
    provides: "RollbackLedger.record_ops_move + ops_backlink_scan.scan_for_title_refs, the atomic-rollback and verify-then-trust primitives this plan wires into the orchestrator"
provides:
  - "migration_status_store -- get_status/patch_status/set_status/new_status mirroring pipeline_status_store's running/complete/blocked/error vocabulary, for the future /vault/migrate/status route"
  - "migration_orchestrator.run/_discover_flat7/_move_ops_bound/start_migration -- the orchestrator spine (shared-lock/try-finally/dry-run/background-task) plus Track A (ops-bound direct move) end to end"
affects: [47-04, 47-05, 47-06, 47-07]

tech-stack:
  added: []
  patterns:
    - "Ops-bound relocate + inline sidecar-key patch bound into ONE RollbackLedger.record_ops_move entry (T-47-03) -- never restores a file path without its embedding sidecar key, or vice versa"
    - "Dual-spelling directory discovery (Pitfall E): probes BOTH singular and plural spellings for reference(s)/accomplishment(s) and merges files found under either, rather than picking one"
    - "Title-based backlink verification: scan_for_title_refs keys off the note's H1 display title (Pattern 4/Obsidian resolution semantics), not its flat-7 filename stem"

key-files:
  created:
    - sentinel-core/app/services/migration_status_store.py
    - sentinel-core/app/services/migration_orchestrator.py
  modified: []

key-decisions:
  - "MigrationReport's dry-run-enumeration field is named `planned_moves` (not the plan text's literal `planned`) -- the Plan 01 Wave 0 RED test (`test_dry_run_writes_nothing`) asserts `report.planned_moves`, which is the authoritative, already-pinned contract; the plan's prose field list was a naming slip, not a new requirement (Rule 1 auto-fix)"
  - "Ops-bound file titles are extracted from the note body's H1 heading (mirrors note_schema._H1_RE), not the filename stem -- `test_embedding_and_wikilink_preservation` proves a `[[Journal Entry]]` wikilink must resolve against the H1 'Journal Entry', which has no relation to the flat-7 filename '2026-02-02-entry.md'; the plan action text's literal 'read the note title (filename stem)' phrasing does not match this already-pinned RED contract (Rule 1 auto-fix)"
  - "_discover_flat7 also enumerates learning/ and reference(s)/ (Track B, notes-bound) with a placeholder destination string, even though this plan does not move them -- required so the dry-run preview shows the operator the FULL flat-7 picture (Pitfall E's dual-spelling probe explicitly covers reference(s)/ too) rather than only the ops-bound subset this plan executes"
  - "start_migration's status-store 'mode' field is 'dry_run'/'live' (migration has no ralph/pipeline/reweave/rethink mode concept) -- chosen to keep new_status(migration_id, status, mode)'s signature shape identical to pipeline_status_store's _new_status while giving the field a meaningful migration-specific value"

patterns-established:
  - "Track A (ops-bound) is fully wired this plan; Track B (notes-bound enqueue via inbox.append_entry + reused pipeline_orchestrator.run(mode='pipeline')) and the hard-failure rollback trigger are explicitly out of scope, landing in Plan 04 per the plan's own objective"

requirements-completed: [MIG-01, MIG-02]

coverage:
  - id: D1
    description: "Orchestrator skeleton (shared-lock/try-finally/dry-run/background-task) + status store: dry_run=True performs zero vault mutations and enumerates every discovered flat-7 file with its computed destination"
    requirement: "MIG-01"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_migration_orchestrator.py::test_dry_run_writes_nothing"
        status: pass
    human_judgment: false
  - id: D2
    description: "Track A ops-bound relocate + embedding-sidecar-key patch (no re-embed) + single rollback-ledger entry + pre/post backlink-scan gate"
    requirement: "MIG-02"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_migration_orchestrator.py::test_embedding_and_wikilink_preservation"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-07-07
status: complete
---

# Phase 47 Plan 03: Migration Orchestrator Spine + Track A (Ops-Bound Moves) Summary

**`migration_orchestrator.run()`'s shared-lock/dry-run/background-task skeleton plus Track A (`journal/`→`ops/journal/{date}/`, `accomplishments/`→`ops/accomplishments/`) with an inline embedding-sidecar-key patch and rollback-ledger-recorded, backlink-scan-gated relocate — both target RED tests turning GREEN.**

## Performance

- **Duration:** ~20 min
- **Tasks:** 2
- **Files modified:** 2 (both new)

## Accomplishments

- `migration_status_store.py` mirrors `pipeline_status_store.py`'s `get_status`/`patch_status`/`set_status`/`new_status` surface exactly, using the same running/complete/blocked/error vocabulary, with fields shaped for `MigrationReport` (`planned_moves`, `ops_moved`, `notes_backfilled`, `verify_failed`, `new_orphans`, `rolled_back`).
- `migration_orchestrator.py` implements the `MigrationReport` dataclass and `run(vault, *, dry_run, embedder=None, settings=None, status_callback=None)` following `pipeline_orchestrator.run`'s lock/try/except/finally shape verbatim: `vault.acquire_sweep_lock()` acquired first, `SweepInProgressError` mapped to status `"blocked"` (re-raised distinctly from generic `"error"`), `release_sweep_lock()` always in `finally`.
- `_discover_flat7` probes `journal/`, both `accomplishments/`/`accomplishment/`, `learning/`, and both `references/`/`reference/` via `vault.list_under()`, merging files found under either spelling (Pitfall E) rather than assuming one. Ops-bound categories (journal, accomplishment) get a real destination via `note_classifier.topic_dir_for`; notes-bound categories (learning, reference) are discovered with a placeholder destination for the dry-run preview only (Track B lands in Plan 04).
- `dry_run=True` populates `report.planned_moves` from discovery and returns before any mutation — the assert-zero-writes contract (D-02) — `test_dry_run_writes_nothing` is GREEN.
- Track A: `_move_ops_bound` reads the note, extracts its H1 title, runs a pre-move `scan_for_title_refs` (Pattern 3/D-03), calls `vault.relocate()`, patches the embedding sidecar key inline (`_patch_sidecar_key`, Pattern 2/D-04 "no re-embed"), records BOTH the relocate and the sidecar-key rename in a single `RollbackLedger.record_ops_move(sidecar_key_moved=...)` entry (T-47-03), then runs a post-move `scan_for_title_refs` and appends any shortfall to `ledger_backlinks` for Plan 04's rollback-trigger logic. `test_embedding_and_wikilink_preservation` is GREEN: the moved note's own `embedding_b64` frontmatter travels unchanged, the sidecar key is renamed old→new with the value untouched, and the pre-existing `[[Journal Entry]]` wikilink still resolves.
- `start_migration` mirrors `start_pipeline`'s background-task-and-status shape: seeds `"running"` status via `migration_status_store`, schedules the run via `AsyncioTaskRunner`, returns an immediate `{migration_id, status, mode}` ack (`mode` is `"dry_run"`/`"live"`).
- Both plan-specified verification commands are GREEN: the two target tests individually, and the quick-run regression subset (`test_pipeline_orchestrator.py`, `test_vault_sweeper.py`, `test_graph_analysis.py`, `test_links_sidecar_index.py`) — 79 tests, zero collateral breakage.

## Task Commits

Each task was committed atomically:

1. **Task 1: Status store + orchestrator skeleton (lock, dry-run, background task, report)** - `f65f015` (feat)
2. **Task 2: Track A — ops-bound relocate + sidecar-key patch + rollback + backlink scan gate** - `537be21` (feat)

**Plan metadata:** (this commit)

## Files Created/Modified

- `sentinel-core/app/services/migration_status_store.py` - In-memory migration status dict with `get_status`/`patch_status`/`set_status`/`new_status`, mirroring `pipeline_status_store.py`'s surface and vocabulary exactly.
- `sentinel-core/app/services/migration_orchestrator.py` - `MigrationReport` dataclass; `_discover_flat7` (dual-spelling probe across all four flat-7 categories); `_extract_title`/`_patch_sidecar_key`/`_move_ops_bound`/`_run_track_a` (Track A); `run()` (shared-lock/dry-run/Track-A-wired); `start_migration()` (background-task ack).

## Decisions Made

- `MigrationReport`'s dry-run field is `planned_moves`, not the plan prose's `planned` — the Plan 01 Wave 0 RED test is the authoritative contract and already asserts `report.planned_moves`.
- Ops-bound titles are extracted from the note body's H1 heading, not the filename stem — required for `scan_for_title_refs` to find the `[[Journal Entry]]`-style wikilinks that actually reference the note, since the flat-7 filename (e.g. `2026-02-02-entry.md`) never matches the wikilink text.
- `_discover_flat7` also enumerates the notes-bound categories (learning, reference(s)) with a placeholder destination, so the dry-run preview reflects the entire flat-7 legacy structure per Pitfall E, even though Track A does not move them this plan.
- `start_migration`'s status `mode` is `"dry_run"`/`"live"` rather than a pipeline-style mode name, since migration has no ralph/pipeline/reweave/rethink concept.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `MigrationReport` field renamed `planned` → `planned_moves` to match the pinned RED test contract**
- **Found during:** Task 1 (orchestrator skeleton)
- **Issue:** The plan's `<action>` prose lists the dataclass field as `planned`, but `tests/test_migration_orchestrator.py::test_dry_run_writes_nothing` (already committed in Plan 01, Wave 0) asserts `report.planned_moves`. Implementing the plan's literal field name would fail the plan's own required-GREEN test.
- **Fix:** Named the field `planned_moves` throughout `MigrationReport` and `migration_status_store`.
- **Files modified:** `sentinel-core/app/services/migration_orchestrator.py`, `sentinel-core/app/services/migration_status_store.py`
- **Verification:** `test_dry_run_writes_nothing` passes.
- **Committed in:** `f65f015` (Task 1 commit)

**2. [Rule 1 - Bug] Ops-bound title extraction uses the note's H1, not the filename stem**
- **Found during:** Task 2 (Track A relocate + sidecar patch)
- **Issue:** The plan's `<action>` prose says "read the note title (filename stem)", but `test_embedding_and_wikilink_preservation` seeds a note at `journal/2026-02-02-entry.md` with H1 `# Journal Entry` and a hub note containing `[[Journal Entry]]` — the pre/post `scan_for_title_refs` gate must search for `"[[Journal Entry]]"`, which never matches the filename stem `2026-02-02-entry`.
- **Fix:** Added `_extract_title(body, src)`, which searches the body for an H1 line (mirrors `note_schema._H1_RE`) and falls back to the filename stem only when no H1 is present.
- **Files modified:** `sentinel-core/app/services/migration_orchestrator.py`
- **Verification:** `test_embedding_and_wikilink_preservation` passes (pre/post scan count unchanged at 1, hub wikilink still resolves).
- **Committed in:** `537be21` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 — the plan's prose diverged from its own already-committed RED test contracts; the tests are authoritative).
**Impact on plan:** Both corrections were required for the plan's own specified verification commands to pass. No scope creep — both target tests and the full regression subset are GREEN.

## Issues Encountered

- `tests/test_migration_orchestrator.py` also contains three tests scoped to Track B (notes-bound enqueue) and the hard-failure rollback trigger (`test_full_backfill_no_grandfathering`, `test_hard_failure_triggers_atomic_rollback`, `test_verify_failed_entry_does_not_rollback`). These remain RED after this plan — expected and explicitly out of scope: the plan's own objective states "Track B `_enqueue_notes_bound` is added in Plan 04", and the rollback-trigger logic for a hard mid-run failure is likewise deferred. Only the two tests the plan's `<verify>` blocks name (`test_dry_run_writes_nothing`, `test_embedding_and_wikilink_preservation`) were required GREEN by this plan, and both are.
- `tests/test_migration_routes.py` (committed in Plan 01, Wave 0) fails to collect (`ModuleNotFoundError: No module named 'app.routes.migration'`) when running the full `tests/` suite without an `--ignore`. This is pre-existing Wave-0 RED scaffolding for the `/vault/migrate/*` routes, which 47-PATTERNS.md assigns to a route file this plan does not touch (route wiring is a separate, later plan in this phase). Confirmed via `git log` that the file was introduced in commit `1c4cb35` (Plan 01), before this plan's work began. Running the full suite with `--ignore=tests/test_migration_routes.py` (or the plan's own specified subset, or targeted files) shows 586 passed / 12 skipped / 3 failed (the three Track-B/rollback tests above) — no collateral breakage from this plan's changes.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `migration_orchestrator.run()`'s shared-lock/try-finally/dry-run/background-task skeleton and Track A (ops-bound direct move + sidecar patch + rollback-ledger + backlink-scan gate) are fully wired and GREEN, ready for Plan 04 to add `_enqueue_notes_bound` (Track B: learning/reference(s) → `inbox.append_entry()` → reused `pipeline_orchestrator.run(mode="pipeline")`) and the hard-failure atomic-rollback trigger inside the same `try` block (the marked call site is already in place in `run()`).
- `ledger_backlinks` (the ops-bound shortfall list) is populated by `_move_ops_bound` but not yet consumed by any rollback-trigger decision — Plan 04's rollback logic is the intended consumer.
- No blockers for Plan 04.

---
*Phase: 47-migration-cutover-hardening*
*Completed: 2026-07-07*

## Self-Check: PASSED

Both created files (`migration_status_store.py`, `migration_orchestrator.py`) and this SUMMARY.md were verified present on disk; both task commits (`f65f015`, `537be21`) were verified present in git log.
