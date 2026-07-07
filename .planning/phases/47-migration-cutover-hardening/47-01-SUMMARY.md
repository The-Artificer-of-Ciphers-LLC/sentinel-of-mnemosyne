---
phase: 47-migration-cutover-hardening
plan: 01
subsystem: testing
tags: [pytest, red-tests, migration, rollback, wikilinks, embeddings, admin-gate, tdd-nyquist]

requires:
  - phase: 46-6-rs-pipeline-orchestrator
    provides: pipeline_orchestrator.run(mode="pipeline"), inbox.append_entry, verify_note/check_note_compliance real-compliance gate
  - phase: 45-note-quality-schema-graph-analysis
    provides: graph_analysis.build_graph_report (notes/-scoped), links_sidecar_index, note_schema _schema block parser
  - phase: 44-vault-namespace-taxonomy-foundation
    provides: PARA namespace/taxonomy, PROTECTED_NAMESPACES, vault.relocate()
provides:
  - Four RED test files pinning the exact symbol/route contracts every Phase 47 implementation task must satisfy
  - migration_rollback_ledger.RollbackLedger contract (record_restore_original/record_ops_move/record_backlink_rewrite/record_inbox_write/replay)
  - ops_backlink_scan.scan_for_title_refs contract (vault-wide, NOT notes/-scoped)
  - migration_orchestrator.run()/MigrationReport contract (MIG-01/MIG-02, dry-run, atomic rollback, rollback-trigger split)
  - POST /vault/migrate/start + GET /vault/migrate/status admin-gated route contract (T-47-01)
affects: [47-02, 47-03, 47-04, 47-05, 47-06, 47-07]

tech-stack:
  added: []
  patterns:
    - "Wave 0 RED test-authoring: function-scope imports of not-yet-existing modules keep pytest collection green while pinning the exact symbol/route contract downstream plans must implement"
    - "Never mock the compliance/verification gate in orchestrator tests (phase46-pipeline-coldstart-gap) -- only the LLM/embedding boundary (reduce_entry, propose_hub_slug) is mocked; real Verify/check_note_compliance drives dead-letter outcomes"

key-files:
  created:
    - sentinel-core/tests/test_migration_rollback_ledger.py
    - sentinel-core/tests/test_ops_backlink_scan.py
    - sentinel-core/tests/test_migration_orchestrator.py
    - sentinel-core/tests/test_migration_routes.py
  modified: []

key-decisions:
  - "Ledger unit tests use a minimal local FakeVault (dict-backed, 4 methods) rather than tests/fakes/vault.py's full-protocol FakeVault -- matches the plan's explicit instruction and the pure-computation test-file precedent (test_graph_analysis.py)"
  - "Orchestrator integration tests reuse tests/fakes/vault.py's FakeVault (full Vault protocol) to match test_pipeline_orchestrator.py's own fixture precedent, since migration_orchestrator will call into pipeline_orchestrator.run() verbatim"
  - "record_inbox_write's inverse contract is pinned as delete-if-absent: replaying an inbox write whose before_body was empty (path did not exist pre-mutation) must remove the key entirely, not leave an empty-string body -- this is asserted directly in test_replay_restores_byte_identical_prestate"

patterns-established:
  - "Pattern 3 gap-filler: ops_backlink_scan is a NEW, standalone, vault-wide scan (never widens graph_analysis/links_sidecar_index, which are deliberately notes/-scoped)"
  - "Rollback-trigger split (Open Question 1 RESOLVED at the test layer): hard exceptions trigger rollback; a dead-lettered Verify-failed entry (report.verify_failed > 0, no exception) does NOT trigger rollback -- already-successful ops-bound moves are retained"

requirements-completed: [MIG-01, MIG-02]

coverage:
  - id: D1
    description: "RollbackLedger contract pinned: byte-identical replay restoration, LIFO inverse-op ordering, and idempotent double-replay"
    requirement: "MIG-02"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_migration_rollback_ledger.py#test_replay_restores_byte_identical_prestate,test_replay_reverse_order,test_replay_is_idempotent"
        status: pass
    human_judgment: false
  - id: D2
    description: "ops_backlink_scan.scan_for_title_refs contract pinned: vault-wide title-reference counting, not notes/-scoped, usable as a pre/post diff"
    requirement: "MIG-02"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_ops_backlink_scan.py#test_scan_counts_title_refs,test_scan_is_not_notes_scoped,test_scan_diff_detects_new_dangling"
        status: pass
    human_judgment: false
  - id: D3
    description: "migration_orchestrator.run()/MigrationReport contract pinned: MIG-01 full backfill with no grandfathering (notes/{slug} + ops/ residency, never inbox/{name}), MIG-02 embedding sidecar + wikilink preservation, D-02 dry-run no-writes, D-02/D-02a atomic rollback on hard failure, and the rollback-trigger split for dead-lettered Verify failures"
    requirement: "MIG-01"
    verification:
      - kind: integration
        ref: "sentinel-core/tests/test_migration_orchestrator.py#test_full_backfill_no_grandfathering,test_embedding_and_wikilink_preservation,test_dry_run_writes_nothing,test_hard_failure_triggers_atomic_rollback,test_verify_failed_entry_does_not_rollback"
        status: pass
    human_judgment: false
  - id: D4
    description: "POST /vault/migrate/start + GET /vault/migrate/status admin-gated route contract pinned (T-47-01 non-admin -> 403)"
    requirement: "MIG-01"
    verification:
      - kind: integration
        ref: "sentinel-core/tests/test_migration_routes.py#test_migrate_start_requires_admin,test_migrate_start_dry_run,test_migrate_status_shape"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-07-07
status: complete
---

# Phase 47 Plan 01: Wave 0 RED Test Authoring Summary

**Four RED test files pinning the exact contract for migration_rollback_ledger, ops_backlink_scan, migration_orchestrator, and /vault/migrate/* routes before any implementation exists.**

## Performance

- **Duration:** ~20 min
- **Tasks:** 3
- **Files modified:** 4 (all new)

## Accomplishments
- `test_migration_rollback_ledger.py` pins `RollbackLedger`'s byte-identical replay restoration, LIFO inverse-op ordering, and idempotent double-replay (D-02/D-02a atomic rollback contract)
- `test_ops_backlink_scan.py` pins `scan_for_title_refs(vault, title) -> int` as a vault-wide (not `notes/`-scoped) title-reference counter, the Pattern 3 backstop for the ops-bound track
- `test_migration_orchestrator.py` pins `run()`/`MigrationReport`'s five contract tests: full backfill with no grandfathering (MIG-01), embedding sidecar + wikilink preservation (MIG-02), dry-run zero-writes (D-02), hard-failure atomic rollback (D-02/D-02a), and the Open Question 1 rollback-trigger split (dead-lettered Verify failures do not unwind already-successful moves)
- `test_migration_routes.py` pins the admin-gated `POST /vault/migrate/start` / `GET /vault/migrate/status` route shape, reusing `test_note_routes.py`'s exact `SENTINEL_ADMIN_USER_IDS` gate setup (T-47-01)
- All four files verified to collect and fail RED with `ModuleNotFoundError`/`ImportError` today — the intended Wave 0 state; no test mocks the real compliance/verification gate

## Task Commits

Each task was committed atomically:

1. **Task 1: RED unit tests for the rollback ledger and ops backlink scan** - `05c566d` (test)
2. **Task 2: RED integration tests for the migration orchestrator** - `0a8e809` (test)
3. **Task 3: RED admin-gated route tests for /vault/migrate/\*** - `1c4cb35` (test)

**Plan metadata:** (this commit)

## Files Created/Modified
- `sentinel-core/tests/test_migration_rollback_ledger.py` - RollbackLedger unit tests (replay byte-identical restoration, LIFO order, idempotency) against a minimal local FakeVault
- `sentinel-core/tests/test_ops_backlink_scan.py` - scan_for_title_refs unit tests against a canned-find()-results FakeVault
- `sentinel-core/tests/test_migration_orchestrator.py` - migration_orchestrator.run() integration tests against tests/fakes/vault.py's full-protocol FakeVault, mocking only the LLM/embedding boundary (reduce_entry, propose_hub_slug)
- `sentinel-core/tests/test_migration_routes.py` - FastAPI TestClient route tests for the not-yet-existing app.routes.migration module

## Decisions Made
- Ledger tests use a minimal local FakeVault (4 methods: read_note/write_note/delete_note/relocate) per the plan's explicit instruction, rather than the full-protocol `tests/fakes/vault.py` FakeVault — matches `test_graph_analysis.py`'s pure-computation style.
- Orchestrator tests reuse `tests/fakes/vault.py`'s FakeVault (matching `test_pipeline_orchestrator.py`'s own fixture) since `migration_orchestrator.run()` will call `pipeline_orchestrator.run(mode="pipeline")` verbatim and needs the full Vault protocol (list_under, find, acquire/release_sweep_lock).
- Pinned `record_inbox_write`'s inverse as delete-if-absent (a path with no pre-existing body must be removed entirely by replay, not left as `""`) — this is a concrete implementation detail future plans must honor, made explicit via a direct assertion rather than left ambiguous.
- `test_verify_failed_entry_does_not_rollback` drives a genuine dead-letter outcome (a `ReduceResult` body with no wikilink, so the REAL `check_note_compliance`/`verify_note` gate fails it) rather than mocking the verification gate to force the outcome — per the explicit phase46-pipeline-coldstart-gap anti-pattern warning in RESEARCH.md/PATTERNS.md.

## Deviations from Plan

None - plan executed exactly as written. All four test files were authored per the task specifications, verified to collect and fail RED with the expected `ModuleNotFoundError`/`ImportError`, and no test mocks a compliance/verification gate.

## Issues Encountered

Running all four test files together (`test_migration_rollback_ledger.py test_ops_backlink_scan.py test_migration_orchestrator.py test_migration_routes.py`) triggers a pytest collection-error interruption at `test_migration_routes.py` (its module-level `from app.routes.migration import router` raises `ModuleNotFoundError` at import time, which pytest treats as a collection error rather than a per-test failure). This is expected and consistent with the plan's own verification block ("All four files MUST collect and fail RED with missing-module/404 errors — this is the intended Wave 0 outcome"); each file was also verified individually to confirm RED status per its own `<automated>` gate.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Every downstream Phase 47 implementation task (Plans 02-07) now has a real, already-authored RED test to turn GREEN — no `<automated>MISSING>` gates remain.
- The exact symbol names (`RollbackLedger`, `scan_for_title_refs`, `migration_orchestrator.run`/`MigrationReport`, `app.routes.migration` route paths) are locked; interface drift across the six-plan dependency chain is prevented.
- Wave 1+ can proceed directly to implementing `migration_rollback_ledger.py`, `ops_backlink_scan.py`, `migration_orchestrator.py`, and `routes/migration.py` against these pinned contracts.

---
*Phase: 47-migration-cutover-hardening*
*Completed: 2026-07-07*

## Self-Check: PASSED

All 4 created test files and the SUMMARY.md were verified present on disk; all 3 task commits (05c566d, 0a8e809, 1c4cb35) were verified present in git log.
