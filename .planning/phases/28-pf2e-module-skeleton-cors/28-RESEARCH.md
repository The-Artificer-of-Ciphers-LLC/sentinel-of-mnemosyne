# Phase 28: pf2e-module Skeleton + CORS — Research

**Researched:** 2026-04-22
**Domain:** FastAPI CORSMiddleware, Docker Compose profiles, module skeleton pattern
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Add `fastapi.middleware.cors.CORSMiddleware` to `sentinel-core/app/main.py`.
- **D-02:** `allow_origins` populated from `CORS_ALLOW_ORIGINS` env var (comma-separated → list). Default: `http://localhost:30000`.
- **D-03:** `allow_origin_regex` populated from `CORS_ALLOW_ORIGIN_REGEX` env var. Default: `https://.*\.forge-vtt\.com`.
- **D-04:** No wildcard in `allow_origins` — breaks `X-Sentinel-Key` credential header delivery.
- **D-05:** `allow_credentials=True`, `allow_headers=["*"]`, `allow_methods=["*"]`.
- **D-06:** Both env vars added to `config.py` (pydantic-settings) and documented in `.env.example`.
- **D-07:** CORS middleware added AFTER `APIKeyMiddleware` in `main.py` source order (FastAPI LIFO means CORSMiddleware runs first on requests — handles OPTIONS before auth).
- **D-08:** Add `GET /modules/{name}/{path:path}` route to `routes/modules.py` (mirror of POST proxy with `http_client.get()`).
- **D-09:** Add `GET /modules` route to `routes/modules.py` — returns registry as list: `[{"name": ..., "base_url": ..., "routes": [...]}]`.
- **D-10:** Docker Compose profile name: `pf2e`.
- **D-11:** Module registry name: `pathfinder`.
- **D-12:** `pf2e` (stack identifier) ≠ `pathfinder` (API logical name).
- **D-13:** `sentinel.sh` adds `--pf2e` flag → `PROFILES+=("pf2e")`; removes/updates existing `--pathfinder` case.
- **D-14:** Module directory: `modules/pathfinder/`.
- **D-15:** pf2e-module calls `POST /modules/register` at startup with retry + exponential backoff (~5 attempts, delays: 1s, 2s, 4s, 8s, 16s).
- **D-16:** If all retries fail: module logs error and exits (Docker restart policy brings it back).
- **D-17:** Registration payload: `{"name": "pathfinder", "base_url": "http://pf2e-module:8000", "routes": [{"path": "healthz", "description": "pf2e module health check"}]}`.
- **D-18:** Module's `/healthz` returns `{"status": "ok", "module": "pathfinder"}`.

### Claude's Discretion

- Exact retry library or implementation (tenacity, manual asyncio.sleep loop, or httpx retry transport)
- Response schema for `GET /modules` beyond containing "pathfinder" in list
- Internal pf2e-module Dockerfile base image (python:3.12-slim preferred per project convention)
- Port assignment for pf2e-module service (8000 conventional; 8001 also acceptable)

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MOD-01 | PF2e module delivered as Docker Compose `include` (Path B reference implementation) | Docker Compose `profiles` + `include` directive pattern confirmed from existing codebase |
| MOD-02 | CORS middleware added to Sentinel Core to allow Foundry browser `fetch()` with `X-Sentinel-Key` | CORSMiddleware configuration verified from FastAPI official docs; credential+explicit-origins pattern confirmed |
</phase_requirements>

---

## Summary

Phase 28 is an infrastructure skeleton phase — no AI, no domain logic, no Obsidian writes. It proves the Path B module pattern by standing up a minimal pf2e-module FastAPI container that registers itself with Sentinel Core on startup, and by adding CORS middleware to Core so Foundry's browser `fetch()` calls can reach it with credential headers.

The two workstreams are nearly independent: Sentinel Core changes (CORS middleware + GET proxy + GET /modules list) can be implemented and tested without the pf2e-module container, and the pf2e-module can be built and unit-tested against a mock Core. The integration point is the `POST /modules/register` call at pf2e-module startup.

The most critical implementation detail is CORS middleware ordering. FastAPI processes `add_middleware()` calls in LIFO order (last added = outermost = runs first on requests). CORSMiddleware must be the outermost middleware so it intercepts `OPTIONS` preflight requests before `APIKeyMiddleware` can reject them with 401. This means the `app.add_middleware(CORSMiddleware, ...)` call must appear AFTER `app.add_middleware(APIKeyMiddleware)` in `main.py` source code — counterintuitive but correct per FastAPI/Starlette specification.

The second critical detail is the wildcard restriction: `allow_credentials=True` is incompatible with `allow_origins=["*"]`. The browser blocks credential-bearing requests to wildcard origins per the CORS specification. The solution (D-02 + D-03) uses an explicit list for LAN IPs plus a regex for Forge VTT's variable subdomains.

**Primary recommendation:** Implement in this order: (1) CORS config settings, (2) CORS middleware in main.py, (3) GET proxy + GET /modules in modules.py, (4) pf2e-module skeleton, (5) docker-compose.yml + sentinel.sh updates, (6) integration smoke test.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| CORS header generation | API / Backend (Sentinel Core) | — | CORS is a server-side concern; middleware intercepts all requests at the entry point |
| CORS origin validation | API / Backend (Sentinel Core) | — | Origin allowlist lives in Core's config; modules don't own CORS |
| Module registration | API / Backend (pf2e-module → Sentinel Core) | — | Module initiates at startup; Core maintains the registry |
| Module proxy routing | API / Backend (Sentinel Core) | — | Core is the single gateway; all Foundry requests go through it |
| Container orchestration | Docker Compose | — | Profile-based inclusion is the project-standard pattern |
| Health endpoint | API / Backend (pf2e-module) | — | `/healthz` is the module's own endpoint; Core proxies it |

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | 0.135.3 (installed) | Web framework for both Core and pf2e-module | Project standard; CORSMiddleware is built-in |
| uvicorn[standard] | >=0.44.0 | ASGI server | Project standard; `[standard]` extra for uvloop |
| httpx | 0.28.1 (installed) | Async HTTP client for registration call | Project standard; no `requests` allowed |
| tenacity | 9.1.2 (installed) | Retry with exponential backoff | Already used in sentinel-core; project pattern for retry |
| pydantic-settings | >=2.13.0 | Env var configuration | Project standard; already in sentinel-core |

[VERIFIED: pip3 show fastapi, tenacity, httpx in project venv]

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `fastapi.middleware.cors.CORSMiddleware` | built-in | CORS headers on all responses | Required for Foundry browser fetch |
| `starlette.middleware.base.BaseHTTPMiddleware` | built-in | Custom middleware base class | Already used for APIKeyMiddleware |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| tenacity | manual asyncio.sleep loop | Manual loop is fine for 5-attempt startup retry; tenacity is cleaner and project-standard |
| tenacity | httpx retry transport | httpx retry transport works at transport level only; tenacity gives more control over exception types |

**Installation (pf2e-module pyproject.toml):**
```bash
pip install "fastapi>=0.135.0" "uvicorn[standard]>=0.44.0" "httpx>=0.28.1" "tenacity>=8.2.0,<10.0" "pydantic-settings>=2.13.0"
```

---

## Architecture Patterns

### System Architecture Diagram

```
Foundry Browser (LAN)
        |
        | HTTP fetch() with X-Sentinel-Key
        v
[Sentinel Core :8000]
   CORSMiddleware  <-- outermost (added last, runs first)
   APIKeyMiddleware
        |
        +---> GET /modules          (list registry)
        +---> GET /modules/pathfinder/healthz  (GET proxy)
        +---> POST /modules/{name}/{path}      (POST proxy -- existing)
        +---> POST /modules/register           (existing)
                          |
                          | http://pf2e-module:8000/healthz
                          v
               [pf2e-module :8000]
               /healthz --> {"status": "ok", "module": "pathfinder"}
               [startup lifespan]
                  POST http://sentinel-core:8000/modules/register
                  with retry (5 attempts, exp backoff)
```

### Recommended Project Structure

```
modules/pathfinder/
├── app/
│   └── main.py          # FastAPI app: /healthz + lifespan startup registration
├── compose.yml          # profiles: ["pf2e"], service name: pf2e-module
├── Dockerfile           # python:3.12-slim, same pattern as sentinel-core
└── pyproject.toml       # dependencies (fastapi, uvicorn, httpx, tenacity, pydantic-settings)
```

### Pattern 1: FastAPI CORSMiddleware Configuration

**What:** Add CORSMiddleware to sentinel-core using explicit origin list + regex. No wildcard.
**When to use:** Any FastAPI app that must respond to browser `fetch()` calls with credentials.

```python
# Source: https://fastapi.tiangolo.com/tutorial/cors/
# sentinel-core/app/main.py

from fastapi.middleware.cors import CORSMiddleware

# In Settings class (config.py):
# cors_allow_origins: str = "http://localhost:30000"
# cors_allow_origin_regex: str = r"https://.*\.forge-vtt\.com"

# In main.py, AFTER app.add_middleware(APIKeyMiddleware):
app.add_middleware(APIKeyMiddleware)  # innermost — runs second

_cors_origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=settings.cors_allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# CORSMiddleware is outermost — runs first on all requests,
# intercepts OPTIONS preflight before APIKeyMiddleware can 401 it.
```

[VERIFIED: fastapi.tiangolo.com/tutorial/cors/ — CORSMiddleware parameters]
[VERIFIED: github.com/fastapi/fastapi/discussions/6983 — CORS must be outermost for OPTIONS to work]

### Pattern 2: LIFO Middleware Ordering (Critical)

**What:** FastAPI processes `add_middleware()` calls LIFO — last added runs outermost (first on requests).
**When to use:** Any time you stack two or more middlewares that must process requests in a specific order.

The source order in `main.py` must be:
```python
app.add_middleware(APIKeyMiddleware)   # call 1 — innermost, runs second
app.add_middleware(CORSMiddleware, ...) # call 2 — outermost, runs first
```

Request path: CORSMiddleware → APIKeyMiddleware → route handler
Response path: route handler → APIKeyMiddleware → CORSMiddleware

[VERIFIED: Starlette middleware docs — LIFO ordering confirmed]

### Pattern 3: pf2e-module Startup Registration with Retry

**What:** Lifespan context manager calls `POST /modules/register` with tenacity exponential backoff.
**When to use:** Any module that must register with Core at startup.

```python
# Source: project pattern from sentinel-core/app/clients/retry_config.py + litellm_provider.py
# modules/pathfinder/app/main.py

import asyncio
import logging
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

REGISTRATION_PAYLOAD = {
    "name": "pathfinder",
    "base_url": "http://pf2e-module:8000",
    "routes": [{"path": "healthz", "description": "pf2e module health check"}],
}

CORE_URL = "http://sentinel-core:8000"  # from env var SENTINEL_CORE_URL

async def _register_with_retry(client: httpx.AsyncClient, api_key: str) -> None:
    """Register with Core, 5 attempts, exponential backoff 1s→2s→4s→8s→16s."""
    delays = [1, 2, 4, 8, 16]
    for attempt, delay in enumerate(delays, start=1):
        try:
            resp = await client.post(
                f"{CORE_URL}/modules/register",
                json=REGISTRATION_PAYLOAD,
                headers={"X-Sentinel-Key": api_key},
                timeout=10.0,
            )
            resp.raise_for_status()
            logger.info("Registered with Sentinel Core (attempt %d)", attempt)
            return
        except Exception as exc:
            logger.warning("Registration attempt %d failed: %s", attempt, exc)
            if attempt < len(delays):
                await asyncio.sleep(delay)
    logger.error("All %d registration attempts failed — exiting", len(delays))
    raise SystemExit(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient() as client:
        await _register_with_retry(client, settings.sentinel_api_key)
    yield
```

[VERIFIED: project pattern from sentinel-core/app/clients/retry_config.py + litellm_provider.py]
[ASSUMED: `asyncio.sleep` manual loop preferred over `tenacity` for simple startup registration — fewer dependencies; decision is Claude's Discretion]

### Pattern 4: Docker Compose Profile + Include

**What:** pf2e-module compose.yml uses `profiles: ["pf2e"]` and build context set to module root.
**When to use:** Every Path B module follows this pattern.

```yaml
# modules/pathfinder/compose.yml
services:
  pf2e-module:
    build:
      context: .
      dockerfile: Dockerfile
    profiles:
      - pf2e
    depends_on:
      sentinel-core:
        condition: service_healthy
    restart: unless-stopped
```

```yaml
# docker-compose.yml (uncommenting the stub):
include:
  - path: modules/pathfinder/compose.yml
```

[VERIFIED: existing codebase — interfaces/discord/compose.yml and sentinel-core/compose.yml as reference]

### Pattern 5: GET Proxy (Mirror of Existing POST Proxy)

**What:** `GET /modules/{name}/{path:path}` is an exact mirror of the existing POST proxy, using `http_client.get()`.
**When to use:** When Foundry needs to pull data from a module (actor JSON, health check).

```python
# Source: sentinel-core/app/routes/modules.py (existing POST proxy as template)
@router.get("/modules/{name}/{path:path}")
async def get_proxy_module(name: str, path: str, request: Request) -> JSONResponse:
    registry = request.app.state.module_registry
    if name not in registry:
        raise HTTPException(status_code=404, detail=f"Module '{name}' not registered")
    module = registry[name]
    target_url = f"{module.base_url.rstrip('/')}/{path}"
    sentinel_key = request.headers.get("X-Sentinel-Key", "")
    try:
        resp = await request.app.state.http_client.get(
            target_url,
            headers={"X-Sentinel-Key": sentinel_key},
        )
        try:
            content = resp.json()
        except Exception:
            content = {"body": resp.text}
        return JSONResponse(content=content, status_code=resp.status_code)
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail={"error": "module unavailable"})
```

[VERIFIED: sentinel-core/app/routes/modules.py — existing POST proxy implementation]

### Pattern 6: shared/ Mounting in Dockerfile

**What:** pf2e-module needs `SENTINEL_API_KEY` to authenticate its registration call. The `shared/sentinel_client.py` is optional — direct httpx is simpler for a single call.
**When to use:** If using `SentinelCoreClient` from shared/, build context must be repo root (same pattern as discord Dockerfile).

```dockerfile
# Option A: Repo root build context (if using shared/)
# docker-compose context: ../.. from modules/pathfinder/
COPY shared/ /app/shared/
COPY modules/pathfinder/ /app/

# Option B: Module-local build context (simpler — no shared/ dependency)
# docker-compose context: . (module directory)
# Just implement the registration call directly in app/main.py
```

**Recommendation (Claude's Discretion):** Use Option B (module-local build context, direct httpx) for Phase 28. The pf2e-module's registration call is too simple to warrant the shared/ dependency. Phases 29+ can add shared/ if needed.

[VERIFIED: interfaces/discord/Dockerfile and discord/compose.yml — shared/ pattern]

### Anti-Patterns to Avoid

- **`allow_origins=["*"]` with `allow_credentials=True`:** Browser blocks credential-bearing requests to wildcard origins. FastAPI CORSMiddleware silently produces malformed CORS headers in this case. [VERIFIED: FastAPI docs]
- **Adding CORSMiddleware before APIKeyMiddleware:** Means CORS runs innermost (last on requests), after APIKeyMiddleware has already rejected OPTIONS with 401. Foundry preflight fails. [VERIFIED: github.com/fastapi/fastapi/discussions/6983]
- **`--pathfinder` in `sentinel.sh`:** Already exists but maps to `pathfinder` profile. Must be changed to `--pf2e` → `pf2e` profile. Leave `--pathfinder` case as a no-op or remove it; do not keep both. [VERIFIED: sentinel.sh source]
- **Port 8000 conflict:** pf2e-module uses port 8000 internally. Only sentinel-core publishes 8000 to the host (`ports: "8000:8000"`). pf2e-module must NOT publish any host port — it's only reachable on the Docker network. [VERIFIED: sentinel-core/compose.yml]

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| CORS headers | Custom response header injection | CORSMiddleware | Handles preflight, simple requests, max_age caching, `Access-Control-Expose-Headers` — 10+ edge cases |
| Retry logic | Custom while-loop with counter | tenacity or asyncio.sleep with explicit delays | Tenacity handles jitter, exception filtering, logging hooks; manual loop for simple cases is acceptable |
| Env var parsing | `os.getenv()` | pydantic-settings | Type-safe, validates at startup, `.env` file support — project standard |

**Key insight:** CORSMiddleware has been battle-tested against every browser's CORS implementation quirk. Any custom header injection will miss edge cases (vary headers, cached preflight responses, non-simple header handling).

---

## Common Pitfalls

### Pitfall 1: CORS Middleware Order (Most Likely Failure)
**What goes wrong:** Foundry's preflight `OPTIONS` request gets rejected with 401 before CORS headers are set. Browser receives a 401 with no `Access-Control-Allow-Origin` header and throws a CORS error, not an auth error.
**Why it happens:** `add_middleware()` is LIFO. If CORSMiddleware is added before APIKeyMiddleware (first call), it runs innermost (second on requests) — after auth has already rejected.
**How to avoid:** `app.add_middleware(APIKeyMiddleware)` first, then `app.add_middleware(CORSMiddleware, ...)`. CORSMiddleware is last call = outermost = runs first.
**Warning signs:** Test with `curl -X OPTIONS -H "Origin: http://localhost:30000" -H "Access-Control-Request-Method: POST" http://localhost:8000/modules/pathfinder/healthz` — must return 200, not 401.

### Pitfall 2: Wildcard + Credentials Incompatibility
**What goes wrong:** `allow_origins=["*"]` with `allow_credentials=True` causes the browser to block the request. The `X-Sentinel-Key` header is never sent.
**Why it happens:** CORS spec prohibits credentials with wildcard origins. FastAPI CORSMiddleware enforces this by not reflecting the origin when wildcard is used.
**How to avoid:** Always use explicit origin list + regex. D-04 is the locked decision.
**Warning signs:** Browser console shows "The value of the 'Access-Control-Allow-Origin' header in the response must not be the wildcard '*' when the request's credentials mode is 'include'."

### Pitfall 3: Docker Service Name vs Registry Name Mismatch
**What goes wrong:** pf2e-module's `compose.yml` uses service name `pf2e-module`. Its registration payload says `"base_url": "http://pf2e-module:8000"`. If the compose service name differs, Core's proxy GET call fails with ConnectError (503).
**Why it happens:** Docker resolves service names as hostnames on the compose network. If service name is `pathfinder` but base_url says `http://pf2e-module:8000`, the request goes nowhere.
**How to avoid:** Service name in `compose.yml` MUST be `pf2e-module` (matching D-17's `base_url`). Verify alignment during plan review.

### Pitfall 4: pf2e-module Starts Before sentinel-core Is Ready
**What goes wrong:** pf2e-module's startup registration fires before sentinel-core's `/modules/register` endpoint is serving. First attempt fails with ConnectError.
**Why it happens:** `depends_on: condition: service_healthy` ensures sentinel-core passes its healthcheck before pf2e-module starts, but there's still a small window.
**How to avoid:** `depends_on: sentinel-core: condition: service_healthy` in `modules/pathfinder/compose.yml`. The retry logic (D-15) handles the remaining window.
**Warning signs:** Logs show "Registration attempt 1 failed: ConnectError" then succeeds on attempt 2 — this is expected and acceptable.

### Pitfall 5: CORS_ALLOW_ORIGINS Parsing Edge Cases
**What goes wrong:** `"http://localhost:30000 , http://192.168.1.100:30000"` (spaces around comma) produces `["http://localhost:30000 ", " http://192.168.1.100:30000"]` — trailing/leading spaces cause origin mismatch.
**Why it happens:** Simple `split(",")` doesn't strip whitespace.
**How to avoid:** `[o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]` — strip each entry and filter empties.

### Pitfall 6: `--pathfinder` Case in sentinel.sh
**What goes wrong:** If `--pathfinder` is kept alongside `--pf2e`, someone who uses `./sentinel.sh --pathfinder up` activates the `pathfinder` profile — which doesn't exist (compose profile is `pf2e`). Silent no-op; pf2e-module doesn't start.
**How to avoid:** Remove the `--pathfinder` case and update `ALL_KNOWN_PROFILES` to include `pf2e`, remove `pathfinder`.

---

## Code Examples

### Verified: Existing Test Pattern for modules.py

The existing `test_modules.py` sets up app state directly without running lifespan. New tests for GET /modules and GET proxy must follow the same `setup_app_state` fixture pattern:

```python
# Source: sentinel-core/tests/test_modules.py (existing)
@pytest.fixture(autouse=True)
def setup_app_state(mock_http_client):
    app.state.module_registry = {}
    app.state.http_client = mock_http_client
    app.state.obsidian_client = MagicMock()
    app.state.ai_provider_name = "lmstudio"
    app.state.settings = MagicMock()
    app.state.settings.pi_harness_url = "http://pi-harness:3000"

# For GET proxy test, also add:
    mock_http_client.get = AsyncMock(return_value=mock_resp)  # not just .post
```

[VERIFIED: sentinel-core/tests/test_modules.py]

### Verified: pydantic-settings Field Pattern (config.py)

```python
# Source: sentinel-core/app/config.py (existing pattern)
class Settings(BaseSettings):
    # ... existing fields ...
    cors_allow_origins: str = "http://localhost:30000"
    cors_allow_origin_regex: str = r"https://.*\.forge-vtt\.com"
    
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}
```

Env vars: `CORS_ALLOW_ORIGINS` and `CORS_ALLOW_ORIGIN_REGEX` (pydantic-settings lowercases field names to match env vars).

[VERIFIED: sentinel-core/app/config.py]

### Verified: Dockerfile Pattern (python:3.12-slim)

```dockerfile
# Source: sentinel-core/Dockerfile (existing pattern)
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    "fastapi>=0.135.0" \
    "uvicorn[standard]>=0.44.0" \
    "httpx>=0.28.1" \
    "tenacity>=8.2.0,<10.0" \
    "pydantic-settings>=2.13.0"

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

[VERIFIED: sentinel-core/Dockerfile]

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `@app.on_event("startup")` | `lifespan` context manager | FastAPI 0.93+ | `on_event` is deprecated; lifespan is the correct pattern |
| `allow_origins=["*"]` | Explicit list + `allow_origin_regex` | CORS spec always | Wildcard breaks credential-bearing requests |
| `docker-compose` v1 | `docker compose` v2 | 2023 | v1 deprecated; project enforces v2 |

**Deprecated/outdated:**
- `@app.on_event("startup")` / `@app.on_event("shutdown")`: deprecated since FastAPI 0.93. Use `lifespan` async context manager. All existing sentinel-core code uses lifespan correctly.
- `allow_origins=["*"]` with `allow_credentials=True`: never valid per CORS spec. FastAPI silently mishandles this combination.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Manual `asyncio.sleep` retry loop is cleaner than tenacity for the 5-attempt startup registration in pf2e-module | Pattern 3, Claude's Discretion | Low — tenacity is equally valid; either works |
| A2 | pf2e-module uses Option B (module-local build context, no shared/ dependency) for Phase 28 | Pattern 6 | Low — Option A also works; shared/ not needed for single registration call |
| A3 | `pydantic-settings` field name `cors_allow_origins` maps to env var `CORS_ALLOW_ORIGINS` (auto-lowercasing) | Code Examples | LOW — pydantic-settings always lowercases; confirmed by existing field conventions in config.py |

A3 is `[VERIFIED]` in practice but flagged for awareness: pydantic-settings field `cors_allow_origins` → env var `CORS_ALLOW_ORIGINS` (case-insensitive match).

---

## Open Questions

1. **Port for pf2e-module (Claude's Discretion)**
   - What we know: Service uses port 8000 internally. Discord uses no published port. sentinel-core publishes `8000:8000`.
   - What's unclear: Whether pf2e-module should publish a host port for local development debugging.
   - Recommendation: No published host port in Phase 28. All access goes through Core proxy. Developer can use `docker exec` or add a port mapping locally if needed.

2. **`ALL_KNOWN_PROFILES` in sentinel.sh**
   - What we know: Current value is `(pi discord pathfinder music finance trader coder)`. D-10 uses `pf2e` as profile name.
   - What's unclear: Whether `pathfinder` should be kept in ALL_KNOWN_PROFILES for backward compatibility with any existing local setup.
   - Recommendation: Replace `pathfinder` with `pf2e` in ALL_KNOWN_PROFILES. No backward compatibility needed for a pre-beta project.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | Container build + run | ✓ | 29.3.1 | — |
| Docker Compose v2 | `include` directive | ✓ | v5.1.1 | — |
| Python 3.12 | pf2e-module Dockerfile base | ✓ (host: 3.14, container: 3.12-slim) | 3.12 in container | — |
| FastAPI 0.135.x | CORSMiddleware | ✓ | 0.135.3 installed in venv | — |
| tenacity 9.x | Retry pattern | ✓ | 9.1.2 installed | asyncio.sleep manual loop |

**Missing dependencies with no fallback:** None.

[VERIFIED: docker --version, docker compose version, pip3 show fastapi tenacity]

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (asyncio_mode = "auto") |
| Config file | `sentinel-core/pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `cd sentinel-core && python3 -m pytest tests/test_modules.py -x -q` |
| Full suite command | `cd sentinel-core && python3 -m pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MOD-01 | `docker compose --profile pf2e up` starts pf2e-module (SC-1) | smoke (docker) | manual — requires running compose | ❌ Wave 0 |
| MOD-01 | `/healthz` on pf2e-module returns 200 with correct body | unit (pf2e-module) | `cd modules/pathfinder && python3 -m pytest tests/ -x -q` | ❌ Wave 0 |
| MOD-02 | `POST /modules/register` succeeds at startup; `GET /modules` returns pathfinder (SC-2) | unit (sentinel-core) | `cd sentinel-core && python3 -m pytest tests/test_modules.py -x -q` | ❌ Wave 0 (GET /modules test) |
| MOD-02 | `GET /modules/pathfinder/healthz` returns 200 via Core proxy (SC-3) | unit (sentinel-core) | `cd sentinel-core && python3 -m pytest tests/test_modules.py -x -q` | ❌ Wave 0 (GET proxy test) |
| MOD-02 | CORS preflight OPTIONS to Core returns 200 with CORS headers (SC-4) | unit (sentinel-core) | `cd sentinel-core && python3 -m pytest tests/test_cors.py -x -q` | ❌ Wave 0 |
| MOD-02 | No wildcard in `allow_origins` (SC-5 / D-04) | unit (sentinel-core) | included in test_cors.py | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd sentinel-core && python3 -m pytest tests/test_modules.py -x -q`
- **Per wave merge:** `cd sentinel-core && python3 -m pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `sentinel-core/tests/test_modules.py` — extend with GET /modules + GET proxy tests (file exists, needs new test functions)
- [ ] `sentinel-core/tests/test_cors.py` — CORS middleware: OPTIONS preflight returns 200 with headers, wildcard check, credential header passthrough
- [ ] `modules/pathfinder/tests/test_healthz.py` — `/healthz` returns `{"status": "ok", "module": "pathfinder"}`
- [ ] `modules/pathfinder/tests/test_registration.py` — startup registration retry logic (mock httpx, verify payload)
- [ ] `modules/pathfinder/pyproject.toml` — `[tool.pytest.ini_options]` with asyncio_mode = "auto"

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `X-Sentinel-Key` shared secret — existing APIKeyMiddleware covers all module proxy routes |
| V3 Session Management | no | Stateless HTTP; no session tokens |
| V4 Access Control | yes | Module routes behind APIKeyMiddleware; CORS allows only explicit LAN origins |
| V5 Input Validation | yes | Pydantic models for `ModuleRegistration`; path params typed by FastAPI |
| V6 Cryptography | no | No crypto operations in this phase |

### Known Threat Patterns for this Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Unauthenticated module registration | Spoofing | APIKeyMiddleware on `/modules/register` — any caller without X-Sentinel-Key gets 401 |
| CORS wildcard + credential theft | Elevation of Privilege | D-04 explicit origins + regex; no wildcard in allow_origins |
| Server-side request forgery via module proxy | Tampering | Module `base_url` is set at registration time; only registered modules can be proxied; internal Docker network only |
| OPTIONS preflight rejection → CORS bypass | Spoofing | CORSMiddleware outermost ensures OPTIONS never hits APIKeyMiddleware |

**Note on SSRF:** The module proxy (`GET/POST /modules/{name}/{path}`) forwards requests to `module.base_url` as set during registration. In the current architecture this is only reachable by callers who possess the `X-Sentinel-Key` shared secret (enforced by APIKeyMiddleware). The Docker internal network limits `base_url` reachability. This is acceptable for a personal LAN tool.

---

## Sources

### Primary (HIGH confidence)
- FastAPI official CORS tutorial — `https://fastapi.tiangolo.com/tutorial/cors/` — CORSMiddleware parameters, wildcard + credentials restriction, example code
- Starlette middleware docs — `https://www.starlette.io/middleware/` — LIFO ordering, CORSMiddleware preflight behavior
- `sentinel-core/app/main.py` — existing middleware pattern (APIKeyMiddleware)
- `sentinel-core/app/routes/modules.py` — existing POST proxy implementation
- `sentinel-core/app/config.py` — pydantic-settings field pattern
- `sentinel-core/Dockerfile` — python:3.12-slim build pattern
- `interfaces/discord/Dockerfile` — shared/ mounting pattern
- `sentinel-core/tests/test_modules.py` — existing test fixture pattern
- `sentinel-core/app/clients/retry_config.py` — tenacity retry pattern in project

### Secondary (MEDIUM confidence)
- `github.com/fastapi/fastapi/discussions/6983` — CORS must be outermost middleware for OPTIONS to work (maintainer response, 2022, still valid for current FastAPI/Starlette)

### Tertiary (LOW confidence)
- None

---

## Metadata

**Confidence breakdown:**
- CORS configuration: HIGH — verified from FastAPI official docs + codebase
- Middleware ordering: HIGH — verified from Starlette docs + GitHub issue with maintainer response
- pf2e-module skeleton pattern: HIGH — derived directly from existing interfaces/discord pattern in codebase
- Retry implementation: MEDIUM — tenacity vs manual asyncio.sleep is Claude's Discretion; both are valid

**Research date:** 2026-04-22
**Valid until:** 2026-05-22 (FastAPI/Starlette CORS behavior is stable)
