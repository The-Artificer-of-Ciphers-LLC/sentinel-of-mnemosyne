---
phase: 46-6-rs-pipeline-orchestrator
plan: 02
subsystem: infra
tags: [python, refactor, model-resolution, litellm, lm-studio, note-classifier]

# Dependency graph
requires:
  - phase: 46-6-rs-pipeline-orchestrator
    provides: "Wave 0 RED test scaffolds (46-01) pinning PIPE-02..07 six_rs API contracts; this plan is pure infrastructure underneath them, not a consumer of any RED test"
provides:
  - "app/services/model_resolution.py exporting resolve_structured_model() — the single public LM Studio model-resolution + profile-lookup helper"
  - "note_classifier._resolve_model_for_classification refactored to a thin delegating wrapper (zero behavior change)"
affects: [46-03-six-rs-reweave-verify-rethink, 46-04-pipeline-orchestrator, 46-06-orchestrator-wiring]
# Reduce/Reflect (whichever Wave-2 plan lands them) and every other six_rs
# structured-completion stage import resolve_structured_model from here.

# Tech tracking
tech-stack:
  added: []
  patterns: ["Dependency-injected resolver: resolve_structured_model() accepts get_loaded_models/select_model/get_profile as keyword overrides (defaulting to the real model_selector/model_profiles implementations) so callers can substitute fakes without the shared module needing its own patch surface — lets note_classifier's thin wrapper forward its own (possibly mock.patch'd) bindings through to the single implementation"]

key-files:
  created:
    - sentinel-core/app/services/model_resolution.py
  modified:
    - sentinel-core/app/services/note_classifier.py

key-decisions:
  - "note_classifier._resolve_model_for_classification was kept as a 5-line delegating wrapper (not a bare alias `_resolve_model_for_classification = resolve_structured_model`) specifically so existing mock.patch(\"app.services.note_classifier.get_loaded_models\"/\"select_model\"/\"get_profile\") targets in test_note_classifier.py continue to take effect — a bare alias would have executed model_resolution.py's own bound imports, silently ignoring those patches."
  - "resolve_structured_model() accepts get_loaded_models/select_model/get_profile as keyword-only overrides defaulting to the real model_selector/model_profiles functions, rather than being parameterless as the plan's artifact bullet literally showed — this is what makes the dependency-injection/patch-forwarding decision above possible while still satisfying 'importable, async, returns a 3-tuple, callable with no required args'."
  - "settings is NOT threaded through as a parameter — model_resolution.py imports the same app.config.settings singleton object note_classifier used, so monkeypatch.setattr(settings, ...) in tests still applies regardless of which module holds the reference."
  - "Removed the now-unused settings/ensure_litellm_prefix/strip_litellm_prefix imports from note_classifier.py (their only call sites moved to model_resolution.py) rather than leaving dead imports."

patterns-established:
  - "Single-implementation LM Studio model-resolution seam: any new six_rs/* structured-completion stage imports resolve_structured_model directly from app.services.model_resolution rather than duplicating the resolution logic (RESEARCH A2 mitigation, T-46-DRIFT)."

requirements-completed: [PIPE-02, PIPE-04, PIPE-05]

coverage:
  - id: D1
    description: "model_resolution.py exports a public async resolve_structured_model() returning (prefixed_model_id, profile, api_base), importable and callable"
    requirement: "PIPE-02"
    verification:
      - kind: unit
        ref: "PYTHONPATH=.:../shared python -c \"from app.services.model_resolution import resolve_structured_model; print(callable(resolve_structured_model))\" -> True"
        status: pass
    human_judgment: false
  - id: D2
    description: "note_classifier delegates to the shared resolver with zero behavior change — all pre-existing classifier tests (including the exo-model-notfound-502 regression test) pass unchanged"
    requirement: "PIPE-04"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_note_classifier.py -q (13 passed)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Exactly one implementation of the model-resolution logic exists in the tree; note_classifier's function is a 5-line delegating wrapper, not a re-implementation; full baseline suite (550 passed / 12 skipped) stays intact with no new regressions"
    requirement: "PIPE-05"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/ -q (550 passed / 12 skipped / 15 pre-existing Wave-2+ RED, byte-identical to pre-plan baseline)"
        status: pass
    human_judgment: false

duration: ~20min
completed: 2026-07-06
status: complete
---

# Phase 46 Plan 02: Shared Model-Resolution Helper Summary

**Promoted `note_classifier._resolve_model_for_classification`'s LM Studio model-resolution + profile-lookup logic into a new public `app/services/model_resolution.resolve_structured_model()` helper — the single implementation every six_rs stage will import, with note_classifier refactored to a thin delegating wrapper and zero behavior change.**

## Performance

- **Duration:** ~20 min
- **Tasks:** 2
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments

- Created `sentinel-core/app/services/model_resolution.py` housing `resolve_structured_model()` — a byte-for-byte move of the classifier's api_base normalization, `get_loaded_models` call, `select_model("structured", ...)` call, litellm prefix ensure/strip, `get_profile` call, and every graceful `except`-warn fallback, with a module docstring naming it the single resolver shared by `note_classifier` and every `six_rs/*` structured completion.
- Made `get_loaded_models`/`select_model`/`get_profile` keyword-only overrides on `resolve_structured_model()` (defaulting to the real `model_selector`/`model_profiles` implementations) so callers can inject fakes — this is what lets `note_classifier`'s wrapper forward its own potentially-`mock.patch`'d bindings through to the one shared implementation.
- Refactored `note_classifier._resolve_model_for_classification` to a 5-line delegating wrapper that calls `resolve_structured_model(get_loaded_models=get_loaded_models, select_model=select_model, get_profile=get_profile)`, preserving the historical patch target name and forwarding the module's current bindings — not a bare alias, which would have silently broken existing `mock.patch("app.services.note_classifier.get_loaded_models")`-style tests.
- Removed the now-dead `settings`/`ensure_litellm_prefix`/`strip_litellm_prefix` imports from `note_classifier.py` (their only call sites moved to `model_resolution.py`).
- Verified zero behavior change: all 13 `test_note_classifier.py` tests pass unchanged, including the `test_resolve_model_for_classification_except_falls_back_to_settings_model_name` exo-model-notfound-502 regression test (which patches `get_loaded_models`/`select_model`/`get_profile` by note_classifier's module-qualified name and asserts the except-handler fallback behavior).
- Confirmed the full `sentinel-core` suite stays at the exact pre-plan baseline: 550 passed / 12 skipped, with the same 15 Wave-2+ `six_rs`/pipeline-orchestrator RED tests still red (expected — those belong to later waves) and zero new failures introduced.

## Task Commits

Each task was committed atomically:

1. **Task 1: extract public model-resolution helper** - `2f1a874` (feat)
2. **Task 2: refactor note_classifier to consume the shared helper (zero behavior change)** - `7391143` (refactor)

## Files Created/Modified

- `sentinel-core/app/services/model_resolution.py` - New module; `resolve_structured_model()` — the single public LM Studio model-resolution + profile-lookup helper, dependency-injectable via keyword overrides
- `sentinel-core/app/services/note_classifier.py` - `_resolve_model_for_classification` refactored to a thin delegating wrapper; dead `settings`/`ensure_litellm_prefix`/`strip_litellm_prefix` imports removed

## Decisions Made

- Kept `_resolve_model_for_classification` as a named wrapper function (not a bare alias) specifically to preserve the `mock.patch("app.services.note_classifier.get_loaded_models"/"select_model"/"get_profile")` patch surface used by `test_note_classifier.py` — a bare alias to `resolve_structured_model` would have executed `model_resolution.py`'s own bound imports, silently ignoring those patches and breaking the exo-model-notfound-502 regression test.
- Added keyword-only `get_loaded_models`/`select_model`/`get_profile` override parameters to `resolve_structured_model()` (defaulting to the real implementations) rather than a strictly parameterless signature — this dependency-injection seam is what makes the wrapper-forwarding decision above possible while keeping exactly one implementation of the resolution logic.
- Left `settings` un-parameterized — `model_resolution.py` imports the same `app.config.settings` singleton, so `monkeypatch.setattr(settings, ...)` in tests applies transparently regardless of which module holds the reference.

## Deviations from Plan

None - plan executed exactly as written. The plan's artifact bullet showed `resolve_structured_model()` as parameterless; adding the keyword-only dependency-injection overrides is a strict superset (all defaults preserve parameterless-callable behavior) needed to satisfy the plan's own acceptance criteria ("Any prior `mock.patch(...)` in the suite still resolves") — not a deviation from the plan's intent, just the concrete mechanism chosen for it.

## Issues Encountered

None. The plan's literal verify command (`python -c "..."`) initially failed with `ModuleNotFoundError: No module named 'sentinel_shared'` when run as a bare script — this is pre-existing project structure (pytest's `pythonpath = [".", "../shared"]` in `pyproject.toml` isn't applied to standalone `python -c` invocations) and reproduces identically against the pre-existing `note_classifier.py`, confirming it's an environment-invocation detail, not a defect introduced by this plan. Re-ran with `PYTHONPATH=".:../shared"` and `SENTINEL_API_KEY` set (matching `tests/conftest.py`'s own env setup) and the verify command passed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `app.services.model_resolution.resolve_structured_model()` is the stable public import target Wave 2's `six_rs/reduce.py`, `six_rs/reflect.py`, `six_rs/reweave.py`, `six_rs/rethink.py`, and Verify's optional claim-title assist should all use — call it with no arguments for the real implementation, or pass `get_loaded_models=`/`select_model=`/`get_profile=` overrides in tests.
- Signature: `async def resolve_structured_model(*, task_kind: str = "structured", get_loaded_models=..., select_model=..., get_profile=...) -> tuple[str, object | None, str | None]` returning `(prefixed_model_id, profile, api_base)`.
- No blockers. Full suite green at 550 passed / 12 skipped (pre-existing baseline, byte-identical) + the same 15 pre-existing Wave-2+ RED tests, exactly matching this plan's `<verification>` block.

---
*Phase: 46-6-rs-pipeline-orchestrator*
*Completed: 2026-07-06*

## Self-Check: PASSED

- FOUND: sentinel-core/app/services/model_resolution.py
- FOUND: .planning/phases/46-6-rs-pipeline-orchestrator/46-02-SUMMARY.md
- FOUND: 2f1a874 (Task 1 commit)
- FOUND: 7391143 (Task 2 commit)
- FOUND: 5abb9f9 (SUMMARY commit)
