---
phase: 46-6-rs-pipeline-orchestrator
plan: 05
subsystem: sentinel-core / six_rs pipeline (Reflect + Reweave + Rethink)
tags: [pipeline, reflect, reweave, rethink, moc, hub-attach, append-only, triage, PIPE-02, PIPE-04, PIPE-05]

# Dependency graph
requires:
  - phase: 46-6-rs-pipeline-orchestrator
    provides: "46-02 model_resolution.resolve_structured_model (shared LM Studio resolver); 46-01 Wave-0 RED scaffolds pinning the reflect/reweave/rethink API contracts; Phase 45 moc_maintenance.find_hub_candidate/attach_to_hub/propose_hub_slug/create_or_update_hub + note_schema.split_schema_block (reused verbatim, never re-implemented)"
provides:
  - "six_rs.reflect.find_and_attach_hub — embedding-first hub lookup + attach, first caller of moc_maintenance.attach_to_hub (D-07)"
  - "six_rs.reweave.reweave_note + REWEAVE_SECTION_PREFIX — append-only idempotent dated-section write (D-01)"
  - "six_rs.rethink.triage_observations — observations(+optional tensions) disposition triage (PIPE-05, A3)"
affects: ["46-06 (Wave-3 pipeline_orchestrator — composes each stage's call site: passes note_vector/index/active_model to Reflect, drafts addition_text via its own completion then calls Reweave, reads ops/observations for Rethink)"]

tech-stack:
  added: []
  patterns:
    - "D-07 embedding-first hub lookup with notes/-prefix filtering as the T-46-03 exclusion mechanism (hub_paths derived by filtering index keys to notes/-prefixed paths BEFORE calling find_hub_candidate, not via a post-hoc check)"
    - "D-01 append-only idempotent write mirroring moc_maintenance.attach_to_hub's read -> split_schema_block -> merge -> single write_note shape, dedupe by a dated marker string test"
    - "Rethink's addition_text/completion drafting is caller-supplied, not stage-internal — reweave_note itself performs zero LLM calls; it is a pure append-mechanics module (see Decisions Made below for why this diverges from the plan's literal artifact bullet)"

key-files:
  created:
    - sentinel-core/app/services/six_rs/reflect.py
    - sentinel-core/app/services/six_rs/reweave.py
    - sentinel-core/app/services/six_rs/rethink.py
  modified:
    - sentinel-core/tests/test_six_rs_reflect.py (added 1 net-new test for the D-07 LLM-naming fallback path; the 2 original Wave-0 tests were untouched)
    - sentinel-core/tests/test_six_rs_reweave.py (added 2 net-new tests: trailing-_schema-block preservation, T-46-03 notes/-only guard; the 1 original Wave-0 test was untouched)
    - sentinel-core/tests/test_six_rs_rethink.py (added 1 net-new test for malformed-completion-coerces-to-KEEP; the 2 original Wave-0 tests were untouched)

key-decisions:
  - "hub_paths is derived by filtering index keys to the notes/ prefix (excluding the member note itself), not passed in by the caller as a separate hub_paths kwarg — the frozen Wave-0 test signature (find_and_attach_hub(vault, *, note_path, note_vector, index, active_model)) has no hub_paths/member_slug/completion_fn-required parameters, so reflect.py derives both member_slug (from note_path's filename stem) and hub_paths (from index-key prefix filtering) internally. This is what makes the notes/-prefix filter double as the T-46-03 exclusion mechanism: a self/ path can never enter hub_paths in the first place, so it can never be scored, let alone selected."
  - "reweave_note performs ZERO LLM calls — it accepts a pre-drafted addition_text string and owns only the append-only, idempotent WRITE mechanics (read -> split_schema_block -> dedupe-by-marker check -> merge -> single write_note). This differs from the plan's literal artifact bullet (\"draft a BOUNDED section body via one schema-constrained completion\"), because the frozen Wave-0 RED test (test_reweave_append_idempotent) calls reweave_note(vault, *, target_path, addition_text, date) directly with a literal addition_text string and asserts no completion_fn/LLM mocking is needed — the actual, executable contract places drafting responsibility on the caller (the Wave-3 orchestrator), mirroring how moc_maintenance.attach_to_hub itself never decides WHAT to attach, only HOW. Per the plan's own Wave-0 allowance (\"the implementing wave may need to adjust these test bodies/signatures to match the final API, as long as observable behavior is preserved\"), this plan followed the frozen test contract rather than the plan's illustrative bullet, since the test is the executable ground truth."
  - "reweave_note raises ValueError (not a silent no-op or False return) when target_path is outside notes/ (T-46-03) — a caller passing a self/ or ops/ path is a programming-contract violation, not a routine outcome the orchestrator should silently swallow; this mirrors reflect's fail-loud-on-guard-violation posture rather than reweave's fail-quiet idempotency-noop posture (which is reserved for the legitimate already-applied case)."
  - "rethink.triage_observations self-discovers ops/observations/ and ops/tensions/ via vault.list_under (no separate path arguments) — matching the frozen Wave-0 test contract exactly and PIPE-05/A3's framing that tensions is optionally-empty input the function discovers itself, not a required caller-supplied argument."
  - "All three stages added one TDD-completeness test beyond the frozen Wave-0 RED scaffold, following the 46-04 precedent: reflect's D-07 LLM-naming fallback path, reweave's trailing-_schema-block preservation + T-46-03 notes/-only guard, and rethink's malformed-completion-coerces-to-KEEP-without-aborting-the-batch. Each was written RED-first, committed as a separate test(46-05) commit, then the implementation commit (feat(46-05)) turned the whole file GREEN."

patterns-established:
  - "T-46-03 self/ exclusion is enforced as a pre-scoring filter (hub_paths construction), not a post-hoc check on the winning candidate — cheaper and structurally impossible to bypass, since an excluded path never enters the candidate set find_hub_candidate scores."

requirements-completed: [PIPE-02, PIPE-04, PIPE-05]

coverage:
  - id: D1
    description: "find_and_attach_hub is the first caller of moc_maintenance.attach_to_hub; embedding-first via find_hub_candidate (no fresh cosine loop, confirmed by grep); LLM-naming fallback (propose_hub_slug + create_or_update_hub) fires when nothing clears the floor"
    requirement: "PIPE-02"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_six_rs_reflect.py -q (3 passed)"
        status: pass
    human_judgment: false
  - id: D2
    description: "T-46-03: a self/ path with an identical embedding to the query is never selected as a hub-attach target and is never mutated"
    requirement: "PIPE-02"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_six_rs_reflect.py::test_reflect_no_wikilink_from_notes_into_self"
        status: pass
    human_judgment: false
  - id: D3
    description: "reweave_note appends a bounded ## Reweave — {date} section append-only and idempotently (D-01): a second identical call is a byte-identical no-op, existing prose survives, and the trailing _schema block is preserved and stays terminal"
    requirement: "PIPE-04"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_six_rs_reweave.py -q (3 passed)"
        status: pass
    human_judgment: false
  - id: D4
    description: "reweave_note restricted to notes/ (T-46-03) — raises ValueError on any other prefix, leaving the target note untouched"
    requirement: "PIPE-04"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_six_rs_reweave.py::test_reweave_rejects_target_outside_notes"
        status: pass
    human_judgment: false
  - id: D5
    description: "triage_observations assigns one of PROMOTE/IMPLEMENT/METHODOLOGY/ARCHIVE/KEEP per item, tolerates an absent ops/tensions/ dir key entirely (A3), and coerces a malformed per-item completion to KEEP without aborting the batch (sibling item still gets its real disposition)"
    requirement: "PIPE-05"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_six_rs_rethink.py -q (3 passed)"
        status: pass
    human_judgment: false
  - id: D6
    description: "sentinel-core full suite: 550-baseline stays green, reduce/verify (46-04) stay green, all 5 frozen Wave-0 reflect/reweave/rethink tests plus 4 net-new TDD-completeness tests flip GREEN; only Wave-3 (46-06) test_pipeline_orchestrator.py (3) + test_pipeline_routes.py (2) remain RED as expected"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/ -q (566 passed, 12 skipped, 5 failed — all 5 failures are pre-existing Wave-3 RED scaffolds out of this plan's scope)"
        status: pass
    human_judgment: false

duration: ~50min
completed: 2026-07-06
status: complete
---

# Phase 46 Plan 05: 6 Rs Pipeline Orchestrator — Reflect + Reweave + Rethink Summary

**Reflect is the first caller of the Phase-45 `moc_maintenance.attach_to_hub`, doing an embedding-first hub match (reusing `find_hub_candidate` verbatim, no fresh cosine loop) with a `notes/`-prefix filter that structurally excludes `self/` before any scoring happens (T-46-03); Reweave appends a bounded, idempotent dated section ahead of the trailing `_schema` block via a pure append-mechanics write (D-01, zero LLM calls of its own); Rethink triages `ops/observations/` (+ optionally-empty `ops/tensions/`) into one of five dispositions per item via a single schema-constrained completion, coercing any malformed result to `KEEP` without aborting the batch.**

## What was built

### `six_rs/reflect.py`

- **`async def find_and_attach_hub(vault, *, note_path, note_vector, index, active_model, completion_fn=None) -> str | None`**
  - Derives `member_slug` from `note_path`'s filename stem and `hub_paths` by filtering `index` keys to the `notes/` prefix (excluding `note_path` itself) — this filter is BOTH the D-07 candidate-restriction mechanism AND the T-46-03 exclusion guard: a `self/` (or `ops/`) path can never enter `hub_paths`, so it can never be scored by `find_hub_candidate`, let alone selected.
  - Calls `moc_maintenance.find_hub_candidate(note_vector=..., hub_paths=..., index=..., active_model=...)` — reused verbatim, confirmed by grep that no fresh cosine implementation exists in the module.
  - On a match: `attach_to_hub(vault, hub_path, member_slug)` (idempotent, Phase-45 machinery) and returns the hub path.
  - On no match: falls back to `propose_hub_slug(member_texts=[note_body], completion_fn=fn)` then `create_or_update_hub(vault, concept_slug=..., member_slug=..., completion_fn=fn)` — LLM naming only as the fallback (D-07). `completion_fn` defaults to a small internal wrapper that resolves a real model via `model_resolution.resolve_structured_model()` and calls `acompletion_with_profile`; callers (tests, the future orchestrator) may inject their own.
  - A defense-in-depth `startswith(notes/)` re-check guards the winning `hub_path` even though `hub_paths` is already notes/-scoped, per the plan's explicit instruction to "assert this boundary in the module."

### `six_rs/reweave.py`

- **`REWEAVE_SECTION_PREFIX = "## Reweave — "`**
- **`async def reweave_note(vault, *, target_path, addition_text, date=None) -> bool`**
  - Raises `ValueError` immediately if `target_path` is not under `notes/` (T-46-03) — the target note is left completely untouched in that case (no read, no write).
  - Reads the full body, `split_schema_block`s it into `(pre_block_body, trailing_block)`.
  - Computes the dated marker `f"{REWEAVE_SECTION_PREFIX}{date}"` (`date` defaults to today's UTC date). If the marker is already present in `pre_block_body`, returns `False` WITHOUT writing — byte-identical idempotent no-op (D-01).
  - Otherwise appends `\n\n{marker}\n\n{addition_text}\n` to the pre-block body, then re-appends `trailing_block` UNCHANGED so it stays the terminal content of the file (mirrors `attach_to_hub`'s exact merge shape), and performs a single `write_note` (never `vault.patch_append`). Returns `True`.
  - **Owns zero LLM calls.** `addition_text` is supplied by the caller — the frozen Wave-0 RED test (`test_reweave_append_idempotent`) calls `reweave_note` with a literal string and mocks no completion function, so drafting the section body via an LLM is the Wave-3 orchestrator's responsibility, not this module's (see Decisions Made for the rationale — this is a deliberate divergence from the plan's illustrative artifact bullet, following the plan's own "frozen test is ground truth" allowance).

### `six_rs/rethink.py`

- **`async def triage_observations(vault) -> list[dict]`**
  - Self-discovers items via `vault.list_under("ops/observations")` and `vault.list_under("ops/tensions")` (builds full paths as `f"{dir}/{filename}"`) — no separate path arguments, matching the frozen Wave-0 signature.
  - `ops/tensions/` absence (key not present in `FakeVault.dirs` at all, degrading to `[]` via `list_under`'s `dict.get(prefix, [])` default) never raises or blocks observations-only triage (A3).
  - Per item: one schema-constrained completion (`_RETHINK_SCHEMA`, `response_format={"type": "json_schema", ...}`) via `acompletion_with_profile`, model resolved through `model_resolution.resolve_structured_model()`. Item text (the note body) is placed ONLY in the user-message slot; the system prompt explicitly frames it as untrusted DATA ONLY (T-46-INJECT, mirrors `propose_hub_slug`).
  - Returns `[{"path": ..., "disposition": ..., "reasoning": ...}, ...]` — `disposition` is always one of `PROMOTE`/`IMPLEMENT`/`METHODOLOGY`/`ARCHIVE`/`KEEP`. Any exception (resolution failure, completion-call failure, JSON parse failure, unknown/missing disposition value) is caught locally per item and coerced to `KEEP` — never propagates, never aborts the batch, sibling items are triaged independently.

## Tests

- `tests/test_six_rs_reflect.py` — the 2 frozen Wave-0 RED tests (`test_reflect_embedding_first_hub_match`, `test_reflect_no_wikilink_from_notes_into_self`) are now GREEN, unmodified. Added 1 new TDD test: `test_reflect_fallback_creates_hub_when_no_candidate_clears_floor` (proves the D-07 `propose_hub_slug` → `create_or_update_hub` fallback fires and is wired with the correct `concept_slug`/`member_slug`).
- `tests/test_six_rs_reweave.py` — the 1 frozen Wave-0 RED test (`test_reweave_append_idempotent`) is now GREEN, unmodified. Added 2 new TDD tests: `test_reweave_preserves_trailing_schema_block` (the dated section lands BEFORE the trailing `_schema` block, which stays terminal) and `test_reweave_rejects_target_outside_notes` (T-46-03 guard raises `ValueError`, target note is left byte-identical).
- `tests/test_six_rs_rethink.py` — the 2 frozen Wave-0 RED tests (`test_rethink_triage_dispositions`, `test_rethink_tolerates_absent_tensions_dir`) are now GREEN, unmodified. Added 1 new TDD test: `test_rethink_coerces_malformed_completion_to_keep` (a two-item batch where one completion is malformed JSON; that item coerces to `KEEP` while its well-formed sibling still gets `PROMOTE`).

## Test outcome (sentinel-core suite)

```
566 passed, 12 skipped, 5 failed in 14.05s
```

- All 9 target tests (3 reflect, 3 reweave, 3 rethink) flipped GREEN as required.
- The 5 remaining failures are ALL pre-existing Wave-0 RED scaffolds explicitly out of this plan's scope (Wave 3 / 46-06 territory), confirmed to be exactly the expected set and nothing else:
  - `tests/test_pipeline_orchestrator.py` (3) — Wave 3 (46-06)
  - `tests/test_pipeline_routes.py` (2) — Wave 3 (46-06)
- No regressions: the 550-test pre-existing baseline stays green, and 46-04's `reduce`/`verify` GREEN tests stay GREEN (confirmed via the full-suite run above — no new failures anywhere outside the expected Wave-3 set).
- `--collect-only` reports 583 tests collected with zero collection errors.

## API shapes downstream consumers (Wave-3 orchestrator, 46-06) must match

- `from app.services.six_rs.reflect import find_and_attach_hub`
  - `await find_and_attach_hub(vault, *, note_path: str, note_vector, index: dict, active_model: str, completion_fn=None) -> str | None` — always returns the hub path touched (never returns `None` in practice, since the fallback path always creates/merges a hub); `note_vector` must be the freshly-embedded single-note vector (on-demand embed-on-Reduce per RESEARCH Open Question 1, resolved in 46-06's ralph branch).
- `from app.services.six_rs.reweave import reweave_note, REWEAVE_SECTION_PREFIX`
  - `await reweave_note(vault, *, target_path: str, addition_text: str, date: str | None = None) -> bool` — `True` when a section was appended, `False` on an idempotent no-op. **The orchestrator must draft `addition_text` itself** (via its own schema-constrained completion call, following the same pattern as `reduce.py`/`rethink.py`) before calling this function — `reweave_note` performs no LLM calls. Raises `ValueError` if `target_path` is outside `notes/`.
- `from app.services.six_rs.rethink import triage_observations`
  - `await triage_observations(vault) -> list[dict]` — each dict has `path`, `disposition` (one of the 5 enum values), `reasoning`. No separate observations/tensions path arguments — the function self-discovers both directories via `vault.list_under`.

## Deviations from Plan

### Auto-fixed / discretionary choices (Rule 1-3 style, no architectural changes)

**1. [Frozen-test-is-ground-truth] `find_and_attach_hub`'s signature omits `member_slug`, `hub_paths`, and a required `completion_fn` — all derived/defaulted internally instead.**
- **Found during:** Task 1 read-first — the plan's artifact bullet showed `find_and_attach_hub(vault, *, member_slug, note_vector, hub_paths, index, active_model, completion_fn=None)`, but the frozen Wave-0 `test_six_rs_reflect.py` (committed in 46-01, not touched by this plan) calls `find_and_attach_hub(vault, note_path=..., note_vector=..., index=..., active_model=...)` with no `member_slug`/`hub_paths`/`completion_fn` kwargs at all.
- **Action:** Implemented to match the actual, executable frozen test contract (`note_path` instead of `member_slug` + `hub_paths` as separate params — both are derived internally from `note_path`/`index`), per the plan's own explicit allowance that Wave-0 API shapes are "best-guess contracts" and implementers "may need to adjust... to match the final signatures chosen, as long as the observable behavior each test name describes is preserved." All plan-mandated observable behaviors (embedding-first match, D-07 fallback, T-46-03 exclusion) are preserved.
- **Files affected:** `sentinel-core/app/services/six_rs/reflect.py`
- **Commit:** `671add9`

**2. [Frozen-test-is-ground-truth] `reweave_note` performs zero LLM calls; drafting is the caller's responsibility.**
- **Found during:** Task 2 read-first — the plan's action text asked for "draft a BOUNDED section body via one schema-constrained completion," but the frozen Wave-0 `test_reweave_append_idempotent` calls `reweave_note(vault, *, target_path, addition_text, date)` with a literal pre-drafted string and mocks no `acompletion_with_profile`/`completion_fn` at all.
- **Action:** Implemented `reweave_note` as a pure append-mechanics function (idempotent read → merge → write, T-46-03 guard) that accepts a pre-drafted `addition_text`. This mirrors how `moc_maintenance.attach_to_hub` itself never decides WHAT text to attach — only HOW to write it idempotently. The Wave-3 orchestrator is responsible for drafting `addition_text` via its own schema-constrained completion (same pattern as `reduce_entry`/`rethink._triage_one`) before calling `reweave_note`. Documented explicitly in "API shapes downstream consumers must match" above so 46-06 wires this correctly.
- **Files affected:** `sentinel-core/app/services/six_rs/reweave.py`
- **Commit:** `e9ec567`

**3. [TDD completeness] Added 1 (reflect) + 2 (reweave) + 1 (rethink) tests beyond the frozen Wave-0 RED scaffolds.**
- **Found during:** Each task's own acceptance criteria required behavior (D-07 fallback path, trailing-`_schema`-block preservation, T-46-03 notes/-only guard on reweave, malformed-completion-coerces-to-KEEP-without-aborting-batch) not exercised by any frozen Wave-0 test.
- **Action:** Followed each task's `tdd="true"` attribute for the net-new surface: wrote failing tests first (confirmed RED via `ModuleNotFoundError`), committed each as a separate `test(46-05)` commit, then implemented each module to make the full file (frozen + net-new) pass in the matching `feat(46-05)` commit.
- **Files affected:** `test_six_rs_reflect.py`, `test_six_rs_reweave.py`, `test_six_rs_rethink.py`
- **Commits:** `4d19ea4` (reflect test), `989fff1` (reweave test), `ea72f4a` (rethink test)

None other — plan executed as written for the rest (Phase-45 machinery reuse, model resolution via the shared helper, T-46-INJECT untrusted-data framing).

## Threat Flags

No new surface beyond what the plan's own `<threat_model>` already covers (T-46-03, T-46-INJECT, T-46-CORRUPT) — all three mitigations are implemented as designed:
- **T-46-03:** hub-path pre-scoring filter (reflect) + `ValueError` guard on non-`notes/` targets (reweave) — both proven by dedicated tests.
- **T-46-INJECT:** item/member text placed only in the user-message slot in `reflect.py` (via `propose_hub_slug`'s existing framing) and `rethink.py`'s own system prompt; never in a system-prompt directive slot.
- **T-46-CORRUPT:** `reweave_note`'s `split_schema_block` → merge → re-append-trailing-block-unchanged → single `write_note` shape, proven by `test_reweave_preserves_trailing_schema_block`.

## Self-Check: PASSED

- `sentinel-core/app/services/six_rs/reflect.py` — FOUND
- `sentinel-core/app/services/six_rs/reweave.py` — FOUND
- `sentinel-core/app/services/six_rs/rethink.py` — FOUND
- `sentinel-core/tests/test_six_rs_reflect.py` (modified) — FOUND
- `sentinel-core/tests/test_six_rs_reweave.py` (modified) — FOUND
- `sentinel-core/tests/test_six_rs_rethink.py` (modified) — FOUND
- Commit `4d19ea4` (test: reflect fallback RED) — FOUND in `git log`
- Commit `671add9` (feat: reflect.py) — FOUND in `git log`
- Commit `989fff1` (test: reweave RED) — FOUND in `git log`
- Commit `e9ec567` (feat: reweave.py) — FOUND in `git log`
- Commit `ea72f4a` (test: rethink RED) — FOUND in `git log`
- Commit `cdc8053` (feat: rethink.py) — FOUND in `git log`
- `sentinel-core` suite: 566 passed / 12 skipped / 5 failed (all 5 pre-existing, out-of-scope Wave-3 RED scaffolds) — confirmed via direct pytest run.
