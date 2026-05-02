---
quick_id: 260502-1ib
slug: fix-all-issues-found-during-260502-0vr-v
date: 2026-05-02
status: planned
---

# PLAN: Fix all issues found during 260502-0vr verification

## Description

Verification of quick task `260502-0vr` surfaced four distinct issues in `sentinel-core/`. Per CLAUDE.md "Fix Everything You Find" rule, fix count must equal find count: 4 issues → 4 fixes, no deferral. Issue 1 is a real guardrail violation (vendor SDK leaking into `app/services/`) that predates the 0vr refactor but became visible because `message_processing.py` is now the only message-domain service file. Issues 2–4 are mechanical lint/latent-bug fixes.

## Issues

1. **AI-agnostic guardrail violation** — `sentinel-core/app/services/message_processing.py:11` imports `litellm.BadRequestError` directly. Vendor SDK imports must live in `app/clients/`. Push detection logic into `app/clients/litellm_provider.py` and surface a typed `ContextLengthError` from `app/services/provider_router.py`.
2. **F821 undefined name** — `sentinel-core/app/services/model_registry.py:141` calls `fetch_anthropic_models` without importing it. Add `from app.clients.anthropic_registry import fetch_anthropic_models`.
3. **F841 unused variable** — `sentinel-core/app/routes/note.py:294` assigns `date_part` but never uses it. Delete the line and its explanatory comment.
4. **E402 module-level imports not at top of file** — `sentinel-core/tests/test_obsidian_client.py` lines 183, 257, 258 import mid-file. Hoist to top-of-file import block; dedupe.

## Files modified

**Edited:**
- `sentinel-core/app/services/message_processing.py`
- `sentinel-core/app/services/provider_router.py`
- `sentinel-core/app/clients/litellm_provider.py`
- `sentinel-core/app/services/model_registry.py`
- `sentinel-core/app/routes/note.py`
- `sentinel-core/tests/test_obsidian_client.py`
- `sentinel-core/tests/test_message_processor.py` (lockstep update for Issue 1)

**Created:** none.
**Deleted:** none.

## Required reading (executor)

- `sentinel-core/app/services/message_processing.py` (full file)
- `sentinel-core/app/clients/litellm_provider.py` (full file)
- `sentinel-core/app/services/provider_router.py` (full file)
- `sentinel-core/app/services/model_registry.py` lines 1–50, 125–150
- `sentinel-core/app/clients/anthropic_registry.py` (full file)
- `sentinel-core/app/routes/note.py` lines 285–310
- `sentinel-core/tests/test_obsidian_client.py` lines 1–15, 175–260
- `sentinel-core/tests/test_ai_agnostic_guardrail.py` (full file — understand pass/fail criteria exactly)
- `sentinel-core/tests/test_message_processor.py` (locate the LiteLLM context-length test)
- `docs/adr/0001-sentinel-persona-source.md`, `CONTEXT.md` (domain language)
- `CLAUDE.md` — Spec-Conflict Guardrail, Test-Rewrite Ban, Behavioral-Test-Only, AI Deferral Ban, Fix Everything You Find

## Tasks

### Task 1 — Fix AI-agnostic guardrail violation (Issue 1)

**Files:** `app/services/provider_router.py`, `app/clients/litellm_provider.py`, `app/services/message_processing.py`, `tests/test_message_processor.py`

**Action:**
1. In `app/services/provider_router.py`, add a new exception class alongside `ProviderUnavailableError`:
   ```python
   class ContextLengthError(Exception):
       """Raised when a provider rejects a completion because the prompt+context exceeds model capacity."""
   ```
2. In `app/clients/litellm_provider.py`:
   - Move the `_CONTEXT_LENGTH_MARKERS` tuple and `_is_context_length_error` helper out of `app/services/message_processing.py` and into this file as private module-level (`_CONTEXT_LENGTH_MARKERS`, `_is_context_length_error`).
   - Import `litellm.BadRequestError` here (vendor SDK is allowed in `app/clients/`).
   - Inside `LiteLLMProvider.complete()`'s exception handling, catch `BadRequestError`. If `_is_context_length_error(exc)` matches, `raise ContextLengthError("Message plus context exceeds model capacity. Try a shorter message.") from exc`. Otherwise re-raise the original `BadRequestError` so existing `provider_misconfigured` mapping in `message_processing.py` still triggers.
3. In `app/services/message_processing.py`:
   - Remove `from litellm import BadRequestError as LiteLLMBadRequestError`.
   - Remove `_CONTEXT_LENGTH_MARKERS` and `_is_context_length_error`.
   - Import `ContextLengthError` from `app.services.provider_router`.
   - Replace the `except LiteLLMBadRequestError` branch with `except ContextLengthError as exc: raise MessageProcessingError("context_overflow", str(exc)) from exc`.
   - Leave the catch-all `except Exception` branch (mapping to `provider_misconfigured`) intact.
4. In `tests/test_message_processor.py`, locate the LiteLLM context-length test. Update the fake provider to raise `ContextLengthError` instead of `LiteLLMBadRequestError`. Assertions on `MessageProcessingError(code="context_overflow")` and the user-facing message remain unchanged — the contract being protected ("MessageProcessor maps context-length signals to context_overflow") is preserved; only the upstream exception type changed. Document this lockstep update in the commit body.

**Spec-conflict note:** observable end-to-end behavior (HTTP 422 + `context_overflow` code + "exceeds model capacity" message) is preserved. This is a refactor of the propagation path, not a behavior change. The lockstep test edit is authorized per CLAUDE.md Test-Rewrite Ban (operator consent given by this plan; record in commit body).

**Verify:**
- `cd sentinel-core && uvx ruff check app/services/message_processing.py app/services/provider_router.py app/clients/litellm_provider.py` → clean
- `cd sentinel-core && PYTHONPATH=$(pwd)/../shared .venv/bin/pytest -q tests/test_message_processor.py tests/test_ai_agnostic_guardrail.py` → pass
- `rg "from litellm" sentinel-core/app/services/` → 0 matches

**Done:** vendor SDK no longer imported in `app/services/`; guardrail test passes; context-overflow → 422 contract preserved.

**Commit:** `fix(core): move litellm context-length detection into clients layer`

---

### Task 2 — Fix F821 undefined `fetch_anthropic_models` (Issue 2)

**File:** `sentinel-core/app/services/model_registry.py`

**Action:** Add `from app.clients.anthropic_registry import fetch_anthropic_models` to the imports section near lines 21–24, alongside the other `app.clients.*` imports. This resolves a latent NameError that would fire whenever `_fetch_claude` runs with `ANTHROPIC_API_KEY` set.

**Verify:**
- `cd sentinel-core && uvx ruff check app/services/model_registry.py` → no F821
- `cd sentinel-core && python -c "from app.services.model_registry import _fetch_claude"` → no error

**Done:** F821 cleared; `_fetch_claude` callable without NameError.

**Commit:** `fix(core): import fetch_anthropic_models in model_registry`

---

### Task 3 — Delete unused `date_part` (Issue 3)

**File:** `sentinel-core/app/routes/note.py`

**Action:** Delete line 294 (`date_part = sweep_id.split("T")[0]`) and the explanatory comment immediately preceding/following it. Confirm `id_part` on line 296 remains the sole identifier used downstream — do not touch `id_part`.

**Verify:**
- `cd sentinel-core && uvx ruff check app/routes/note.py` → no F841
- `cd sentinel-core && PYTHONPATH=$(pwd)/../shared .venv/bin/pytest -q tests/ -k "note"` → pass

**Done:** F841 cleared; sweep behavior unchanged.

**Commit:** `fix(core): remove unused date_part in note route`

---

### Task 4 — Hoist late imports in test_obsidian_client.py (Issue 4)

**File:** `sentinel-core/tests/test_obsidian_client.py`

**Action:** Move the three module-level imports at lines 183, 257, 258 to the top-of-file import block (around lines 1–5). Specifically:
- `import unittest.mock` (line 183)
- `import pytest` (line 257)
- `from unittest.mock import AsyncMock` (line 258)

If `pytest` or `unittest.mock` are already imported at the top, dedupe — do not double-import. Remove the section-divider comments that previously announced them mid-file (they have no structural meaning once the imports move).

**Verify:**
- `cd sentinel-core && uvx ruff check tests/test_obsidian_client.py` → no E402
- `cd sentinel-core && PYTHONPATH=$(pwd)/../shared .venv/bin/pytest -q tests/test_obsidian_client.py` → pass

**Done:** E402 ×3 cleared; tests still pass.

**Commit:** `style(core): hoist late imports in test_obsidian_client`

## Verification (whole task)

Run from `sentinel-core/`:

- `uvx ruff check .` → **0 errors** (clears Issues 2, 3, 4 plus any incidentals)
- `PYTHONPATH=$(pwd)/../shared .venv/bin/pytest -q` → **all pass**, including:
  - `tests/test_ai_agnostic_guardrail.py::test_no_vendor_ai_imports_or_hardcoded_models` (was failing pre-task, must pass post-task)
  - `tests/test_message_processor.py` LiteLLM context-length test (lockstep-updated, must pass)
  - Expected count rises to 231 passed (from 230 with 1 failing) — verify the +1 corresponds to the previously-failing guardrail test now passing.
- `rg "from litellm" sentinel-core/app/services/` → **0 matches**
- `rg "import litellm" sentinel-core/app/services/` → **0 matches**

## Guardrail call-outs

- **Spec-Conflict Guardrail (CLAUDE.md):** Issue 1 refactors the exception propagation path for context-length errors. Validated v0.x behavior is "context-overflow request returns HTTP 422 with `context_overflow` code and a clear message". This contract is preserved end-to-end. The change is purely internal (where the marker check runs and which exception type carries the signal). No deviation from PROJECT.md or REQUIREMENTS.md validated items.
- **Test-Rewrite Ban (CLAUDE.md):** Task 1 includes a lockstep edit to a `test_message_processor.py` test that protects shipped behavior. The edit is authorized by this plan as part of the locked design (operator-approved scope). The assertions on `MessageProcessingError(code="context_overflow")` and the user-facing message remain unchanged — only the upstream exception type the fake provider raises changes. Record this authorization in the Task 1 commit body.
- **Behavioral-Test-Only (CLAUDE.md):** the guardrail test in `test_ai_agnostic_guardrail.py` is a source-grep test, but it is a *structural* check (no vendor SDK in `app/services/`), not a behavioral assertion about a function — that's a legitimate use of source-inspection and is not in scope to rewrite.
- **AI Deferral Ban (CLAUDE.md):** all 4 issues are fixed in this task. No TODOs, no `# noqa`, no `# type: ignore`, no skipped tests. If any task surfaces a blocker, STOP and surface to operator — do not partial-ship.

## Constraints

- Commit directly to `main`. No feature branches, no PRs.
- One atomic commit per task (4 commits total).
- Tasks are independent except Task 1's lockstep test edit, which must land in the same commit as the production-code change.
- Planner does not execute. This PLAN.md is the executor's contract.
