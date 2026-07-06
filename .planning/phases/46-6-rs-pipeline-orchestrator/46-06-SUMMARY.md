---
phase: 46-6-rs-pipeline-orchestrator
plan: 06
subsystem: sentinel-core / pipeline orchestrator + routes (integration keystone)
tags: [pipeline, orchestrator, routes, wave-3, integration, PIPE-02, PIPE-03, PIPE-04, PIPE-05, PIPE-06, PIPE-07]

# Dependency graph
requires:
  - phase: 46-6-rs-pipeline-orchestrator
    plan: "03"
    provides: "pipeline_status_store (D-03a field set) + PendingEntry.retry_count/needs_attention"
  - phase: 46-6-rs-pipeline-orchestrator
    plan: "04"
    provides: "six_rs.reduce.reduce_entry/build_schema_block, six_rs.verify.verify_note/VERIFY_RETRY_CAP"
  - phase: 46-6-rs-pipeline-orchestrator
    plan: "05"
    provides: "six_rs.reflect.find_and_attach_hub, six_rs.reweave.reweave_note, six_rs.rethink.triage_observations"
provides:
  - "app.services.pipeline_orchestrator.run(vault, *, mode, ...) -> PipelineReport"
  - "app.services.pipeline_orchestrator.start_pipeline(*, vault, mode, embedder=None, settings=None, task_runner=None) -> dict"
  - "app.routes.pipeline router: POST /vault/pipeline/start, GET /vault/pipeline/status"
affects: ["47 (vault migration/backfill)", "Discord :ralph/:pipeline/:reweave/:rethink rewiring (deferred to a Discord-side plan, not in this phase's scope list)"]

tech-stack:
  added: []
  patterns:
    - "D-04 shared-lock reuse: run() acquires vault.acquire_sweep_lock() BEFORE any inbox read (Pitfall 8), released in finally -- byte-identical shape to vault_sweeper.run_sweep"
    - "Pitfall 10 never-crash-the-loop: every per-entry stage call wrapped so one bad entry appends to report.errors and the loop continues"
    - "D-02 Verify-gates-Reflect/Reweave: in pipeline mode, only a note that PASSES verify_note is Reflected + Reweaved and kept in notes/; a failing note is deleted from notes/ and unconditionally requeued to inbox/ with the outcome's retry_count/needs_attention (never silently dropped)"
    - "reweave_note/rethink.triage_observations perform zero LLM calls of their own (46-05 decision) -- the orchestrator drafts reweave's addition_text via its own schema-constrained completion, mirroring reduce_entry/rethink._triage_one's Pitfall-6 coerce-to-fallback discipline"
    - "Reverse-entry_n processing order in inbox loops: remove_entry renumbers remaining entries sequentially from 1, so processing from the tail keeps not-yet-processed entry_n values stable across removals"

key-files:
  created:
    - sentinel-core/app/services/pipeline_orchestrator.py
    - sentinel-core/app/routes/pipeline.py
  modified:
    - sentinel-core/app/main.py

key-decisions:
  - "Verify gates Reflect/Reweave for :pipeline mode (explicit ordering decision, matches D-02's clean-graph invariant): the plan's action text describes 'Reduce -> Verify-gate -> Reflect -> Reweave' and this is implemented literally -- a note is Reflected/Reweaved and kept in notes/ ONLY when verify_note reports passed=True; on failure the draft is deleted from notes/ and the original inbox entry is unconditionally re-appended with the outcome's retry_count/needs_attention (never a bare drop), preserving the 6 Rs conceptual sequence while honoring the locked clean-graph constraint."
  - "reweave_note (46-05) performs zero LLM calls -- the orchestrator now owns drafting addition_text via a small schema-constrained completion (_draft_reweave_addition), mirroring reduce_entry's Pitfall-6 coerce-to-safe-fallback discipline (never raises; falls back to a deterministic '[[Member]] — Claim' string on any resolution/completion/parse failure). This matches the API-shape guidance recorded in the 46-05 SUMMARY ('the orchestrator must draft addition_text itself')."
  - "Slug generation reuses moc_maintenance._slugify (not graph_analysis._slugify, which is a wikilink-normalization helper, not a general filename slugifier) and is bounded to 60 chars to satisfy ClassificationResult.title_slug's max_length on the Verify-failure requeue path."
  - "embedder is optional in run()/start_pipeline() (frozen Wave-0 tests call run(vault, mode=\"ralph\") with no embedder): when absent, or when the call fails, an empty vector is passed through to find_and_attach_hub, which degrades gracefully (no cosine match clears the floor) rather than the orchestrator raising."
  - "reweave mode's candidate-discovery heuristic (RESEARCH's exact heuristic was left to Claude's discretion): embedding-first, reusing find_hub_candidate verbatim over all notes/-scoped index entries pairwise (excluding stale/wrong-model entries) -- no test exercises this mode directly, so the implementation favors reusing shipped D-07 machinery over inventing a new one."
  - "start_pipeline's error/blocked status updates use patch_pipeline_status(status=...) (a real .update() mutation on the module-level dict), not note_sweep_runner's get_status()[\"status\"] = ... pattern -- the latter mutates a throwaway copy returned by get_sweep_status() and has no effect on the actual store. This pre-existing pattern in note_sweep_runner.py is out of this plan's file scope (not touched), but the new pipeline code does not replicate the no-op bug."

requirements-completed: [PIPE-02, PIPE-03, PIPE-04, PIPE-05, PIPE-06, PIPE-07]

coverage:
  - id: D1
    description: "run() acquires the shared sweep lock before any inbox read (Pitfall 8, D-04); a concurrent pipeline/sweep run raises SweepInProgressError with zero inbox reads"
    requirement: "PIPE-06"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_pipeline_orchestrator.py::test_concurrent_pipeline_and_sweep_refused"
        status: pass
    human_judgment: false
  - id: D2
    description: "ralph mode drives Reduce+Reflect per inbox entry, writing notes/{slug}.md and reporting reduced/hubs_touched counts"
    requirement: "PIPE-02"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_pipeline_orchestrator.py::test_ralph_mode_reduce_and_reflect"
        status: pass
    human_judgment: false
  - id: D3
    description: "pipeline mode exercises Reduce, Verify, Reflect, Reweave, and one end-of-run Rethink with populated per-phase counts; Rethink runs exactly once per run, never per entry"
    requirement: "PIPE-03/04/05"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_pipeline_orchestrator.py::test_pipeline_mode_full_sequence"
        status: pass
    human_judgment: false
  - id: D4
    description: "POST /vault/pipeline/start is admin-gated (403 for non-admin, importing _is_admin_route -- T-46-01); GET /vault/pipeline/status is ungated and returns the PipelineReport dict shape"
    requirement: "PIPE-06"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_pipeline_routes.py -q (2 passed)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Full sentinel-core suite: the 566-baseline (550 + Waves 1-2) stays green, all 5 remaining Wave-0 RED scaffolds (3 orchestrator + 2 routes) flip GREEN -- zero RED phase-46 tests remain"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/ -q (571 passed / 12 skipped / 0 failed); --collect-only reports 583 tests collected with zero errors"
        status: pass
    human_judgment: false

duration: ~70min
completed: 2026-07-06
status: complete
---

# Phase 46 Plan 06: 6 Rs Pipeline Orchestrator — Integration Keystone Summary

**`pipeline_orchestrator.run(vault, *, mode, ...)` clones `vault_sweeper.run_sweep`'s lock/walk/error-isolation shape to make the 6 Rs pipeline actually mutate the vault: `ralph` drives Reduce+Reflect over the inbox queue; `pipeline` adds a Verify gate before Reflect/Reweave (D-02's clean-graph invariant — a failing note is deleted from `notes/` and unconditionally requeued to `inbox/` with a bounded retry count) plus one end-of-run Rethink; `reweave`/`rethink` run their respective passes standalone. `start_pipeline()` schedules a run via `AsyncioTaskRunner` and updates `pipeline_status_store`; `routes/pipeline.py` exposes the admin-gated start route (importing `_is_admin_route`, never duplicating it) and the ungated status route, registered in `main.py`.**

## What was built

### `app/services/pipeline_orchestrator.py`

- **`class PipelineReport(BaseModel)`** — `pipeline_id`, `status`, `mode`, `entries_total`, `entries_processed`, `reduced`, `hubs_touched`, `reweave_edits`, `verify_failed`, `verify_requeued`, `errors: list[str]` — the exact D-03a field set `pipeline_status_store.set_pipeline_status_from_report` duck-reads.
- **`async def run(vault, *, mode, embedder=None, settings=None, status_callback=None) -> PipelineReport`** — acquires `vault.acquire_sweep_lock()` FIRST (raising `SweepInProgressError("a vault operation is already in progress")` before any inbox read when a sweep or pipeline is already running, D-04/Pitfall 8), dispatches on `mode`, sets `status="complete"` on clean exit, `"blocked"` on lock contention, `"error"` on any other exception (mirroring `run_sweep` exactly), and always releases the lock in `finally`.
  - **`ralph`** — Reduce (`reduce_entry`) each inbox entry, compose the note via `# {claim_title}\n\n{body}\n\n` + the net-new `build_schema_block(type=result.schema_type, status="draft")`, write `notes/{slug}.md` (slug via `moc_maintenance._slugify`, reused rather than hand-rolled), embed on-demand (`embedder` optional — degrades to an empty vector when absent/failing) and call `find_and_attach_hub`, then `remove_entry` the consumed inbox entry. No Verify in ralph mode.
  - **`pipeline`** — same Reduce+compose+write, then `verify_note(vault, note_path=..., body=..., filename_slug=slug, retry_count=entry.retry_count)`. On **pass**: embed + Reflect (`find_and_attach_hub`) + draft a bounded Reweave addition via a small schema-constrained completion (`_draft_reweave_addition`, Pitfall-6 coerce-to-fallback) + `reweave_note`, then remove the inbox entry. On **fail**: delete the draft from `notes/`, and unconditionally requeue the original entry to `inbox/` (`_requeue_or_flag`) carrying the outcome's `retry_count`/`needs_attention` — never silently dropped (D-02/PIPE-07). After all entries, runs `triage_observations` exactly **once** (end-of-run Rethink, never per-entry).
  - **`reweave`** — backward-pass only: for each `notes/`-scoped embedding-index entry, finds the nearest OTHER `notes/` entry clearing the cosine floor (reusing `find_hub_candidate` verbatim) and appends a bounded Reweave section, counting `reweave_edits`.
  - **`rethink`** — triage-only: calls `triage_observations` once, folds the disposition count into `entries_total`/`entries_processed`.
  - Every per-entry stage call is wrapped in its own `try/except` appending `f"entry {n}: {exc}"` to `report.errors` — one bad entry never aborts the run (Pitfall 10).
- **`async def start_pipeline(*, vault, mode, embedder=None, settings=None, task_runner=None) -> dict`** — generates a UTC-timestamp `pipeline_id`, seeds `pipeline_status_store` with a "running" status via `patch_pipeline_status(**_new_pipeline_status(...))`, schedules an inner `_runner()` coroutine via `task_runner or AsyncioTaskRunner()`, and returns `{"pipeline_id", "status": "running", "mode"}` immediately (D-03 always-async ack). `_runner()` awaits `run(...)`, updates the status store on completion, and mirrors the sweep runner's exception handling (`SweepInProgressError` → `"blocked"`, broad `Exception` → log + `"error"`) — using `patch_pipeline_status(status=...)` (a real mutation), not `note_sweep_runner`'s `get_status()["status"] = ...` pattern (see Decisions Made).
- **`get_status()` / `_set_pipeline_status()` / `reset_status_for_tests()`** — thin wrappers over `pipeline_status_store`, mirroring `vault_sweeper`'s analogous status wrappers.

### `app/routes/pipeline.py`

- **`class PipelineStartRequest(BaseModel)`** — `user_id: str`, `mode: str`.
- **`POST /vault/pipeline/start`** — `from app.routes.note import _is_admin_route` (imported, never duplicated — T-46-01); 403 for a non-admin `user_id`; 422 for a `mode` outside `{ralph, pipeline, reweave, rethink}`; otherwise `await start_pipeline(vault=ctx.vault, embedder=ctx.embedder, settings=ctx.settings, mode=req.mode)`.
- **`GET /vault/pipeline/status`** — ungated, returns `get_status()` (the `PipelineReport` dict shape).

### `app/main.py`

- Added `from app.routes.pipeline import router as pipeline_router` and `app.include_router(pipeline_router)` alongside the other routers.

## Route contract for downstream consumers (Wave-4 Discord gateway)

**`POST /vault/pipeline/start`**
- Request: `{"user_id": "<discord user id>", "mode": "ralph" | "pipeline" | "reweave" | "rethink"}`
- Response (200, admin): `{"pipeline_id": "<UTC ISO-8601 timestamp>", "status": "running", "mode": "<mode>"}`
- Response (403): non-admin `user_id` (`{"detail": "admin only"}`)
- Response (422): `mode` not in the 4-value enum (`{"detail": "invalid mode: '<mode>'"}`)

**`GET /vault/pipeline/status`** (ungated)
- Response (200): the live `PipelineReport` dict —
  `{"pipeline_id": str | None, "status": "idle" | "running" | "complete" | "blocked" | "error", "mode": str | None, "entries_total": int, "entries_processed": int, "reduced": int, "hubs_touched": int, "reweave_edits": int, "verify_failed": int, "verify_requeued": int, "errors": list[str]}`
- Idle/default state before any run: `pipeline_id=None`, `status="idle"`, `mode=None`, all counts `0`, `errors=[]`.

## Test outcome (sentinel-core suite)

```
571 passed, 12 skipped, 0 failed in 15.55s
```

- All 5 target Wave-0 RED tests flipped GREEN: `tests/test_pipeline_orchestrator.py` (3 — ralph, pipeline full-sequence, concurrency) and `tests/test_pipeline_routes.py` (2 — admin-gate 403, status shape).
- The 566-test baseline (550 Phase-45-and-earlier + Waves 1-2's `pipeline_status_store`/`six_rs.*` tests) stays fully green — importing every `six_rs/*` stage into the orchestrator introduced zero regressions.
- **Zero RED phase-46 tests remain** in sentinel-core.
- `pytest --collect-only -q` reports 583 tests collected with zero collection errors (confirms no import-time breakage from the new `app.routes.pipeline` / `app.services.pipeline_orchestrator` modules).

## Task Commits

Each task group was committed atomically:

1. **Tasks 1-3: `pipeline_orchestrator.py` (run() + all four mode branches + start_pipeline())** — `7715c1c` (feat) — built and verified together as one cohesive module since Task 1's `run()` scaffold and Task 2's mode-dispatch extension share the same function; the frozen Wave-0 tests validate the combined behavior.
2. **Task 4: `routes/pipeline.py` + `main.py` registration** — `1373194` (feat)

## Files Created/Modified

- `sentinel-core/app/services/pipeline_orchestrator.py` — new; `PipelineReport`, `run()`, `start_pipeline()`, mode-branch helpers, status wrappers
- `sentinel-core/app/routes/pipeline.py` — new; admin-gated start route + ungated status route
- `sentinel-core/app/main.py` — modified; registers `pipeline_router`

## Deviations from Plan

### Auto-fixed / discretionary choices (Rule 1-3 style, no architectural changes)

**1. [Rule 1 — correctness] Reverse-entry_n processing order to avoid inbox renumbering drift.**
- **Found during:** Task 1 implementation — `inbox.remove_entry` renumbers ALL remaining entries sequentially from 1 after removing one. Processing a frozen entry list in ascending `entry_n` order while removing-as-you-go would cause later removals to target the WRONG (renumbered) entry.
- **Fix:** Both `_run_ralph` and `_run_pipeline` iterate `sorted(entries, key=lambda e: e.entry_n, reverse=True)` — removing from the tail first means the remaining prefix (`1..k`) is never renumbered by an intervening removal, so every `remove_entry(body, entry.entry_n)` call targets the entry the caller intended.
- **Files modified:** `sentinel-core/app/services/pipeline_orchestrator.py`
- **Commit:** `7715c1c`

**2. [Rule 1 — correctness] Did not replicate `note_sweep_runner`'s no-op status-mutation pattern.**
- **Found during:** Task 3 read-first — `note_sweep_runner._runner()`'s exception handlers do `get_status()["status"] = "blocked"` / `"error"`, but `get_status()` returns `dict(_SWEEP_STATUS)` (a fresh copy each call), so that assignment mutates a throwaway dict and has zero effect on the actual module-level store — a pre-existing bug in that file.
- **Action:** The new `start_pipeline._runner()` uses `patch_pipeline_status(status=...)`, which calls `_PIPELINE_STATUS.update(...)` and genuinely persists the blocked/error state. `note_sweep_runner.py` itself was NOT touched (outside this plan's `files_modified` list — only `pipeline_orchestrator.py`, `routes/pipeline.py`, `main.py` — and fixing it is a sweep-scoped change, not a pipeline one); the new pipeline code simply does not inherit the bug.
- **Files modified:** `sentinel-core/app/services/pipeline_orchestrator.py`
- **Commit:** `7715c1c`

None else — the plan's `<action>` texts for all four tasks were implemented as written, honoring the frozen Wave-0 test contracts and the 46-04/46-05 SUMMARY API shapes exactly.

## Threat Flags

No new surface beyond what the plan's own `<threat_model>` already covers (T-46-01, T-46-04, T-46-05, T-46-RETRY, T-46-INJECT, T-46-DOS-BATCH) — all mitigations are implemented as designed:
- **T-46-01:** `_is_admin_route` imported from `app.routes.note`, never duplicated (grep-confirmed single definition site).
- **T-46-04:** Shared `acquire_sweep_lock`/`release_sweep_lock` acquired before any inbox read, `finally`-released; proven by `test_concurrent_pipeline_and_sweep_refused`.
- **T-46-05 / T-46-RETRY:** Verify gates Reflect/Reweave; failing notes never land in `notes/`; requeue is unconditional (never dropped) and bounded by `VERIFY_RETRY_CAP` (owned by `six_rs.verify`, consumed here via the outcome dict).
- **T-46-INJECT:** The orchestrator's own `_draft_reweave_addition` completion places note excerpt text ONLY in the user-message slot, with an explicit DATA-ONLY system-prompt framing (mirrors `reduce.py`/`rethink.py`).
- **T-46-DOS-BATCH:** Accepted per plan (personal-vault scale, admin-triggered, pollable status) — no change needed.

## Self-Check: PASSED

- `sentinel-core/app/services/pipeline_orchestrator.py` — FOUND
- `sentinel-core/app/routes/pipeline.py` — FOUND
- `sentinel-core/app/main.py` (modified: pipeline_router import + include_router) — FOUND
- Commit `7715c1c` (feat: pipeline_orchestrator.py) — FOUND in `git log`
- Commit `1373194` (feat: routes/pipeline.py + main.py) — FOUND in `git log`
- `sentinel-core` suite: 571 passed / 12 skipped / 0 failed — confirmed via direct pytest run; `--collect-only` reports 583 tests collected with zero errors.

---
*Phase: 46-6-rs-pipeline-orchestrator*
*Completed: 2026-07-06*
