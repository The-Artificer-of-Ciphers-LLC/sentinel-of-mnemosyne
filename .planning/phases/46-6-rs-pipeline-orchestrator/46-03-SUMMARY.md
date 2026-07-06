---
phase: 46-6-rs-pipeline-orchestrator
plan: 03
subsystem: pipeline-infra
tags: [inbox, retry-count, pipeline-status-store, tdd, wave-1]

# Dependency graph
requires:
  - phase: 46-6-rs-pipeline-orchestrator
    plan: 01
    provides: "test_pipeline_status_store.py RED contract this plan turns GREEN"
provides:
  - "PendingEntry.retry_count / needs_attention -- bounded requeue-counter storage for D-02/D-02b Verify-failure requeue"
  - "app.services.pipeline_status_store -- in-memory PipelineReport progress store (get/set/patch/reset + _new_status), field set: pipeline_id, status, mode, entries_total, entries_processed, reduced, hubs_touched, reweave_edits, verify_failed, verify_requeued, errors"
affects: [46-04-pipeline-orchestrator, 46-05-pipeline-status-routes, 46-06-orchestrator-wiring]

# Tech tracking
tech-stack:
  added: []
  patterns: ["retry_count/needs_attention parse uses the same safe-coercion-with-default discipline as confidence (never raises on bad/missing input)", "pipeline_status_store is a near-verbatim structural clone of sweep_status_store, kept as a fully separate dict per D-04 (no store unification)"]

key-files:
  created:
    - sentinel-core/app/services/pipeline_status_store.py
  modified:
    - sentinel-core/app/services/inbox.py

key-decisions:
  - "append_entry gained optional retry_count/needs_attention kwargs (both defaulting to 0/False) rather than a separate requeue_entry twin -- this satisfies the plan's 'requeue path must be able to set an incremented count' requirement with a single function, and the defaults guarantee the plain capture call site (PIPE-01) is byte-for-byte unaffected."
  - "needs_attention renders as literal 'true'/'false' strings (not Python's True/False) to keep the markdown line human-editable/greppable, consistent with how topic/reasoning are plain lowercase tokens elsewhere in the file; parsed back via a case-insensitive string compare."
  - "pipeline_status_store's PipelineReport field set matches exactly what test_pipeline_status_store.py (Wave 0) and 46-PATTERNS.md's D-03a table specify -- no additional fields invented, so Wave 3's PipelineReport model has an unambiguous target to match."

requirements-completed: [PIPE-01, PIPE-06, PIPE-07]

coverage:
  - id: D1
    description: "PendingEntry carries retry_count + needs_attention that round-trip through render/parse; legacy entries with no retry_count line default to 0 (no migration)"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_inbox.py -q (8 passed) + ad hoc round-trip/legacy-default scratch test (not committed, verification-only)"
        status: pass
    human_judgment: false
  - id: D2
    description: "append_entry's default (capture) call path is unchanged -- PIPE-01 frictionless capture regression guard holds"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_inbox.py::test_parse_two_entries_round_trip, test_append_creates_initial_when_body_empty (both call append_entry with no retry_count/needs_attention args and pass)"
        status: pass
    human_judgment: false
  - id: D3
    description: "pipeline_status_store round-trips a PipelineReport's mode + D-03a per-phase counts (duck-typed, no PipelineReport import) and resets to idle"
    requirement: "PIPE-06"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_pipeline_status_store.py::test_status_store_round_trips_pipeline_report"
        status: pass
    human_judgment: false
  - id: D4
    description: "Full sentinel-core suite: 550-baseline stays green, the Wave-0 pipeline_status_store RED flips GREEN, only the expected Wave-2/3 six_rs + orchestrator + route RED tests remain"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/ -q (551 passed / 12 skipped / 14 remaining RED, all in test_six_rs_*, test_pipeline_orchestrator.py, test_pipeline_routes.py)"
        status: pass
    human_judgment: false

duration: ~20min
completed: 2026-07-06
status: complete
---

# Phase 46 Plan 03: Bounded Retry Storage + Pipeline Status Store Summary

**Extended the shipped `inbox.py` `PendingEntry` with a bounded `retry_count`/`needs_attention` pair (D-02b storage) and cloned `sweep_status_store.py` into `pipeline_status_store.py` (D-03a/D-04) -- flipping the Wave-0 `test_pipeline_status_store.py` RED test to GREEN while leaving the capture path (PIPE-01) and full 550-test baseline untouched.**

## Performance

- **Duration:** ~20 min
- **Tasks:** 2
- **Files modified:** 1 modified (`inbox.py`), 1 created (`pipeline_status_store.py`)

## Accomplishments

- `PendingEntry` gained `retry_count: int = 0` and `needs_attention: bool = False`. `_parse_entry_section` reads a `- retry_count: N` line with the same try/except int-coercion shape used for `confidence` (default 0 on missing/invalid) and a `- needs_attention: true/false` line (default False, case-insensitive). `_render_entry` emits both lines. `append_entry` accepts optional `retry_count`/`needs_attention` kwargs (default 0/False) so the plain capture call is byte-for-byte unaffected.
- Verified backward compatibility directly: a legacy inbox body with no `retry_count`/`needs_attention` lines parses to `retry_count=0`, `needs_attention=False` -- no migration step needed, matching 46-RESEARCH.md's "Runtime State Inventory" finding.
- Created `sentinel-core/app/services/pipeline_status_store.py` as a near-verbatim structural clone of `sweep_status_store.py`: `_PIPELINE_STATUS` dict, `get_pipeline_status()`, `set_pipeline_status_from_report(report)` (duck-typed, no `PipelineReport` import), `patch_pipeline_status(**kwargs)`, `reset_pipeline_status()`, and a `_new_status(pipeline_id, status, mode)` factory for Wave-3's runner. Field set: `pipeline_id`, `status`, `mode`, `entries_total`, `entries_processed`, `reduced`, `hubs_touched`, `reweave_edits`, `verify_failed`, `verify_requeued`, `errors` -- exactly the D-03a set `test_pipeline_status_store.py` (Wave 0) pins.
- Full suite run: `pytest tests/ -q` -> 551 passed / 12 skipped / 14 failed. The 550-baseline is intact (now 551 because `test_pipeline_status_store.py`'s single test flipped RED->GREEN); the 14 remaining failures are exactly the Wave-2/3 `six_rs/*`, `pipeline_orchestrator.py`, and `pipeline_routes.py` tests this plan was not scoped to implement.

## Task Commits

Each task was committed atomically:

1. **Task 1: extend PendingEntry with bounded retry_count + needs_attention** - `78cfd4c` (feat)
2. **Task 2: pipeline_status_store cloned from sweep_status_store** - `9aba1ab` (feat)

## Files Created/Modified

- `sentinel-core/app/services/inbox.py` - `PendingEntry` gains `retry_count`/`needs_attention`; parse/render/append_entry updated; capture path unchanged (PIPE-01)
- `sentinel-core/app/services/pipeline_status_store.py` - New in-memory pipeline progress store (D-03a field set), cloned from `sweep_status_store.py`

## Decisions Made

- `append_entry` gained optional `retry_count`/`needs_attention` kwargs rather than a separate `requeue_entry` twin (plan offered both options at Claude's discretion) -- one function covers both the capture call (defaults) and the future Wave-3 requeue call (explicit incremented value), with less surface area to test/maintain.
- `needs_attention` renders as the literal strings `true`/`false` (not Python `True`/`False`) for a human-editable markdown line, parsed back case-insensitively.
- No additional `pipeline_status_store` fields beyond what Wave 0's RED test and 46-PATTERNS.md's D-03a table already specify -- keeps Wave 3's `PipelineReport` model target unambiguous.

## Deviations from Plan

None - plan executed exactly as written. Both tasks' `<verify>` commands pass exactly as specified, and the plan's `<verification>` block (inbox + status-store suites green, backward-compat confirmed, capture path unchanged) is fully satisfied.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **Final `PipelineReport` field names the status store expects** (per the plan's `<output>` instruction, for Wave 3's `PipelineReport` model to match): `pipeline_id: str`, `status: str` (`idle|running|complete|blocked|error`), `mode: str`, `entries_total: int`, `entries_processed: int`, `reduced: int`, `hubs_touched: int`, `reweave_edits: int`, `verify_failed: int`, `verify_requeued: int`, `errors: list[str]`.
- `pipeline_status_store.set_pipeline_status_from_report(report)` reads these attributes duck-typed off `report` -- Wave 3's `PipelineReport` (pydantic `BaseModel` or otherwise) just needs these exact attribute names.
- `pipeline_status_store._new_status(pipeline_id, status, mode)` is available for Wave 3's `start_pipeline`/runner to seed the "running" state before the first real report lands (mirrors `vault_sweeper`'s status-seeding shape).
- `inbox.append_entry(..., retry_count=N, needs_attention=True)` is the requeue call Wave 3's `six_rs/verify.py` should use when a Verify-failed entry needs to go back into `inbox/` with an incremented count (D-02); at the cap, pass `needs_attention=True` and the orchestrator's own retry-cap constant governs when to stop retrying (not the inbox layer itself, which has no opinion on the cap value).
- Remaining Wave-0 RED tests this plan intentionally left red (Waves 2-3 own them): `test_six_rs_reduce.py` (2), `test_six_rs_reflect.py` (2), `test_six_rs_reweave.py` (1), `test_six_rs_verify.py` (2), `test_six_rs_rethink.py` (2), `test_pipeline_orchestrator.py` (3), `test_pipeline_routes.py` (2).
- No blockers.

---
*Phase: 46-6-rs-pipeline-orchestrator*
*Completed: 2026-07-06*

## Self-Check: PASSED

- FOUND: sentinel-core/app/services/inbox.py (modified)
- FOUND: sentinel-core/app/services/pipeline_status_store.py
- FOUND: 78cfd4c (Task 1 commit)
- FOUND: 9aba1ab (Task 2 commit)
