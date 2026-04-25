---
phase: 35-foundry-vtt-event-ingest
verified: 2026-04-25T22:00:00Z
status: human_needed
score: 18/18
overrides_applied: 2
overrides:
  - must_have: "modules/pathfinder/app/main.py defines PNACORSMiddleware subclassing Starlette CORSMiddleware"
    reason: "Starlette 1.0+ natively supports allow_private_network=True on CORSMiddleware directly — no subclass needed. The implementation uses CORSMiddleware(allow_private_network=True) which injects Access-Control-Allow-Private-Network on OPTIONS preflight responses. Functionally identical. Code comment in main.py explains why no subclass was needed."
    accepted_by: "trekkie"
    accepted_at: "2026-04-25T22:00:00Z"
  - must_have: ".env.example has DISCORD_WEBHOOK_URL"
    reason: "discordWebhookUrl is a Foundry world setting stored in the Foundry database, not a server-side env var. The .env.example explicitly documents this with the note 'do NOT put it in .env'. The documentation IS present in .env.example as a comment explaining the setting — the design decision is correct and intentional."
    accepted_by: "trekkie"
    accepted_at: "2026-04-25T22:00:00Z"
re_verification:
  previous_status: human_needed
  previous_score: 15/15
  gaps_closed:
    - "Plan 35-06 delivered: discordWebhookUrl world setting, sentinelBaseUrl (empty default), postEvent() with AbortController 3s timeout and no-cors webhook fallback"
    - "Plan 35-06 delivered: CORS + PNA header support via CORSMiddleware(allow_private_network=True) in main.py"
    - ".env.example extended with discordWebhookUrl guidance and Tailscale HTTPS cert setup"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Install sentinel-connector.zip in Foundry v14 via manifest URL. Set Sentinel Base URL and API Key in module settings. Make an attack roll against a target with a DC. Verify Discord embed appears in the configured channel with emoji title, LLM narrative or fallback, and roll/DC footer."
    expected: "Discord embed posts to configured channel. Title has outcome emoji and label. Footer shows Roll total and DC/AC value. Narrative appears in embed description."
    why_human: "Requires a running Foundry VTT v14 instance with the pf2e system, a live LM Studio model, the full Docker stack, and a configured Discord bot. Cannot be exercised programmatically without all three services running."
  - test: "Make an attack roll against an enemy with a GM-secret DC (hidden DC toggle). Verify Discord embed shows 'DC: [hidden]' in footer and does NOT show 'DC/AC: N'."
    expected: "Footer reads 'DC: [hidden]' not 'DC/AC: 14'. Embed still posts. Foundry chat message is not suppressed."
    why_human: "Hidden-DC behavior requires the PF2e system flag pf2e.context.dc to be set with a null value — only testable in a live Foundry session."
  - test: "Verify apiKey world setting is NOT visible in Foundry's module settings panel UI (config: false fix for CR-03)."
    expected: "API key field does not appear in the Module Settings panel. Other settings (Base URL, Chat Prefix, Discord Webhook URL) appear normally."
    why_human: "Requires Foundry VTT browser UI to inspect the Module Settings panel."
  - test: "Configure only discordWebhookUrl (leave Sentinel Base URL empty). Make a PF2e attack roll. Verify a Discord embed appears in the channel via webhook (webhook-only mode)."
    expected: "Discord embed appears in channel. Sentinel is not contacted. Embed has emoji title, roll total, DC/AC or DC: [hidden] in footer."
    why_human: "Requires live Foundry VTT, Discord channel with configured webhook, and browser inspection to confirm no Sentinel request was made."
  - test: "Configure sentinelBaseUrl pointing to an unreachable host (e.g., http://10.0.0.99:8000) and configure discordWebhookUrl. Make a PF2e roll. Verify the hook does NOT hang, that Foundry chat message appears immediately, and that Discord embed arrives via webhook within ~4 seconds."
    expected: "AbortController fires after 3s. Foundry chat message not delayed. Discord embed arrives within ~4s total. Console warns 'Sentinel POST failed, falling back to webhook'."
    why_human: "Timeout fallback behavior can only be observed in a live browser with the Foundry VTT client running against an unreachable host."
---

# Phase 35: Foundry VTT Event Ingest — Verification Report

**Phase Goal:** A Foundry VTT JavaScript module hooks into chat messages and dice rolls, POSTs events to Sentinel Core, and receives Discord responses with roll interpretations.
**Verified:** 2026-04-25T22:00:00Z
**Status:** human_needed
**Re-verification:** Yes — after Plans 35-05 and 35-06 (gap closure, connectivity fix)

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | POST /foundry/event with correct key and valid roll payload returns 200 | VERIFIED | `app/routes/foundry.py` has `router = APIRouter(prefix="/foundry")`, auth check (status_code=401), Pydantic discriminated union. Route wired in `main.py`. 6/6 test_foundry.py tests GREEN. |
| 2 | POST /foundry/event with wrong key returns 401 | VERIFIED | Auth check at request time: `if x_sentinel_key != api_key: raise HTTPException(status_code=401)`. `test_auth_rejected` GREEN. |
| 3 | POST /foundry/event with malformed payload returns 422 | VERIFIED | Pydantic discriminated union on `event_type` field. `FoundryRollEvent` requires `roll_type`, `actor_name`, `outcome`, `roll_total`, `timestamp`. Missing fields → FastAPI returns 422. `test_invalid_payload` GREEN. |
| 4 | LLM timeout produces plain-text fallback; notify_discord_bot still called | VERIFIED | `app/foundry.py`: `generate_foundry_narrative` wraps `litellm.acompletion` in `try/except Exception` returning `""` on failure. Route checks `if not narrative: narrative = build_narrative_fallback(...)`. `notify_discord_bot` called in all paths. `test_llm_fallback` GREEN. |
| 5 | 'foundry/event' appears in REGISTRATION_PAYLOAD routes list | VERIFIED | `grep -c '"foundry/event"' modules/pathfinder/app/main.py` returns 1 (line 88). `test_registration_payload` GREEN. |
| 6 | StaticFiles mount serves /foundry/static/ BEFORE foundry router include | VERIFIED | `main.py`: StaticFiles mount at line ~251, `app.include_router(foundry_router)` at line ~258 — mount before router (Pitfall 3 prevented). |
| 7 | compose.yml has DISCORD_BOT_INTERNAL_URL env var | VERIFIED | Confirmed in `modules/pathfinder/compose.yml`. |
| 8 | .env.example has Foundry VTT section with FOUNDRY_NARRATION_MODEL and DISCORD_BOT_INTERNAL_URL | VERIFIED | Section at lines 109-133. Both vars documented. |
| 9 | build_foundry_roll_embed() is a module-level pure function in bot.py | VERIFIED | `grep -c 'def build_foundry_roll_embed' interfaces/discord/bot.py` = 1. Both `test_discord_foundry.py` tests GREEN. |
| 10 | SentinelBot has _internal_runner, aiohttp startup in setup_hook(), _handle_internal_notify(), close() override | VERIFIED | `_internal_runner` grep = 6. `_handle_internal_notify` grep >= 2. `async def close` = 1. `from aiohttp import web` = 1. |
| 11 | module.json exists with correct v14 manifest fields | VERIFIED | `esmodules` array present. `"minimum": "12"` present. `relationships.systems` for pf2e present. |
| 12 | sentinel-connector.js: deriveOutcome, always returns true, postEvent() calls correct endpoint | VERIFIED | `function deriveOutcome` = 1. `return true` >= 5. `modules/pathfinder/foundry/event` in fetch URL. |
| 13 | package.sh creates sentinel-connector.zip with sentinel-connector/ subdirectory at zip root | VERIFIED | Pre-built zip committed. `unzip -l` confirms `sentinel-connector/module.json` and `sentinel-connector/sentinel-connector.js` under `sentinel-connector/`. |
| 14 | uat_phase35.sh exists, is executable, has no syntax errors, covers foundry/event | VERIFIED | `bash -n scripts/uat_phase35.sh` exits 0. `grep -c 'foundry/event'` >= 3. |
| 15 | sentinel-connector.js has 'discordWebhookUrl' world setting registered in Hooks.once('init') | VERIFIED | `grep -c 'discordWebhookUrl' sentinel-connector.js` = 2 (register + get). `discordWebhookUrl` setting registered at line 53. |
| 16 | sentinel-connector.js skips Sentinel when sentinelBaseUrl is empty and posts directly to Discord webhook | VERIFIED | `postEvent()` at line 179: `if (sentinelUrl)` guard skips Sentinel block when empty. Default `sentinelBaseUrl` is `''`. Falls through to webhook path. |
| 17 | sentinel-connector.js attempts Sentinel with 3-second AbortController timeout, then falls back to webhook | VERIFIED | `AbortController` at line 186. `SENTINEL_TIMEOUT_MS = 3000`. Try/catch wrapping fetch. Falls through to webhook on any error. `mode: 'no-cors'` + `embeds` array at webhook call site. |
| 18 | CORS + Private Network Access headers configured in main.py for Forge origins | VERIFIED | `from starlette.middleware.cors import CORSMiddleware`. `app.add_middleware(CORSMiddleware, allow_origins=[...forge-vtt.com...], allow_private_network=True)`. Starlette natively injects `Access-Control-Allow-Private-Network` header. `X-Sentinel-Key` in allow_headers. App imports cleanly. 178 pathfinder tests pass. |
| 19 | PNACORSMiddleware subclass defined in main.py | PASSED (override) | Override: Starlette 1.0+ supports allow_private_network natively — no subclass needed. Direct CORSMiddleware(allow_private_network=True) achieves the same result. Code comment at lines 217-221 explains the design. Accepted by trekkie. |
| 20 | .env.example documents DISCORD_WEBHOOK_URL variable | PASSED (override) | Override: discordWebhookUrl is a Foundry world setting stored in Foundry DB, not a server-side env var. .env.example at lines 123-127 explicitly documents this setting with correct placement guidance ("do NOT put it in .env"). Accepted by trekkie. |

**Score:** 18/18 truths verified (16 VERIFIED + 2 PASSED (override))

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `modules/pathfinder/tests/test_foundry.py` | 6 tests for FVT-01/02 | VERIFIED | 6 tests GREEN (178 full suite pass) |
| `interfaces/discord/tests/test_discord_foundry.py` | 2 tests for FVT-03 | VERIFIED | 2 tests GREEN |
| `interfaces/discord/tests/conftest.py` | gold() classmethod in _ColorStub | VERIFIED | Present |
| `modules/pathfinder/app/foundry.py` | generate_foundry_narrative, notify_discord_bot, build_narrative_fallback | VERIFIED | All 3 functions present |
| `modules/pathfinder/app/routes/foundry.py` | FastAPI router at /foundry | VERIFIED | router = APIRouter(prefix="/foundry"), auth, discriminated union |
| `modules/pathfinder/app/config.py` | foundry_narration_model + discord_bot_internal_url | VERIFIED | Both fields confirmed |
| `modules/pathfinder/app/main.py` | foundry/event in REGISTRATION_PAYLOAD, StaticFiles, router include, lifespan wiring, CORS middleware | VERIFIED | All elements confirmed; CORS via CORSMiddleware(allow_private_network=True) |
| `modules/pathfinder/compose.yml` | DISCORD_BOT_INTERNAL_URL env block | VERIFIED | Confirmed |
| `.env.example` | Foundry VTT section + discordWebhookUrl guidance + Tailscale HTTPS guidance | VERIFIED | Lines 109-133. tailscale cert at line 130. |
| `interfaces/discord/bot.py` | build_foundry_roll_embed, _handle_internal_notify, close(), aiohttp import, _internal_runner | VERIFIED | All 5 elements confirmed |
| `modules/pathfinder/foundry-client/module.json` | v14 manifest with esmodules, compatibility, relationships | VERIFIED | All fields confirmed |
| `modules/pathfinder/foundry-client/sentinel-connector.js` | deriveOutcome, always-true hook, postEvent() with sentinelBaseUrl + discordWebhookUrl + AbortController + no-cors webhook fallback | VERIFIED | All confirmed; _postRollEvent/_postChatEvent removed |
| `modules/pathfinder/foundry-client/package.sh` | zip builder with sentinel-connector/ at root | VERIFIED | Executable; correct zip structure |
| `modules/pathfinder/foundry-client/sentinel-connector.zip` | Pre-built zip committed | VERIFIED | Exists with correct subdirectory structure |
| `scripts/uat_phase35.sh` | 9-step live stack UAT | VERIFIED | Executable; bash -n passes; covers foundry/event |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `app/routes/foundry.py` | `app/foundry.py` | `import app.foundry as _foundry; _foundry.generate_foundry_narrative(...)` | WIRED | Module-ref pattern; patch targets work correctly |
| `app/foundry.py` | `litellm.acompletion` | `await litellm.acompletion(**kwargs)` | WIRED | Confirmed in foundry.py |
| `app/foundry.py` | `httpx.AsyncClient` | `async with httpx.AsyncClient(timeout=5.0) as client` | WIRED | Confirmed in notify_discord_bot |
| `main.py` | `app/routes/foundry.py` | `from app.routes.foundry import router as foundry_router; app.include_router(foundry_router)` | WIRED | Lines 56 and 258 confirmed |
| `main.py` | `foundry-client/` | `StaticFiles(directory=str(FOUNDRY_CLIENT_DIR))` at `/foundry/static` | WIRED | Before router include — Pitfall 3 prevented |
| `main.py lifespan` | `app.routes.foundry.discord_bot_url` | `_foundry_module.discord_bot_url = settings.discord_bot_internal_url` | WIRED | Set + cleared in lifespan |
| `main.py` | `CORSMiddleware(allow_private_network=True)` | `app.add_middleware(CORSMiddleware, ..., allow_private_network=True)` | WIRED | forge-vtt.com origins, X-Sentinel-Key in allow_headers |
| `SentinelBot.setup_hook()` | `aiohttp.web.AppRunner` | `web.AppRunner(_aiohttp_app); await runner.setup(); TCPSite start` | WIRED | Bound to 127.0.0.1 (CR-02) |
| `_handle_internal_notify()` | `build_foundry_roll_embed` | `embed = build_foundry_roll_embed(data)` | WIRED | Confirmed in bot.py |
| `_handle_internal_notify()` | `ALLOWED_CHANNEL_IDS` | `min(ALLOWED_CHANNEL_IDS)` | WIRED | Deterministic channel selection (WR-02) |
| `sentinel-connector.js postEvent()` | `sentinelBaseUrl` → `POST .../modules/pathfinder/foundry/event` | `game.settings.get(MODULE_ID, 'sentinelBaseUrl')` → `fetch(...)` | WIRED | 3s AbortController timeout |
| `sentinel-connector.js postEvent()` | `discordWebhookUrl` → Discord webhook | `game.settings.get(MODULE_ID, 'discordWebhookUrl')` → `fetch(webhookUrl, {mode:'no-cors',...})` | WIRED | Fallback when sentinelUrl empty or Sentinel unreachable |
| `package.sh` | `sentinel-connector.zip` | `mkdir tmpdir/sentinel-connector; cp files; zip` | WIRED | `sentinel-connector/` at zip root confirmed |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `bot.py::build_foundry_roll_embed` | `data` dict | POST from `notify_discord_bot` in `app/foundry.py` → `_handle_internal_notify` | Yes — dict populated from FoundryRollEvent fields + LLM narrative | FLOWING |
| `app/routes/foundry.py::_handle_roll` | `narrative` | `_foundry.generate_foundry_narrative()` → `litellm.acompletion` or `build_narrative_fallback` fallback | Yes — LLM call with real actor/target/outcome data; fallback from deterministic function | FLOWING |
| `sentinel-connector.js::postEvent()` | `payload` | `chatMessage.flags?.pf2e?.context` + `chatMessage.rolls[0].total` | Yes — live PF2e ChatMessage flags; human-only | FLOWING (human-only) |
| `sentinel-connector.js::postEvent()` — webhook path | `embed` | `payload.outcome`, `payload.roll_total`, `payload.dc`, `payload.dc_hidden`, `payload.item_name` | Yes — built from live payload; no hardcoded empty values | FLOWING |

### Behavioral Spot-Checks

Step 7b skipped — pf2e-module container not running. The `scripts/uat_phase35.sh` is the designated mechanism for live behavioral verification. All pytest suites pass: 178 pathfinder, 52 discord (2 foundry-specific + 50 other).

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| FVT-01 | 35-01, 35-02, 35-04, 35-05, 35-06 | Foundry VTT JS module hooks into chat messages and dice rolls and POSTs events to Sentinel Core (authenticated with X-Sentinel-Key) | SATISFIED | sentinel-connector.js registers preCreateChatMessage hook with `sentinelBaseUrl` setting; POSTs with X-Sentinel-Key; POST /foundry/event validates auth and schema; route wired into main.py |
| FVT-02 | 35-01, 35-02, 35-03, 35-04 | Sentinel processes incoming Foundry events and sends responses to the DM's Discord channel | SATISFIED | app/foundry.py calls LLM then notify_discord_bot; bot.py _handle_internal_notify validates, builds embed, sends to channel |
| FVT-03 | 35-01, 35-03, 35-06 | Sentinel interprets roll results in Discord (hit/miss, effect description, DC comparison) | SATISFIED | build_foundry_roll_embed produces emoji-title, LLM narrative description, Roll/DC/AC footer; hidden-DC shows "DC: [hidden]"; 2 tests GREEN. Plan 35-06 adds webhook-direct embed path with same fields for Forge players. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `modules/pathfinder/foundry-client/module.json` | 29-30 | `YOUR_SENTINEL_IP` placeholder in manifest/download URLs | Info | Expected — operator replaces LAN IP at install time. Not a stub. |
| `interfaces/discord/bot.py` | ~374 | Duplicate OUTCOME_EMOJIS/OUTCOME_LABELS vs app/foundry.py | Info | WR-04 acknowledged; cross-reference comment added. Separate containers prevent sharing. No data flow impact. |
| `.env.example` | 133 | References `PNACORSMiddleware` in comment but class does not exist in main.py | Info | Stale comment from pre-implementation design. Does not affect functionality. The actual CORS implementation is correct. |

No blockers found. No stubs in functional paths. No TODO/FIXME in phase-introduced code.

### Human Verification Required

#### 1. Live Roll Event — End-to-End (Sentinel path)

**Test:** With Docker stack running (`docker compose --profile pf2e up -d`), install `sentinel-connector.zip` in Foundry v14, configure Sentinel Base URL and API Key in module settings. Make an attack roll against a target with a known DC in the PF2e system.
**Expected:** Discord embed appears in configured channel. Title: `{emoji} {outcome} | {actor} vs {target}`. Footer: `Roll: {total} | DC/AC: {dc} | {item_name}`. Description: LLM-generated narrative or fallback plain text.
**Why human:** Requires live Foundry v14 + pf2e system + LM Studio loaded + Docker stack + Discord bot connected.

#### 2. Hidden-DC Roll Behavior

**Test:** Make a saving throw against a GM-secret DC (hidden DC toggle in Foundry). Verify Discord embed and that Foundry chat message is NOT suppressed.
**Expected:** Embed footer shows `DC: [hidden]`. Foundry chat message remains visible. No outcome label mismatch from null DC coercion (CR-01 fix).
**Why human:** Hidden-DC flag (`flags.pf2e.context.dc` with null value) only appears in a live PF2e combat encounter.

#### 3. Module Settings Panel — apiKey Visibility (CR-03)

**Test:** Open Foundry module settings panel while logged in as GM. Inspect Sentinel Connector settings.
**Expected:** "Sentinel Base URL", "Discord Webhook URL", and "Chat Trigger Prefix" fields appear. "Sentinel API Key" field does NOT appear in the UI panel (`config: false` applied).
**Why human:** Requires Foundry VTT browser UI.

#### 4. Webhook-Only Mode (Plan 35-06 — Forge players)

**Test:** Configure only `discordWebhookUrl` in Foundry module settings. Leave Sentinel Base URL empty. Make a PF2e attack roll.
**Expected:** Discord embed appears in channel via webhook. Sentinel is not contacted (no network request to sentinel URL). Embed has emoji title, roll total, DC/AC or DC: [hidden] in footer.
**Why human:** Requires live Foundry VTT + Discord channel with configured webhook.

#### 5. AbortController Timeout Fallback (Plan 35-06)

**Test:** Configure `sentinelBaseUrl` pointing to an unreachable host (e.g., `http://10.0.0.99:8000`) and configure `discordWebhookUrl`. Make a PF2e roll.
**Expected:** Hook does not hang Foundry chat. Foundry chat message appears immediately. Discord embed arrives via webhook within ~4 seconds. Console warns `Sentinel POST failed, falling back to webhook`.
**Why human:** Timeout fallback behavior requires a live browser with Foundry VTT running against an unreachable Sentinel host.

### Gaps Summary

No gaps requiring closure. All 18 truths verified (16 VERIFIED + 2 PASSED via override). Two overrides applied for intentional deviations from plan literal wording where the functional goal was achieved via alternative implementation:
- `PNACORSMiddleware` subclass → replaced by native Starlette `CORSMiddleware(allow_private_network=True)` (same PNA header behavior, simpler code)
- `DISCORD_WEBHOOK_URL` in .env.example → correctly documented as a Foundry world setting in .env.example comments with explicit guidance not to store it as an env var

Five items require human verification in a live Foundry VTT environment (3 carried from initial verification + 2 new for Plan 35-06 connectivity features). These are inherent to browser-only behavior that cannot be checked programmatically.

One stale comment in `.env.example` references `PNACORSMiddleware` but the class does not exist. This is informational only — functionality is unaffected.

---

_Verified: 2026-04-25T22:00:00Z_
_Verifier: Claude (gsd-verifier)_
