---
phase: 46-6-rs-pipeline-orchestrator
plan: 01
subsystem: testing
tags: [pytest, tdd, red-scaffold, six-rs, pipeline-orchestrator, fastapi]

# Dependency graph
requires:
  - phase: 45-note-quality-schema-graph-analysis
    provides: "note_schema.check_note_compliance, moc_maintenance.find_hub_candidate/attach_to_hub, graph_analysis — the Verify + Reflect building blocks these RED tests pin as reuse targets"
provides:
  - "six_rs/__init__.py empty package marker — unblocks Wave 2 stage-module ownership without an __init__.py conflict"
  - "15 named RED tests across 8 files pinning every PIPE-02..07 observable behavior, including the Pitfall-6 (Reduce never drops a malformed completion) and Pitfall-8 (lock strictly precedes inbox read) invariants"
  - "Best-guess API contracts for six_rs.reduce.reduce_entry/ReduceResult, six_rs.reflect.find_and_attach_hub, six_rs.reweave.reweave_note, six_rs.verify.verify_note/VERIFY_RETRY_CAP, six_rs.rethink.triage_observations, pipeline_orchestrator.run/PipelineReport, pipeline_status_store, routes/pipeline.py — subject to revision at the implementing wave, per plan's explicit allowance"
affects: [46-02-six-rs-reduce-reflect, 46-03-six-rs-reweave-verify-rethink, 46-04-pipeline-orchestrator, 46-05-pipeline-status-routes, 46-06-orchestrator-wiring, 46-07-discord-wiring]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Wave 0 RED stubs use function-scope imports (inside each test body) so pytest collection succeeds before the implementing waves land the modules (STATE Phase 33-01/45-01 precedent) — a ModuleNotFoundError raised inside the test body is a FAILED test (RED), never a collection ERROR"]

key-files:
  created:
    - sentinel-core/app/services/six_rs/__init__.py
    - sentinel-core/tests/test_six_rs_reduce.py
    - sentinel-core/tests/test_six_rs_reflect.py
    - sentinel-core/tests/test_six_rs_reweave.py
    - sentinel-core/tests/test_six_rs_verify.py
    - sentinel-core/tests/test_six_rs_rethink.py
    - sentinel-core/tests/test_pipeline_orchestrator.py
    - sentinel-core/tests/test_pipeline_status_store.py
    - sentinel-core/tests/test_pipeline_routes.py
  modified: []

key-decisions:
  - "Reduce's Pitfall-6 malformed-completion test targets reduce_entry itself (a pure coerce-never-raise transform mirroring note_classifier's coerce-to-unsure discipline) rather than the orchestrator, with an explicit TODO for a Wave-3 companion test asserting the actual _schema.status:draft vault write, since the plan explicitly permits either seam."
  - "Reflect's T-46-03 self/ exclusion guard is tested as a hard architectural exclusion (self/ must never be selected as an attach target even when it embeds identically to the query) rather than a cosine-floor accident, since RESEARCH frames it as an information-disclosure guard, not a scoring nuance."
  - "Verify's requeue contract assumes a dict return shape ({passed, requeued, retry_count, needs_attention}) and a module-level VERIFY_RETRY_CAP constant (D-02b) rather than a typed model, matching the lighter-weight shape used by check_note_compliance itself."
  - "Rethink's triage_observations(vault) takes only the vault (no separate observations/tensions path args) and returns a flat list of {path, disposition} dicts, since PIPE-05/A3 frame tensions as optionally-empty input the function discovers itself."
  - "Orchestrator/route/status-store patches target usage-site names (e.g. app.services.pipeline_orchestrator.reduce_entry) rather than definition-site names, matching this codebase's established direct-name-import convention (confirmed in vault_sweeper.py's own import block) — this is the correct 'patch where it's used' convention for whichever import style Wave 3 adopts."

patterns-established:
  - "Every six_rs/* RED test imports its target symbol inside the test body (never at module scope), so `pytest --collect-only` stays green across the whole suite while individual tests FAIL (not ERROR) until the implementing wave lands the module — verified directly for all 15 new tests in this plan."

requirements-completed: [PIPE-02, PIPE-03, PIPE-04, PIPE-05, PIPE-06, PIPE-07]

coverage:
  - id: D1
    description: "six_rs/__init__.py package marker exists and app.services.six_rs is importable"
    verification:
      - kind: unit
        ref: "sentinel-core/app/services/six_rs/__init__.py (import app.services.six_rs)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Five six_rs stage RED test files (reduce, reflect, reweave, verify, rethink) collect cleanly and FAIL (not error) at runtime with the RESEARCH-mandated test names, pinning PIPE-02..07 including Pitfall 6 (Reduce never drops a malformed completion) and T-46-03 (no wikilink from notes/ into self/)"
    requirement: "PIPE-02, PIPE-04, PIPE-05, PIPE-07"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_six_rs_reduce.py, test_six_rs_reflect.py, test_six_rs_reweave.py, test_six_rs_verify.py, test_six_rs_rethink.py --collect-only"
        status: pass
    human_judgment: false
  - id: D3
    description: "Orchestrator, status-store, and route RED tests collect cleanly; the concurrency test encodes lock-before-inbox-read (Pitfall 8); the status test asserts mode + per-phase counts (D-03a); the route test asserts the 403 admin gate on start and an ungated status read"
    requirement: "PIPE-02, PIPE-03, PIPE-06"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_pipeline_orchestrator.py, test_pipeline_status_store.py, test_pipeline_routes.py --collect-only"
        status: pass
    human_judgment: false
  - id: D4
    description: "Full-suite collection is error-free and the pre-existing baseline stays green; only the 15 new phase-46 RED tests are red"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/ -q (577 collected, 550 passed / 12 skipped / 15 new RED failures)"
        status: pass
    human_judgment: false

duration: ~25min
completed: 2026-07-06
status: complete
---

# Phase 46 Plan 01: Wave 0 6 Rs Pipeline RED Scaffolds Summary

**15 named RED tests across 8 new files (plus the `six_rs/` package stub) pin every PIPE-02..07 observable behavior — including the Pitfall-6 malformed-completion draft-coercion and Pitfall-8 lock-before-inbox-read invariants — as the executable contract Waves 1-4 must turn GREEN.**

## Performance

- **Duration:** ~25 min
- **Tasks:** 3
- **Files modified:** 9 created (1 package marker + 8 test files)

## Accomplishments

- Created `sentinel-core/app/services/six_rs/__init__.py`, an empty package marker so both Wave-2 stage plans can add modules without an `__init__.py` ownership conflict.
- Wrote 9 RED tests across `test_six_rs_reduce.py` (2), `test_six_rs_reflect.py` (2), `test_six_rs_reweave.py` (1), `test_six_rs_verify.py` (2), `test_six_rs_rethink.py` (2) — pinning the Reduce claim/schema extraction contract, the Pitfall-6 never-drop-a-malformed-completion invariant, the Reflect embedding-first hub match, the T-46-03 self/ information-disclosure guard, the Reweave idempotent dated-section append (D-01), the Verify retry-cap requeue + `check_note_compliance` reuse (D-02/D-02a/D-02b), and the Rethink disposition triage + A3 absent-tensions-dir tolerance.
- Wrote 6 RED tests across `test_pipeline_orchestrator.py` (3), `test_pipeline_status_store.py` (1), `test_pipeline_routes.py` (2) — pinning the `:ralph`/`:pipeline` mode sequencing (PIPE-02/03), the Pitfall-8 lock-strictly-precedes-inbox-read ordering (verified via a `read_note` spy asserting `INBOX_PATH` is never read after a pre-acquired lock forces `SweepInProgressError`), the `PipelineReport` mode + per-phase-count round-trip (D-03a), and the admin-gated `POST /vault/pipeline/start` (403) / ungated `GET /vault/pipeline/status` route contract.
- Verified the full core suite: `pytest tests/ --collect-only -q` reports zero collection errors across all 577 tests (up from 562 pre-plan); `pytest tests/ -q` shows exactly the 15 new phase-46 tests FAILING while the pre-existing 550 passed / 12 skipped baseline stays fully green.

## Task Commits

Each task was committed atomically:

1. **Task 1: six_rs package stub + six_rs stage RED tests** - `55d1933` (test)
2. **Task 2: orchestrator + route + status-store RED tests** - `97932fd` (test)
3. **Task 3: whole-suite collection gate (no regressions introduced)** - no commit (verification-only; zero file changes — confirmed via `git status --short` producing no output for this task)

_Note: this is a test-scaffold-only plan (Wave 0) — no `feat`/`refactor` commits, matching the Phase 45-01 precedent that Wave 0 must precede any feature module._

## Files Created/Modified

- `sentinel-core/app/services/six_rs/__init__.py` - Empty package marker (module docstring only)
- `sentinel-core/tests/test_six_rs_reduce.py` - RED: `reduce_entry` claim/schema extraction + Pitfall-6 malformed-completion draft-coercion
- `sentinel-core/tests/test_six_rs_reflect.py` - RED: embedding-first hub match calling `attach_to_hub` + T-46-03 self/ exclusion guard
- `sentinel-core/tests/test_six_rs_reweave.py` - RED: idempotent `## Reweave — {date}` dated-section append (D-01)
- `sentinel-core/tests/test_six_rs_verify.py` - RED: retry-cap requeue (D-02b) + `check_note_compliance` reuse, not re-implementation (D-02a)
- `sentinel-core/tests/test_six_rs_rethink.py` - RED: PROMOTE/IMPLEMENT/METHODOLOGY/ARCHIVE/KEEP disposition triage + A3 absent-`ops/tensions/`-dir tolerance
- `sentinel-core/tests/test_pipeline_orchestrator.py` - RED: `:ralph`/`:pipeline` mode sequencing (PIPE-02/03) + Pitfall-8 lock-before-inbox-read ordering
- `sentinel-core/tests/test_pipeline_status_store.py` - RED: `PipelineReport` mode + per-phase-count round-trip (D-03a)
- `sentinel-core/tests/test_pipeline_routes.py` - RED: admin-gated start (403) + ungated status shape (PIPE-06)

## Decisions Made

- Reduce's Pitfall-6 test targets `reduce_entry` itself (coerce-never-raise, mirroring `note_classifier`'s coerce-to-`unsure` discipline) with an explicit TODO for a future orchestrator-level companion test asserting the actual `_schema.status: draft` vault write — the plan explicitly permitted either seam ("may target the orchestrator helper if Reduce itself is a pure transform").
- Reflect's T-46-03 guard is tested as a hard architectural exclusion: a `self/` entry with an *identical* embedding to the query must still never be selected as an attach target, proving the guard is a categorical exclusion rather than merely losing a cosine-floor tie.
- Verify's contract assumes a lightweight dict return (`{passed, requeued, retry_count, needs_attention}`) and a module-level `VERIFY_RETRY_CAP` named constant (D-02b), matching the shape of the pre-existing `check_note_compliance` dict rather than introducing a new pydantic model at this seam.
- Rethink's `triage_observations(vault)` takes only the vault and self-discovers `ops/observations/` (+ optional `ops/tensions/`), returning `[{path, disposition}, ...]` — consistent with A3's framing that tensions is optionally-empty input, not a required argument.
- Orchestrator/status-store/route test patches target usage-site names (e.g., `app.services.pipeline_orchestrator.reduce_entry`) rather than definition-site names, matching the codebase's established direct-name-import convention (confirmed via `vault_sweeper.py`'s own `from app.services.X import (...)` style) — the standard "patch where it's used" discipline.
- All API shapes invented for this Wave-0 plan (function names, exact signatures, `PipelineReport` field set) are **best-guess contracts per the plan's explicit allowance** ("Write assertions describing the intended API, not implementation") — the implementing waves (46-02 through 46-06) may need to adjust these test bodies to match the final signatures chosen there; this is expected and does not indicate a defect in this plan.

## Deviations from Plan

None - plan executed exactly as written. All three tasks' `<verify>` commands pass exactly as specified: the five six_rs files collect with zero errors (Task 1), the three orchestrator/status/route files collect with zero errors (Task 2), and the whole-suite `--collect-only` reports zero errors with the pre-existing 550/12 baseline fully intact and only the 15 new phase-46 tests red (Task 3).

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **RED test node-ids Waves 1-4 must turn GREEN** (15 total, across 8 files):
  - `tests/test_six_rs_reduce.py::test_reduce_extracts_claim_and_schema_draft`
  - `tests/test_six_rs_reduce.py::test_reduce_malformed_completion_still_filed_as_draft`
  - `tests/test_six_rs_reflect.py::test_reflect_embedding_first_hub_match`
  - `tests/test_six_rs_reflect.py::test_reflect_no_wikilink_from_notes_into_self`
  - `tests/test_six_rs_reweave.py::test_reweave_append_idempotent`
  - `tests/test_six_rs_verify.py::test_verify_failure_requeues_with_retry_cap`
  - `tests/test_six_rs_verify.py::test_verify_reuses_check_note_compliance`
  - `tests/test_six_rs_rethink.py::test_rethink_triage_dispositions`
  - `tests/test_six_rs_rethink.py::test_rethink_tolerates_absent_tensions_dir`
  - `tests/test_pipeline_orchestrator.py::test_ralph_mode_reduce_and_reflect`
  - `tests/test_pipeline_orchestrator.py::test_pipeline_mode_full_sequence`
  - `tests/test_pipeline_orchestrator.py::test_concurrent_pipeline_and_sweep_refused`
  - `tests/test_pipeline_status_store.py::test_status_store_round_trips_pipeline_report`
  - `tests/test_pipeline_routes.py::test_pipeline_start_admin_gated_403`
  - `tests/test_pipeline_routes.py::test_pipeline_status_returns_report_shape`
- Since every API shape here is a best-guess contract (function names/signatures not yet locked by an implementation), the next waves' planners/implementers should treat these RED tests as a strong starting contract but feel free to adjust patch targets / exact signatures within the test bodies to match whatever concrete API they land, as long as the *observable behavior* each test name describes is preserved.
- No blockers. Full suite green at 550 passed / 12 skipped (pre-existing baseline, byte-identical) + 15 new RED, exactly as this plan's `<verification>` block specifies.

---
*Phase: 46-6-rs-pipeline-orchestrator*
*Completed: 2026-07-06*

## Self-Check: PASSED

- FOUND: sentinel-core/app/services/six_rs/__init__.py
- FOUND: sentinel-core/tests/test_six_rs_reduce.py
- FOUND: sentinel-core/tests/test_six_rs_reflect.py
- FOUND: sentinel-core/tests/test_six_rs_reweave.py
- FOUND: sentinel-core/tests/test_six_rs_verify.py
- FOUND: sentinel-core/tests/test_six_rs_rethink.py
- FOUND: sentinel-core/tests/test_pipeline_orchestrator.py
- FOUND: sentinel-core/tests/test_pipeline_status_store.py
- FOUND: sentinel-core/tests/test_pipeline_routes.py
- FOUND: 55d1933 (Task 1 commit)
- FOUND: 97932fd (Task 2 commit)
- FOUND: 8448dc9 (SUMMARY commit)
