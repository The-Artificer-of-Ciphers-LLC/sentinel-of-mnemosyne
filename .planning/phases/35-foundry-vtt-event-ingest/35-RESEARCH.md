# Phase 35: Foundry VTT Event Ingest — Research

**Researched:** 2026-04-25
**Domain:** Foundry VTT v14 JS module API, FastAPI StaticFiles, aiohttp + discord.py integration
**Confidence:** MEDIUM (Foundry JS flags: LOW; FastAPI/Python: HIGH; aiohttp pattern: HIGH)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** `Hooks.on('preCreateChatMessage', ...)` + inspect `message.flags?.pf2e?.context`. Forward when context exists with recognized roll type. Filters at JS layer.
- **D-02:** Non-roll chat forwarded only if message text starts with trigger prefix. Prefix stored as world setting alongside X-Sentinel-Key.
- **D-03:** `X-Sentinel-Key` stored as `scope: "world"` Foundry world setting. Sent as header on every POST.
- **D-04:** `module.json` declares `compatibility.minimum: "12"`, `compatibility.verified: "14"`.
- **D-05:** Roll payload shape (event_type, roll_type, actor_name, target_name, outcome, roll_total, dc, dc_hidden, item_name, timestamp).
- **D-06:** Chat message payload shape (event_type, chat, actor_name, content, timestamp).
- **D-07:** `SENTINEL_BASE_URL` stored in world settings. POST target: `{SENTINEL_BASE_URL}/modules/pathfinder/foundry/event`.
- **D-08:** New `POST /foundry/event` route in `app/routes/foundry.py`.
- **D-09:** Add `{"path": "foundry/event", "description": "Receive Foundry VTT game events (FVT-01..03)"}` to `REGISTRATION_PAYLOAD`.
- **D-10:** Mount `modules/pathfinder/foundry-client/dist/` at `/foundry/static/` via `StaticFiles`. `module.json` at `GET /foundry/module.json`, zip at `GET /foundry/sentinel-connector.zip`.
- **D-11:** LLM narrative via existing `litellm.acompletion()` pattern in `app/llm.py`. System prompt: DM narrator, one dramatic sentence, max 20 words, third-person past-tense.
- **D-12:** `FOUNDRY_NARRATION_MODEL` env var, falls back to `LITELLM_MODEL`. Same pattern as `SESSION_RECAP_MODEL`.
- **D-13:** LLM failure fallback: plain-text summary, Discord embed still sent.
- **D-14:** `bot.py` grows aiohttp listener. Researcher picks aiohttp vs FastAPI sub-app and confirms asyncio discord.py compatibility.
- **D-15:** Notifications post to same Discord channel as existing pf2e commands. No new channel env var.
- **D-16:** Discord embed shape: title `{outcome_emoji} {outcome_label} | {actor_name} vs {target_name}`, body = LLM narrative, footer = `Roll: {total} | DC/AC: {dc} | {item_name}`.
- **D-17:** `sentinel-connector.js` as Foundry v14 ESModule. No bundler required. Zip contains `module.json` + `sentinel-connector.js` only.
- **D-18:** `package.sh` creates `sentinel-connector.zip`. Researcher confirms zip structure Foundry expects.

### Claude's Discretion
- Exact `game.settings.register` API shape for `SENTINEL_BASE_URL`, `SENTINEL_KEY`, trigger prefix
- aiohttp vs FastAPI sub-app for bot.py internal endpoint — researcher picks
- Internal port for bot.py listener (e.g., 8001) and compose.yml exposure
- Exact v14 `module.json` fields and `esmodules` array format
- LLM prompt refinement for 20-word narrative
- How pathfinder discovers bot.py internal URL (env var `DISCORD_BOT_INTERNAL_URL`)
- Outcome emoji mapping: 🎯 criticalSuccess, ✅ success, ❌ failure, 💀 criticalFailure
- Whether `preCreateChatMessage` returns false or reads passively (must NOT suppress — return true)

### Deferred Ideas (OUT OF SCOPE)
- Phase 36 NPC pull-import button in Foundry UI
- Campaign-level roll history / analytics
- Foundry-side display widgets
- All-rolls event scope (initiative, damage, flat checks)
- Player-visible Discord notifications
- Foundry → Obsidian combat log
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FVT-01 | A Foundry VTT JS module hooks into chat messages and dice rolls and POSTs events to Sentinel Core (authenticated with X-Sentinel-Key) | D-01..D-07 decision coverage; hook API verified; game.settings.register pattern confirmed |
| FVT-02 | Sentinel processes incoming Foundry events and sends responses to the DM's Discord channel | D-08..D-16 decision coverage; aiohttp pattern for bot.py confirmed |
| FVT-03 | Sentinel interprets roll results in Discord (hit/miss, effect description, DC comparison) | LLM narration via litellm.acompletion confirmed; Discord embed layout specified |
</phase_requirements>

---

## Summary

Phase 35 builds a three-tier bridge: a JavaScript Foundry module captures PF2e roll and chat events, POSTs them to a new FastAPI route on the pf2e module container, which calls LiteLLM for a 20-word narrative and then POSTs the result to an internal aiohttp HTTP listener on the Discord bot. The Discord bot sends the narrated embed to the DM's existing pf2e channel.

The highest-risk item is the Foundry JS side. The `preCreateChatMessage` hook fires before the message is persisted, which is the same hook used by pf2e-modifiers-matter. However, the critical finding is that `flags.pf2e.context.outcome` (the pre-computed degree of success string) is NOT reliably present at `preCreateChatMessage` time — pf2e-modifiers-matter calculates the outcome from scratch using the raw roll total and DC rather than reading it from a flag. The planner must decide between: (a) using `preCreateChatMessage` and computing outcome from `rollTotal − dc.value`, or (b) switching to `createChatMessage` where the message is fully formed but cannot be cancelled.

The aiohttp-inside-discord.py integration is well-established: use `aiohttp.web.AppRunner` + `TCPSite` started inside `setup_hook()` on the existing asyncio event loop. No separate thread required.

**Primary recommendation:** Use `createChatMessage` hook (fires after message is stored, outcome is fully set), compute outcome from `rollTotal - dc.value` using the pf2e degree-of-success algorithm, serve all Foundry JS assets via `StaticFiles`, add the aiohttp server to `setup_hook()` in `SentinelBot`.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Roll event capture | Browser / Foundry Client | — | JS module runs inside Foundry's browser context |
| Event authentication (X-Sentinel-Key) | Browser / Foundry Client | — | Header added by JS before fetch |
| Event ingestion + classification | API / Backend (pf2e module) | — | FastAPI `POST /foundry/event` |
| LLM narration | API / Backend (pf2e module) | — | litellm.acompletion call, same as other LLM paths |
| Discord notification dispatch | API / Backend (pf2e module) → Discord bot | — | pf2e POSTs to bot's internal endpoint |
| Discord embed rendering | Discord bot container | — | bot.py receives internal POST, sends embed to channel |
| Module file distribution | API / Backend (pf2e module) StaticFiles | — | FastAPI mounts foundry-client/dist/ |
| GM settings storage | Browser / Foundry Client | — | game.settings.register world-scope |

---

## Standard Stack

### Core (existing — reuse)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `litellm` | >=1.83.0 | LLM calls for narration (D-11) | Already in pyproject.toml + Dockerfile; `acompletion()` pattern from llm.py |
| `fastapi` | >=0.135.0 | `POST /foundry/event` route (D-08); `StaticFiles` mount (D-10) | Already in stack |
| `aiohttp` | >=3.9.0 | Internal HTTP listener in bot.py (D-14) | Already a discord.py dependency; `AppRunner + TCPSite` pattern |

### New — no additional pip installs needed
The `aiohttp` package ships with `discord.py` as a required dependency and is already installed in the Discord container. No new `pip install` is required for any Phase 35 component. The pf2e module container needs no new Python dependencies.

**Version verification:** [VERIFIED: pyproject.toml + Dockerfile read in session]

---

## Architecture Patterns

### System Architecture Diagram

```
Foundry VTT (browser)
  └─ sentinel-connector.js
       ├─ preCreateChatMessage / createChatMessage hook
       │    └─ POST {BASE_URL}/modules/pathfinder/foundry/event
       │         X-Sentinel-Key: <world setting>
       └─ game.settings.get('sentinel-connector', 'baseUrl')
              │
              ▼
pf2e-module container (FastAPI :8000)
  └─ POST /foundry/event  ← app/routes/foundry.py
       │  validates X-Sentinel-Key
       │  classifies event_type (roll | chat)
       │
       ├─ [roll] → app/foundry.py helpers
       │    ├─ litellm.acompletion() → narrative str
       │    └─ POST http://discord-bot:8001/internal/notify
       │         X-Sentinel-Key: <shared secret>
       │         {embed payload}
       │
       └─ GET /foundry/module.json  ← StaticFiles
          GET /foundry/sentinel-connector.zip
              │
              ▼
discord-bot container (discord.py + aiohttp :8001)
  └─ aiohttp POST /internal/notify handler
       └─ bot.get_channel(DISCORD_ALLOWED_CHANNELS[0]).send(embed=...)
```

### Recommended Project Structure
```
modules/pathfinder/
├── app/
│   ├── routes/
│   │   └── foundry.py           # NEW — POST /foundry/event router
│   ├── foundry.py               # NEW — pure helpers (parse, narrate, notify)
│   └── config.py                # EXTEND — foundry_narration_model field
├── foundry-client/
│   ├── module.json              # Foundry manifest
│   ├── sentinel-connector.js    # ES module
│   └── package.sh               # zip builder script
└── compose.yml                  # EXTEND — FOUNDRY_NARRATION_MODEL, DISCORD_BOT_INTERNAL_URL

interfaces/discord/
└── bot.py                       # EXTEND — aiohttp server in setup_hook()
```

### Pattern 1: `preCreateChatMessage` vs `createChatMessage` Hook Choice

**Critical finding:** The CONTEXT.md locked decision D-01 specifies `preCreateChatMessage`. From the pf2e-modifiers-matter source code, `preCreateChatMessage` fires before the message is stored. The `flags.pf2e.context` object IS present at this time (since pf2e-modifiers-matter uses it), but the `outcome` field on context is the pre-computed degree-of-success stored by the PF2e system itself. [ASSUMED] The PF2e system pre-computes and stores the outcome string before `preCreateChatMessage` fires, meaning `flags.pf2e.context.outcome` should be readable at preCreate time. However, pf2e-modifiers-matter does NOT read `context.outcome` — it recalculates from scratch. This suggests either: (a) the field doesn't exist at that point, or (b) the module prefers computing it for accuracy.

**Recommendation for planner:** Follow D-01 as locked. Use `preCreateChatMessage`. Read `flags.pf2e.context.outcome` if present. If not present (null/undefined), derive outcome from `rollTotal - dc.value` using the PF2e four-degree algorithm (criticalSuccess: ≥10 over, success: ≥0 over, failure: <0, criticalFailure: ≤-10 under). This defensive approach handles both scenarios.

```javascript
// Source: pf2e-modifiers-matter source (VERIFIED via WebFetch 2026-04-25)
Hooks.once('ready', () => {
  Hooks.on('preCreateChatMessage', (chatMessage, _data, _options) => {
    const pf2eFlags = chatMessage.flags?.pf2e;
    if (!pf2eFlags?.context) return true; // not a pf2e roll, pass through

    const context = pf2eFlags.context;
    const dcValue = context.dc?.value ?? context.dc?.parent?.dc?.value;
    if (dcValue == null) return true; // no DC, not a tracked roll type

    // Read pre-computed outcome or derive it
    const outcome = context.outcome ?? deriveOutcome(chatMessage.rolls?.[0]?.total, dcValue);

    // POST to Sentinel
    fetch(`${getBaseUrl()}/modules/pathfinder/foundry/event`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Sentinel-Key': game.settings.get('sentinel-connector', 'apiKey'),
      },
      body: JSON.stringify({ /* D-05 payload */ }),
    }).catch(() => {}); // fire-and-forget, never block the hook

    return true; // ALWAYS return true — never suppress the Foundry message
  });
});
```

### Pattern 2: `game.settings.register` API (v14)

[VERIFIED: Foundry VTT official documentation + WebSearch 2026-04-25]

```javascript
// Source: https://foundryvtt.com/api/classes/foundry.helpers.ClientSettings.html
Hooks.once('init', () => {
  game.settings.register('sentinel-connector', 'baseUrl', {
    name: 'Sentinel Base URL',
    hint: 'Base URL of your Sentinel server, e.g. http://192.168.1.10:8000',
    scope: 'world',   // stored in world database, GM-only write
    config: true,     // appears in module settings panel
    type: String,
    default: 'http://localhost:8000',
  });

  game.settings.register('sentinel-connector', 'apiKey', {
    name: 'Sentinel API Key',
    hint: 'The X-Sentinel-Key shared secret from your .env',
    scope: 'world',
    config: true,
    type: String,
    default: '',
  });

  game.settings.register('sentinel-connector', 'chatPrefix', {
    name: 'Chat Trigger Prefix',
    hint: 'Messages starting with this prefix are forwarded to Sentinel. Leave blank to disable chat forwarding.',
    scope: 'world',
    config: true,
    type: String,
    default: '',
  });
});

// Reading a setting:
const baseUrl = game.settings.get('sentinel-connector', 'baseUrl');
```

`scope: 'world'` means only Assistants and GMs can write the value; all players can read it. For `apiKey`, the DM should understand this is world-stored (not encrypted). Sufficient for LAN home use per CLAUDE.md security model.

**Note on `restricted` field:** There is no `restricted: true` field in v14 `game.settings.register` that makes a setting invisible to players in the settings panel — `config: true` shows it to all users in the settings UI but only GMs can save changes. To hide the API key from players entirely, either omit `config: true` (but then it's not visible to GM in UI either) or accept that players can see but not change it. For this use case, `config: true` on all three settings is correct.

### Pattern 3: `module.json` v14 Manifest Format

[VERIFIED: Foundry VTT official module development guide + WebFetch 2026-04-25]

```json
{
  "id": "sentinel-connector",
  "title": "Sentinel Connector",
  "description": "Sends PF2e roll events and chat messages to the Sentinel of Mnemosyne AI assistant.",
  "version": "1.0.0",
  "compatibility": {
    "minimum": "12",
    "verified": "14"
  },
  "esmodules": [
    "sentinel-connector.js"
  ],
  "relationships": {
    "systems": [
      {
        "id": "pf2e",
        "type": "system",
        "compatibility": {
          "minimum": "6.0.0"
        }
      }
    ]
  },
  "authors": [
    {
      "name": "Sentinel of Mnemosyne"
    }
  ],
  "manifest": "http://{MAC_MINI_IP}:8000/modules/pathfinder/foundry/module.json",
  "download": "http://{MAC_MINI_IP}:8000/modules/pathfinder/foundry/sentinel-connector.zip"
}
```

Fields `manifest` and `download` are the URLs the DM pastes into Foundry's module installer. They point back to the pf2e-module StaticFiles mount. These are hardcoded during development — the DM replaces the IP placeholder.

**Alternative:** Omit `manifest` and `download` from the JSON in the repo (they contain a LAN IP) and document them separately. The DM installs by pasting the manifest URL into Foundry's "Install Module" dialog.

### Pattern 4: aiohttp Internal HTTP Listener in bot.py

[VERIFIED: pf2e-modifiers-matter cog gist + discord.py docs 2026-04-25]

The correct pattern is `AppRunner + TCPSite` started inside `SentinelBot.setup_hook()`. The `setup_hook()` method runs on the bot's asyncio event loop after login, making it the right integration point. This does NOT require Cog-based architecture — it works directly on `SentinelBot`.

```python
# interfaces/discord/bot.py — additions to SentinelBot class
import aiohttp
from aiohttp import web

DISCORD_BOT_INTERNAL_URL = os.environ.get("DISCORD_BOT_INTERNAL_URL", "")
DISCORD_BOT_INTERNAL_PORT = int(os.environ.get("DISCORD_BOT_INTERNAL_PORT", "8001"))

class SentinelBot(discord.Client):
    def __init__(self) -> None:
        # ... existing code ...
        self._internal_runner: web.AppRunner | None = None

    async def setup_hook(self) -> None:
        # ... existing sync code (tree.sync, thread ID load) ...

        # Start internal aiohttp notification server (D-14)
        app = web.Application()
        app.router.add_post('/internal/notify', self._handle_internal_notify)
        self._internal_runner = web.AppRunner(app)
        await self._internal_runner.setup()
        site = web.TCPSite(self._internal_runner, '0.0.0.0', DISCORD_BOT_INTERNAL_PORT)
        await site.start()
        logger.info("Internal notification server started on port %d", DISCORD_BOT_INTERNAL_PORT)

    async def _handle_internal_notify(self, request: web.Request) -> web.Response:
        # Validate X-Sentinel-Key
        key = request.headers.get('X-Sentinel-Key', '')
        if key != SENTINEL_API_KEY:
            return web.Response(status=401)
        data = await request.json()
        # Build embed from data and send to channel
        # ... (see D-16 embed shape) ...
        return web.Response(status=200)

    async def close(self) -> None:
        if self._internal_runner:
            await self._internal_runner.cleanup()
        await super().close()
```

**Port choice:** 8001. This does NOT need to be exposed publicly — only within the Docker internal network. In `interfaces/discord/compose.yml` it should NOT be port-mapped to the host; only accessible inside the `sentinel-network`.

**aiohttp version compatibility:** discord.py 2.7.x requires `aiohttp>=3.9.1`. The `AppRunner/TCPSite` API is stable across aiohttp 3.x. No conflict. [CITED: https://pypi.org/project/discord.py/]

### Pattern 5: FastAPI `StaticFiles` Mount

[VERIFIED: FastAPI docs + existing `app.include_router` pattern in main.py 2026-04-25]

```python
# modules/pathfinder/app/main.py additions
from fastapi.staticfiles import StaticFiles
from pathlib import Path

# Mount after app = FastAPI(...) construction but before route includes
FOUNDRY_CLIENT_DIST = Path(__file__).parent.parent / "foundry-client"
if FOUNDRY_CLIENT_DIST.exists():
    app.mount("/foundry/static", StaticFiles(directory=str(FOUNDRY_CLIENT_DIST)), name="foundry_static")
```

`module.json` served from `/foundry/static/module.json`. The DM's manifest URL is `http://{IP}:8000/foundry/static/module.json`. The zip is served at `http://{IP}:8000/foundry/static/sentinel-connector.zip`.

The `GET /foundry/module.json` and `GET /foundry/sentinel-connector.zip` aliases from D-10 can be implemented as explicit FastAPI routes that return `FileResponse`, or the StaticFiles mount alone is sufficient since the DM pastes the direct URL. The planner should choose StaticFiles-only (simpler, no extra route).

### Pattern 6: `POST /foundry/event` Route Structure

Mirror `app/routes/session.py` single-route-many-verbs pattern:

```python
# modules/pathfinder/app/routes/foundry.py
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import logging
from typing import Literal, Optional
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/foundry", tags=["foundry"])

class FoundryRollEvent(BaseModel):
    event_type: Literal["roll"]
    roll_type: str
    actor_name: str
    target_name: Optional[str] = None
    outcome: str
    roll_total: int
    dc: Optional[int] = None
    dc_hidden: bool = False
    item_name: Optional[str] = None
    timestamp: str

class FoundryChatEvent(BaseModel):
    event_type: Literal["chat"]
    actor_name: str
    content: str
    timestamp: str

class FoundryEvent(BaseModel):
    event_type: str
    # Additional fields validated in dispatch

@router.post("/event")
async def foundry_event(req: FoundryEvent) -> JSONResponse:
    # dispatch to app.foundry helpers
    ...
```

### Pattern 7: Zip Structure for Foundry Module

[VERIFIED: Foundry VTT module development docs + WebSearch 2026-04-25]

Foundry expects the zip to contain the module folder at its root, meaning the directory named after the module ID is the first entry inside the zip. When unzipped, Foundry places the contents inside `{userData}/Data/modules/sentinel-connector/`.

**Correct zip structure:**
```
sentinel-connector.zip
└── sentinel-connector/
    ├── module.json
    └── sentinel-connector.js
```

**`package.sh` script:**
```bash
#!/bin/bash
# modules/pathfinder/foundry-client/package.sh
# Creates sentinel-connector.zip with correct subdirectory structure

cd "$(dirname "$0")/.."  # cd to modules/pathfinder/
rm -f foundry-client/sentinel-connector.zip
zip -r foundry-client/sentinel-connector.zip foundry-client/module.json foundry-client/sentinel-connector.js \
    --junk-paths --prefix sentinel-connector/
```

**Alternative (more robust):**
```bash
#!/bin/bash
cd "$(dirname "$0")"       # cd to foundry-client/
cd ..                       # cd to modules/pathfinder/
zip -r foundry-client/sentinel-connector.zip foundry-client -i "foundry-client/module.json" -i "foundry-client/sentinel-connector.js"
```

The simplest approach for development: create a `sentinel-connector/` sibling directory, copy files in, zip that directory, delete it. The planner should pick the cleanest one-liner that produces a zip where `unzip -l` shows `sentinel-connector/module.json` at the top.

### Pattern 8: LLM Narration Function

New function in `app/llm.py` following the established pattern:

```python
async def generate_foundry_narrative(
    actor_name: str,
    target_name: str | None,
    item_name: str | None,
    outcome: str,
    roll_total: int,
    dc: int | None,
    model: str,
    api_base: str | None = None,
) -> str:
    """Generate a 20-word dramatic narrative for a PF2e roll result (D-11).

    Returns plain string. On failure, returns empty string (caller uses fallback).
    Never raises — D-13 fallback policy.
    """
    outcome_labels = {
        "criticalSuccess": "critical success",
        "success": "success",
        "failure": "failure",
        "criticalFailure": "critical failure",
    }
    outcome_label = outcome_labels.get(outcome, outcome)
    ...
```

### Anti-Patterns to Avoid

- **Blocking the Foundry hook by awaiting the fetch:** The `preCreateChatMessage` callback must be synchronous or return a Promise that resolves quickly. Use `.catch(() => {})` to make it truly fire-and-forget. Never `await` inside the hook if it might delay Foundry's message rendering.
- **Returning `false` from `preCreateChatMessage`:** This cancels the message and suppresses it from Foundry's chat. The sentinel-connector must always return `true`. [VERIFIED: pf2e-modifiers-matter source always returns `true`]
- **Relying on `bot.loop` attribute in discord.py 2.x:** The `bot.loop` attribute is deprecated in discord.py v2. Use `asyncio.get_event_loop()` or create tasks inside `setup_hook()` which runs in the correct loop.
- **Using `web.run_app()` in aiohttp alongside discord.py:** This tries to take over the event loop. Use `AppRunner + TCPSite` started as async within `setup_hook()` instead.
- **Placing `StaticFiles` directory at the app level instead of per-router:** `app.mount()` at the top-level FastAPI app is correct. Do NOT try to mount inside a router — `StaticFiles` requires the `app.mount()` interface.
- **Including `manifest` and `download` URLs with hardcoded IPs in version control:** Either document them as fill-in-the-blank in a separate README, or generate them at serve-time from a config env var.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Serving static JS/JSON from FastAPI | Custom file endpoint | `fastapi.staticfiles.StaticFiles` | Handles ETag, If-Modified-Since, range requests automatically |
| HTTP server inside discord.py | Thread-based Flask/FastAPI | `aiohttp AppRunner + TCPSite` in `setup_hook()` | Shares event loop with discord.py; no threading issues |
| PF2e degree-of-success calculation | Custom algorithm | Use pf2e-modifiers-matter's pattern: `deltaFromDc = rollTotal - dcValue` then standard four-degree rules | Edge cases: nat-1 always crits down, nat-20 always crits up |
| Request validation in FastAPI | Manual `if "field" not in data:` checks | Pydantic BaseModel with Optional fields and validators | Already the project pattern |
| aiohttp client in pathfinder→bot POST | Persistent connection manager | Single-call `httpx.AsyncClient()` as context manager | Bot endpoint is fire-and-forget; persistent client unnecessary |

---

## Runtime State Inventory

Step 2.5 SKIPPED — this is a greenfield feature addition, not a rename/refactor/migration phase. No existing runtime state uses a "foundry" or "sentinel-connector" string that would require migration.

---

## Common Pitfalls

### Pitfall 1: PF2e `outcome` Field Not Present at `preCreateChatMessage` Time
**What goes wrong:** CONTEXT.md D-01 assumes `flags.pf2e.context.outcome` is pre-computed. pf2e-modifiers-matter does NOT read this field — it recalculates from roll total and DC.
**Why it happens:** The outcome string may be computed after the preCreate hook fires, or the TypeScript type shows it but it's not populated until the message is saved.
**How to avoid:** Defensive null-check: `const outcome = context.outcome ?? deriveOutcome(rollTotal, dcValue)`. Implement `deriveOutcome` using the PF2e four-degree algorithm.
**Warning signs:** If `context.outcome` is always `undefined` in testing, the derive fallback kicks in silently.

### Pitfall 2: `preCreateChatMessage` vs `createChatMessage` — Roll Data Availability
**What goes wrong:** If using `preCreateChatMessage` and `message.rolls` is not yet populated (it might be added to the message object after the hook fires), `roll.total` will be undefined.
**Why it happens:** Some versions of Foundry document hooks pass the pre-populated data object, others pass a mutable init object.
**How to avoid:** `const rollTotal = chatMessage.rolls?.[0]?.total ?? chatMessage.roll?.total;` with defensive fallback. If both are null, skip the event (don't POST garbage).
**Warning signs:** `roll_total: null` in the POST body causes backend validation errors.

### Pitfall 3: StaticFiles Mount Ordering in FastAPI
**What goes wrong:** If `app.mount("/foundry/static", StaticFiles(...))` is called before the app object is fully built, or after a router at `/foundry/` is included, path conflicts cause 404s.
**Why it happens:** FastAPI routes are matched in registration order. A router registered at `/foundry` prefix captures `/foundry/static` paths before the StaticFiles mount sees them.
**How to avoid:** Mount `StaticFiles` BEFORE including the `foundry_router`. Or use a non-overlapping path: mount at `/foundry-assets/` and declare `module.json` manifest URL accordingly.

### Pitfall 4: Docker Network for aiohttp Internal Listener
**What goes wrong:** The discord-bot container's aiohttp listener on port 8001 is not reachable from the pf2e-module container if they're on different Docker networks.
**Why it happens:** Docker Compose uses per-project default networks unless explicitly shared.
**How to avoid:** Ensure both `pf2e-module` (in `modules/pathfinder/compose.yml`) and `discord-bot` (in `interfaces/discord/compose.yml`) share the same Docker network (`sentinel-network`). The top-level `docker-compose.yml` defines this network; both services must declare it. Verify with `docker inspect sentinel-network` after startup.
**Warning signs:** `httpx.ConnectError` in pf2e-module logs when posting to `http://discord-bot:8001`.

### Pitfall 5: aiohttp `AppRunner.cleanup()` on Bot Shutdown
**What goes wrong:** If `cleanup()` is not called during bot shutdown, the aiohttp server leaks its socket.
**Why it happens:** `AppRunner` holds an active TCP listener; Python's GC does not automatically close it.
**How to avoid:** Override `SentinelBot.close()` to call `await self._internal_runner.cleanup()` before `await super().close()`.

### Pitfall 6: Foundry Module Settings `restricted` vs `config`
**What goes wrong:** Setting `config: true` makes the API key visible to all players in the Module Settings panel (they can see it, just not save changes).
**Why it happens:** There is no `restricted: true` field in v14 `game.settings.register`. GM-only _write_ is automatic for `scope: "world"` but visibility to players is unavoidable with `config: true`.
**How to avoid:** Accept for home LAN use (shared secret, not a production secret). If key secrecy is needed in a future phase, use `config: false` for the key and require GM to set it via console.
**Warning signs:** Players open Module Settings and see the API key in plaintext.

### Pitfall 7: zip structure — flat vs subdirectory
**What goes wrong:** If `package.sh` creates a zip with `module.json` at the root (no subdirectory), Foundry unzips it into `{modules}/` directly, not into `{modules}/sentinel-connector/`. The module is not findable.
**Why it happens:** `zip file.zip module.json sentinel-connector.js` creates a flat zip.
**How to avoid:** The zip must contain a `sentinel-connector/` directory. Use: `cd /tmp && mkdir sentinel-connector && cp /path/module.json sentinel-connector/ && cp /path/sentinel-connector.js sentinel-connector/ && zip -r /output/sentinel-connector.zip sentinel-connector/ && rm -rf sentinel-connector`

---

## Code Examples

### Foundry Hook Registration (complete skeleton)
```javascript
// Source: pf2e-modifiers-matter pattern (VERIFIED 2026-04-25) + Foundry v14 docs
const MODULE_ID = 'sentinel-connector';

function deriveOutcome(rollTotal, dcValue) {
  // PF2e four-degree algorithm
  const delta = rollTotal - dcValue;
  if (delta >= 10) return 'criticalSuccess';
  if (delta >= 0)  return 'success';
  if (delta >= -9) return 'failure';
  return 'criticalFailure';
}

Hooks.once('init', () => {
  game.settings.register(MODULE_ID, 'baseUrl', {
    name: 'Sentinel Base URL',
    scope: 'world', config: true, type: String, default: 'http://localhost:8000',
  });
  game.settings.register(MODULE_ID, 'apiKey', {
    name: 'Sentinel API Key',
    scope: 'world', config: true, type: String, default: '',
  });
  game.settings.register(MODULE_ID, 'chatPrefix', {
    name: 'Chat Trigger Prefix (optional)',
    scope: 'world', config: true, type: String, default: '',
  });
});

Hooks.once('ready', () => {
  Hooks.on('preCreateChatMessage', (chatMessage, _data, _options) => {
    const pf2eFlags = chatMessage.flags?.pf2e ?? chatMessage.flags?.sf2e;
    if (!pf2eFlags?.context) {
      // Not a PF2e roll — check chat prefix
      const prefix = game.settings.get(MODULE_ID, 'chatPrefix');
      if (!prefix) return true;
      const content = chatMessage.content ?? '';
      if (!content.startsWith(prefix)) return true;
      _postChatEvent(chatMessage, prefix);
      return true;
    }

    const context = pf2eFlags.context;
    const dcValue = context.dc?.value ?? context.dc?.parent?.dc?.value;
    if (dcValue == null) return true; // no DC tracked

    const rollTotal = chatMessage.rolls?.[0]?.total ?? chatMessage.roll?.total;
    if (rollTotal == null) return true; // roll data not available

    const outcome = context.outcome ?? deriveOutcome(rollTotal, dcValue);
    const actorName = chatMessage.actor?.name ?? chatMessage.speaker?.alias ?? 'Unknown';
    const targetTokenUuid = context.target?.token;
    // targetName requires resolving the UUID — use synchronous fromUuidSync if available
    const targetToken = targetTokenUuid ? fromUuidSync?.(targetTokenUuid) : null;
    const targetName = targetToken?.name ?? null;

    _postRollEvent({
      event_type: 'roll',
      roll_type: context.type ?? 'check',
      actor_name: actorName,
      target_name: targetName,
      outcome: outcome,
      roll_total: rollTotal,
      dc: dcValue,
      dc_hidden: dcValue == null,
      item_name: pf2eFlags.origin?.name ?? null,
      timestamp: new Date().toISOString(),
    });
    return true; // NEVER suppress the message
  });
});

function _postRollEvent(payload) {
  const baseUrl = game.settings.get(MODULE_ID, 'baseUrl');
  const apiKey = game.settings.get(MODULE_ID, 'apiKey');
  if (!apiKey) return; // not configured
  fetch(`${baseUrl}/modules/pathfinder/foundry/event`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Sentinel-Key': apiKey },
    body: JSON.stringify(payload),
  }).catch(err => console.warn('[sentinel-connector] POST failed:', err));
}

function _postChatEvent(chatMessage, prefix) {
  const baseUrl = game.settings.get(MODULE_ID, 'baseUrl');
  const apiKey = game.settings.get(MODULE_ID, 'apiKey');
  if (!apiKey) return;
  const content = (chatMessage.content ?? '').replace(prefix, '').trim();
  fetch(`${baseUrl}/modules/pathfinder/foundry/event`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Sentinel-Key': apiKey },
    body: JSON.stringify({
      event_type: 'chat',
      actor_name: chatMessage.speaker?.alias ?? 'DM',
      content: content,
      timestamp: new Date().toISOString(),
    }),
  }).catch(err => console.warn('[sentinel-connector] POST failed:', err));
}
```

### Config Extension Pattern (app/config.py)
```python
# modules/pathfinder/app/config.py — add to Settings class
# Pattern matches session_recap_model: str | None = None (D-37 in Phase 34 CONTEXT.md)
foundry_narration_model: str | None = None  # FOUNDRY_NARRATION_MODEL env var; fallback: litellm_model
```

### Discord Embed Builder for Foundry Rolls (bot.py)
```python
# Source: existing build_harvest_embed + build_session_embed patterns in bot.py
def build_foundry_roll_embed(data: dict) -> "discord.Embed":
    """Build embed for a Foundry roll event notification (D-16)."""
    OUTCOME_EMOJIS = {
        "criticalSuccess": "🎯",
        "success": "✅",
        "failure": "❌",
        "criticalFailure": "💀",
    }
    OUTCOME_LABELS = {
        "criticalSuccess": "Critical Hit!",
        "success": "Success",
        "failure": "Failure",
        "criticalFailure": "Critical Failure!",
    }
    OUTCOME_COLORS = {
        "criticalSuccess": discord.Color.gold(),
        "success": discord.Color.green(),
        "failure": discord.Color.orange(),
        "criticalFailure": discord.Color.red(),
    }
    outcome = data.get("outcome", "")
    actor = data.get("actor_name", "?")
    target = data.get("target_name")
    narrative = data.get("narrative", "")
    roll_total = data.get("roll_total", "?")
    dc = data.get("dc")
    dc_hidden = data.get("dc_hidden", False)
    item_name = data.get("item_name", "")
    roll_type = data.get("roll_type", "check")

    emoji = OUTCOME_EMOJIS.get(outcome, "🎲")
    label = OUTCOME_LABELS.get(outcome, outcome.capitalize())
    color = OUTCOME_COLORS.get(outcome, discord.Color.blue())

    if target:
        title = f"{emoji} {label} | {actor} vs {target}"
    else:
        title = f"{emoji} {label} | {actor} ({roll_type})"

    dc_str = "DC: [hidden]" if dc_hidden else f"DC/AC: {dc}"
    footer_parts = [f"Roll: {roll_total}", dc_str]
    if item_name:
        footer_parts.append(item_name)
    footer = " | ".join(footer_parts)

    embed = discord.Embed(
        title=title,
        description=narrative[:4000] if narrative else None,
        color=color,
    )
    embed.set_footer(text=footer)
    return embed
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `scripts` array in module.json | `esmodules` array for ES module files | Foundry v10+ | Use `esmodules` not `scripts` for any `import/export` JS |
| `discord.Client.loop.create_task()` for background tasks | `setup_hook()` async method | discord.py v2.0 | `loop` attribute deprecated; setup_hook is the replacement |
| `system` field for system dependency | `relationships.systems` array | Foundry v10+ | `system` field removed; use `relationships` |

**Deprecated/outdated:**
- `scripts` array: still works but `esmodules` is the v14 recommendation for ES6 modules.
- `discord.Client.loop`: deprecated in v2.0; `setup_hook()` is the v2 pattern.
- `module.json` v9 flat fields (`author`, `url`): replaced by `authors` array and link objects in v10+.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `flags.pf2e.context.outcome` (pre-computed degree-of-success string) may not be present at `preCreateChatMessage` time | Pitfall 1, Hook Pattern | If wrong (outcome IS always present), the `deriveOutcome` fallback is unused but harmless. If right (outcome is absent), without the fallback we'd POST `null` and the backend would fail to narrate. |
| A2 | `fromUuidSync()` is available globally in Foundry v14 for synchronously resolving token UUIDs | Hook Pattern code example | If not available, target name resolution must be omitted (send `target_name: null`) |
| A3 | pf2e `context.type` contains values like `"attack-roll"`, `"saving-throw"`, `"skill-check"` | D-05 payload | From CONTEXT.md decision, not verified in source code. Could be different strings (e.g., `"strike"`, `"save"`). Module should send `context.type` as-is and let backend interpret. |
| A4 | The zip must have `sentinel-connector/module.json` at root (subdirectory named after module ID) | D-18 zip structure | If wrong (flat zip expected), Foundry install would dump files into modules/ root and fail. |
| A5 | discord.py 2.7.x and aiohttp 3.9.x are compatible (no version conflict) | D-14 aiohttp pattern | If wrong, the Discord container restart-loops on import error. Verify with `pip show aiohttp` in container. |

---

## Open Questions (RESOLVED)

1. **`preCreateChatMessage` vs `createChatMessage` — outcome availability** — RESOLVED
   - What we know: pf2e-modifiers-matter uses `preCreateChatMessage` but derives outcome from scratch rather than reading `context.outcome`
   - What's unclear: Whether `context.outcome` is populated before `preCreateChatMessage` fires, or only after the message is stored
   - Recommendation: Implement with the defensive fallback (read `context.outcome`, derive if null). If the DM reports missing outcomes in production, switch to `createChatMessage`.
   - **Resolution:** Use `preCreateChatMessage` (D-01 locked). Read `context.outcome ?? deriveOutcome()` as the defensive fallback implemented in Plan 35-05.

2. **`context.type` string values for roll classification (D-05)** — RESOLVED
   - What we know: pf2e-modifiers-matter uses `dcSlug` (`"armor"` = strike, `"fortitude"` = Fort save) rather than a roll type string
   - What's unclear: Whether `context.type` contains `"attack-roll"`, `"saving-throw"`, `"skill-check"` (as CONTEXT.md assumes) or different values
   - Recommendation: Log `context.type` in the JS module during development session. Send the value as-is in the `roll_type` field. Backend accepts any string.
   - **Resolution:** Filter on `flags.pf2e` existence rather than type string. Treat any message with `flags.pf2e.context` as an eligible roll. Send `context.type` as-is in `roll_type`; backend accepts any string.

3. **Actor name resolution: `chatMessage.actor?.name` vs `chatMessage.speaker?.alias`** — RESOLVED
   - What we know: `chatMessage.speaker.alias` is the display name visible in chat; `chatMessage.actor?.name` may be the actual actor document name
   - What's unclear: Which is more reliable for NPC vs PC identification
   - Recommendation: Use `chatMessage.actor?.name ?? chatMessage.speaker?.alias ?? 'Unknown'` — actor name preferred, speaker alias as fallback.
   - **Resolution:** Use `message.speaker?.alias` as primary (always populated for player speakers in PF2e chat); `message.actor?.name` as fallback.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| aiohttp | bot.py internal listener (D-14) | ✓ | ships with discord.py >=2.7.x | — (required by discord.py) |
| fastapi `StaticFiles` | `/foundry/static/` mount (D-10) | ✓ | part of fastapi | — |
| litellm | LLM narration (D-11) | ✓ | >=1.83.0 in pyproject.toml | — |

All dependencies required by Phase 35 are already installed. No new pip install steps.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (asyncio_mode = "auto") |
| Config file | `modules/pathfinder/pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `cd modules/pathfinder && python -m pytest tests/test_foundry.py -x` |
| Full suite command | `cd modules/pathfinder && python -m pytest tests/ -x` |

### TDD Eligibility Table

| Component | TDD-Eligible? | Reason |
|-----------|--------------|--------|
| `app/routes/foundry.py` — `POST /foundry/event` route | YES | Pydantic validation, event classification, auth check are pure I/O |
| `app/foundry.py` — LLM narration + fallback | YES | `generate_foundry_narrative` can be mocked like `generate_session_recap` |
| `app/foundry.py` — Discord notification POST (httpx call to bot) | YES | Mock httpx.AsyncClient, assert payload shape |
| `app/config.py` extension (`foundry_narration_model`) | YES | Settings instantiation test |
| `app/main.py` REGISTRATION_PAYLOAD + StaticFiles mount | YES | Test that `/foundry/event` appears in the registration payload |
| `build_foundry_roll_embed()` in bot.py | YES | Pure function; existing conftest.py `_EmbedStub` pattern |
| `_handle_internal_notify()` in bot.py | YES | Mocked aiohttp request; test auth + embed dispatch |
| Foundry JS module (`sentinel-connector.js`) | NO | Requires Foundry VTT browser environment; no JS test harness in this project |
| aiohttp server startup in `setup_hook()` | NO | Requires live asyncio + discord.py event loop |
| Integration: Foundry → pf2e-module → bot → Discord | NO | End-to-end requires Foundry VTT running |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FVT-01 | `POST /foundry/event` accepts roll payload with valid X-Sentinel-Key | unit | `pytest tests/test_foundry.py::test_roll_event_accepted -x` | ❌ Wave 0 |
| FVT-01 | `POST /foundry/event` rejects missing/wrong X-Sentinel-Key → 401 | unit | `pytest tests/test_foundry.py::test_auth_rejected -x` | ❌ Wave 0 |
| FVT-01 | `POST /foundry/event` rejects malformed event payload → 422 | unit | `pytest tests/test_foundry.py::test_invalid_payload -x` | ❌ Wave 0 |
| FVT-02 | pf2e module POSTs to bot internal endpoint on roll event | unit | `pytest tests/test_foundry.py::test_notify_dispatched -x` | ❌ Wave 0 |
| FVT-02 | LLM timeout produces fallback text (D-13), still sends embed | unit | `pytest tests/test_foundry.py::test_llm_fallback -x` | ❌ Wave 0 |
| FVT-03 | `build_foundry_roll_embed` produces correct title/footer for criticalSuccess | unit | `pytest tests/test_discord_foundry.py::test_embed_critical_success -x` | ❌ Wave 0 |
| FVT-03 | `build_foundry_roll_embed` shows `DC: [hidden]` when dc_hidden=True | unit | `pytest tests/test_discord_foundry.py::test_embed_hidden_dc -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd modules/pathfinder && python -m pytest tests/test_foundry.py -x`
- **Per wave merge:** `cd modules/pathfinder && python -m pytest tests/ -x && cd ../../interfaces/discord && python -m pytest tests/ -x`
- **Phase gate:** Both test suites green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `modules/pathfinder/tests/test_foundry.py` — covers FVT-01, FVT-02 route + helper tests
- [ ] `interfaces/discord/tests/test_discord_foundry.py` — covers FVT-03 embed builder tests
- [ ] Framework already installed — no additional pytest setup needed

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `X-Sentinel-Key` header check on `POST /foundry/event` (same pattern as all other routes) |
| V3 Session Management | no | Stateless POST, no session |
| V4 Access Control | yes | Foundry `scope: "world"` for GM-only settings write |
| V5 Input Validation | yes | Pydantic model for FoundryEvent; JS content sanitized before POST |
| V6 Cryptography | no | Shared secret header (existing project standard, not bcrypt/JWT) |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Rogue Foundry module POSTing fake events | Spoofing | `X-Sentinel-Key` header validation on `POST /foundry/event` |
| LLM prompt injection via actor/item names | Tampering | System prompt "opaque data" anchor (D-11 system prompt); truncate field lengths |
| JS module exposing API key to non-GM players | Information Disclosure | `config: true` with `scope: "world"` — acceptable for home LAN use; document the limitation |
| Flood of roll events overwhelming pf2e-module | DoS | No rate-limiting in MVP; acceptable for single-table home use |

---

## Sources

### Primary (HIGH confidence)
- pf2e-modifiers-matter `scripts/pf2e-modifiers-matter.mjs` source (VERIFIED via WebFetch 2026-04-25) — hook name, `flags.pf2e.context` field paths, `dc.value`, `dc.slug`, `target.token`, return `true` pattern
- Foundry VTT module development docs `https://foundryvtt.com/article/module-development/` (VERIFIED via WebFetch 2026-04-25) — `esmodules` array, `compatibility` block shape
- aiohttp cog gist `https://gist.github.com/anshulxyz/437dc88597f661bb8f18570ab4f0d2bc` (VERIFIED via WebFetch 2026-04-25) — `AppRunner + TCPSite` pattern
- `modules/pathfinder/app/llm.py` (VERIFIED: read in session) — `litellm.acompletion()` signature, `_strip_code_fences` helper, timeout pattern
- `modules/pathfinder/app/config.py` (VERIFIED: read in session) — Settings class extension pattern
- `interfaces/discord/bot.py` (VERIFIED: read in session) — `SentinelBot.setup_hook()` pattern, embed builder pattern, `SENTINEL_API_KEY` module-level var

### Secondary (MEDIUM confidence)
- WebSearch Foundry VTT `game.settings.register` v12-v14 — `scope: "world"`, `config: true`, `type: String` verified in multiple sources
- Foundry VTT packaging guide search results — module zip must contain subdirectory named after module ID
- pf2e source `src/module/chat-message/document.ts` (WebFetch 2026-04-25) — `context.type === "damage-roll"` confirmed as a type value

### Tertiary (LOW confidence)
- `flags.pf2e.context.outcome` field being pre-populated at preCreateChatMessage time — NOT directly confirmed; inferred from D-01 CONTEXT.md decision plus defensive fallback recommended

---

## Project Constraints (from CLAUDE.md)

- Python 3.12, FastAPI >=0.135.0, httpx (not requests), Pydantic v2 syntax
- New Python deps: dual-ship in `modules/pathfinder/pyproject.toml` AND `modules/pathfinder/Dockerfile` — Phase 35 adds NO new Python deps (aiohttp is already installed via discord.py)
- `docker compose` (v2, no hyphen)
- No `requests` library — use `httpx.AsyncClient()`
- Structured logging via `logging.getLogger(__name__)` pattern (from Phase 34 D-38)
- `sentinel-connector.js` is a new JS artifact, NOT a Python dep — no dual-ship concern for JS
- The bot.py internal port (8001) must NOT be port-mapped to the Docker host in `interfaces/discord/compose.yml` — internal network only

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all existing Python/FastAPI patterns; no new dependencies
- Foundry JS hook API: MEDIUM — hook name verified, field paths verified from real module source; outcome field LOW
- Architecture (aiohttp pattern): HIGH — `AppRunner + TCPSite` pattern verified from working example
- Pitfalls: MEDIUM — based on code inspection and community patterns; not all verified from official docs

**Research date:** 2026-04-25
**Valid until:** 2026-05-25 (Foundry v14 stable; pf2e system API relatively stable; discord.py 2.7.x stable)
