---
phase: 46-6-rs-pipeline-orchestrator
plan: 04
subsystem: sentinel-core / six_rs pipeline (Reduce + Verify)
tags: [pipeline, reduce, verify, note-quality, structured-completion, PIPE-02, PIPE-07]
dependency-graph:
  requires: ["46-02 (model_resolution.resolve_structured_model)", "46-03 (retry_count / needs_attention on PendingEntry, not directly consumed here)"]
  provides: ["six_rs.reduce.reduce_entry", "six_rs.reduce.build_schema_block", "six_rs.reduce.ReduceResult", "six_rs.verify.verify_note", "six_rs.verify.VERIFY_RETRY_CAP", "six_rs.verify.claim_title_assist"]
  affects: ["46-06 (Wave-3 pipeline_orchestrator — composes notes via build_schema_block, drives requeue loop via verify_note's outcome + VERIFY_RETRY_CAP)"]
tech-stack:
  added: []
  patterns: ["D-05 single-shared model-resolution + structured json_schema completion (note_classifier.classify_note analog)", "Pitfall-6 coerce-to-safe-default (never raise, never drop)", "D-02a reuse-not-reimplement (check_note_compliance)", "T-46-INJECT untrusted-data system-prompt framing (moc_maintenance.propose_hub_slug analog)"]
key-files:
  created:
    - sentinel-core/app/services/six_rs/reduce.py
    - sentinel-core/app/services/six_rs/verify.py
  modified:
    - sentinel-core/tests/test_six_rs_reduce.py (added 2 net-new tests for build_schema_block; the 2 original Wave-0 tests were untouched)
decisions:
  - "claim_title_assist implemented as a pure-Python heuristic (verb-word overlap check), not an LLM call — avoids a third network round-trip per note and check_note_compliance's has_claim_title already does the mandatory structural check; this assist is purely additive, never gates pass/fail on its own."
  - "verify_note performs no vault I/O — it is a pure decision function (passed/requeued/retry_count/needs_attention). The actual requeue-to-inbox/ write and retry-count persistence are left to the Wave-3 orchestrator (46-06), which acts on this function's returned outcome. vault/note_path are accepted as parameters for call-site parity with the orchestrator's eventual signature, matching the frozen Wave-0 RED test contract exactly."
  - "reduce_entry does not mock/override resolve_structured_model in its own tests (matches the frozen Wave-0 test's patch surface, which only patches acompletion_with_profile) — the real resolver runs and gracefully degrades (all its internal network calls are wrapped in try/except) when no LM Studio/exo endpoint is reachable in the test environment. Confirmed fast (<1.2s for all 4 reduce tests) — no hang."
metrics:
  duration: "~45 minutes"
  completed: 2026-07-06
status: complete
---

# Phase 46 Plan 04: 6 Rs Pipeline Orchestrator — Reduce + Verify Summary

One-liner: Reduce turns one raw inbox entry into a `{claim_title, body, schema_type}` draft via a single json_schema-constrained completion that never blocks on bad output, and owns the net-new `build_schema_block()` `_schema` fence constructor; Verify is a pure decision wrapper around the shipped `check_note_compliance` exposing a named `VERIFY_RETRY_CAP`.

## What was built

### `six_rs/reduce.py`

- **`class ReduceResult(BaseModel)`** — `claim_title: str`, `body: str`, `schema_type: str`.
- **`async def reduce_entry(entry_text: str) -> ReduceResult`** — resolves `(model_id, profile, api_base)` via `model_resolution.resolve_structured_model()` (D-05, the single shared resolver), then calls `acompletion_with_profile` with `response_format={"type": "json_schema", "json_schema": _REDUCE_SCHEMA}` and `temperature=0.0`. The captured entry text is placed ONLY in the user-message slot; the system prompt (`_REDUCE_SYSTEM_PROMPT`) explicitly frames it as untrusted DATA ONLY and instructs the model to ignore any embedded directives (T-46-INJECT, mirrors `moc_maintenance.propose_hub_slug`'s framing). Content extraction uses the classifier's `content` OR `reasoning_content` fallback (Qwen3 thinking-mode / LM Studio bug #1773).
  - **Pitfall 6 discipline:** every failure surface (model-resolution exception, completion-call exception, JSON parse failure, non-dict payload, invalid `schema_type`, missing/empty `claim_title`/`body`, or `ReduceResult` validation failure) is caught and coerced to a safe, non-empty fallback result via `_fallback_result()` — `reduce_entry` NEVER raises and NEVER returns `None`/empty. `_fallback_result` derives `claim_title` from the entry's first line (truncated to 120 chars), uses the raw entry text as `body`, and defaults `schema_type="fleeting"`.
  - `reduce_entry` never calls `note_schema.check_note_compliance` — enforcement is reserved for Verify only (Pitfall 6).
- **`def build_schema_block(type: str, status: str, hub: str | None = None) -> str`** — net-new pure constructor (no I/O, no LLM). Renders the inner block via `yaml.safe_dump({"type": ..., "status": ..., "hub": ...})` (hub key omitted entirely when `hub is None`, not merely `null`), wrapped as:
  ```
  ```_schema
  type: permanent
  status: draft
  ```
  ```
  Verified (new tests, see below) to round-trip through `note_schema.parse_schema_block` and satisfy `check_note_compliance`'s `has_schema`/`has_type`. **Callers must append this as the terminal content of the note body** (note_schema's terminal-block rule) — the Wave-3 orchestrator (46-06) is expected to compose `# {claim_title}\n\n{body}\n\n` + `build_schema_block(type=result.schema_type, status="draft")`.

### `six_rs/verify.py`

- **`VERIFY_RETRY_CAP = 2`** — named module-level constant (D-02b), importable by the Wave-3 orchestrator.
- **`async def verify_note(vault, *, note_path, body, filename_slug, retry_count=0) -> dict`** — thin wrapper: calls `note_schema.check_note_compliance(body, filename_slug)` (D-02a — the ONLY compliance check, never re-implemented) and derives `passed = not compliance["failures"]`. Returns:
  - `passed: bool`
  - `requeued: bool` — `True` iff failed AND `retry_count < VERIFY_RETRY_CAP`
  - `retry_count: int` — unchanged on pass or at-cap; incremented by 1 otherwise
  - `needs_attention: bool` — `True` iff failed AND `retry_count >= VERIFY_RETRY_CAP`
  - `compliance: dict` — the raw `check_note_compliance` result (extra field, not required by tests but useful to the orchestrator for the outcome report)
  - **No vault I/O.** `vault`/`note_path` are accepted for signature parity with the frozen Wave-0 test contract and the eventual orchestrator call site; the actual requeue-to-`inbox/` write + retry-count persistence is the Wave-3 orchestrator's responsibility (per plan text: "the requeue/increment logic itself lives in the Wave-3 orchestrator").
- **`async def claim_title_assist(title: str) -> bool`** — OPTIONAL, implemented as a **pure-Python heuristic** (documented discretion, D-02a): returns `True` when the title has ≥3 words and at least one word overlaps a small hand-picked set of claim-like verbs/copulas (`is`, `governs`, `requires`, `enables`, ...). Never calls an LLM, never raises, purely additive on top of `check_note_compliance`'s mandatory `has_claim_title` structural check — not wired into `verify_note`'s pass/fail decision (kept separate per the plan's "adding only" framing).

## Tests

- `tests/test_six_rs_reduce.py` — the 2 frozen Wave-0 RED tests (`test_reduce_extracts_claim_and_schema_draft`, `test_reduce_malformed_completion_still_filed_as_draft`) are now GREEN, unmodified.
- Added 2 new tests (RED-then-GREEN, TDD) to the same file for the net-new `build_schema_block`:
  - `test_build_schema_block_round_trips_through_check_note_compliance` — proves an H1 + wikilink + `build_schema_block(type="permanent", status="draft")` note satisfies `check_note_compliance`'s `has_schema`/`has_type` with no corresponding failure strings.
  - `test_build_schema_block_hub_kwarg_included_only_when_provided` — proves the `hub` kwarg round-trips into the parsed dict when given, and is entirely absent (not `None`) when omitted, in both cases with `has_type` still True.
- `tests/test_six_rs_verify.py` — the 2 frozen Wave-0 RED tests (`test_verify_failure_requeues_with_retry_cap`, `test_verify_reuses_check_note_compliance`) are now GREEN, unmodified.

## Test outcome (sentinel-core suite)

```
557 passed, 12 skipped, 10 failed in 14.19s
```

- All 6 target tests (2+2 reduce, 2 verify) flipped GREEN as required.
- The 10 remaining failures are ALL pre-existing Wave-0 RED scaffolds explicitly out of this plan's scope (46-05 / Wave-3 territory), confirmed to be exactly the expected set and nothing else:
  - `tests/test_six_rs_reflect.py` (2) — 46-05
  - `tests/test_six_rs_reweave.py` (1) — 46-05
  - `tests/test_six_rs_rethink.py` (2) — 46-05
  - `tests/test_pipeline_orchestrator.py` (3) — Wave 3 (46-06)
  - `tests/test_pipeline_routes.py` (2) — Wave 3 (46-06)
- No regressions in the pre-existing (non-six_rs) baseline — every other test in the suite passed.

## API shapes downstream consumers (Wave-3 orchestrator, 46-06) must match

- `from app.services.six_rs.reduce import reduce_entry, build_schema_block, ReduceResult`
  - `await reduce_entry(entry_text: str) -> ReduceResult` (`.claim_title`, `.body`, `.schema_type` — always populated, never raises)
  - `build_schema_block(type: str, status: str, hub: str | None = None) -> str` — synchronous, pure; append as the LAST content of a composed note body.
- `from app.services.six_rs.verify import verify_note, VERIFY_RETRY_CAP, claim_title_assist`
  - `await verify_note(vault, *, note_path: str, body: str, filename_slug: str, retry_count: int = 0) -> dict` with keys `passed`, `requeued`, `retry_count`, `needs_attention`, `compliance`.
  - The orchestrator is responsible for: on `requeued=True`, writing `body` to `inbox/{filename_slug}.md` (or similar) with the returned `retry_count` persisted, and removing/not-landing the note in `notes/`; on `needs_attention=True`, leaving the note in `inbox/` and marking it `needs-attention` in the outcome report (this plan does not perform that I/O — it only computes the decision).
  - `VERIFY_RETRY_CAP == 2`.

## Deviations from Plan

### Auto-fixed / discretionary choices (no Rule 1-3 fixes were needed — no bugs found)

**1. [TDD completeness] Added 2 tests for `build_schema_block` not present in the Wave-0 RED scaffold.**
- **Found during:** Task 1 planning — the plan's own acceptance criteria required a "ROUND-TRIP PROOF" and hub-kwarg behavior for `build_schema_block`, but `tests/test_six_rs_reduce.py` (frozen from 46-01) only pinned `reduce_entry`'s two tests, not this net-new builder.
- **Action:** Followed the task's `tdd="true"` attribute properly for the net-new surface: wrote 2 failing tests first (confirmed RED via `ModuleNotFoundError`), committed as `test(46-04): ...`, then implemented `reduce.py` to make all 4 reduce tests (2 original + 2 new) pass in the same `feat(46-04)` commit.
- **Files modified:** `sentinel-core/tests/test_six_rs_reduce.py`
- **Commit:** `484fcc7`

None other — plan executed as written for the rest.

## Threat Flags

No new surface beyond what the plan's own `<threat_model>` already covers (T-46-INJECT, T-46-BADOUT, T-46-RETRY) — all three mitigations are implemented as designed: untrusted-data system-prompt framing (T-46-INJECT), `response_format=json_schema` + `ReduceResult.model_validate` + safe-fallback-on-failure (T-46-BADOUT), and the named `VERIFY_RETRY_CAP` bound (T-46-RETRY).

## Self-Check: PASSED

- `sentinel-core/app/services/six_rs/reduce.py` — FOUND
- `sentinel-core/app/services/six_rs/verify.py` — FOUND
- `sentinel-core/tests/test_six_rs_reduce.py` (modified) — FOUND
- Commit `484fcc7` (test: RED build_schema_block tests) — FOUND in `git log`
- Commit `70876fc` (feat: reduce.py) — FOUND in `git log`
- Commit `1aae882` (feat: verify.py) — FOUND in `git log`
- `sentinel-core` suite: 557 passed / 12 skipped / 10 failed (all 10 pre-existing, out-of-scope Wave-0 RED scaffolds) — confirmed via direct pytest run.
