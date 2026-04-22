---
phase: 28-pf2e-module-skeleton-cors
reviewed: 2026-04-21T00:00:00Z
depth: standard
files_reviewed: 17
files_reviewed_list:
  - .env.example
  - docker-compose.yml
  - modules/pathfinder/__init__.py
  - modules/pathfinder/app/__init__.py
  - modules/pathfinder/app/main.py
  - modules/pathfinder/compose.yml
  - modules/pathfinder/Dockerfile
  - modules/pathfinder/pyproject.toml
  - modules/pathfinder/tests/__init__.py
  - modules/pathfinder/tests/test_healthz.py
  - modules/pathfinder/tests/test_registration.py
  - sentinel-core/app/config.py
  - sentinel-core/app/main.py
  - sentinel-core/app/routes/modules.py
  - sentinel-core/tests/test_cors.py
  - sentinel-core/tests/test_modules.py
  - sentinel.sh
findings:
  critical: 0
  warning: 3
  info: 2
  total: 5
status: issues_found
---

# Phase 28: Code Review Report

**Reviewed:** 2026-04-21
**Depth:** standard
**Files Reviewed:** 17
**Status:** issues_found

## Summary

Phase 28 delivers the pf2e-module skeleton (FastAPI service with startup registration and `/healthz` endpoint) and CORS middleware configuration for Sentinel Core. The architecture is clean: middleware ordering is correctly documented (LIFO with CORSMiddleware outermost to intercept OPTIONS before auth), the registration retry logic is well-structured with deterministic backoff, and the secret handling follows the established Docker secrets pattern.

Three warnings require attention: incomplete `httpx` exception coverage in the proxy routes (non-`ConnectError` transport errors will surface as 500s instead of 503s), a dead module-level variable in the pf2e module that creates a misleading code path, and an environment mutation in a test that can cause ordering-dependent failures. Two info items cover a bare `except` on JSON decode and the test environment mutation pattern.

## Warnings

### WR-01: Proxy catches only `ConnectError` — other transport errors return 500

**File:** `sentinel-core/app/routes/modules.py:81-82` (and `:114-116`)
**Issue:** Both `get_proxy_module` and `proxy_module` catch only `httpx.ConnectError`. Other network-level failures — `httpx.TimeoutException`, `httpx.RemoteProtocolError`, `httpx.ReadError`, and the parent `httpx.TransportError` — are not caught and will propagate as unhandled exceptions, producing a 500 response with a raw Python traceback rather than the consistent `{"error": "module unavailable"}` 503.

Callers (e.g. Foundry VTT) should receive 503 for any module-unreachability condition, not 500 for a subset of them.

**Fix:**
```python
    except (httpx.ConnectError, httpx.TimeoutException, httpx.TransportError):
        raise HTTPException(status_code=503, detail={"error": "module unavailable"})
```
Apply to both the `get_proxy_module` and `proxy_module` handlers (lines 81-82 and 115-116).

---

### WR-02: Dead module-level variable `SENTINEL_API_KEY` in pf2e module

**File:** `modules/pathfinder/app/main.py:27` and `:50`
**Issue:** Line 27 reads `SENTINEL_API_KEY = os.getenv("SENTINEL_API_KEY", "")` into a module-level constant. Line 50, inside `_register_with_retry`, re-reads the same env var directly with `os.getenv("SENTINEL_API_KEY", "")` — the module-level constant is never referenced. The constant is dead code and creates the misleading impression that changing `SENTINEL_API_KEY` at import time controls the header value, when it actually has no effect.

**Fix:** Remove the module-level variable and keep a single source of truth, or use the constant consistently:
```python
# Option A: remove the module-level variable; keep the inline read
# (delete line 27)

# Option B: use the constant in the header
headers={"X-Sentinel-Key": SENTINEL_API_KEY},
```
Option B is preferred — it removes the redundant `os.getenv` call inside the hot retry loop and makes the intent clear.

---

### WR-03: Test permanently mutates `SENTINEL_API_KEY` environment variable

**File:** `modules/pathfinder/tests/test_registration.py:68-69`
**Issue:** `test_registration_payload_correct` sets `os.environ["SENTINEL_API_KEY"] = "test-sentinel-key"` using direct assignment (not `setdefault`). Unlike `setdefault`, this overwrites the value even if it was already set by a previous test. If this test runs before `test_healthz_returns_ok` (which imports `app.main` and captures the key at module-load time for the `app.main.app` singleton), the key seen by the lifespan may differ from the one expected in `test_cors.py`'s `AUTH_HEADERS`.

pytest does not guarantee intra-module test order to be stable across runs in all configurations.

**Fix:** Use a `monkeypatch` fixture or restore the original value after the test:
```python
async def test_registration_payload_correct(monkeypatch):
    monkeypatch.setenv("SENTINEL_API_KEY", "test-sentinel-key")
    from app.main import _register_with_retry, REGISTRATION_PAYLOAD
    ...
```

## Info

### IN-01: Bare `except Exception` on JSON decode silently drops decode errors

**File:** `sentinel-core/app/routes/modules.py:77-79` and `:111-113`
**Issue:** The pattern `try: content = resp.json() except Exception: content = {"body": resp.text}` catches every exception from `resp.json()` — including `MemoryError` and unexpected `AttributeError` — and silently substitutes a fallback. This is acceptable behavior in production, but using bare `except Exception` obscures the intent. The only expected failure mode is `json.JSONDecodeError` (or `httpx`'s wrapper around it).

**Fix:**
```python
try:
    content = resp.json()
except Exception:  # noqa: BLE001  ← document the intent, or narrow:
    content = {"body": resp.text}
# Preferred: catch the specific exception
try:
    content = resp.json()
except ValueError:
    content = {"body": resp.text}
```
`resp.json()` raises `json.JSONDecodeError` (a subclass of `ValueError`) on parse failure.

---

### IN-02: `test_cors.py` fixture sets `app.state` on a singleton after lifespan has already run

**File:** `sentinel-core/tests/test_cors.py:17-24`
**Issue:** `app` is imported at module level (line 13), which triggers `config.py`'s `settings = Settings()` at import time. The `setup_app_state` autouse fixture then writes directly to `app.state.*` before each test. This is a valid pattern since `ASGITransport` does not re-run the lifespan, but it means the tests bypass the real startup path entirely. If a future route handler accesses `app.state.injection_filter` or `app.state.output_scanner` (which the fixture does not mock), the test will raise `AttributeError` with no obvious cause.

**Fix:** Either extend the fixture to mock all `app.state` attributes that routes access, or document the known-missing state explicitly:
```python
@pytest.fixture(autouse=True)
def setup_app_state():
    app.state.module_registry = {}
    app.state.http_client = MagicMock()
    app.state.obsidian_client = MagicMock()
    app.state.ai_provider_name = "lmstudio"
    app.state.settings = MagicMock()
    app.state.settings.pi_harness_url = "http://pi-harness:3000"
    # Add these to guard against future route additions:
    app.state.injection_filter = MagicMock()
    app.state.output_scanner = MagicMock()
```

---

_Reviewed: 2026-04-21_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
