---
quick_id: 260502-1ib
slug: fix-all-issues-found-during-260502-0vr-v
date: 2026-05-02
status: complete
commits:
  - 9fe7c82 fix(core): move litellm context-length detection into clients layer
  - 2a3daa1 fix(core): import fetch_anthropic_models in model_registry
  - 8603c4f fix(core): remove unused date_part in note route
  - 69b88ca style(core): hoist late imports in test_obsidian_client
---

# SUMMARY: Fix all issues found during 260502-0vr verification

## Outcome

All 4 issues from the 260502-0vr verification pass are fixed. Fix count
equals find count. No deferral, no TODOs, no skipped tests.

## Tasks completed

1. **Task 1 — AI-agnostic guardrail violation** (commit `9fe7c82`)
   - Added `ContextLengthError` to `app/services/provider_router.py`.
   - Moved `_CONTEXT_LENGTH_MARKERS` and `_is_context_length_error` from
     `app/services/message_processing.py` into
     `app/clients/litellm_provider.py`, alongside the legitimate
     `from litellm import BadRequestError` import.
   - `LiteLLMProvider.complete()` now translates context-length variants of
     `BadRequestError` to `ContextLengthError`; all other `BadRequestError`s
     re-raise unchanged.
   - `MessageProcessor.process()` catches `ContextLengthError` and maps it
     to `MessageProcessingError(code="context_overflow")` — observable
     end-to-end behavior unchanged (HTTP 422 + `context_overflow` +
     "exceeds model capacity" message preserved).
   - Lockstep test updates (authorized in PLAN.md per CLAUDE.md
     Test-Rewrite Ban): `tests/test_message_processor.py` and
     `tests/test_message.py::test_bad_request_error_returns_422` now raise
     `ContextLengthError` from their fakes/mocks. Assertions on the
     observable contract (HTTP code, `context_overflow` code, message
     content) are unchanged.

2. **Task 2 — F821 missing import** (commit `2a3daa1`)
   - Added `from app.clients.anthropic_registry import fetch_anthropic_models`
     to `app/services/model_registry.py`. Resolves a latent NameError that
     would have fired the first time `_fetch_claude` ran with
     `ANTHROPIC_API_KEY` set.

3. **Task 3 — F841 unused variable** (commit `8603c4f`)
   - Deleted the unused `date_part = sweep_id.split("T")[0]` line in
     `app/routes/note.py`. The `id_part` derivation that follows is the
     sole identifier used downstream.

4. **Task 4 — E402 late imports** (commit `69b88ca`)
   - Hoisted `import unittest.mock`, `import pytest`, and
     `from unittest.mock import AsyncMock` from mid-file (lines 183, 257,
     258) to the top-of-file import block in
     `tests/test_obsidian_client.py`. Deduped the redundant `pytest`
     re-import.

## Lockstep test edits (Task 1)

- `tests/test_message_processor.py::test_litellm_context_length_string_mapped_to_context_overflow`
  — fake AI provider now raises `ContextLengthError`; assertion on
  `MessageProcessingError(code="context_overflow")` unchanged.
- `tests/test_message.py::test_bad_request_error_returns_422` — mocked
  `ai_provider.complete` now raises `ContextLengthError`; assertions on
  HTTP 422 status and `"context"`/`"capacity"` substring in detail
  unchanged.

## Final verification

- `cd sentinel-core && uvx ruff check .` → All checks passed (0 errors)
- `cd sentinel-core && PYTHONPATH=$(pwd)/../shared .venv/bin/pytest -q`
  → 231 passed, 12 skipped (`test_no_vendor_ai_imports_or_hardcoded_models`
  now passes)
- `rg "from litellm" sentinel-core/app/services/` → 0 matches
- `rg "import litellm" sentinel-core/app/services/` → 1 match in
  `app/services/model_selector.py` (in the guardrail's `EXCLUDED_PATHS`)

## Pre-existing issues encountered (out of scope)

- `tests/test_output_scanner.py::test_timeout_fails_open` emits a
  `RuntimeWarning: coroutine 'OutputScanner._classify' was never awaited`.
  Pre-existing; not caused by this task.

## Guardrail compliance

- **Spec-Conflict Guardrail**: Validated end-to-end contract (HTTP 422 +
  `context_overflow` + capacity message) preserved.
- **Test-Rewrite Ban**: Two shipped-feature tests updated under PLAN.md
  pre-authorization; behavioral assertions unchanged.
- **Behavioral-Test-Only**: All edited tests still call `processor.process()`
  (or POST to `/message`) and assert on observable results.
- **AI Deferral Ban**: 4 issues found, 4 fixed. No TODOs, no skips.
