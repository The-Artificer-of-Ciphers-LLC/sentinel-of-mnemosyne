---
phase: 35-foundry-vtt-event-ingest
reviewed: 2026-04-25T00:00:00Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - interfaces/discord/bot.py
  - interfaces/discord/tests/conftest.py
  - interfaces/discord/tests/test_discord_foundry.py
  - interfaces/discord/tests/test_thread_persistence.py
  - modules/pathfinder/app/config.py
  - modules/pathfinder/app/foundry.py
  - modules/pathfinder/app/main.py
  - modules/pathfinder/app/routes/foundry.py
  - modules/pathfinder/compose.yml
  - modules/pathfinder/foundry-client/module.json
  - modules/pathfinder/foundry-client/sentinel-connector.js
  - modules/pathfinder/tests/test_foundry.py
  - modules/pathfinder/tests/test_registration.py
  - scripts/uat_phase35.sh
findings:
  critical: 3
  warning: 4
  info: 2
  total: 9
status: issues_found
---

# Phase 35: Code Review Report

**Reviewed:** 2026-04-25
**Depth:** standard
**Files Reviewed:** 14
**Status:** issues_found

## Summary

Phase 35 adds the Foundry VTT event ingest pipeline: a JS module (`sentinel-connector.js`) that hooks `preCreateChatMessage`, POSTs events to `POST /foundry/event` on the pathfinder module, which narrates via LLM and forwards to the Discord bot's internal aiohttp endpoint. The architecture is sound and the happy path works. Three blockers were found — two security issues and one logic bug — plus four warnings.

---

## Critical Issues

### CR-01: `dc_hidden` computed before early-return, then `deriveOutcome` called with `null` DC

**File:** `modules/pathfinder/foundry-client/sentinel-connector.js:87-97`

**Issue:** `dc_hidden` is correctly captured at line 89 before the `if (!context.dc) return true` guard at line 91. However the `deriveOutcome` fallback at line 97 is called with `dcValue` which is `null` when `dc_hidden` is true (DC structure exists but value is secret). `rollTotal - null` evaluates to `rollTotal - 0` in JavaScript (coercion), which means every hidden-DC roll is incorrectly classified as a `criticalSuccess` whenever `rollTotal >= 10`. This produces wrong outcomes for secret-DC saves (traps, hazards, GM rolls).

```
const dcValue = context.dc?.value ?? null;          // null for hidden DC
const dc_hidden = (context.dc != null && dcValue == null);
// ...
const outcome = context.outcome ?? deriveOutcome(rollTotal, dcValue);
//   ^ deriveOutcome(18, null) => 18 - null => 18 - 0 => 18 >= 10 => criticalSuccess (WRONG)
```

**Fix:** When `dc_hidden` is true and `context.outcome` is absent, do not call `deriveOutcome` — the outcome is genuinely unknown. Emit `outcome: null` (or skip the event entirely) so the backend renders it faithfully as `dc_hidden: true` with no misleading outcome label.

```js
const outcome = context.outcome
  ?? (dc_hidden ? null : deriveOutcome(rollTotal, dcValue));

// Then in _postRollEvent payload:
outcome: outcome,   // null → backend renders "DC: [hidden]" without an outcome label
```

The `FoundryRollEvent` Pydantic model on the Python side already accepts `outcome: str` (not Optional), so the model also needs `outcome: Optional[str] = None` to tolerate a null outcome from hidden-DC events without a 422.

---

### CR-02: Internal aiohttp endpoint has no authentication on the network level — shared secret transmitted from pf2e-module as plaintext HTTP

**File:** `interfaces/discord/bot.py:1373-1375` and `modules/pathfinder/app/foundry.py:113-116`

**Issue:** `_handle_internal_notify` validates `X-Sentinel-Key` — that part is correct. However `notify_discord_bot` sends the key over plain HTTP to `http://discord-bot:8001`. Within Docker's bridge network this is acceptable, but the listening socket is bound to `0.0.0.0` (all interfaces) not `127.0.0.1` or the Docker internal interface:

```python
# bot.py line 1364
site = web.TCPSite(self._internal_runner, "0.0.0.0", internal_port)
```

Binding to `0.0.0.0` on port 8001 exposes the internal notify endpoint on all host interfaces if any port mapping exists (or if the container's network is `host` mode). Any process that can reach that port bypasses the Discord allowlist and injects arbitrary embeds into the configured Discord channel. There is no rate limiting, no payload size cap, and the embed content is rendered directly.

**Fix:** Bind to `"127.0.0.1"` or `"discord-bot"` (the Docker service interface) instead of `"0.0.0.0"`. At minimum add a payload size guard in `_handle_internal_notify`:

```python
# bot.py setup_hook
site = web.TCPSite(self._internal_runner, "127.0.0.1", internal_port)

# _handle_internal_notify — add before json parse
body = await request.read()
if len(body) > 64_000:  # Discord embed content cap with headroom
    return web.Response(status=413)
data = json.loads(body)
```

---

### CR-03: `X-Sentinel-Key` stored as plain text in Foundry world settings — visible to all GM-level users and in client JS

**File:** `modules/pathfinder/foundry-client/sentinel-connector.js:49-56`

**Issue:** The API key is registered as a `config: true` world setting with `type: String`. Foundry world settings with `config: true` are displayed in the module settings panel and are accessible from browser developer tools via `game.settings.get('sentinel-connector', 'apiKey')` by any logged-in GM. More critically, the value is transmitted from the Foundry client (browser) directly to the Sentinel server — anyone with browser devtools open during a roll can read the key from the outgoing `X-Sentinel-Key` request header. In a home-lab context this is low-impact, but it is documented in `CLAUDE.md` as a deliberate design decision ("sufficient for personal local-network use") — the finding stands as BLOCKER because the current implementation uses `config: true` which renders the secret in the UI settings form, making it trivially readable. Using `config: false` would at least keep it out of the visible settings panel.

**Fix:**

```js
game.settings.register(MODULE_ID, 'apiKey', {
  name: 'Sentinel API Key',
  hint: 'The X-Sentinel-Key shared secret from your .env file.',
  scope: 'world',
  config: false,   // hide from the settings panel UI — read programmatically only
  type: String,
  default: '',
});
```

Add a GM-only registration command or a settings dialog with a password-type input if UI config is needed. Alternatively, document this exposure explicitly in `CLAUDE.md` so it is a known accepted risk rather than an oversight.

---

## Warnings

### WR-01: `test_auth_rejected` bypasses the lifespan startup — `test_invalid_payload` may too — tests exercise the route without the foundry route's `_SENTINEL_API_KEY` being set from the real env

**File:** `modules/pathfinder/tests/test_foundry.py:57-91`

**Issue:** Both `test_auth_rejected` and `test_invalid_payload` construct `AsyncClient(transport=ASGITransport(app=app))` without patching the lifespan. FastAPI's `ASGITransport` runs the app but does **not** invoke the `lifespan` context manager unless `app.router.lifespan_context` is triggered. This means:

1. `_register_with_retry` is NOT called — that is intentional and fine.
2. `_SENTINEL_API_KEY` is read from `os.environ.get("SENTINEL_API_KEY", "")` at module import time (line 34). The test file sets `os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")` at the top, so this works correctly for `test_auth_rejected` (wrong key → 401).
3. However `test_invalid_payload` sends the **correct** key (`"test-key-for-pytest"`) with a malformed body. Auth passes, Pydantic validation runs and returns 422. This test will pass now — but if the auth check is ever moved after validation (a common FastAPI refactor), the test will continue to pass for the wrong reason (it would now get 422 from validation even with wrong key). The test does not assert auth was not the cause of the 422.

This is not a test-reliability blocker today but will mask a regression. Add a second assertion confirming the correct key was used:

```python
async def test_invalid_payload():
    # ... existing setup ...
    resp = await client.post(
        "/foundry/event",
        json={"event_type": "roll"},
        headers={"X-Sentinel-Key": "test-key-for-pytest"},  # correct key
    )
    assert resp.status_code == 422
    # Guard: if auth fails the test is also wrong
    assert resp.status_code != 401, "Auth rejected before Pydantic validation — test is incorrect"
```

---

### WR-02: `_handle_internal_notify` sends to the **first** channel in `ALLOWED_CHANNEL_IDS` — a `set` has no defined iteration order

**File:** `interfaces/discord/bot.py:1381`

**Issue:**

```python
channel_id = next(iter(ALLOWED_CHANNEL_IDS), None)
```

`ALLOWED_CHANNEL_IDS` is a `set[int]`. Python sets do not guarantee insertion order. If multiple channels are configured, the notify endpoint will post to a non-deterministic channel across process restarts (hash randomisation changes iteration order). This is a correctness bug: the operator configures channels expecting predictable routing, but the bot may post Foundry roll embeds to a different channel after each restart.

**Fix:** Use an ordered structure. The simplest fix is to parse `DISCORD_ALLOWED_CHANNELS_RAW` into a `list[int]` and use the first element as the designated Foundry notification channel, with the full set still used for allowlist checks:

```python
ALLOWED_CHANNEL_IDS: set[int] = set()
ALLOWED_CHANNEL_LIST: list[int] = []
if DISCORD_ALLOWED_CHANNELS_RAW.strip():
    ALLOWED_CHANNEL_LIST = [
        int(cid.strip())
        for cid in DISCORD_ALLOWED_CHANNELS_RAW.split(",")
        if cid.strip().isdigit()
    ]
    ALLOWED_CHANNEL_IDS = set(ALLOWED_CHANNEL_LIST)

# In _handle_internal_notify:
channel_id = ALLOWED_CHANNEL_LIST[0] if ALLOWED_CHANNEL_LIST else None
```

---

### WR-03: `test_discord_foundry.py` async tests have no `pytest.mark.asyncio` or `asyncio_mode` config — they will silently pass without executing

**File:** `interfaces/discord/tests/test_discord_foundry.py:22-62`

**Issue:** Both `test_embed_critical_success` and `test_embed_hidden_dc` are defined as `async def` but there is no `@pytest.mark.asyncio` decorator and no `asyncio_mode = "auto"` in a `pytest.ini` / `pyproject.toml`. Without one of these, pytest collects the coroutine objects as tests and marks them **passed** immediately — the coroutine body never runs. This means the FVT-03 embed builder is completely untested despite appearing green in CI.

The same issue affects `test_thread_persistence.py` which also has bare `async def test_*` functions.

**Fix:** Either add `@pytest.mark.asyncio` to every async test function, or add to the project's pytest config:

```ini
# pytest.ini or pyproject.toml [tool.pytest.ini_options]
asyncio_mode = "auto"
```

Verify that `pytest-asyncio` is in `dev-dependencies`.

---

### WR-04: `build_foundry_roll_embed` duplicates `OUTCOME_EMOJIS` / `OUTCOME_LABELS` / `OUTCOME_COLORS` from `app/foundry.py` — desync risk

**File:** `interfaces/discord/bot.py:373-390` and `modules/pathfinder/app/foundry.py:18-29`

**Issue:** Both files define identical `OUTCOME_EMOJIS` and `OUTCOME_LABELS` dicts. `bot.py` additionally defines `OUTCOME_COLORS`. These are independent copies. If a PF2e rule change requires adding a new outcome degree (e.g. Foundry adds "extremeSuccess"), it must be updated in both files. The fallback emoji `"🎲"` in `bot.py` line 401 and the fallback label logic differ subtly from `app/foundry.py` line 96 (`outcome.capitalize() if outcome else "Roll"` vs `outcome.capitalize() if outcome else "Roll"` — these match, but only by coincidence).

This is a quality defect, not a live bug. The two modules are in separate services and cannot share code directly, but the duplication should be documented as a known sync point.

**Fix:** Add a comment in both files cross-referencing the other, or extract to a shared constants file if a shared library layer exists in this project.

---

## Info

### IN-01: `module.json` contains placeholder URLs that will cause Foundry installation to fail for any user who installs by manifest URL

**File:** `modules/pathfinder/foundry-client/module.json:29-30`

**Issue:**

```json
"manifest": "http://YOUR_SENTINEL_IP:8000/foundry/static/module.json",
"download": "http://YOUR_SENTINEL_IP:8000/foundry/static/sentinel-connector.zip"
```

`YOUR_SENTINEL_IP` is a literal placeholder. Foundry VTT will attempt to fetch this URL for version checking and updates. If a user installs the module by pasting the manifest URL into Foundry's module installer, Foundry will try to resolve `http://YOUR_SENTINEL_IP:8000/...` and fail. While this is intended to be customised per deployment, there is no validation step in the UAT script or installation docs to catch the case where the operator forgets to substitute the IP.

**Fix:** Add a check to `uat_phase35.sh` that the manifest URL in the served `module.json` does not contain the literal string `YOUR_SENTINEL_IP`:

```bash
MANIFEST_CONTENT=$(curl -s "${PF2E_URL}/foundry/static/module.json")
if echo "$MANIFEST_CONTENT" | grep -q "YOUR_SENTINEL_IP"; then
  echo "  FAIL: module.json still contains placeholder YOUR_SENTINEL_IP — update before distributing"
  ((FAIL++)) || true
fi
```

---

### IN-02: UAT Step 7/8 route via `BASE_URL` (sentinel-core proxy) for static assets — will fail if sentinel-core strips the `/foundry/` prefix

**File:** `scripts/uat_phase35.sh:133-151`

**Issue:** Steps 7 and 8 fetch `module.json` and `sentinel-connector.zip` from `${BASE_URL}/foundry/static/...` where `BASE_URL` defaults to the sentinel-core proxy (`http://localhost:8000`). The static files are mounted on the pf2e-module directly. If sentinel-core proxies `/modules/pathfinder/foundry/static/...` but not `/foundry/static/...`, steps 7–8 will return 404 or 502 from sentinel-core rather than the pf2e-module's StaticFiles mount. The comment in `uat_phase35.sh` says "direct" for step 1 (`PF2E_URL`) but steps 7–8 use `BASE_URL` (the proxy). This should use `PF2E_URL` for static assets, matching step 1.

**Fix:**

```bash
# Step 7 — use PF2E_URL directly (static assets are not proxied via sentinel-core)
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  "${PF2E_URL}/foundry/static/module.json")
```

---

_Reviewed: 2026-04-25_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
