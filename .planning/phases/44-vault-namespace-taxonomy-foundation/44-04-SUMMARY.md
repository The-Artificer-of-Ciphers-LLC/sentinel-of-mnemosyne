---
phase: 44-vault-namespace-taxonomy-foundation
plan: 04
subsystem: recall
tags: [obsidian-vault, self-context, lazy-create, rest-only, recall-module, pytest]

# Dependency graph
requires:
  - phase: 44-vault-namespace-taxonomy-foundation (plan 03)
    provides: RecallConfig.exclude_prefixes as single source of truth for warm-tier exclusion; carrier-namespace allowlist removed
provides:
  - "build_self_stub(path) — pure, token-bounded seeded-stub builder for the four canonical self/ files"
  - "Recall._ensure_self_stub(path) — REST-only read-then-conditionally-write stub-ensure wired at the self-context gather (_hot_self)"
  - "Guaranteed non-empty self-context on every message (VAULT-05): self/identity.md, self/methodology.md, self/goals.md, self/relationships.md self-heal into seeded stubs on first read-miss"
affects: [45-note-quality-schema-graph-analysis, 46-6rs-pipeline-orchestrator, 47-migration-cutover-hardening]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "D-14 lazy-create-if-missing via REST PUT, applied to self/ canonical files (mirrors note_intake.py's INBOX_PATH read-then-conditionally-write and inbox.py's build_initial_inbox pure-builder shape)"
    - "Stub-ensure composed at the call site (Recall._hot_self), never inside the shared read-only read_self_context — keeps that method's graceful-404 contract stable for every other caller"

key-files:
  created: []
  modified:
    - sentinel-core/app/services/recall.py
    - sentinel-core/tests/test_recall.py
    - sentinel-core/tests/test_message.py
    - sentinel-core/tests/test_integration_obsidian_llm.py

key-decisions:
  - "Stub-ensure uses read_note + conditional write_note (not read_self_context) so read_self_context's read-only, graceful-404 contract stays untouched for every other caller and for the two non-canonical self_paths entries"
  - "isinstance(body, str) guard in _ensure_self_stub (not truthiness alone) — a bare/unconfigured AsyncMock test double returns a non-str mock whose .strip() is itself an awaitable, and calling it un-awaited leaked a RuntimeWarning; the guard both fixes the leak and correctly treats any non-str read as 'missing'"
  - "Only the four canonical self/ paths (identity, methodology, goals, relationships) are stub-ensured via an explicit allowlist iterated in _hot_self — ops/reminders.md and self/learning-areas.md (also in RecallConfig.self_paths) are never auto-created"

patterns-established:
  - "Self-context is now guaranteed non-empty on every message once the vault has been read once — several test_message.py fixtures that previously modeled 'no hot tier' scenarios were updated to reflect this as intended, guaranteed behavior (VAULT-05), not a regression to work around"

requirements-completed: [VAULT-01, VAULT-05]

coverage:
  - id: D1
    description: "build_self_stub(path) pure builder returns non-empty, token-bounded seeded content for each of the four canonical self/ paths"
    requirement: "VAULT-01"
    verification:
      - kind: unit
        ref: "tests/test_recall.py#test_build_self_stub_returns_nonempty_token_bounded_content"
        status: pass
    human_judgment: false
  - id: D2
    description: "Stub-ensure creates a canonical self/ file exactly once on read-miss, never overwrites existing content, and never touches the two non-canonical self_paths extras"
    requirement: "VAULT-01"
    verification:
      - kind: unit
        ref: "tests/test_recall.py#test_self_stub_creation_on_miss"
        status: pass
      - kind: unit
        ref: "tests/test_recall.py#test_self_stub_no_overwrite_when_present"
        status: pass
      - kind: unit
        ref: "tests/test_recall.py#test_self_stub_canonical_paths_only"
        status: pass
    human_judgment: false
  - id: D3
    description: "Every message reads the four canonical self/ files and the read never hits a missing file, end-to-end through the production /message path"
    requirement: "VAULT-05"
    verification:
      - kind: integration
        ref: "tests/test_message.py#test_first_message_self_heals_missing_self_files"
        status: pass
      - kind: integration
        ref: "tests/test_message.py#test_second_message_does_not_rewrite_existing_self_files"
        status: pass
    human_judgment: false
  - id: D4
    description: "read_self_context keeps its existing read-only, graceful-404 contract; full suite stays green with no regressions"
    verification:
      - kind: unit
        ref: "full suite: cd sentinel-core && .venv/bin/python -m pytest tests/ -q (473 passed, 12 skipped, 0 warnings)"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-07-06
status: complete
---

# Phase 44 Plan 04: Self/ Stub Auto-Creation Summary

**Recall now self-heals the four canonical `self/` files (identity, methodology, goals, relationships) into minimal seeded stubs on first read-miss via a REST-only read-then-conditionally-write pattern, guaranteeing non-empty hot-tier self-context on every message.**

## Performance

- **Duration:** ~25 min
- **Tasks:** 2/2 completed
- **Files modified:** 4 (1 production, 3 test)

## Accomplishments

- `build_self_stub(path)` — pure, token-bounded, seeded-content builder for the four canonical `self/` files (mirrors `inbox.build_initial_inbox()`'s pure-builder shape)
- `Recall._ensure_self_stub(path)` — composes `read_note` + conditional `write_note` at the `_hot_self` self-context gather; `read_self_context`'s read-only, graceful-404 contract is completely untouched
- `_hot_self` now branches per-path: the four canonical `self/` paths go through the stub-ensure; the two extras (`ops/reminders.md`, `self/learning-areas.md`) keep using the unchanged `read_self_context` read
- Unit test coverage in `test_recall.py`: pure-builder non-emptiness, creation-on-miss (write exactly once), no-overwrite-when-present, canonical-paths-only allowlist enforcement
- Integration test coverage in `test_message.py`: first message against an empty vault self-heals all four canonical files through the production `/message` route; a second message does not re-write them
- Full suite green: 473 passed, 12 skipped, **zero warnings** (baseline was 467 passed / 12 skipped before this plan; net +6 tests: 4 new unit tests in `test_recall.py`, 2 new integration tests in `test_message.py`)

## Task Commits

1. **Task 1: build_self_stub pure builder + stub-ensure wiring at the self-context gather (D-04, D-04a)** - `6b33424` (feat)
2. **Task 2: Message-path integration test — first message self-heals missing self/ files (VAULT-05)** - `5cfd24a` (test)

_Note: TDD flow was followed procedurally (RED tests written and confirmed failing via `ImportError: cannot import name 'build_self_stub'` before implementation), but Task 1's RED and GREEN states were combined into a single commit rather than two separate `test(...)` → `feat(...)` commits — see Deviations._

## Files Created/Modified

- `sentinel-core/app/services/recall.py` — `build_self_stub()`, `_CANONICAL_SELF_STUB_PATHS`, `Recall._ensure_self_stub()`, `_hot_self()` branching
- `sentinel-core/tests/test_recall.py` — 4 new stub-ensure unit tests; 2 existing tests (`test_assemble_returns_self_context`, `test_empty_vault_graceful_degrade`) updated for the new guaranteed-non-empty self-context behavior
- `sentinel-core/tests/test_message.py` — 2 new integration tests; several AsyncMock-backed fixtures and message-count assertions updated to reflect that hot-tier context is now always present (see Deviations)
- `sentinel-core/tests/test_integration_obsidian_llm.py` — mock/assertion updated so the identity-injection test tracks the new `read_note`-based call site for `self/identity.md`

## Decisions Made

- Stub-ensure composes `read_note` + conditional `write_note` directly at the `_hot_self` call site rather than modifying `read_self_context` — keeps the shared read-only contract stable for every other caller (persona read in `message_processing.py`, the two non-canonical `self_paths` extras).
- `_ensure_self_stub` guards with `isinstance(body, str)` rather than bare truthiness — this is both a correctness fix (a non-str read result is unambiguously "no usable content" and should self-heal) and a bug fix for a silent unawaited-coroutine leak that truthiness-only would have hidden (see Deviations).
- The four-path allowlist (`_CANONICAL_SELF_STUB_PATHS`) is iterated explicitly in `_hot_self`, never derived by iterating all of `RecallConfig.self_paths` — this is a structural guarantee (not just documentation) that `ops/reminders.md` and `self/learning-areas.md` can never be auto-created even if `self_paths` is edited later without matching review.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Unawaited-coroutine leak in `_ensure_self_stub`'s missing-body check**
- **Found during:** Task 1, full-suite verification pass (after initial GREEN)
- **Issue:** `if not body or not body.strip():` assumed `body` is always a `str` (true for the real Vault contract), but several `test_message.py` fixtures use a bare/unconfigured `AsyncMock()` vault. Calling `.strip()` on that mock's non-str return value returns another mock whose `.strip()` call is itself an awaitable (`AsyncMockMixin._execute_mock_call`) — never awaited, so Python's GC raised `RuntimeWarning: coroutine ... was never awaited` across 24 test cases. Per project CLAUDE.md, warnings must be root-caused and fixed inline, not waved off.
- **Fix:** Changed the guard to `if not isinstance(body, str) or not body.strip():` so `.strip()` is only ever called on a confirmed `str`. This also corrected the semantics: a non-str read result now correctly triggers self-heal (treated as "missing"), which is more consistent with VAULT-05's guarantee than the previous accidental behavior (silently excluding non-str content from self-context without creating a stub).
- **Files modified:** `sentinel-core/app/services/recall.py`
- **Verification:** `pytest tests/ -q -W error::RuntimeWarning` — 0 warnings, 473 passed
- **Committed in:** `6b33424` (Task 1 commit)

**2. [Rule 1 - Bug] Stale `read_self_context`-based assertion in `test_integration_obsidian_llm.py`**
- **Found during:** Task 1, full-suite verification pass
- **Issue:** `test_obsidian_context_injected_into_llm_prompt` mocked `read_self_context` to return known identity content and asserted `read_self_context.assert_any_call("self/identity.md")`. Since `self/identity.md` is now read via `read_note` + stub-ensure (this plan's change), that call never reaches `read_self_context`, breaking both the content-injection assertion and the call-site assertion. This file is not in the plan's declared `files_modified`, but the break is a direct, unavoidable consequence of Task 1's production code change.
- **Fix:** Configured `mock_obsidian.read_note` with the same path-aware side effect and updated the assertion to `read_note.assert_any_call("self/identity.md")`.
- **Files modified:** `sentinel-core/tests/test_integration_obsidian_llm.py`
- **Verification:** `pytest tests/test_integration_obsidian_llm.py -q` — all pass
- **Committed in:** `6b33424` (Task 1 commit)

**3. [Rule 1 - Bug] Multiple `test_message.py` fixtures/assertions broken by guaranteed non-empty self-context**
- **Found during:** Task 1 full-suite pass, and again after the `isinstance` fix widened self-heal to more fixtures
- **Issue:** Several `test_message.py` fixtures used a blanket `mock.read_note.return_value = "<warm-tier body>"` intended only for the post-RRF warm-tier body read. Since `_ensure_self_stub` now also calls `read_note` for the four canonical self/ paths, that blanket value leaked into self-context, and separately, three `read_note.assert_called_once_with(...)` assertions became too strict (read_note is legitimately called 5 times now: 4 self-heal + 1 warm-tier body read, not once). After the `isinstance` fix, tests using a bare/unconfigured `AsyncMock` (previously silently excluded from self-context by an `isinstance` filter downstream) also began correctly self-healing, breaking four more "no hot tier" message-count assertions (`== 2`).
- **Fix:** Converted 4 blanket `read_note.return_value` assignments to path-aware `side_effect` functions; updated 3 `assert_called_once_with` checks to `assert_any_call` / explicit call-list membership checks that preserve each test's real intent (e.g., "ops/sessions and ops/sweeps paths never reach read_note"); updated 8 message-count/index assertions (`== 2` → `== 4`, `== 4` → `== 6`, and shifted `captured_messages[1]` → `captured_messages[3]` for vault content) across `test_warm_tier_injected_when_results_present`, `test_warm_tier_injected_when_score_meets_threshold`, `test_warm_tier_excludes_ops_session_and_sweep_paths`, `test_warm_tier_injects_full_note_content_not_snippet`, `test_no_injection_when_user_file_missing`, `test_warm_tier_skipped_when_empty`, `test_warm_tier_skipped_when_all_results_below_threshold`, and `test_warm_tier_result_missing_score_defaults_to_negative_infinity`. Added a shared `_SELF_HEAL_STUB_PATHS` / `_filing_writes()` helper so the four `_CapturingFakeVault`-based note-filing tests (`test_substantive_chat_content_filed_as_vault_note`, `test_trivial_content_not_filed`, `test_chat_note_path_passes_warm_tier_exclusion_filter`, `test_observation_topic_chat_note_redirected_to_searchable_path`) filter out self-heal writes before asserting on note-filing destinations, preserving their original narrower intent.
- **Files modified:** `sentinel-core/tests/test_message.py`
- **Verification:** `pytest tests/ -q -W error::RuntimeWarning` — 473 passed, 12 skipped, 0 warnings
- **Committed in:** `5cfd24a` (Task 2 commit, same file scope as Task 2's own new tests)

**4. [Rule 1 - Bug] Two existing `test_recall.py` assertions predated the guaranteed-non-empty behavior**
- **Found during:** Task 1, writing the RED tests
- **Issue:** `test_assemble_returns_self_context` asserted `len(result.self_context) == 3` when only 3 of 6 `self_paths` were seeded; `test_empty_vault_graceful_degrade` asserted `result.self_context == []` for an empty vault. Both predate this plan's intentional change (VAULT-05: self-context is now guaranteed non-empty via stub-ensure).
- **Fix:** Updated both to assert the new, intended counts (5 and 4 respectively) and added assertions that the newly stub-created canonical paths are indeed present and non-empty in the fake vault's backing store.
- **Files modified:** `sentinel-core/tests/test_recall.py`
- **Verification:** `pytest tests/test_recall.py -q` — 56/56 pass
- **Committed in:** `6b33424` (Task 1 commit)

---

**Total deviations:** 4 auto-fixed (all Rule 1 — direct, necessary consequences of this plan's own production change; no scope creep, no architectural changes)
**Impact on plan:** All four fixes were required to keep the full suite green per the plan's own success criterion. None altered the plan's intended production behavior — `recall.py`'s only production edit beyond the plan's literal task description was the `isinstance` guard, which is a correctness/robustness improvement consistent with (not contrary to) the plan's stated intent.

**TDD process note:** Task 1 had `tdd="true"`. RED was followed procedurally — the new tests were written first and confirmed to fail (`ImportError: cannot import name 'build_self_stub'`) before any implementation code was added — but the RED and GREEN states were combined into a single `feat(...)` commit rather than a separate `test(...)` → `feat(...)` commit pair, because the full scope of required fixes (including the `isinstance` bug found only after running the complete suite) wasn't known until after GREEN was reached. This plan's frontmatter is `type: execute` (not `type: tdd`), so the strict plan-level RED/GREEN gate-commit sequencing does not apply as a hard gate here; documented for transparency.

## Issues Encountered

None beyond the deviations documented above — all were discovered and resolved during the same execution pass via the standard verify-fix-reverify loop.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- VAULT-01 (self/ stub auto-creation) and VAULT-05 (guaranteed session-start self/ read) are both closed; this completes the three-space namespace foundation started in plans 44-01/44-02.
- Phase 44 (Vault Namespace + Taxonomy Foundation) is now fully complete — all 4 plans (44-01 through 44-04) executed, 19 requirements (VAULT-01..05 plus prerequisite work) validated.
- Phase 45 (Note-Quality Schema + Graph Analysis) depends on Phase 44 and can now proceed — the taxonomy/namespace foundation it builds on is in place.
- No blockers introduced by this plan.

---
*Phase: 44-vault-namespace-taxonomy-foundation*
*Completed: 2026-07-06*

## Self-Check: PASSED

All claimed files exist on disk (`recall.py`, `test_recall.py`, `test_message.py`, `test_integration_obsidian_llm.py`, this SUMMARY.md) and both claimed commit hashes (`6b33424`, `5cfd24a`) are present in `git log`.
