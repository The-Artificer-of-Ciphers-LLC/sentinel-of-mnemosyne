---
phase: 35-foundry-vtt-event-ingest
reviewed: 2026-04-25T12:00:00Z
depth: standard
files_reviewed: 11
files_reviewed_list:
  - .env.example
  - interfaces/discord/bot.py
  - interfaces/discord/tests/conftest.py
  - interfaces/discord/tests/test_discord_foundry.py
  - interfaces/discord/tests/test_thread_persistence.py
  - modules/pathfinder/app/main.py
  - modules/pathfinder/compose.yml
  - modules/pathfinder/foundry-client/sentinel-connector.js
  - modules/pathfinder/tests/test_foundry.py
  - modules/pathfinder/tests/test_registration.py
  - scripts/uat_phase35.sh
findings:
  critical: 2
  warning: 4
  info: 1
  total: 7
status: issues_found
---

# Phase 35: Code Review Report

**Reviewed:** 2026-04-25T12:00:00Z
**Depth:** standard
**Files Reviewed:** 11
**Status:** issues_found

## Summary

Phase 35 adds Foundry VTT event ingest: `sentinel-connector.js` posts roll and chat events to the pf2e-module, which narrates via LLM and notifies the Discord bot through an internal aiohttp endpoint. The implementation is structurally sound with one exception: the internal notification server in `bot.py` is bound to `127.0.0.1` (loopback), making it unreachable from the `pf2e-module` container over the Docker bridge network. This completely breaks the Discord notification pipeline in deployed environments. There is also a type contract mismatch where `outcome=None` (valid for hidden-DC rolls per CR-01 comments) is passed to a function that treats `outcome` as `str`, producing a malformed LLM prompt. Two JavaScript issues — a timer not cleared in `finally` and HTTP error responses not triggering the webhook fallback — are confirmed and need fixes.

---

## Critical Issues

### CR-01: Internal aiohttp server bound to `127.0.0.1` — unreachable from `pf2e-module` container

**File:** `interfaces/discord/bot.py:1365`

**Issue:** `web.TCPSite(self._internal_runner, "127.0.0.1", internal_port)` binds the notification endpoint to the loopback interface inside the `discord-bot` container. The `pf2e-module` container calls `http://discord-bot:8001/internal/notify` over the Docker bridge network. Docker bridge traffic arrives on the container's eth0 interface, not loopback. The connection is refused for every roll event. Every `notify_discord_bot()` call silently logs a warning and Discord never receives any Foundry event notification — the entire Phase 35 FVT-02/FVT-03 notification path is dead in Docker deployment.

**Fix:** Bind to `0.0.0.0` so the container's network interface accepts connections from other containers. The port is unexposed to the host network (no `ports:` mapping in `discord-bot`'s compose service), so binding broadly within Docker does not increase the external attack surface.

```python
# bot.py:1365 — change "127.0.0.1" to "0.0.0.0"
site = web.TCPSite(self._internal_runner, "0.0.0.0", internal_port)
```

If strict isolation between containers is desired, the alternative is to use a Docker internal network shared only between `discord-bot` and `pf2e-module` — but `0.0.0.0` with no host port mapping achieves the same security posture more simply.

---

### CR-02: `generate_foundry_narrative` receives `None` for `outcome` — type mismatch produces garbled LLM prompt

**File:** `modules/pathfinder/app/routes/foundry.py:98`, `modules/pathfinder/app/foundry.py:42`

**Issue:** `FoundryRollEvent.outcome` is `Optional[str] = None` (routes/foundry.py:46). On hidden-DC rolls the JS module sends `outcome: "unknown"` or omits the field entirely (sentinel-connector.js:125). When `outcome` is `None`, `_handle_roll` passes it directly to `generate_foundry_narrative(outcome=event.outcome, ...)`. The function signature declares `outcome: str` (foundry.py:42), but Python does not enforce this at runtime.

Inside `generate_foundry_narrative`:
- `OUTCOME_LABELS.get(None, None)` → returns `None` (not in dict, default is second arg which defaults to `None`)
- The f-string becomes: `"Outcome: None."` in the LLM prompt

`build_narrative_fallback` handles `None` correctly (foundry.py:96: `outcome.capitalize() if outcome else "Roll"`), but it is only called when `generate_foundry_narrative` returns `""` — the LLM still receives the malformed prompt first.

**Fix:** Annotate the signature correctly and add a None guard:

```python
# foundry.py:42 — update signature
async def generate_foundry_narrative(
    actor_name: str,
    target_name: str | None,
    item_name: str | None,
    outcome: str | None,        # was: str
    roll_total: int,
    dc: int | None,
    model: str,
    api_base: str | None = None,
) -> str:
    outcome_label = OUTCOME_LABELS.get(outcome or "", outcome.capitalize() if outcome else "unknown")
    # rest unchanged
```

---

## Warnings

### WR-01: `clearTimeout` not in `finally` — timer leaks when `fetch()` throws

**File:** `modules/pathfinder/foundry-client/sentinel-connector.js:187-206`

**Issue:** `clearTimeout(timeoutId)` is only called in the `try` block after `await fetch(...)` returns. When `fetch()` throws (TypeError for network error, AbortError when the timer fires first), execution jumps directly to `catch` without clearing the timer. In the TypeError case (e.g., network blocked by CORS), a 3-second-stale `setTimeout` callback fires `controller.abort()` on an already-abandoned request. In a long-running Foundry session this accumulates per-roll timer orphans.

**Fix:**

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
  if (!response.ok) throw new Error(`Sentinel returned HTTP ${response.status}`);
  return; // success — no fallback needed
} catch (err) {
  console.warn('[sentinel-connector] Sentinel POST failed, falling back to webhook:', err.message);
} finally {
  clearTimeout(timeoutId);
}
```

---

### WR-02: HTTP 4xx/5xx from Sentinel treated as success — event silently dropped, no webhook fallback

**File:** `modules/pathfinder/foundry-client/sentinel-connector.js:197-199`

**Issue:** `fetch()` resolves (does not throw) on 4xx/5xx HTTP responses. The current code calls `clearTimeout(timeoutId); return;` without checking `response.ok`. A 401 Unauthorized (wrong API key), 422 Unprocessable Entity (schema mismatch), or 503 Service Unavailable causes `postEvent` to silently return as if the event was delivered. The webhook fallback is never attempted. The fix is to throw on non-ok status as shown in the WR-01 fix block above.

---

### WR-03: `_handle_internal_notify` always calls `build_foundry_roll_embed` — chat events produce malformed roll embeds

**File:** `interfaces/discord/bot.py:1394-1399`

**Issue:** `bot.py:1394` checks `if event_type != "roll": return 200` before calling `build_foundry_roll_embed`. This means chat events are silently dropped (status 200 returned without sending anything to Discord). However, `sentinel-connector.js` does forward chat events to the Sentinel endpoint (`postEvent` is called for both roll and chat in lines 100-107). The phase 35 MVP intentionally omits chat notification (`_handle_chat` in routes/foundry.py:147 returns ok without notifying), but the internal notify handler also needs to handle the eventual chat path gracefully.

The current code on line 1394-1397 silently ignores non-roll events. If the pf2e-module is later updated to notify chat events (chat events arrive at `/internal/notify` with `event_type: "chat"`), the bot will log a warning and return 200 without displaying anything — a silent no-op rather than a useful display.

**Fix:** Document the intentional no-op and add a simple chat embed path for future use:

```python
event_type = data.get("event_type", "roll")
if event_type == "roll":
    embed = build_foundry_roll_embed(data)
elif event_type == "chat":
    # Phase 35 MVP: route chat events to Discord too
    embed = discord.Embed(
        title=f"[Chat] {data.get('actor_name', 'DM')}",
        description=(data.get("content") or "")[:4000],
        color=discord.Color.blue(),
    )
else:
    logger.info("_handle_internal_notify: unsupported event_type %r — ignoring", event_type)
    return web.Response(status=200)
```

---

### WR-04: `min(ALLOWED_CHANNEL_IDS)` selects notification channel by snowflake age — wrong if channels were created out-of-order

**File:** `interfaces/discord/bot.py:1382`

**Issue:** `channel_id = min(ALLOWED_CHANNEL_IDS) if ALLOWED_CHANNEL_IDS else None` selects the numerically smallest Discord channel ID from the allowlist. Discord snowflake IDs encode creation timestamp, so `min()` picks the oldest channel. If a server has multiple allowed channels configured and the DM channel was created after a general channel, roll notifications go to the wrong channel. The comment says "WR-02: deterministic" — determinism is correct but the selection criterion is wrong.

**Fix:** Add a dedicated `DISCORD_NOTIFY_CHANNEL_ID` env var for the Foundry roll notification target, falling back to `min()` only if absent:

```python
# bot.py — near ALLOWED_CHANNEL_IDS parsing
NOTIFY_CHANNEL_ID_RAW = os.environ.get("DISCORD_NOTIFY_CHANNEL_ID", "")
NOTIFY_CHANNEL_ID: int | None = int(NOTIFY_CHANNEL_ID_RAW) if NOTIFY_CHANNEL_ID_RAW.isdigit() else None

# in _handle_internal_notify:
channel_id = NOTIFY_CHANNEL_ID or (min(ALLOWED_CHANNEL_IDS) if ALLOWED_CHANNEL_IDS else None)
```

Alternatively, document in `.env.example` that `DISCORD_ALLOWED_CHANNELS` should list the notification channel first and change `min()` to `next(iter(...))` with a consistent ordering guarantee.

---

## Info

### IN-01: `test_discord_foundry.py` has no async test markers but `asyncio_mode = "auto"` in pyproject.toml covers it

**File:** `interfaces/discord/tests/test_discord_foundry.py:22-62`

**Issue:** The two test functions `test_embed_critical_success` and `test_embed_hidden_dc` are declared `async def` without `@pytest.mark.asyncio`. This is intentional because `asyncio_mode = "auto"` in `interfaces/discord/pyproject.toml:21` applies the marker automatically. This is not a bug, but worth noting for reviewers: the tests exercise synchronous embed-builder functions via `async def` test functions, which is unnecessary overhead. Sync functions do not need async test wrappers.

**Fix (optional):** Convert to `def` (non-async) — `build_foundry_roll_embed` is a pure synchronous function. Reduces cognitive overhead for future contributors.

```python
def test_embed_critical_success():
    ...

def test_embed_hidden_dc():
    ...
```

---

_Reviewed: 2026-04-25T12:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
