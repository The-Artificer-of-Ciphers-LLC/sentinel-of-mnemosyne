---
phase: 35-foundry-vtt-event-ingest
reviewed: 2026-04-25T00:00:00Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - interfaces/discord/bot.py
  - interfaces/discord/tests/conftest.py
  - interfaces/discord/tests/test_discord_foundry.py
  - interfaces/discord/tests/test_thread_persistence.py
  - modules/pathfinder/app/main.py
  - modules/pathfinder/compose.yml
  - modules/pathfinder/foundry-client/sentinel-connector.js
  - modules/pathfinder/tests/test_foundry.py
  - modules/pathfinder/tests/test_registration.py
  - .env.example
findings:
  critical: 2
  warning: 3
  info: 2
  total: 7
status: issues_found
---

# Phase 35: Code Review Report

**Reviewed:** 2026-04-25
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

Phase 35 introduces Foundry VTT event ingest: `sentinel-connector.js` delivers roll/chat events to the pf2e-module via a webhook-first hybrid path, and `app/main.py` adds `PNACORSMiddleware` to permit browser fetch from Forge VTT (Private Network Access spec compliance).

The gap-closure changes in Plan 35-06 contain two critical defects. The `PNACORSMiddleware` subclass both duplicates functionality already present in Starlette 1.0.0 (the installed version) and places the PNA header in `simple_headers` — the non-preflight response headers — whereas the PNA spec requires the header only on the `OPTIONS` preflight response. Starlette 1.0.0 already handles the correct placement via its native `allow_private_network` constructor parameter. Additionally the `AbortController` timer in `sentinel-connector.js` is not cleared in a `finally` block, so a non-abort exception during the fetch leaves the 3-second timer running against a discarded request.

---

## Critical Issues

### CR-01: `PNACORSMiddleware` puts PNA header on wrong response type; Starlette 1.0.0 already handles it natively

**File:** `modules/pathfinder/app/main.py:231-252`

**Issue:** Starlette 1.0.0 (installed version confirmed) accepts `allow_private_network=True` as a native constructor parameter and emits `Access-Control-Allow-Private-Network: true` inside `preflight_response()` at line 139 of Starlette's cors.py — exactly where the WICG PNA spec requires it (only on the `OPTIONS` preflight).

The `PNACORSMiddleware` subclass additionally injects this header into `self.simple_headers` (line 235). `simple_headers` is applied to all non-OPTIONS responses (Starlette cors.py line 163). The net effect is:

1. The PNA header is correctly sent on `OPTIONS` preflights by native Starlette logic (because `allow_private_network=True` is passed through `**kwargs`).
2. The subclass additionally stamps the header onto every `POST` and `GET` simple response, which is a PNA spec violation.
3. The stated motivation (fill in a missing Starlette feature) no longer applies to Starlette 1.0.0.

**Fix:** Delete `PNACORSMiddleware` entirely. Replace the `add_middleware` call with native `CORSMiddleware`:

```python
# Remove the subclass entirely.
# Replace add_middleware call with:
from starlette.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://forge-vtt.com",
        "http://localhost:30000",
        "http://localhost:8000",
        "http://127.0.0.1:30000",
        "http://127.0.0.1:8000",
    ],
    allow_origin_regex=r"https://[a-zA-Z0-9-]+\.forge-vtt\.com",  # see WR-01
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Sentinel-Key"],
    allow_credentials=False,
    allow_private_network=True,
)
```

---

### CR-02: `clearTimeout` is only called on the happy path — timer leaks on network error

**File:** `modules/pathfinder/foundry-client/sentinel-connector.js:198-203`

**Issue:** `clearTimeout(timeoutId)` is inside the `try` block after `await fetch(...)`. When the fetch throws (TypeError for network/CORS block, or AbortError when the timer already fired), execution jumps to `catch` without calling `clearTimeout`. In the TypeError case (network blocked), the 3-second timer is still live when the catch block runs. Three seconds later it calls `controller.abort()` on a request that has already been abandoned. In a long-running browser session such as FoundryVTT this causes a spurious abort call per forwarded event. More importantly, if the server returns a non-2xx status (4xx/5xx), `fetch()` resolves rather than throws, so `clearTimeout` is called and `return` exits — silently dropping the event without a fallback (see WR-02 for that related bug).

**Fix:** Move `clearTimeout` to a `finally` block:

```javascript
const controller = new AbortController();
const timeoutId = setTimeout(() => controller.abort(), SENTINEL_TIMEOUT_MS);
try {
  const response = await fetch(`${sentinelUrl}/modules/pathfinder/foundry/event`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Sentinel-Key': sentinelKey,
    },
    body: JSON.stringify(payload),
    signal: controller.signal,
  });
  if (!response.ok) {
    throw new Error(`Sentinel returned HTTP ${response.status}`);
  }
  return; // success — no fallback needed
} catch (err) {
  console.warn('[sentinel-connector] Sentinel POST failed, falling back to webhook:', err.message);
} finally {
  clearTimeout(timeoutId);
}
```

---

## Warnings

### WR-01: Wildcard subdomain origin `https://*.forge-vtt.com` is not supported by Starlette CORS and is silently ignored

**File:** `modules/pathfinder/app/main.py:242`

**Issue:** Starlette's `CORSMiddleware.is_allowed_origin()` performs exact string membership (`origin in self.allow_origins`). The string `"https://*.forge-vtt.com"` is never equal to an actual origin like `"https://user123.forge-vtt.com"`, so all Forge subdomains are silently rejected. The entry has zero effect and creates a false impression of Forge support. The fix is to use `allow_origin_regex` as shown in CR-01's fix above.

**Fix:** Remove `"https://*.forge-vtt.com"` from `allow_origins` and add `allow_origin_regex=r"https://[a-zA-Z0-9-]+\.forge-vtt\.com"` (anchored so it cannot match `evil.forge-vtt.com.attacker.com`).

---

### WR-02: HTTP 4xx/5xx from Sentinel is treated as success — event silently dropped without webhook fallback

**File:** `modules/pathfinder/foundry-client/sentinel-connector.js:197-199`

**Issue:** `fetch()` in a browser does not reject on HTTP error status codes — it resolves with a `Response` object whose `ok` property is `false`. After `await fetch(...)` the code calls `clearTimeout(timeoutId); return;` without checking `response.ok`. A 401 (bad API key), 422 (validation error), or 503 (module down) causes `postEvent` to return successfully with no fallback to the Discord webhook. The event is silently dropped.

**Fix:** Add a `response.ok` guard as shown in the CR-02 fix block above.

---

### WR-03: `_handle_internal_notify` calls `build_foundry_roll_embed` unconditionally — chat events produce malformed roll embeds

**File:** `interfaces/discord/bot.py:1394`

**Issue:** The internal notify handler calls `build_foundry_roll_embed(data)` for every incoming event. `sentinel-connector.js` sends both `event_type: "roll"` and `event_type: "chat"` to the same endpoint. When a chat event arrives (e.g., from a chat-prefix trigger with `sentinelBaseUrl` set), `build_foundry_roll_embed` is invoked with a dict that contains `content` but lacks `outcome`, `roll_total`, `dc`, and `roll_type`. The function defaults all missing fields to `"?"` or `""` and produces a confusing embed with `"🎲  | ? (check)"` as the title rather than any useful chat display.

**Fix:**
```python
event_type = data.get("event_type", "roll")
if event_type == "roll":
    embed = build_foundry_roll_embed(data)
else:
    # chat event — simple embed
    embed = discord.Embed(
        title=f"[Chat] {data.get('actor_name', 'DM')}",
        description=(data.get("content") or "")[:4000],
        color=discord.Color.blue(),
    )
```

---

## Info

### IN-01: `test_thread_persistence.py` duplicates the discord stub already provided by `conftest.py`

**File:** `interfaces/discord/tests/test_thread_persistence.py:14-45`

**Issue:** `test_thread_persistence.py` contains a full inline discord stub identical to the one in `conftest.py`. The conftest comment explicitly flags this pattern as prohibited ("Phase 32-05 Rule 3 fix — centralise here; never add per-file"). The duplicate uses `sys.modules.setdefault` so it is currently harmless (conftest wins), but it adds 30 lines of dead code and will confuse anyone extending the stub.

**Fix:** Remove lines 14–57 of `test_thread_persistence.py` (the inline stub + `sys.modules.setdefault` calls + path insertions). The conftest already handles all of this. Keep only the `os.environ.setdefault` calls if any are not already in conftest.

---

### IN-02: `.env.example` instructs storing the Discord webhook URL "for reference" in `.env`

**File:** `.env.example:127`

**Issue:** The comment `# DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/{id}/{token}` tells the user to store the webhook URL in `.env` for reference. Discord webhook URLs contain a secret token in the path. Despite the top-of-file warning not to commit `.env`, storing secrets there increases accidental-commit risk. The comment should redirect to `secrets/`.

**Fix:**
```
# discordWebhookUrl is configured in Foundry module settings — do NOT store it in .env.
# The URL embeds a secret token. If you need a local record, add it to secrets/discord_webhook_url.
```

---

_Reviewed: 2026-04-25_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
