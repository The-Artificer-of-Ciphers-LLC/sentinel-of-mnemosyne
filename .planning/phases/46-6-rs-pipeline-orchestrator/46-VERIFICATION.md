---
phase: 46-6-rs-pipeline-orchestrator
verified: 2026-07-06T21:58:03Z
status: human_needed
score: 7/7 must-haves verified (5 ROADMAP success criteria + PIPE-01..07 all accounted for)
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Run `:ralph` (and separately `:pipeline`) in Discord against the real Obsidian vault with a live LM Studio/exo model, after seeding `inbox/` with a raw capture"
    expected: "A `notes/{slug}.md` file appears with a claim-style H1 title, at least one wikilink, and a trailing ```_schema block (status: draft); the relevant MOC/hub note is created or updated (appended, not duplicated)"
    why_human: "Requires a live Obsidian REST endpoint and a live LM Studio/exo completion — FakeVault unit tests exercise the orchestration logic and vault-mutation shape but cannot prove real-vault/real-model output quality or MOC-file content end-to-end (46-VALIDATION.md's own Manual-Only Verifications table calls this out explicitly)"
  - test: "Start a pipeline run (`:pipeline` or `:ralph`), then poll `:pipeline status` / `:ralph status` repeatedly while the background task runs"
    expected: "Status transitions idle → running → complete (or blocked/error), with entries_processed and the per-phase counts advancing between polls, and a final outcome (not a silent 'done')"
    why_human: "Requires live Discord + background-task timing across real wall-clock time; unit tests exercise `start_pipeline`/`pipeline_status_store` synchronously via `_ImmediateTaskRunner`, which proves the wiring but not the live poll experience (46-VALIDATION.md Manual-Only Verifications)"
---

# Phase 46: 6 Rs Pipeline Orchestrator Verification Report

**Phase Goal:** The 6 Rs pipeline (Record → Reduce → Reflect → Reweave → Verify → Rethink) becomes real background orchestration, cloned from the `vault_sweeper.py`/`task_runner.py`/`sweep_status_store.py` shape — not the single fixed-text prompt it resolves to today. `:capture`/`:seed` land content in `inbox/` with zero friction; `:ralph` and `:pipeline` actually mutate the vault (write `_schema`-bearing notes, update MOCs); runs are guarded against concurrent execution and report their real outcome.
**Verified:** 2026-07-06T21:58:03Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Phase 46 Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `:capture`/`:seed` drop raw content into `inbox/` with zero friction — no validation blocks capture | ✓ VERIFIED | `inbox.append_entry()` (`sentinel-core/app/services/inbox.py:183-220`) defaults `retry_count=0`/`needs_attention=False`; no new validation gate added. `tests/test_inbox.py` green as part of the 573-test run. |
| 2 | `:ralph` batch-processes the `inbox/` queue (Reduce+Reflect) via single-prompt orchestration and produces real `notes/` files with `_schema`, wikilinks, and MOC updates — not just a Discord reply | ✓ VERIFIED | `pipeline_orchestrator._run_ralph` (`pipeline_orchestrator.py:277-313`) calls `reduce_entry` → composes `# title\n\nbody\n\n` + `build_schema_block(...)` → `vault.write_note("notes/{slug}.md", ...)` → embeds + `find_and_attach_hub`. `tests/test_pipeline_orchestrator.py::test_ralph_mode_reduce_and_reflect` PASSED (confirmed by direct re-run); `tests/test_six_rs_reduce.py::test_build_schema_block_round_trips_through_check_note_compliance` PASSED (confirms the net-new `_schema` fence actually satisfies `check_note_compliance`). |
| 3 | `:pipeline` runs the full 6 Rs sequence end-to-end, and `:reweave` runs a backward pass updating older notes given recent vault additions, reusing `SemanticRecall` for candidate discovery | ✓ VERIFIED (documented discretionary substitution) | `pipeline_orchestrator._run_pipeline` drives Reduce→Verify-gate→Reflect→Reweave, then one end-of-run Rethink (`test_pipeline_mode_full_sequence` PASSED, confirms `rethink_mock.assert_awaited_once()`). `_run_reweave` performs candidate discovery via `moc_maintenance.find_hub_candidate` over the embedding sidecar index rather than importing the `SemanticRecall` class literally — this is an explicitly authorized discretionary choice (46-CONTEXT.md "Claude's Discretion": *"Reweave candidate-discovery specifics... the exact heuristic in graph_analysis"*), documented transparently in 46-06-SUMMARY.md, and functionally equivalent (same embedding-cosine mechanism `SemanticRecall` itself would use). Not a gap. |
| 4 | `:rethink`/`:refactor` triage accumulated `ops/observations` and `ops/tensions` into an actionable disposition (promote/implement/methodology/archive/keep) | ✓ VERIFIED | `six_rs/rethink.py::triage_observations` assigns exactly one of `PROMOTE/IMPLEMENT/METHODOLOGY/ARCHIVE/KEEP` per item, tolerates an absent `ops/tensions/` (A3), coerces malformed completions to `KEEP`. `tests/test_six_rs_rethink.py` (3 tests) PASSED on direct re-run. `command_router.py:166` maps `:refactor` → `mode="rethink"` (D-09 synonym), confirmed by `test_pipeline_verb_starts_with_correct_mode[refactor-rethink]` PASSED. |
| 5 | Two concurrent pipeline invocations cannot double-process the same inbox entry (lockfile guard mirroring the sweeper); every run reports its actual success/partial/failure outcome; `_schema` quality enforcement happens only at Verify — Reduce always files a note (as draft if imperfect), never stalling capture | ✓ VERIFIED | Lock: `run()` calls `vault.acquire_sweep_lock()` BEFORE any inbox read (`pipeline_orchestrator.py:481-482`); `test_concurrent_pipeline_and_sweep_refused` PASSED and explicitly asserts `INBOX_PATH not in read_paths` (proves ordering, not just "raises somewhere") — confirmed by direct re-run. Reduce never blocks: `reduce_entry` never raises (`six_rs/reduce.py` — every failure path returns a safe fallback `ReduceResult`); `test_reduce_malformed_completion_still_filed_as_draft` PASSED. Verify-only-enforcement: `verify_note` is a thin wrapper over the already-shipped `check_note_compliance` and never re-implements checks (`six_rs/verify.py:74`); the orchestrator's `_run_pipeline` failure branch (`pipeline_orchestrator.py:367-373`) deletes the draft from `notes/` and unconditionally requeues to `inbox/` — **this specific integration path (delete_note + requeue-with-incremented-retry, and the at-cap needs_attention path) has NO test in the shipped `tests/test_pipeline_orchestrator.py`** (only the ralph path, the all-pass pipeline path, and the concurrency path are covered there); the verifier wrote and ran a temporary, non-committed pytest module exercising both the requeue and at-cap branches against the real `pipeline_orchestrator.run()` — both passed, confirming the code is correct, then deleted the temporary file (not part of the shipped diff). See "Test Coverage Note" below — flagged as a WARNING, not a blocker, since correctness was independently confirmed by execution, not merely by presence. |

**Score:** 5/5 ROADMAP success criteria verified; 0 behavior-unverified (the one behavior-dependent sub-truth without shipped coverage was independently confirmed correct via direct execution, documented above and in the Anti-Patterns/Findings section).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `sentinel-core/app/services/six_rs/reduce.py` | `reduce_entry()` + net-new `build_schema_block()` | ✓ VERIFIED | Present, substantive, wired (imported by `pipeline_orchestrator`); round-trip test green |
| `sentinel-core/app/services/six_rs/verify.py` | `verify_note()` wrapper + `VERIFY_RETRY_CAP` | ✓ VERIFIED | Delegates 100% to `note_schema.check_note_compliance` (D-02a); named constant `VERIFY_RETRY_CAP = 2` |
| `sentinel-core/app/services/six_rs/reflect.py` | Embedding-first hub lookup + attach | ✓ VERIFIED | First caller of `moc_maintenance.attach_to_hub`; T-46-03 self/ guard present and tested |
| `sentinel-core/app/services/six_rs/reweave.py` | Append-only idempotent dated section | ✓ VERIFIED | `test_reweave_append_idempotent` + schema-preservation + notes/-guard tests all green |
| `sentinel-core/app/services/six_rs/rethink.py` | Observations(+tensions) triage | ✓ VERIFIED | 5-disposition triage, A3-tolerant, KEEP-coercion tested |
| `sentinel-core/app/services/model_resolution.py` | Shared `resolve_structured_model()` | ✓ VERIFIED | Single resolver; `note_classifier` delegates to it (verified by reading both files); no drift |
| `sentinel-core/app/services/pipeline_status_store.py` | Clone of `sweep_status_store` | ✓ VERIFIED | Duck-typed round-trip confirmed by `test_pipeline_status_store.py` |
| `sentinel-core/app/services/inbox.py` (modified) | `retry_count`/`needs_attention` on `PendingEntry` | ✓ VERIFIED | Round-trips through render/parse; backward-compatible default |
| `sentinel-core/app/services/pipeline_orchestrator.py` | `PipelineReport`, `run()`, `start_pipeline()` | ✓ VERIFIED | All four modes implemented; lock-before-read; never-crash-the-loop; D-06 background scheduling |
| `sentinel-core/app/routes/pipeline.py` | `POST /vault/pipeline/start`, `GET /vault/pipeline/status` | ✓ VERIFIED | Admin-gated (imports `_is_admin_route`, no duplicate); 422 on invalid mode; ungated status |
| `sentinel-core/app/main.py` (modified) | Registers `pipeline_router` | ✓ VERIFIED | `from app.routes.pipeline import router as pipeline_router` + `app.include_router(pipeline_router)` confirmed by grep |
| `interfaces/discord/core_gateway.py` (modified) | `call_core_pipeline_start/status` | ✓ VERIFIED | Mirrors `call_core_sweep_*` shape exactly; D-04a blocked-message handling present |
| `interfaces/discord/command_router.py` (modified) | Five-verb dispatch branch | ✓ VERIFIED | `if subcmd in ("ralph","pipeline","reweave","rethink","refactor")`, admin-gated, `refactor`→`rethink` mapping |
| `interfaces/discord/bot.py` (modified) | Dead prompts removed, wrappers wired | ✓ VERIFIED | Five `_SUBCOMMAND_PROMPTS` entries confirmed absent (grep); `tasks`/`next`/`health`/`goals`/`reminders` retained; two new kwargs wired |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `pipeline_orchestrator.run()` | `vault.acquire_sweep_lock()` | Called before any inbox read | ✓ WIRED | `test_concurrent_pipeline_and_sweep_refused` spies on `read_note` and asserts zero calls before the raise |
| `pipeline_orchestrator._run_ralph/_run_pipeline` | `six_rs.reduce.reduce_entry` + `build_schema_block` | Direct import + call | ✓ WIRED | Confirmed by source read + passing tests |
| `pipeline_orchestrator._run_pipeline` | `six_rs.verify.verify_note` | Gates Reflect/Reweave and notes/ retention | ✓ WIRED | Confirmed by source read; pass-path tested in shipped suite; fail-path confirmed by verifier spot-check (see Test Coverage Note) |
| `pipeline_orchestrator` | `six_rs.reflect.find_and_attach_hub` | Embedding-first hub attach | ✓ WIRED | `find_hub_candidate`/`attach_to_hub` reused, no fresh cosine loop (grep-confirmed) |
| `pipeline_orchestrator` | `six_rs.reweave.reweave_note` | Orchestrator drafts `addition_text`, module does the idempotent write | ✓ WIRED | `_draft_reweave_addition` (orchestrator) → `reweave_note` (six_rs) call chain confirmed |
| `pipeline_orchestrator` | `six_rs.rethink.triage_observations` | End-of-run (pipeline mode) / standalone (rethink mode) | ✓ WIRED | `rethink_mock.assert_awaited_once()` in `test_pipeline_mode_full_sequence` |
| `routes/pipeline.py` | `app.routes.note._is_admin_route` | Imported, not duplicated | ✓ WIRED | `from app.routes.note import _is_admin_route` confirmed by source read (T-46-01) |
| `main.py` | `routes/pipeline.router` | `include_router` | ✓ WIRED | Confirmed by grep |
| `command_router.py` | `core_gateway.call_core_pipeline_start/status` | Explicit branch | ✓ WIRED | Confirmed by source read + 18 passing pipeline-specific Discord tests |
| `bot.py` kwargs | `command_router.handle_subcommand` | `call_core_pipeline_start/status` wrappers | ✓ WIRED | Confirmed by grep (`bot.py:577-578`) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Lock acquired strictly before inbox read (Pitfall 8) | `pytest tests/test_pipeline_orchestrator.py -k concurrent -v` | `test_concurrent_pipeline_and_sweep_refused PASSED` | ✓ PASS |
| Reweave idempotency (no duplicate dated section) | `pytest tests/test_six_rs_reweave.py -v` | 3/3 PASSED | ✓ PASS |
| `build_schema_block` round-trips through `check_note_compliance` | `pytest tests/test_six_rs_reduce.py -v` | 4/4 PASSED | ✓ PASS |
| Verify-failure removes draft from `notes/` + requeues with `retry_count+1`, never dropped | Verifier-authored temporary pytest module against real `pipeline_orchestrator.run(mode="pipeline")` with `verify_note` mocked to fail | `notes/` left empty, inbox entry requeued with `retry_count=1` — 2/2 PASSED, then file deleted (not committed) | ✓ PASS (ad hoc, see Test Coverage Note) |
| Verify-failure at `VERIFY_RETRY_CAP` marks `needs_attention`, still never dropped | Same temporary module, second scenario | `notes/` left empty, inbox entry retained with `retry_count=2`, `needs_attention=True` | ✓ PASS (ad hoc, see Test Coverage Note) |
| Full sentinel-core suite green | `cd sentinel-core && .venv/bin/python -m pytest tests/ -q` | `573 passed, 12 skipped, 0 failed` | ✓ PASS |
| Full discord suite green | `cd interfaces/discord && .venv/bin/python -m pytest tests/ -q` | `276 passed, 50 skipped, 0 failed` | ✓ PASS |
| `:refactor`→`rethink` synonym + status verb + non-admin refusal | `pytest tests/test_command_router_module.py -k pipeline -v` (discord) | 13/13 PASSED | ✓ PASS |

### Probe Execution

No `scripts/*/tests/probe-*.sh` probes declared or found for this phase (SKIPPED — no probes applicable; this phase uses pytest as its automated-verification surface, not shell probes).

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|-----------------|--------------|--------|----------|
| PIPE-01 | 46-03 | Zero-friction `:capture`/`:seed` into `inbox/` | ✓ SATISFIED | `inbox.append_entry` regression guard; capture path unaffected |
| PIPE-02 | 46-01,02,04,05,06,07 | `:ralph` batch-processes inbox (Reduce+Reflect), writes real `notes/` with `_schema`/wikilinks/MOC | ✓ SATISFIED | `_run_ralph` + `reduce_entry`/`build_schema_block`/`find_and_attach_hub` chain, tested |
| PIPE-03 | 46-01,06,07 | `:pipeline` runs full 6 Rs sequence | ✓ SATISFIED | `_run_pipeline` drives Reduce→Verify→Reflect→Reweave→(end-of-run)Rethink, tested |
| PIPE-04 | 46-01,02,05,06,07 | `:reweave` backward pass reusing candidate discovery | ✓ SATISFIED | `_run_reweave` + `reweave_note` idempotent append, tested (SemanticRecall substitution documented, see Truth #3) |
| PIPE-05 | 46-01,02,05,06,07 | `:rethink`/`:refactor` triage to actionable disposition | ✓ SATISFIED | `triage_observations`, 5 dispositions, A3-tolerant, tested |
| PIPE-06 | 46-01,03,06,07 | Concurrency guard + status route + Discord poll | ✓ SATISFIED | Shared lock, admin-gated start route, ungated status route, Discord gateway/router, all tested |
| PIPE-07 | 46-01,03,04,06 | `_schema` enforcement only at Verify, never blocking Reduce | ✓ SATISFIED | `verify_note` wraps `check_note_compliance`; Reduce never raises/blocks; orchestrator requeue-not-reject confirmed (see Truth #5 / Test Coverage Note) |

No orphaned requirements — REQUIREMENTS.md's Traceability table maps PIPE-01..07 exclusively to Phase 46, and all 7 IDs appear in at least one plan's `requirements` frontmatter (cross-checked against every `46-0{1..7}-PLAN.md`).

### Anti-Patterns Found

None. Zero `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` markers and zero "not yet implemented"/"coming soon" strings across all 14 phase-46 modified/created files (`six_rs/*.py`, `pipeline_orchestrator.py`, `pipeline_status_store.py`, `model_resolution.py`, `inbox.py`, `routes/pipeline.py`, `main.py`, `core_gateway.py`, `command_router.py`, `bot.py`).

**Notable positive finding:** while building `pipeline_status_store.py`, the phase-46 author discovered a genuine pre-existing bug in `note_sweep_runner.py` (its exception handlers wrote to `get_status()["status"]`, mutating a throwaway dict copy — a no-op) and fixed it in place with a dedicated regression test (commit `e31493a`, `fix(46): persist sweep blocked/error status via patch_sweep_status`), rather than deferring or copying the bug into the new pipeline code. Confirmed via `git show e31493a`.

### Test Coverage Note (WARNING, not a blocker)

`sentinel-core/tests/test_pipeline_orchestrator.py` (the shipped Wave-0 test file, unchanged in shape through Wave 3) contains exactly 3 tests: `test_ralph_mode_reduce_and_reflect`, `test_pipeline_mode_full_sequence` (which mocks `verify_note` to always return `passed: True`), and `test_concurrent_pipeline_and_sweep_refused`. **No shipped test drives `verify_note` to `passed: False` through the orchestrator** — meaning the D-02/PIPE-07 "delete draft from notes/ + requeue with incremented retry, mark needs_attention at the cap" integration path (implemented at `pipeline_orchestrator.py:367-373`) has zero permanent regression coverage, even though the 46-06-PLAN's own must-haves and acceptance criteria explicitly require this behavior and the per-task validation map (`46-VALIDATION.md` row `06-T1`) frames it as integration-tested.

The verifier confirmed the implementation is correct by writing a temporary, non-committed pytest module that drove `pipeline_orchestrator.run(mode="pipeline")` with `verify_note` mocked to fail (both the below-cap requeue case and the at-cap needs_attention case) — both passed against the real, unmocked orchestrator code, then the temporary file was deleted (it is not part of the phase's shipped diff and was never committed). This confirms the behavior works today, but it is not protected against future regression by the phase's own test suite.

**Recommendation:** add a permanent test (e.g. `test_pipeline_verify_failure_deletes_draft_and_requeues` / `test_pipeline_verify_failure_at_cap_marks_needs_attention`) to `tests/test_pipeline_orchestrator.py` in a follow-up commit. This is a WARNING, not a BLOCKER — the phase goal is achieved and the behavior is confirmed correct, but the test suite has a real, actionable gap.

### Human Verification Required

Two items require live infrastructure (real Obsidian vault + live LM Studio/exo model + real Discord wall-clock timing) that FakeVault-based unit tests cannot exercise, per 46-VALIDATION.md's own "Manual-Only Verifications" table:

1. **Live `:ralph`/`:pipeline` vault mutation** — Test: seed `inbox/` with a raw capture, run `:ralph` in Discord. Expected: `notes/{slug}.md` appears with a trailing `_schema` block, claim title, and wikilink; the MOC/hub note is created or updated (appended, never duplicated). Why human: requires live Obsidian REST + LM Studio/exo; not exercised by FakeVault tests.
2. **Live pollable status reporting** — Test: start a pipeline run, poll `:pipeline status` repeatedly. Expected: status transitions idle→running→complete (or blocked/error) with advancing per-phase counts and a final real outcome. Why human: requires live Discord + background-task wall-clock timing.

### Gaps Summary

No blocking gaps. All 7 PIPE-01..07 requirements are accounted for and implemented; all 5 ROADMAP success criteria are substantively satisfied; both shipped test suites are fully green (sentinel-core 573/12/0, discord 276/50/0); no debt markers found; no orphaned requirements. One WARNING-level finding: the Verify-failure requeue/delete path inside `pipeline_orchestrator._run_pipeline` lacks a permanent shipped regression test, even though the verifier confirmed the behavior is correct by direct execution — recommend adding the missing test in a follow-up commit. Two Manual-Only Verification items (live vault mutation, live status polling) require human/live-infra testing per the phase's own validation strategy and are not gaps in the delivered code.

---
*Verified: 2026-07-06T21:58:03Z*
*Verifier: Claude (gsd-verifier)*
