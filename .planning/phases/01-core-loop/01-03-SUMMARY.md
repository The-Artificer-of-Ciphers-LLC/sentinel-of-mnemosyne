---
phase: 01-core-loop
plan: "03"
subsystem: sentinel-core
tags: [fastapi, python, async, httpx, tiktoken, pydantic-settings, token-guard, lmstudio, wave-2]
dependency_graph:
  requires:
    - 01-01 (Python project scaffold, test stubs, pyproject.toml)
    - 01-02 (Pi harness Fastify bridge — POST /prompt endpoint)
  provides:
    - FastAPI app with asynccontextmanager lifespan (CORE-03)
    - LM Studio async HTTP client with get_context_window and 4096 fallback (CORE-04)
    - Token guard service: count_tokens, check_token_limit, TokenLimitError (CORE-05)
    - pydantic-settings Settings singleton with required SENTINEL_API_KEY (CORE-06 partial)
    - POST /message: token guard → Pi harness → ResponseEnvelope
    - GET /health: always 200
    - 11 tests green, zero skips
  affects:
    - Phase 3: Discord/iMessage interfaces call POST /message
    - Phase 4: LM Studio auth (T-1-03-03 accepted risk)
tech_stack:
  added:
    - pydantic-settings>=2.13.0 (Settings singleton, env var loading)
    - tiktoken (cl100k_base encoding for token counting)
    - httpx.MockTransport (test isolation pattern)
    - ASGITransport (FastAPI integration testing without real server)
  patterns:
    - asynccontextmanager lifespan (not deprecated @app.on_event)
    - Single shared httpx.AsyncClient across lifespan (connection pooling)
    - app.state for shared resource injection (http_client, context_window, pi_adapter, lm_client, settings)
    - PiAdapterClient._client replacement pattern for test mock injection
    - context_window=5 in 422 test to trigger token guard without hitting Pydantic max_length=32_000
key_files:
  created:
    - sentinel-core/app/__init__.py
    - sentinel-core/app/config.py
    - sentinel-core/app/models.py
    - sentinel-core/app/services/__init__.py
    - sentinel-core/app/services/token_guard.py
    - sentinel-core/app/clients/__init__.py
    - sentinel-core/app/clients/lmstudio.py
    - sentinel-core/app/clients/pi_adapter.py
    - sentinel-core/app/routes/__init__.py
    - sentinel-core/app/routes/message.py
    - sentinel-core/app/main.py
  modified:
    - sentinel-core/tests/conftest.py (added SENTINEL_API_KEY env var setup)
    - sentinel-core/tests/test_token_guard.py (replaced 3 stubs with 5 real tests)
    - sentinel-core/tests/test_lmstudio_client.py (replaced 3 stubs with 3 real tests)
    - sentinel-core/tests/test_message.py (replaced 3 stubs with 3 real tests)
decisions:
  - "test_message.py uses context_window=5 (not 10,000 words) for 422 test — avoids Pydantic max_length=32_000 rejection before token guard fires"
  - "PiAdapterClient._client injected directly in tests (not via lifespan mock) — simpler than monkeypatching lifespan"
  - "ASGITransport triggers FastAPI lifespan; state set immediately after client context entry before request"
metrics:
  duration: "12 minutes"
  completed: "2026-04-10"
  tasks_completed: 2
  tasks_total: 2
  files_created: 11
  files_modified: 4
---

# Phase 01 Plan 03: Sentinel Core Implementation Summary

FastAPI app with asynccontextmanager lifespan, pydantic-settings config, token guard using tiktoken cl100k_base, LM Studio async client with 4096 fallback, Pi adapter HTTP client, POST /message + GET /health routes, and 11 tests green (zero skips, zero failures).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Config, models, token guard, LM Studio client, Pi adapter | ea9a83b | app/__init__.py, app/config.py, app/models.py, app/services/token_guard.py, app/clients/lmstudio.py, app/clients/pi_adapter.py, tests/conftest.py, tests/test_token_guard.py, tests/test_lmstudio_client.py |
| 2 | FastAPI app, POST /message, GET /health, test_message.py | 2580047 | app/main.py, app/routes/message.py, app/routes/__init__.py, tests/test_message.py |

## What Was Built

### Configuration (CORE-06 partial)

`sentinel-core/app/config.py` defines a `Settings(BaseSettings)` class loaded from environment variables via pydantic-settings. `sentinel_api_key: str` has no default — startup fails fast if the variable is missing. All other settings have sensible defaults (`lmstudio_base_url`, `pi_harness_url`, `model_name`, `log_level`). The `settings` singleton is imported by `main.py` lifespan and attached to `app.state.settings` for route access.

### Pydantic v2 models (CORE-03)

`MessageEnvelope`: `content` (required, min_length=1, max_length=32_000) and `user_id` (default "default", max_length=64). `ResponseEnvelope`: `content` and `model` strings. Both use Pydantic v2 syntax (`Field(...)`, no `class Config`).

### Token guard (CORE-05)

`count_tokens(messages)` follows the OpenAI cookbook formula: 3 overhead per message + token count of each value via tiktoken `cl100k_base` + 3 reply priming tokens. `check_token_limit(messages, context_window)` raises `TokenLimitError` (with `.count` and `.limit` attributes) if count exceeds limit. 5 tests cover: oversized rejection, normal pass, overhead counting, raise-on-exceeded, pass-for-normal.

### LM Studio client (CORE-04)

`get_context_window(client, base_url, model_name)` strips `/v1` suffix using `removesuffix("/v1")` to build the `/api/v0/models/{model_name}` URL, returns `max_context_length` from JSON, returns `4096` on any exception. `LMStudioClient.complete(messages)` posts to `/v1/chat/completions` and returns `choices[0].message.content`. 3 tests cover: completion return, context window fetch (8192), and 4096 fallback on unreachable.

### Pi adapter client

`PiAdapterClient.send_prompt(message)` posts `{"message": message}` to Pi harness `POST /prompt` with a 35-second timeout (5s margin over Pi's internal 30s). Raises `httpx.ConnectError` or `httpx.HTTPStatusError` — handled in the message route as 503.

### FastAPI app and routes (CORE-03)

`main.py` uses `@asynccontextmanager` lifespan (not deprecated `@app.on_event`). Lifespan creates one shared `httpx.AsyncClient(timeout=30.0)`, fetches context window from LM Studio (logs warning on 4096 fallback), creates `LMStudioClient` and `PiAdapterClient`, and attaches all to `app.state`. Shutdown closes the httpx client via `await http_client.aclose()`.

`routes/message.py` implements `POST /message`: builds messages array, calls `check_token_limit` (422 on `TokenLimitError`), calls `pi_adapter.send_prompt` (503 on `ConnectError`/`RemoteProtocolError` or 503/504 `HTTPStatusError`), returns `ResponseEnvelope(content=..., model=settings.model_name)`.

`GET /health` always returns `{"status": "ok"}` without checking downstream dependencies.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] 422 test used oversized message that hit Pydantic max_length before token guard**

- **Found during:** Task 2, first test run
- **Issue:** Plan's `test_post_message_422_when_message_too_long` used `"word " * 10_000` (50,000 chars), which exceeds `MessageEnvelope.content` `max_length=32_000`. FastAPI returned Pydantic validation error (list detail) before token guard ran.
- **Fix:** Changed test to use `"hello world"` with `context_window=5` — any real message costs more than 5 tokens, so token guard fires correctly.
- **Files modified:** `sentinel-core/tests/test_message.py`
- **Commit:** 2580047

**2. [Rule 1 - Bug] ASGITransport does not initialize app.state before first assertion**

- **Found during:** Task 2, first test run (`AttributeError: 'State' object has no attribute 'pi_adapter'`)
- **Issue:** Plan's test pattern injected mocks into `app.state` inside `AsyncClient` context, but lifespan hadn't run yet for the first request. State attributes set by lifespan were not available.
- **Fix:** Set `app.state.pi_adapter`, `app.state.context_window`, and `app.state.settings` explicitly in each test after entering the `AsyncClient` context (lifespan runs on context entry, tests then override state before the actual request).
- **Files modified:** `sentinel-core/tests/test_message.py`
- **Commit:** 2580047

## Known Stubs

None. All 9 original stubs from Plan 01 are replaced with real assertions. 11 tests pass.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: no-auth-on-message-endpoint | sentinel-core/app/routes/message.py | POST /message has no authentication in Phase 1. T-1-03-04 (accepted risk) — X-Sentinel-Key deferred to Phase 3 IFACE-06. |

## Self-Check: PASSED

Files verified:
- sentinel-core/app/__init__.py: FOUND
- sentinel-core/app/config.py: FOUND (contains BaseSettings, sentinel_api_key: str)
- sentinel-core/app/models.py: FOUND (contains MessageEnvelope, ResponseEnvelope)
- sentinel-core/app/services/token_guard.py: FOUND (contains count_tokens, check_token_limit, TokenLimitError, cl100k_base)
- sentinel-core/app/clients/lmstudio.py: FOUND (contains LMStudioClient, get_context_window, return 4096, removesuffix)
- sentinel-core/app/clients/pi_adapter.py: FOUND (contains PiAdapterClient, send_prompt)
- sentinel-core/app/routes/message.py: FOUND (contains check_token_limit, send_prompt, AI backend not ready)
- sentinel-core/app/main.py: FOUND (contains asynccontextmanager, app.state.context_window, await http_client.aclose())
- sentinel-core/tests/test_token_guard.py: FOUND (5 real tests, no skips)
- sentinel-core/tests/test_lmstudio_client.py: FOUND (3 real tests, no skips)
- sentinel-core/tests/test_message.py: FOUND (3 real tests, no skips)

Commits verified:
- ea9a83b: Task 1 (config, models, token guard, LM Studio client, Pi adapter, 8 tests)
- 2580047: Task 2 (FastAPI app, routes, 3 message tests, full suite 11 passed)

Test suite: 11 passed, 0 failed, 0 skipped.
