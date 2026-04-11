---
phase: 25
status: findings
critical_count: 0
high_count: 1
medium_count: 3
low_count: 3
---

# Phase 25 Code Review

## Summary

Reviewed 13 source files changed across Phase 25 sub-plans 04–07: shared library extraction
(`shared/sentinel_client.py`), status routes, Discord bot and iMessage bridge migrations,
jailbreak baseline (`security/pentest/jailbreak_baseline.py`), injection filter expansion,
and MessageEnvelope model extension.

Overall quality is high. The shared client extraction is clean, error surfaces are well-
handled, and the injection filter normalization pipeline is correct. One high-severity bug
was found in the iMessage attributedBody decoder — the function will silently return `None`
for all real Ventura+ messages because it looks for `NS.string` at the wrong level of the
NSKeyedArchiver plist structure. Three medium-severity issues cover a month-boundary date
bug, a path-traversal risk in the debug context endpoint, and confusing suppression logic in
`_safe_request`. Three low-severity quality items round out the findings.

---

## Findings

### HIGH — `_decode_attributed_body` always returns None for real macOS Ventura blobs

**File:** `interfaces/imessage/bridge.py:58-59`

**Finding:** The function calls `plistlib.loads(blob)` and then `plist.get("NS.string", None)`.
Real macOS `attributedBody` blobs are NSKeyedArchiver archives. When decoded by `plistlib`,
the root dictionary has keys `$version`, `$archiver`, `$top`, and `$objects`. The actual text
string — accessed via the `NS.string` key on an `NSAttributedString` entry — lives inside the
`$objects` array at an index referenced by `$top['root']`, not at the root level.

`plist.get("NS.string", None)` on the root dict will always return `None` for any real
`attributedBody` blob from `chat.db`. The function silently falls back to `None`, messages
are skipped, and no log entry is produced at warning level. The tests pass because they use
a synthetic plist `{"NS.string": text}` that is not the real NSKeyedArchiver format.

The net result is that all Ventura+ messages whose `text` column is `NULL` are silently
dropped. This is the exact scenario the feature was built to handle.

**Fix:**

```python
def _decode_attributed_body(blob: bytes) -> str | None:
    """Decode macOS Ventura+ NSKeyedArchiver attributedBody blob to plain text."""
    if not blob:
        return None
    try:
        import plistlib
        plist = plistlib.loads(blob)
        # NSKeyedArchiver format: text is inside $objects, not at root.
        # Walk $objects to find the NSAttributedString entry that holds NS.string.
        objects = plist.get("$objects", [])
        for obj in objects:
            if isinstance(obj, dict):
                text = obj.get("NS.string")
                if isinstance(text, str) and text:
                    return text
        return None
    except Exception:
        return None
```

Update `test_bridge.py` to use a realistic plist structure:

```python
def _make_plist_blob(text: str) -> bytes:
    """Minimal NSKeyedArchiver-style plist matching the real $objects structure."""
    data = {
        "$version": 100000,
        "$archiver": "NSKeyedArchiver",
        "$top": {"root": plistlib.UID(1)},
        "$objects": [
            "$null",
            {"NS.string": text, "$class": plistlib.UID(2)},
            {"$classes": ["NSAttributedString", "NSObject"], "$classname": "NSAttributedString"},
        ],
    }
    return plistlib.dumps(data, fmt=plistlib.FMT_BINARY)
```

---

### MEDIUM — Month-boundary bug in `get_recent_sessions` yesterday computation

**File:** `sentinel-core/app/clients/obsidian.py:106`

**Finding:** On the first day of any month (`now.day == 1`), the guard `if now.day > 1 else now`
falls back to `now` instead of computing the previous month's last day. The `dates` list
becomes `[today, today]` — the same date twice — so the last day of the previous month is
never queried. Recent sessions from the prior month are silently excluded on day 1.

**Fix:**

```python
from datetime import datetime, timezone, timedelta

# Replace lines 105-107 with:
now = datetime.now(timezone.utc)
dates = [now.strftime("%Y-%m-%d")]
yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
dates.append(yesterday)
```

`timedelta(days=1)` handles month and year boundaries correctly without manual day arithmetic.

---

### MEDIUM — `/context/{user_id}` accepts unvalidated path segments forwarded to Obsidian API

**File:** `sentinel-core/app/routes/status.py:36`

**Finding:** The `user_id` path parameter is accepted as a plain `str` with no validation.
It is passed directly to `obsidian.get_recent_sessions(user_id)`, which interpolates it into
file path strings: `f"ops/sessions/{date}/{filename}"` where filenames are matched against
`f"{user_id}-"`. An attacker who can reach the `/context/` endpoint (authenticated by
`X-Sentinel-Key`) could supply a `user_id` containing path traversal sequences (e.g.,
`../../etc/`) that get forwarded to the Obsidian REST API.

For the personal-use threat model this is low exploitability (attacker needs the shared
secret), but the endpoint is described as a debug endpoint and `user_id` values are also
echoed back in the JSON response without sanitization.

**Fix:** Add a `Path` parameter with a regex constraint matching the same pattern used in
`MessageEnvelope.user_id`:

```python
from fastapi import APIRouter, Path, Request

@router.get("/context/{user_id}")
async def debug_context(
    request: Request,
    user_id: str = Path(..., pattern=r"^[a-zA-Z0-9_-]+$", max_length=64),
) -> JSONResponse:
    ...
```

This aligns the debug endpoint with the model-layer validation already present in
`MessageEnvelope`.

---

### MEDIUM — `_safe_request` log-suppression logic is inverted and fragile

**File:** `sentinel-core/app/clients/obsidian.py:36`

**Finding:** The condition `if not isinstance(default, bool)` suppresses log warnings only
when `default` is a `bool`. The intent is to avoid warning noise from `check_health()` which
returns `False` on failure. However the condition is confusing and has a subtle design flaw:
any future method that legitimately uses `False` as a default (unrelated to health checks)
will silently swallow errors. The condition also conflates "this is a health check" with
"this uses a bool default", which are orthogonal concepts.

The method signature also lacks type annotations for `coro` and `default`.

**Fix:**

```python
async def _safe_request(self, coro, default, operation: str, *, silent: bool = False):
    """Execute a coroutine, returning default on any failure.

    Args:
        silent: If True, suppress the warning log (for expected-degraded operations
                like check_health where a failure is not actionable).
    """
    try:
        return await coro
    except Exception as exc:
        if not silent:
            logger.warning("%s failed: %s", operation, exc)
        return default
```

Update the `check_health` call site:

```python
return await self._safe_request(_inner(), False, "check_health", silent=True)
```

---

### LOW — File handle not protected by context manager in `run_bridge`

**File:** `interfaces/imessage/bridge.py:125`

**Finding:** `chat_db.open("rb").close()` is called inline without a context manager. If an
exception is raised between `.open()` and `.close()` (however unlikely for this simple
pattern), the file descriptor leaks. The idiomatic pattern is to use a `with` statement.

**Fix:**

```python
try:
    with chat_db.open("rb"):
        pass
except PermissionError:
    ...
```

---

### LOW — Test docstrings say "403" but middleware returns 401

**File:** `sentinel-core/tests/test_status.py:96,125`

**Finding:** `test_status_requires_auth` has docstring `"GET /status without X-Sentinel-Key returns 403."` and `test_context_requires_auth` says the same. The `APIKeyMiddleware` in `main.py` returns `status_code=401`. The assertions correctly accept `(401, 403)`, but the docstrings state 403, which would mislead anyone reading the test to understand what the API contract is.

**Fix:** Update both docstrings to match the actual behaviour:

```python
"""GET /status without X-Sentinel-Key returns 401 (Unauthorized)."""
```

---

### LOW — `DISCORD_BOT_TOKEN` raises `KeyError` at module import, not at startup

**File:** `interfaces/discord/bot.py:61`

**Finding:** `DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]` is evaluated at module
import time. A missing env var raises `KeyError` with a bare traceback, producing a
confusing error in some container environments. `SENTINEL_API_KEY` has the same pattern on
line 62. `bridge.py` handles the missing-key case more gracefully with an explicit check and
`sys.exit(1)`. The inconsistency means Discord bot container failures produce a less
actionable error message than the iMessage bridge.

This is a minor quality issue (fail-fast is intentional) but the error surface is different
from the documented interface.

**Fix:** Either document that the Discord bot requires these env vars and the `KeyError` is
intentional, or add a startup validation consistent with `bridge.py`:

```python
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
SENTINEL_API_KEY = os.environ.get("SENTINEL_API_KEY", "")

def main() -> None:
    if not DISCORD_BOT_TOKEN:
        logger.error("DISCORD_BOT_TOKEN is not set.")
        sys.exit(1)
    if not SENTINEL_API_KEY:
        logger.error("SENTINEL_API_KEY is not set.")
        sys.exit(1)
    bot.run(DISCORD_BOT_TOKEN)
```

---

## Self-Check: PASSED

All findings have file paths, line numbers, descriptions, and concrete fix suggestions.
No source files were modified. Review covers all 13 files in scope at standard depth.
