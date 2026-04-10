---
phase: 04-ai-provider-multi-provider-support-retry-logic-fallback
plan: "02"
subsystem: sentinel-core
tags: [ai-provider, litellm, tenacity, retry, timeout, protocol, tdd]
dependency_graph:
  requires:
    - sentinel-core/pyproject.toml — litellm, tenacity runtime deps (Plan 01)
    - sentinel-core/app/config.py — all provider Settings fields (Plan 01)
  provides:
    - sentinel-core/app/clients/base.py — AIProvider Protocol
    - sentinel-core/app/clients/litellm_provider.py — LiteLLMProvider (primary impl)
    - sentinel-core/app/clients/ollama_provider.py — OllamaProvider stub
    - sentinel-core/app/clients/llamacpp_provider.py — LlamaCppProvider stub
    - sentinel-core/tests/test_litellm_provider.py — 9 TDD tests all passing
  affects:
    - sentinel-core/app/main.py — updated to use LiteLLMProvider instead of LMStudioClient
tech_stack:
  added:
    - litellm.acompletion() — unified AI backend call via openai/ prefix for LM Studio
    - tenacity @retry — 3 attempts, wait_exponential(multiplier=1, min=1, max=4), reraise=True
  patterns:
    - AIProvider Protocol — structural typing via typing.Protocol
    - tenacity @retry on async method — retry decorator applied directly to complete()
    - timeout=30.0 kwarg on every acompletion() call (PROV-03 hard ceiling)
    - Retryable exceptions tuple defined as module-level constant (_RETRYABLE)
key_files:
  created:
    - sentinel-core/app/clients/base.py
    - sentinel-core/app/clients/litellm_provider.py
    - sentinel-core/app/clients/ollama_provider.py
    - sentinel-core/app/clients/llamacpp_provider.py
    - sentinel-core/tests/test_litellm_provider.py
  modified:
    - sentinel-core/app/main.py — LMStudioClient → LiteLLMProvider, get_context_window → get_context_window_from_lmstudio
  deleted:
    - sentinel-core/app/clients/lmstudio.py
    - sentinel-core/tests/test_lmstudio_client.py
decisions:
  - "LiteLLMProvider uses openai/ prefix for LM Studio — matches LiteLLM's OpenAI-compatible provider routing"
  - "get_context_window_from_lmstudio retained in litellm_provider.py — startup check needs LM Studio /api/v0 endpoint, not litellm"
  - "main.py lm_client updated to LiteLLMProvider even though message route currently uses pi_adapter — keeps app state coherent for Plan 03 provider routing"
  - "_RETRYABLE defined as module-level tuple so tenacity retry_if_exception_type receives a stable reference (not a closure)"
metrics:
  duration: "~25 min"
  completed: 2026-04-10
  tasks_completed: 2
  files_changed: 7
---

# Phase 04 Plan 02: AIProvider Protocol and LiteLLMProvider Summary

AIProvider Protocol defined, LiteLLMProvider implemented with tenacity retry (3 attempts, exp backoff 1-4s) and hard 30s timeout per call (PROV-03), lmstudio.py deleted and replaced — 9 TDD tests all pass.

## What Was Built

### Task 1: AIProvider Protocol, LiteLLMProvider, TDD tests (commit 7d1592d)

Created `sentinel-core/app/clients/base.py` — the AIProvider Protocol with a single `async complete(messages)` method. Structural typing via `typing.Protocol` means any class with a matching `complete()` signature satisfies the contract without explicit inheritance.

Created `sentinel-core/app/clients/litellm_provider.py` — `LiteLLMProvider` wrapping `litellm.acompletion()`:

| Property | Value |
|----------|-------|
| Retry attempts | 3 |
| Backoff | exponential 1s → 2s → 4s |
| Retryable | RateLimitError, ServiceUnavailableError, httpx.ConnectError, httpx.TimeoutException |
| Fatal (no retry) | AuthenticationError (401), BadRequestError (422) |
| Hard timeout | 30.0 seconds per call (PROV-03) |

`get_context_window_from_lmstudio()` moved from the deleted `lmstudio.py` — LM Studio startup check still works via `/api/v0/models/{model}`.

Deleted `sentinel-core/app/clients/lmstudio.py` — `LMStudioClient` fully replaced by `LiteLLMProvider`. `sentinel-core/tests/test_lmstudio_client.py` deleted — superseded by `test_litellm_provider.py`.

Updated `sentinel-core/app/main.py` to import `LiteLLMProvider` and `get_context_window_from_lmstudio`, and instantiate `LiteLLMProvider(model_string="openai/{model_name}", api_base=lmstudio_base_url, api_key="lmstudio")` instead of `LMStudioClient`.

Created `sentinel-core/tests/test_litellm_provider.py` with 9 TDD tests — written before implementation (RED), all pass after implementation (GREEN):

| Test | Assertion |
|------|-----------|
| test_complete_returns_text_on_success | Returns assistant content on success |
| test_retries_on_rate_limit_error | call_count == 3 on RateLimitError |
| test_retries_on_service_unavailable | call_count == 3 on ServiceUnavailableError |
| test_retries_on_connect_error | call_count == 3 on httpx.ConnectError |
| test_no_retry_on_authentication_error | call_count == 1 on AuthenticationError |
| test_no_retry_on_bad_request_error | call_count == 1 on BadRequestError |
| test_retries_on_timeout_exception | call_count == 3 on httpx.TimeoutException (PROV-03) |
| test_get_context_window_from_lmstudio_returns_value | Returns 32768 from mock response |
| test_get_context_window_from_lmstudio_returns_4096_on_error | Returns 4096 on ConnectError |

### Task 2: OllamaProvider and LlamaCppProvider stubs (commit 6c8914d)

Created `sentinel-core/app/clients/ollama_provider.py` — `OllamaProvider` stub with `NotImplementedError` on `complete()`. Message includes actionable setup instructions: nvidia-container-toolkit, GPU device reservations, `OLLAMA_HOST=0.0.0.0`.

Created `sentinel-core/app/clients/llamacpp_provider.py` — `LlamaCppProvider` stub with `NotImplementedError` on `complete()`. Message includes llama-server invocation and a note to prefer OllamaProvider.

Both stubs log their configuration at `INFO` level in `__init__` for observability.

## Verification Results

All plan verification checks passed:

1. `ls sentinel-core/app/clients/` — shows base.py, litellm_provider.py, ollama_provider.py, llamacpp_provider.py, obsidian.py, pi_adapter.py — NO lmstudio.py
2. `ls sentinel-core/tests/` — shows test_litellm_provider.py — NO test_lmstudio_client.py
3. `pytest tests/test_litellm_provider.py -v` — 9 passed
4. `grep -r "from app.clients.lmstudio"` — returns nothing
5. `grep "stop_after_attempt(3)" litellm_provider.py` — matches
6. `grep '"timeout": 30.0' litellm_provider.py` — matches (PROV-03)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed broken import in app/main.py after deleting lmstudio.py**
- **Found during:** Task 1, after deleting lmstudio.py
- **Issue:** `app/main.py` imported `LMStudioClient` and `get_context_window` from the now-deleted `app.clients.lmstudio`. Left unfixed, the app would fail to start with `ModuleNotFoundError`.
- **Fix:** Updated `main.py` to import `LiteLLMProvider` and `get_context_window_from_lmstudio` from `app.clients.litellm_provider`. Updated `app.state.lm_client` instantiation to use `LiteLLMProvider(model_string="openai/{model_name}", api_base=lmstudio_base_url, api_key="lmstudio")`.
- **Files modified:** `sentinel-core/app/main.py`
- **Commit:** 7d1592d

### Environment Setup (not a deviation — prerequisite)

The test environment had no Python venv. Created `.venv` via `uv venv` and installed all project dependencies (`uv pip install httpx litellm tenacity anthropic pydantic-settings pytest pytest-asyncio`) before running tests. The `.venv/` directory is gitignored and not committed.

## Threat Mitigations Applied

| Threat ID | Mitigation |
|-----------|-----------|
| T-04-04 (api_key logging) | `logger.debug` logs only `model_string`, never `api_key`. api_key passed only in kwargs to litellm, not logged anywhere. |
| T-04-05 (DoS via retry loop) | Max 3 attempts, 1-4s backoff (max wall time ~37s including retries). Hard 30s timeout per call. |

## Known Stubs

`OllamaProvider.complete()` and `LlamaCppProvider.complete()` raise `NotImplementedError`. This is intentional — stub-only scope for Phase 4 per plan. Full implementations are deferred to when GPU workstation infrastructure is available. Neither is wired as the active provider (`ai_provider` defaults to `"lmstudio"`).

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| sentinel-core/app/clients/base.py | FOUND |
| sentinel-core/app/clients/litellm_provider.py | FOUND |
| sentinel-core/app/clients/ollama_provider.py | FOUND |
| sentinel-core/app/clients/llamacpp_provider.py | FOUND |
| sentinel-core/tests/test_litellm_provider.py | FOUND |
| sentinel-core/app/clients/lmstudio.py | CONFIRMED DELETED |
| sentinel-core/tests/test_lmstudio_client.py | CONFIRMED DELETED |
| commit 7d1592d | FOUND |
| commit 6c8914d | FOUND |
| 9 tests passing | CONFIRMED |
