---
phase: 27-architecture-pivot
reviewed: 2026-04-20T00:00:00Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - docker-compose.yml
  - docs/ARCHITECTURE-Core.md
  - docs/PRD-Sentinel-of-Mnemosyne.md
  - interfaces/discord/bot.py
  - interfaces/discord/tests/test_subcommands.py
  - interfaces/discord/tests/test_thread_persistence.py
  - pi-harness/compose.yml
  - sentinel-core/app/main.py
  - sentinel-core/app/routes/modules.py
  - sentinel-core/compose.yml
  - sentinel-core/tests/test_modules.py
  - sentinel.sh
findings:
  critical: 1
  warning: 5
  info: 4
  total: 10
status: issues_found
---

# Phase 27: Code Review Report

**Reviewed:** 2026-04-20T00:00:00Z
**Depth:** standard
**Files Reviewed:** 12
**Status:** issues_found

## Summary

This review covers the Phase 27 Path B architecture pivot: the module API gateway in `sentinel-core/app/routes/modules.py`, the Discord bot interface, Compose infrastructure, and documentation updates. The core chat path and lifespan wiring in `main.py` are well-structured. The module gateway is clean. The primary concerns are a security issue in the proxy endpoint (no `X-Sentinel-Key` forwarded to modules), a data-loss risk when the module registry is in-memory with no re-registration guarantee, missing pytest marks causing async tests to run synchronously (tests silently pass without executing), a `discord-bot-token` secret wired at top-level compose but absent from `sentinel-core/compose.yml` where it would never be used, and minor issues with `sentinel.sh`'s unquoted variable expansion.

---

## Critical Issues

### CR-01: Async test functions missing `@pytest.mark.asyncio` — tests never actually run

**File:** `sentinel-core/tests/test_modules.py:45-104` and `interfaces/discord/tests/test_subcommands.py:60-103` and `interfaces/discord/tests/test_thread_persistence.py:79-142`

**Issue:** All async test functions (`test_register_module`, `test_proxy_module`, `test_proxy_module_unavailable`, `test_proxy_unknown_module`, `test_register_requires_auth`, `test_help_subcommand_returns_help_text`, `test_known_subcommand_calls_core`, etc.) are defined as `async def` but have no `@pytest.mark.asyncio` decorator and no `asyncio_mode = "auto"` in a `pytest.ini` / `pyproject.toml`. Without one of these, pytest collects the coroutine functions as tests but never awaits them — each test "passes" by returning a coroutine object (truthy), producing a false-green suite. This means the entire Phase 27 test suite (SC-1 through SC-4 and thread-persistence assertions) has never actually executed.

**Fix:** Add `asyncio_mode = "auto"` to `pyproject.toml` (or `pytest.ini`):

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

This is the project-wide fix. Alternatively, decorate each async test individually:

```python
import pytest

@pytest.mark.asyncio
async def test_register_module():
    ...
```

The `asyncio_mode = "auto"` approach is preferred as it avoids per-test decoration across three test files.

---

## Warnings

### WR-01: Module proxy does not forward `X-Sentinel-Key` to module containers

**File:** `sentinel-core/app/routes/modules.py:54-55`

**Issue:** The proxy handler forwards the raw request body to the target module but strips all headers, including `X-Sentinel-Key`. If module containers implement their own auth check (per the spec in `ARCHITECTURE-Core.md` §3.4 — all modules receive `SENTINEL_API_KEY`), they will receive unauthenticated requests from sentinel-core and may reject them with 401, surfacing as a silent 503 to the caller.

```python
# current — no auth header forwarded
resp = await request.app.state.http_client.post(
    target_url,
    content=body,
    headers={"Content-Type": "application/json"},
)
```

**Fix:** Forward the sentinel key so modules can validate inbound proxied calls:

```python
resp = await request.app.state.http_client.post(
    target_url,
    content=body,
    headers={
        "Content-Type": "application/json",
        "X-Sentinel-Key": request.app.state.settings.sentinel_api_key,
    },
)
```

---

### WR-02: In-memory module registry clears on sentinel-core restart with no guaranteed re-registration

**File:** `sentinel-core/app/main.py:173-174` and `sentinel-core/app/routes/modules.py:36`

**Issue:** The module registry is initialised as an empty dict at startup (`app.state.module_registry = {}`). ARCHITECTURE-Core.md §11 open question #1 acknowledges this but marks it as v0.5 scope. The problem is functional right now: if sentinel-core restarts (crash, redeploy, OOM) while module containers are running, all modules disappear from the registry. The proxy returns 404 for every module request until each module container independently restarts. In the Docker Compose `unless-stopped` setup, sentinel-core will restart but module containers will not automatically re-register — they only call `POST /modules/register` in their own lifespan startup.

**Fix:** Two options — pick one:

Option A (immediate, no code): Add `depends_on: [sentinel-core]` with condition `service_healthy` to every module's compose fragment. This causes Docker Compose to restart dependent modules when sentinel-core restarts, triggering re-registration. Document this as the required pattern in `ARCHITECTURE-Core.md` §3.4 module compose spec.

Option B (robust): Add a `/modules/registered` GET endpoint that returns currently registered modules, and add a startup re-registration loop to each module that polls sentinel-core until registration succeeds.

Option A is the correct near-term fix given the current architecture.

---

### WR-03: `sentinel.sh` passes `$PROFILE_FLAGS` unquoted — breaks on shell word splitting

**File:** `sentinel.sh:27`

**Issue:** `PROFILE_FLAGS` is built as a string (`"$PROFILE_FLAGS --profile $p"`) and then expanded unquoted in the final `docker compose $PROFILE_FLAGS` call. This is safe when profile names are simple alphanumeric strings (which they currently are), but the pattern is fragile — any profile name or future flag containing a space would cause incorrect word splitting. More immediately, if `PROFILES` is empty, `PROFILE_FLAGS` is an empty string and `docker compose  "${ARGS[@]}"` passes a leading empty token to docker compose on some shells.

**Fix:** Use an array instead of a string for flags:

```bash
PROFILE_FLAGS=()
for p in "${PROFILES[@]}"; do
  PROFILE_FLAGS+=("--profile" "$p")
done

docker compose "${PROFILE_FLAGS[@]}" "${ARGS[@]}"
```

---

### WR-04: `discord_bot_token` secret declared at top level but never mounted into any service

**File:** `docker-compose.yml:26` and `sentinel-core/compose.yml:18-27`

**Issue:** `discord_bot_token` is declared in the top-level `secrets:` block of `docker-compose.yml` but is not listed in the `secrets:` section of `sentinel-core/compose.yml`. Sentinel Core does not need the Discord token — that is correct. However, `interfaces/discord/compose.yml` (included via the `include` directive) must mount this secret for the Discord container. If that file is absent or does not reference `discord_bot_token`, the secret file is declared but never consumed, which is harmless but confusing. More seriously, if the Discord compose fragment does not mount `discord_bot_token`, then `bot.py:73` (`_read_secret("discord_bot_token", ...)`) falls through to the env var fallback, silently degrading to a less secure pattern. Verify that `interfaces/discord/compose.yml` mounts `discord_bot_token` under its service's `secrets:` key.

**Fix:** Confirm `interfaces/discord/compose.yml` contains:

```yaml
services:
  discord-interface:
    secrets:
      - discord_bot_token
      - sentinel_api_key
```

If it does not, add these entries. The secret declaration in the top-level file is correct; the mount in the interface service is what makes Docker deliver it to `/run/secrets/discord_bot_token`.

---

### WR-05: `proxy_module` silently returns module error responses without propagating non-2xx status codes meaningfully

**File:** `sentinel-core/app/routes/modules.py:59`

**Issue:** When a registered module returns a non-2xx response (e.g., 422 validation error, 400 bad request), the proxy returns that status code to the caller. This is intentional and correct. However, `resp.json()` is called unconditionally — if the module returns a non-JSON response body (e.g., a plain-text 500 error from uvicorn's default error handler), this raises a `json.JSONDecodeError` that is not caught, producing an unhandled 500 from sentinel-core with no useful error detail.

```python
# current — json() raises if module returns plain text
return JSONResponse(content=resp.json(), status_code=resp.status_code)
```

**Fix:**

```python
try:
    content = resp.json()
except Exception:
    content = {"error": "module returned non-JSON response", "body": resp.text[:500]}
return JSONResponse(content=content, status_code=resp.status_code)
```

---

## Info

### IN-01: `_call_core` creates a new `httpx.AsyncClient` per call — bypasses the shared client

**File:** `interfaces/discord/bot.py:173-174`

**Issue:** `_call_core` opens `httpx.AsyncClient()` as a context manager on every invocation. The module docstring says the client "owns no persistent connection state," which is true — but creating a new client per call means no connection pooling across calls to sentinel-core. For a personal single-user bot this is negligible, but it contradicts the project's own CLAUDE.md guidance ("Use `httpx.AsyncClient()` as a context manager for connection pooling"). The module-level `_sentinel_client` already holds the URL and key; it just needs a shared http_client passed in.

**Fix:** Create a module-level `httpx.AsyncClient` alongside `_sentinel_client` and reuse it:

```python
_http_client = httpx.AsyncClient(timeout=200.0)

async def _call_core(user_id: str, message: str) -> str:
    return await _sentinel_client.send_message(user_id, message, _http_client)
```

Close it in the bot's `close()` or `on_close` handler.

---

### IN-02: `on_ready` accesses `self.user.id` without null guard

**File:** `interfaces/discord/bot.py:335`

**Issue:** `self.user` can be `None` before the bot is fully authenticated. While `on_ready` is only called after authentication completes (making `self.user` non-None in practice), the type annotation for `discord.Client.user` is `Optional[ClientUser]`, so accessing `.id` directly produces a mypy warning and could theoretically raise `AttributeError` if the event fires in an unexpected state.

**Fix:**

```python
async def on_ready(self) -> None:
    if self.user:
        logger.info(f"Sentinel bot ready: {self.user} (id={self.user.id})")
    else:
        logger.info("Sentinel bot ready (user not yet available)")
```

---

### IN-03: PRD §6.6 references deprecated `alpaca-trade-api` package

**File:** `docs/PRD-Sentinel-of-Mnemosyne.md:396`

**Issue:** The trading module section ends with "Dependencies: Alpaca Python SDK (`alpaca-trade-api` or the newer `alpaca-py`)". CLAUDE.md explicitly states `alpaca-trade-api` is deprecated and must never be used — use `alpaca-py` only. The PRD is still listing the deprecated option as valid.

**Fix:** Update the dependencies line in PRD §6.6:

```
Dependencies: alpaca-py (official Alpaca SDK — alpaca-trade-api is deprecated, do not use)
```

---

### IN-04: ARCHITECTURE-Core.md §8.5 wrapper script example uses deprecated `-f` flag stacking

**File:** `docs/ARCHITECTURE-Core.md:644-663`

**Issue:** The sentinel.sh example in §8.5 of the architecture doc shows the old `-f docker-compose.yml -f interfaces/discord/docker-compose.override.yml` pattern. The actual `sentinel.sh` and the project's CLAUDE.md both mandate the `include` directive approach (Compose v2.20+), not `-f` stacking. This stale example will mislead anyone writing new module compose fragments.

**Fix:** Update §8.5 to reflect the actual `include`-based approach:

```bash
# Current (actual sentinel.sh behaviour):
# ./sentinel.sh --discord up -d
# Compose uses include: directive in docker-compose.yml — no -f stacking.
```

The example code block in §8.5 should be replaced with a description matching how `sentinel.sh` actually works.

---

_Reviewed: 2026-04-20T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
