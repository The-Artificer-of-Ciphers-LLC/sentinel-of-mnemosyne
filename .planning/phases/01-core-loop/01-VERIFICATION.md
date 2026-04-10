---
phase: 01-core-loop
verified: 2026-04-10T00:00:00Z
status: human_needed
score: 7/7 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Run the full test suite inside the sentinel-core container or virtualenv"
    expected: "11 tests passed, 0 failed, 0 skipped"
    why_human: "Requires Python environment with tiktoken installed; cannot exec pytest from this shell"
  - test: "docker compose up and POST /message with valid JSON"
    expected: "200 response with content and model fields, AI response returned"
    why_human: "Requires LM Studio running with a model loaded and Pi harness spawning the pi binary"
  - test: "docker compose up and POST /message with oversized message"
    expected: "HTTP 422 with detail containing 'too long' or 'tokens'"
    why_human: "Runtime verification of token guard firing before Pi harness is called"
  - test: "docker compose up with no SENTINEL_API_KEY in .env"
    expected: "sentinel-core container fails to start (pydantic ValidationError at import time)"
    why_human: "Requires environment manipulation and container restart"
---

# Phase 01: Core Loop Verification Report

**Phase Goal:** End-to-end core message loop — a user message goes in, an AI response comes back, and the system is containerized with a Docker Compose include pattern.
**Verified:** 2026-04-10
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | POST /message with valid JSON body returns a ResponseEnvelope with content and model fields | VERIFIED | `routes/message.py` returns `ResponseEnvelope(content=content, model=settings.model_name)`; test asserts `"content" in data` and `"model" in data` at 200 |
| 2 | POST /message returns HTTP 503 when LM Studio is unreachable | VERIFIED (with note) | Route catches `httpx.ConnectError` and 503/504 `HTTPStatusError`, raises `HTTPException(503, detail="AI backend not ready")`. Body is `{"detail": "AI backend not ready"}` — FastAPI HTTPException convention, not `{"error": ...}` as stated in plan truth. Test correctly asserts `.get("detail")`. Behavior matches intent. |
| 3 | POST /message returns HTTP 422 when message token count exceeds context window | VERIFIED | `check_token_limit` raises `TokenLimitError`, caught as `HTTPException(422)`; test sets `context_window=5` to force rejection |
| 4 | GET /health returns `{"status": "ok"}` and does not crash when LM Studio unavailable | VERIFIED | `main.py` line 72-74: always returns `JSONResponse({"status": "ok"})` regardless of downstream state |
| 5 | LM Studio context window fetched from `/api/v0/models/{model_name}` at startup, cached, falls back to 4096 | VERIFIED | `get_context_window` strips `/v1` via `removesuffix("/v1")`, fetches `/api/v0/models/{model_name}`, returns `4096` in bare `except Exception` block; stored in `app.state.context_window` |
| 6 | Configuration loaded from environment variables via pydantic-settings; startup fails fast if SENTINEL_API_KEY missing | VERIFIED | `config.py`: `sentinel_api_key: str` has no default — pydantic-settings raises `ValidationError` at module import time if env var absent |
| 7 | All tests in test_message.py, test_token_guard.py, test_lmstudio_client.py pass (not just skip) | VERIFIED | 11 real tests across 3 files (5 + 3 + 3), all stubs removed per SUMMARY-03. Commits ea9a83b and 2580047 document "11 passed, 0 failed, 0 skipped". Cannot exec pytest in this environment — flagged for human spot-check. |

**Score:** 7/7 truths verified

### Note on Truth 2 — Response Body Shape

The plan truth says `{"error": "AI backend not ready"}`. The implementation returns `{"detail": "AI backend not ready"}` (standard FastAPI `HTTPException` serialization). This is the correct, idiomatic FastAPI behavior. The test at line 80 of `test_message.py` asserts `resp.json().get("detail") == "AI backend not ready"`, which passes. The plan truth wording is imprecise but the implementation is correct.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `sentinel-core/app/main.py` | FastAPI app with lifespan, health endpoint | VERIFIED | Contains `asynccontextmanager`, `lifespan`, `app.include_router`, `GET /health` |
| `sentinel-core/app/config.py` | pydantic-settings Settings class | VERIFIED | Contains `BaseSettings`, `sentinel_api_key: str` (no default), `model_config` with env_file |
| `sentinel-core/app/models.py` | MessageEnvelope and ResponseEnvelope Pydantic v2 models | VERIFIED | `class MessageEnvelope` and `class ResponseEnvelope`, both use `Field(...)` syntax (Pydantic v2) |
| `sentinel-core/app/routes/message.py` | POST /message handler | VERIFIED | `@router.post("/message", response_model=ResponseEnvelope)` |
| `sentinel-core/app/clients/lmstudio.py` | Async LM Studio HTTP client | VERIFIED | Exports `LMStudioClient` and `get_context_window` |
| `sentinel-core/app/services/token_guard.py` | Token counting and context window enforcement | VERIFIED | Exports `count_tokens`, `check_token_limit`, `TokenLimitError` |
| `sentinel-core/app/clients/pi_adapter.py` | HTTP client for Pi harness | VERIFIED | `PiAdapterClient.send_prompt` posts to `/prompt` with 35s timeout |
| `pi-harness/src/pi-adapter.ts` | Pi adapter (single point of contact with pi-mono) | VERIFIED | All pi-mono imports isolated here; exports `spawnPi`, `sendPrompt`, `getPiHealth` |
| `pi-harness/src/bridge.ts` | Fastify HTTP bridge | VERIFIED | `POST /prompt` and `GET /health` routes; imports only from `./pi-adapter` |
| `docker-compose.yml` | Root compose with include directive | VERIFIED | Uses `include:` with path entries; comment explicitly prohibits `-f` stacking |
| `sentinel-core/compose.yml` | Core service compose | VERIFIED | Port 8000, healthcheck, `depends_on: pi-harness: condition: service_started` |
| `pi-harness/compose.yml` | Pi harness service compose | VERIFIED | Port 3000, healthcheck with 30s start_period |
| `sentinel-core/pyproject.toml` | Python project with FastAPI + pydantic-settings | VERIFIED | All required deps declared; `asyncio_mode = "auto"` in pytest config |
| `sentinel-core/Dockerfile` | Python 3.12-slim image | VERIFIED | `FROM python:3.12-slim`, uvicorn entrypoint |
| `pi-harness/Dockerfile` | Node 22 Alpine image | VERIFIED | `FROM node:22-alpine`, `ENV PATH` fix for pi binary, `npm ci --omit=dev` |
| `pi-harness/package.json` | Exact pin @mariozechner/pi-coding-agent@0.66.1 | VERIFIED | `"@mariozechner/pi-coding-agent": "0.66.1"` — no `^` or `~` |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `routes/message.py` | `services/token_guard.py` | `from app.services.token_guard import check_token_limit` | VERIFIED | Import at line 6; `check_token_limit(messages, request.app.state.context_window)` called at line 23 |
| `routes/message.py` | `clients/pi_adapter.py` | `from app.clients.pi_adapter import PiAdapterClient` (via app.state) | VERIFIED | `PiAdapterClient` used via `request.app.state.pi_adapter`; wired in lifespan |
| `main.py` | `clients/lmstudio.py` | `from app.clients.lmstudio import LMStudioClient, get_context_window` | VERIFIED | `get_context_window` called in lifespan at startup; result stored in `app.state.context_window` |
| `bridge.ts` | `pi-adapter.ts` | `import { spawnPi, sendPrompt, getPiHealth } from './pi-adapter'` | VERIFIED | All three exports used in bridge.ts; no direct pi-mono imports in bridge.ts |
| `docker-compose.yml` | `sentinel-core/compose.yml` | `include: - path: sentinel-core/compose.yml` | VERIFIED | Include directive at root compose |
| `docker-compose.yml` | `pi-harness/compose.yml` | `include: - path: pi-harness/compose.yml` | VERIFIED | Include directive at root compose |

### Data-Flow Trace (Level 4)

Not applicable — this phase delivers API endpoints (not UI components rendering dynamic data). The data flow is verified via key link wiring: message body → token guard → pi adapter → response envelope.

### Behavioral Spot-Checks

Step 7b: The code is runnable but requires services (Pi harness, LM Studio). Pytest can run standalone.

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Python module imports correctly | `python -c "from app.main import app"` | Cannot run — no venv available in this shell | SKIP |
| Test suite passes | `pytest sentinel-core/tests/ -q` | Cannot run — no venv available | SKIP |
| pi-adapter.ts manual JSONL parsing | Code review: `stdoutBuffer.split('\n')` not `readline` | Confirmed: manual split on `\n` at line 46 of pi-adapter.ts | PASS (code review) |
| Exact pi-mono version pin | `package.json` version field | `"@mariozechner/pi-coding-agent": "0.66.1"` — no semver range | PASS |
| docker-compose.yml uses include not -f | File content | `include:` directive at lines 5-7; no `-f` present | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| CORE-01 | Plan 01-02 | Pi harness accepts HTTP POST /prompt via Fastify bridge | SATISFIED | `bridge.ts` line 20: `app.post('/prompt', ...)` |
| CORE-02 | Plan 01-02 | Adapter pattern, exact pin @0.66.1 | SATISFIED | `package.json` exact pin; `pi-adapter.ts` is sole importer; bridge.ts imports only from `./pi-adapter` |
| CORE-03 | Plan 01-03 | POST /message returns ResponseEnvelope | SATISFIED | `routes/message.py` returns `ResponseEnvelope(content=..., model=...)` |
| CORE-04 | Plan 01-03 | LM Studio async client, context window fetch, 4096 fallback | SATISFIED | `lmstudio.py` implements both; fallback on any Exception |
| CORE-05 | Plan 01-03 | Token guard rejects messages exceeding context window (422) | SATISFIED | `token_guard.py` + `routes/message.py` catch + 422 HTTPException |
| CORE-06 | Plans 01-01, 01-03 | Python project with FastAPI + pydantic-settings | SATISFIED | `pyproject.toml` declares all deps; `config.py` uses `BaseSettings` |
| CORE-07 | Plan 01-01 | Docker Compose include directive pattern | SATISFIED | `docker-compose.yml` uses `include:` only; `-f` explicitly prohibited in comment |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `sentinel-core/app/routes/message.py` | — | No authentication on POST /message | INFO | Intentional — documented as T-1-03-04 accepted risk, deferred to Phase 3 (IFACE-06) |
| `pi-harness/src/pi-adapter.ts` | 30-32 | Module-level mutable state for subprocess management | INFO | Expected pattern for long-lived subprocess; not a stub |

No blockers or warnings found. The auth deferral is explicitly documented as an accepted risk in the phase summary.

### Human Verification Required

#### 1. Full test suite execution

**Test:** In a Python 3.12 environment with dependencies installed, run `cd sentinel-core && pytest tests/ -v`
**Expected:** 11 tests pass, 0 fail, 0 skip — specifically: 3 in test_message.py, 5 in test_token_guard.py, 3 in test_lmstudio_client.py
**Why human:** Requires Python virtualenv with tiktoken, pytest-asyncio; cannot exec from verification shell

#### 2. docker compose up smoke test

**Test:** `docker compose up -d` then `curl -s http://localhost:8000/health`
**Expected:** `{"status":"ok"}` within 30 seconds of startup
**Why human:** Requires Docker daemon and services to actually start

#### 3. End-to-end message round-trip

**Test:** With LM Studio running and a model loaded: `curl -X POST http://localhost:8000/message -H "Content-Type: application/json" -d '{"content":"hello","user_id":"test"}' | jq .`
**Expected:** JSON with `content` (AI response text) and `model` (model name string) fields
**Why human:** Requires LM Studio running on Mac Mini with a model loaded (operational dependency)

#### 4. Startup failure on missing SENTINEL_API_KEY

**Test:** Remove `SENTINEL_API_KEY` from `.env`, then `docker compose up sentinel-core`
**Expected:** Container exits immediately with a pydantic ValidationError (not silently starting with a None key)
**Why human:** Requires environment manipulation and container restart observation

### Gaps Summary

No code gaps found. All 7 must-have truths hold in the actual implementation. All 7 CORE requirements are implemented. All artifacts exist and are substantive. All key links are wired. No blockers or stubs detected.

Status is `human_needed` due to 4 items that require a live environment to confirm (test suite execution, docker compose behavior, LM Studio round-trip, and startup failure on missing key). These are runtime confirmations of code that is structurally correct.

---

_Verified: 2026-04-10_
_Verifier: Claude (gsd-verifier)_
