# Phase 35: Foundry VTT Event Ingest — Pattern Map

**Mapped:** 2026-04-25
**Files analyzed:** 13 (5 new, 5 modified, 2 test files, 1 shell script)
**Analogs found:** 11 / 13

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `modules/pathfinder/app/routes/foundry.py` | route | request-response | `modules/pathfinder/app/routes/session.py` | exact |
| `modules/pathfinder/app/foundry.py` | service/utility | request-response | `modules/pathfinder/app/llm.py` | exact |
| `modules/pathfinder/foundry-client/module.json` | config | — | none (JS/JSON manifest) | no analog |
| `modules/pathfinder/foundry-client/sentinel-connector.js` | client/adapter | event-driven | none (browser JS, no project analog) | no analog |
| `modules/pathfinder/foundry-client/package.sh` | utility | batch | none (shell scripts rare) | no analog |
| `modules/pathfinder/app/main.py` (modify) | config/bootstrap | request-response | self (existing patterns) | self |
| `modules/pathfinder/app/config.py` (modify) | config | — | self (existing Settings class) | self |
| `interfaces/discord/bot.py` (modify) | service/listener | event-driven | self (`setup_hook` + embed builders) | self |
| `modules/pathfinder/compose.yml` (modify) | config | — | self (existing env block) | self |
| `.env.example` (modify) | config | — | self (Phase 34 SESSION block) | self |
| `modules/pathfinder/tests/test_foundry.py` | test | request-response | `modules/pathfinder/tests/test_session_integration.py` | role-match |
| `interfaces/discord/tests/test_discord_foundry.py` | test | request-response | `interfaces/discord/tests/test_subcommands.py` | role-match |

---

## Pattern Assignments

### `modules/pathfinder/app/routes/foundry.py` (route, request-response)

**Analog:** `modules/pathfinder/app/routes/session.py`

**Imports pattern** (lines 18-48 of session.py):
```python
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/foundry", tags=["foundry"])

# Module-level singletons — set by main.py lifespan, patchable in tests.
# (For foundry.py: no Obsidian singleton needed; httpx client for bot notify is per-call)
```

**Auth pattern** — the project uses `X-Sentinel-Key` validation. Copy from `interfaces/discord/bot.py`'s `SENTINEL_API_KEY` module-level var and compare in route:
```python
# Validate X-Sentinel-Key on every POST /foundry/event
import os
SENTINEL_API_KEY: str = os.environ.get("SENTINEL_API_KEY", "")

# In route handler:
from fastapi import Header
async def foundry_event(
    req: FoundryEventUnion,
    x_sentinel_key: str = Header(default=""),
) -> JSONResponse:
    if x_sentinel_key != SENTINEL_API_KEY:
        raise HTTPException(status_code=401, detail={"error": "unauthorized"})
```

**Core event-dispatch pattern** (adapted from session.py lines 629-660):
```python
@router.post("/event")
async def foundry_event(req: FoundryEventUnion) -> JSONResponse:
    """Dispatch Foundry event to the appropriate handler (FVT-01..03)."""
    event_type = req.event_type
    if event_type == "roll":
        result = await _handle_roll(req)
    elif event_type == "chat":
        result = await _handle_chat(req)
    else:
        raise HTTPException(status_code=422, detail={"error": f"unknown event_type: {event_type!r}"})
    return JSONResponse(content=result)
```

**Pydantic model pattern** (session.py lines 86-109):
```python
class FoundryRollEvent(BaseModel):
    event_type: Literal["roll"]
    roll_type: str
    actor_name: str
    target_name: str | None = None
    outcome: str
    roll_total: int
    dc: int | None = None
    dc_hidden: bool = False
    item_name: str | None = None
    timestamp: str

class FoundryChatEvent(BaseModel):
    event_type: Literal["chat"]
    actor_name: str
    content: str
    timestamp: str
```

**Error handling pattern** (session.py lines 267-275):
```python
try:
    result = await some_operation()
    logger.info("foundry_event: event_type=%s actor=%s", event_type, actor_name)
except Exception as exc:
    logger.error("foundry_event: operation failed: %s", exc)
    raise HTTPException(
        status_code=503,
        detail={"error": "internal error", "detail": str(exc)},
    )
```

**503 guard on uninitialized singleton** (session.py lines 636-640):
```python
if some_singleton is None:
    raise HTTPException(
        status_code=503,
        detail={"error": "foundry subsystem not initialised (lifespan incomplete?)"},
    )
```

---

### `modules/pathfinder/app/foundry.py` (service/utility, request-response)

**Analog:** `modules/pathfinder/app/llm.py`

**Module header pattern** (llm.py lines 1-23):
```python
"""Foundry VTT event helpers — LLM narration and Discord notification dispatch.

Calls litellm.acompletion() for roll narration (D-11).
POSTs to Discord bot internal endpoint via httpx.AsyncClient (D-14).

Never raises on LLM failure — D-13 fallback policy: plain-text summary returned.
"""
import logging

import litellm

logger = logging.getLogger(__name__)
```

**LLM call pattern** (llm.py lines 78-91 — `extract_npc_fields`):
```python
kwargs: dict = {
    "model": model,
    "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ],
    "timeout": 30.0,  # short timeout for per-roll narration (max 20 words)
}
if api_base:
    kwargs["api_base"] = api_base

response = await litellm.acompletion(**kwargs)
content = response.choices[0].message.content
return content.strip()
```

**D-13 fallback pattern** (llm.py lines 874-880 — `generate_story_so_far`):
```python
async def generate_foundry_narrative(...) -> str:
    """Generate 20-word dramatic narrative for a PF2e roll result (D-11).

    Returns plain string. On failure, returns empty string (caller uses fallback).
    Never raises — D-13 fallback policy.
    """
    try:
        response = await litellm.acompletion(**kwargs)
        content = response.choices[0].message.content or ""
        return content.strip()
    except Exception as exc:
        logger.warning("generate_foundry_narrative: LLM call failed: %s", exc)
        return ""  # caller builds plain-text fallback
```

**Plain-text fallback builder** (D-13):
```python
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

def build_narrative_fallback(event: FoundryRollEvent) -> str:
    emoji = OUTCOME_EMOJIS.get(event.outcome, "🎲")
    label = OUTCOME_LABELS.get(event.outcome, event.outcome)
    target = f" → {event.target_name}" if event.target_name else f" ({event.roll_type})"
    dc_str = f"vs DC {event.dc}" if not event.dc_hidden and event.dc else ""
    return f"{emoji} {label} | {event.actor_name}{target} | Roll: {event.roll_total} {dc_str}".strip()
```

**httpx fire-and-forget pattern** (from RESEARCH.md "Don't Hand-Roll" table):
```python
async def notify_discord_bot(payload: dict, bot_url: str, api_key: str) -> None:
    """POST embed payload to Discord bot internal endpoint (D-14).

    Fire-and-forget: errors are logged but not raised (D-13 policy).
    Uses per-call AsyncClient — bot endpoint is not high-frequency.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{bot_url}/internal/notify",
                json=payload,
                headers={"X-Sentinel-Key": api_key},
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("notify_discord_bot: POST failed: %s", exc)
```

---

### `modules/pathfinder/app/main.py` (modify — REGISTRATION_PAYLOAD + StaticFiles)

**Analog:** self (existing main.py)

**REGISTRATION_PAYLOAD extension** (main.py lines 65-85):
```python
# Add as 15th entry in the routes list (after "session" at line 84):
{"path": "foundry/event", "description": "Receive Foundry VTT game events (FVT-01..03)"},
```

**StaticFiles mount pattern** (from RESEARCH.md Pattern 5 — no existing analog in codebase):
```python
# Add to imports at top of main.py
from fastapi.staticfiles import StaticFiles
from pathlib import Path

# Add BEFORE app.include_router(foundry_router) to avoid path-conflict (Pitfall 3)
FOUNDRY_CLIENT_DIR = Path(__file__).parent.parent / "foundry-client"
if FOUNDRY_CLIENT_DIR.exists():
    app.mount(
        "/foundry/static",
        StaticFiles(directory=str(FOUNDRY_CLIENT_DIR)),
        name="foundry_static",
    )
```

**Router import + include pattern** (main.py lines 49-56):
```python
# Add to imports:
import app.routes.foundry as _foundry_module
from app.routes.foundry import router as foundry_router

# Add to lifespan teardown (after session_module teardown):
_foundry_module.some_singleton = None

# Add to include_router block:
app.include_router(foundry_router)
```

**Lifespan singleton wiring pattern** (main.py lines 172-188):
```python
# If foundry.py needs a module-level reference (e.g. to settings):
# Note: foundry.py uses per-call httpx.AsyncClient — no persistent client needed.
# Wire DISCORD_BOT_INTERNAL_URL from settings instead:
_foundry_module.discord_bot_url = settings.discord_bot_internal_url
```

---

### `modules/pathfinder/app/config.py` (modify — add `foundry_narration_model`)

**Analog:** self (existing Settings class)

**Extension pattern** (config.py lines 36-39 — SESSION_RECAP_MODEL pattern, D-37):
```python
# Add after session_recap_model in Settings class:
# Phase 35 Foundry VTT narration settings (D-12)
foundry_narration_model: str | None = None  # FOUNDRY_NARRATION_MODEL; None falls back to litellm_model

# Also add the bot URL so pf2e module knows where to POST:
discord_bot_internal_url: str = "http://discord-bot:8001"  # DISCORD_BOT_INTERNAL_URL
```

The `model_config` line (config.py line 41) already has `"extra": "ignore"` — no change needed.

---

### `interfaces/discord/bot.py` (modify — aiohttp server + embed builder + internal handler)

**Analog:** self (existing `SentinelBot.setup_hook()` + `build_harvest_embed`)

**New imports to add** (after existing imports at lines 48-52):
```python
from aiohttp import web
import aiohttp
```

**SentinelBot `__init__` extension** (bot.py lines 1255-1260):
```python
def __init__(self) -> None:
    intents = discord.Intents.default()
    intents.message_content = True
    super().__init__(intents=intents)
    self.tree = app_commands.CommandTree(self)
    self._internal_runner: "web.AppRunner | None" = None  # D-14: aiohttp server
```

**`setup_hook` extension pattern** (bot.py lines 1261-1296 — add after existing tree.sync + thread-ID load):
```python
async def setup_hook(self) -> None:
    # ... existing: tree.sync, thread ID load ...

    # D-14: Start internal aiohttp notification server
    internal_port = int(os.environ.get("DISCORD_BOT_INTERNAL_PORT", "8001"))
    app = web.Application()
    app.router.add_post("/internal/notify", self._handle_internal_notify)
    self._internal_runner = web.AppRunner(app)
    await self._internal_runner.setup()
    site = web.TCPSite(self._internal_runner, "0.0.0.0", internal_port)
    await site.start()
    logger.info("Internal notification server started on port %d", internal_port)
```

**`close` override for cleanup** (Pitfall 5 from RESEARCH.md):
```python
async def close(self) -> None:
    if self._internal_runner:
        await self._internal_runner.cleanup()
    await super().close()
```

**`_handle_internal_notify` method**:
```python
async def _handle_internal_notify(self, request: web.Request) -> web.Response:
    """Handle POST /internal/notify from pf2e-module (D-14)."""
    key = request.headers.get("X-Sentinel-Key", "")
    if key != SENTINEL_API_KEY:
        return web.Response(status=401)
    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400)

    # Send embed to the first allowed channel (D-15 — same channel as other pf2e commands)
    channel_id = next(iter(ALLOWED_CHANNEL_IDS), None)
    if channel_id is None:
        logger.warning("_handle_internal_notify: no DISCORD_ALLOWED_CHANNELS configured")
        return web.Response(status=500)

    channel = self.get_channel(channel_id)
    if channel is None:
        logger.warning("_handle_internal_notify: channel %d not found", channel_id)
        return web.Response(status=500)

    embed = build_foundry_roll_embed(data)
    try:
        await channel.send(embed=embed)
    except Exception as exc:
        logger.error("_handle_internal_notify: channel.send failed: %s", exc)
        return web.Response(status=500)

    return web.Response(status=200)
```

**`build_foundry_roll_embed` function** — pure function, add near other `build_*` functions (lines 320-497):
```python
def build_foundry_roll_embed(data: dict) -> "discord.Embed":
    """Build embed for a Foundry roll event notification (D-16, FVT-03)."""
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
    label = OUTCOME_LABELS.get(outcome, outcome.capitalize() if outcome else "Roll")
    color = OUTCOME_COLORS.get(outcome, discord.Color.blue())

    title = (
        f"{emoji} {label} | {actor} vs {target}"
        if target
        else f"{emoji} {label} | {actor} ({roll_type})"
    )
    dc_str = "DC: [hidden]" if dc_hidden else f"DC/AC: {dc}"
    footer_parts = [f"Roll: {roll_total}", dc_str]
    if item_name:
        footer_parts.append(item_name)

    embed = discord.Embed(
        title=title,
        description=narrative[:4000] if narrative else None,
        color=color,
    )
    embed.set_footer(text=" | ".join(footer_parts))
    return embed
```

---

### `modules/pathfinder/compose.yml` (modify — new env vars)

**Analog:** self (existing SESSION_* env block, lines 32-36)

**Extension pattern** — append after the SESSION block:
```yaml
# Foundry VTT event ingest (Phase 35 / FVT-01..03, D-12)
- DISCORD_BOT_INTERNAL_URL=http://discord-bot:8001
# FOUNDRY_NARRATION_MODEL: leave unset to fall back to LITELLM_MODEL
# - FOUNDRY_NARRATION_MODEL=
```

Note: port 8001 must NOT be port-mapped to host in `interfaces/discord/compose.yml` — internal network only (RESEARCH.md Pitfall 4).

---

### `.env.example` (modify — document new env vars)

**Analog:** self (Phase 34 SESSION block, lines 98-106)

**Extension pattern** — add new section after SESSION Notes block:
```bash
# ------------------------------------------------------------
# Foundry VTT Event Ingest (Phase 35 / FVT-01..03)
# D-12: override narration LLM (defaults to LITELLM_MODEL if unset)
# D-14: internal URL for Discord bot notification endpoint
# ------------------------------------------------------------
# FOUNDRY_NARRATION_MODEL=
DISCORD_BOT_INTERNAL_URL=http://discord-bot:8001
```

---

### `modules/pathfinder/tests/test_foundry.py` (test, request-response)

**Analog:** `modules/pathfinder/tests/test_session_integration.py`

**File header + env setup pattern** (test_session_integration.py lines 1-21):
```python
"""Tests for foundry route and helpers (FVT-01, FVT-02, FVT-03).

Wave 0 RED stubs — symbols referenced below land in:
  - app.routes.foundry (Wave N / Plan 35-XX)
  - app.foundry helpers (Wave N / Plan 35-XX)

Imports are function-scope inside each test so pytest collection succeeds
before the implementation lands (pattern from Phase 33/34 Wave 0).
"""
import os

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("SENTINEL_CORE_URL", "http://sentinel-core:8000")
os.environ.setdefault("OBSIDIAN_BASE_URL", "http://localhost:27123")
os.environ.setdefault("OBSIDIAN_API_KEY", "")
os.environ.setdefault("LITELLM_MODEL", "openai/local-model")
os.environ.setdefault("LITELLM_API_BASE", "http://localhost:1234/v1")

import pytest
from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient
```

**Route test pattern with ASGI client** (test_session_integration.py lines 85-120):
```python
async def test_roll_event_accepted():
    """POST /foundry/event with valid roll payload + correct key returns 200 (FVT-01)."""
    from app.main import app

    payload = {
        "event_type": "roll",
        "roll_type": "attack-roll",
        "actor_name": "Seraphina",
        "target_name": "Goblin Warchief",
        "outcome": "criticalSuccess",
        "roll_total": 28,
        "dc": 14,
        "dc_hidden": False,
        "item_name": "Longsword +1",
        "timestamp": "2026-04-25T19:42:00Z",
    }
    with patch("app.routes.foundry.notify_discord_bot", new=AsyncMock()):
        with patch("app.foundry.generate_foundry_narrative", new=AsyncMock(return_value="Seraphina struck true.")):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/foundry/event",
                    json=payload,
                    headers={"X-Sentinel-Key": "test-key-for-pytest"},
                )
    assert resp.status_code == 200


async def test_auth_rejected():
    """POST /foundry/event with wrong X-Sentinel-Key returns 401 (FVT-01)."""
    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/foundry/event",
            json={"event_type": "roll", "actor_name": "X", "outcome": "success",
                  "roll_total": 10, "roll_type": "attack-roll", "timestamp": "..."},
            headers={"X-Sentinel-Key": "wrong-key"},
        )
    assert resp.status_code == 401
```

**LLM mock pattern** (test_session_integration.py uses `patch("litellm.acompletion", ...)`):
```python
async def test_llm_fallback():
    """LLM timeout triggers plain-text fallback; embed still sent (D-13, FVT-02)."""
    from app.main import app

    with patch("litellm.acompletion", new=AsyncMock(side_effect=Exception("timeout"))):
        with patch("app.foundry.notify_discord_bot", new=AsyncMock()) as mock_notify:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/foundry/event",
                    json={"event_type": "roll", "actor_name": "Sera",
                          "outcome": "success", "roll_total": 18,
                          "roll_type": "attack-roll", "timestamp": "..."},
                    headers={"X-Sentinel-Key": "test-key-for-pytest"},
                )
    assert resp.status_code == 200
    # Discord bot was still called (fallback text in payload, not error)
    mock_notify.assert_called_once()
    notify_payload = mock_notify.call_args[0][0]
    assert notify_payload.get("narrative")  # fallback text present
```

---

### `interfaces/discord/tests/test_discord_foundry.py` (test, request-response)

**Analog:** `interfaces/discord/tests/test_subcommands.py` + `conftest.py`

**File header** (function-scope imports pattern from test_subcommands.py):
```python
"""Tests for build_foundry_roll_embed and _handle_internal_notify (FVT-03, D-14, D-16).

Wave 0 RED stubs — symbols referenced land in:
  - bot.build_foundry_roll_embed (Wave N / Plan 35-XX)
  - bot.SentinelBot._handle_internal_notify (Wave N / Plan 35-XX)

All discord.* imports use the centralized _EmbedStub from conftest.py.
Do NOT re-stub discord here — conftest.py already handles it (L-5 prevention).
"""
import os

os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token-for-pytest")
os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")

import pytest
import bot  # noqa: E402 — conftest.py stubs discord before this import
```

**`_EmbedStub` consumption pattern** (conftest.py sets `discord.Embed = _EmbedStub`):
```python
async def test_embed_critical_success():
    """build_foundry_roll_embed: criticalSuccess has 🎯 title and gold color (D-16, FVT-03)."""
    data = {
        "outcome": "criticalSuccess",
        "actor_name": "Seraphina",
        "target_name": "Goblin Warchief",
        "narrative": "Seraphina's blade found the gap in the warchief's armor.",
        "roll_total": 28,
        "dc": 14,
        "dc_hidden": False,
        "item_name": "Longsword +1",
        "roll_type": "attack-roll",
    }
    embed = bot.build_foundry_roll_embed(data)
    assert "🎯" in embed.title
    assert "Critical Hit!" in embed.title
    assert "Seraphina" in embed.title
    assert "Goblin Warchief" in embed.title
    assert "Seraphina's blade" in embed.description
    assert "Roll: 28" in embed.footer_text
    assert "DC/AC: 14" in embed.footer_text
    assert "Longsword +1" in embed.footer_text


async def test_embed_hidden_dc():
    """build_foundry_roll_embed: dc_hidden=True shows 'DC: [hidden]' in footer (D-16, FVT-03)."""
    data = {
        "outcome": "success",
        "actor_name": "Seraphina",
        "target_name": None,
        "narrative": "",
        "roll_total": 18,
        "dc": None,
        "dc_hidden": True,
        "item_name": None,
        "roll_type": "saving-throw",
    }
    embed = bot.build_foundry_roll_embed(data)
    assert "DC: [hidden]" in embed.footer_text
    assert "DC/AC" not in embed.footer_text
```

**`_ColorStub` extension requirement** — `conftest.py` must add `gold()` for criticalSuccess color:
```python
# In interfaces/discord/tests/conftest.py _ColorStub class — ADD:
@classmethod
def gold(cls):
    return "gold"
```

---

### `modules/pathfinder/foundry-client/module.json` (config — JS manifest)

**No Python analog.** Use RESEARCH.md Pattern 3 verbatim (lines 239-271).

Key fields confirmed for v14:
- `"esmodules": ["sentinel-connector.js"]` — not `"scripts"`
- `"compatibility": {"minimum": "12", "verified": "14"}`
- `"relationships": {"systems": [{"id": "pf2e", "type": "system", ...}]}`
- `"authors": [{"name": "Sentinel of Mnemosyne"}]`
- `manifest` and `download` URLs: leave as `{MAC_MINI_IP}` placeholders in repo (RESEARCH.md anti-pattern note)

---

### `modules/pathfinder/foundry-client/sentinel-connector.js` (client, event-driven)

**No Python analog.** Use RESEARCH.md Code Examples section (lines 531-629) verbatim as the implementation template.

Key patterns verified from pf2e-modifiers-matter source:
- `Hooks.once('init', ...)` for `game.settings.register` calls
- `Hooks.once('ready', ...)` wrapping `Hooks.on('preCreateChatMessage', ...)`
- Always `return true` — never return `false` (never suppress the message)
- `fetch(...).catch(() => {})` — fire-and-forget, never block the hook
- Defensive outcome derivation: `context.outcome ?? deriveOutcome(rollTotal, dcValue)`

---

### `modules/pathfinder/foundry-client/package.sh` (utility, batch)

**No direct analog.** Use RESEARCH.md Pattern 7 "correct zip structure" guidance.

Correct structure (Foundry requires `sentinel-connector/` subdirectory at zip root):
```bash
#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"  # cd to foundry-client/
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT
mkdir "$TMPDIR/sentinel-connector"
cp module.json sentinel-connector.js "$TMPDIR/sentinel-connector/"
(cd "$TMPDIR" && zip -r sentinel-connector.zip sentinel-connector/)
mv "$TMPDIR/sentinel-connector.zip" .
echo "Created sentinel-connector.zip"
```

---

## Shared Patterns

### Authentication — X-Sentinel-Key Header Check
**Source:** `interfaces/discord/bot.py` lines 77-79 (module-level `SENTINEL_API_KEY`) + `modules/pathfinder/app/main.py` lines 97-99 (registration header)
**Apply to:** `app/routes/foundry.py` (incoming from Foundry JS) + `app/foundry.py` `notify_discord_bot()` (outgoing to bot) + `bot.py` `_handle_internal_notify()` (incoming from pf2e module)
```python
SENTINEL_API_KEY: str = _read_secret("sentinel_api_key", os.environ.get("SENTINEL_API_KEY", ""))
# In handler: if key != SENTINEL_API_KEY: raise 401 / return web.Response(status=401)
```

### Logging Pattern
**Source:** Every module uses `logger = logging.getLogger(__name__)`
**Apply to:** All new Python files
```python
import logging
logger = logging.getLogger(__name__)
# Usage: logger.info("foundry_event: event_type=%s actor=%s", event_type, actor_name)
# Usage: logger.warning("generate_foundry_narrative: LLM call failed: %s", exc)
```

### LLM Model Resolution
**Source:** `modules/pathfinder/app/config.py` lines 36-39 (`session_recap_model` pattern)
**Apply to:** `app/foundry.py` `generate_foundry_narrative()` call site
```python
# Resolve narration model: foundry_narration_model → litellm_model
model = settings.foundry_narration_model or settings.litellm_model
api_base = settings.litellm_api_base or None
```

### httpx Per-Call AsyncClient (fire-and-forget)
**Source:** `interfaces/discord/bot.py` lines 177-178 (`_call_core`)
**Apply to:** `app/foundry.py` `notify_discord_bot()`
```python
async with httpx.AsyncClient() as http_client:
    # single call — no persistent client needed for fire-and-forget
```

### Module-Level Singleton + Lifespan Wire Pattern
**Source:** `modules/pathfinder/app/main.py` lines 113-198 (lifespan) + route modules lines 50-52 (module-level `obsidian = None`)
**Apply to:** `app/routes/foundry.py` if any module-level singleton is needed (e.g. `discord_bot_url`)
```python
# In app/routes/foundry.py:
discord_bot_url: str = ""  # set by main.py lifespan

# In main.py lifespan:
import app.routes.foundry as _foundry_module
_foundry_module.discord_bot_url = settings.discord_bot_internal_url
```

### `_EmbedStub` and `_ColorStub` Extension
**Source:** `interfaces/discord/tests/conftest.py` lines 35-108
**Apply to:** `interfaces/discord/tests/test_discord_foundry.py`
**Action:** Add `gold()` classmethod to `_ColorStub` in `conftest.py` to support `discord.Color.gold()` used in `build_foundry_roll_embed`. Do NOT add it in the test file (L-5 prevention — conftest is the single source for stub extensions).

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `modules/pathfinder/foundry-client/module.json` | config | — | JSON manifest for Foundry VTT; no existing project manifests; use RESEARCH.md Pattern 3 |
| `modules/pathfinder/foundry-client/sentinel-connector.js` | client | event-driven | Browser JS with Foundry VTT hooks API; no JS modules exist in this project; use RESEARCH.md Code Examples |
| `modules/pathfinder/foundry-client/package.sh` | utility | batch | Shell packaging script; no existing shell scripts in the repo; use RESEARCH.md Pattern 7 |

---

## Critical Implementation Notes for Planner

1. **StaticFiles mount ordering (Pitfall 3):** Mount `/foundry/static` StaticFiles BEFORE `app.include_router(foundry_router)` in `main.py`. A router registered at `/foundry` prefix captures `/foundry/static` paths before StaticFiles sees them.

2. **`_ColorStub.gold()` must be added to conftest.py** before `test_discord_foundry.py` is written. The Wave 0 stub creation step for Discord tests must patch conftest.py, not the test file itself.

3. **`aiohttp.web` import in `bot.py`:** aiohttp ships as a discord.py dependency — no new pip installs. The test stub does NOT need to stub `aiohttp` (tests mock at the method level, not the library level).

4. **Zip structure (Pitfall 7):** `package.sh` must produce `sentinel-connector/module.json` inside the zip — NOT flat. The `tmpdir` approach in the pattern above is the safest.

5. **Docker network:** Both `pf2e-module` and `discord-bot` services must be on `sentinel-network` for `http://discord-bot:8001` to resolve. Verify the shared network declaration in the top-level `docker-compose.yml`.

6. **`close()` override in SentinelBot:** Required to avoid aiohttp socket leak on bot shutdown (Pitfall 5). Must call `await self._internal_runner.cleanup()` before `await super().close()`.

---

## Metadata

**Analog search scope:** `modules/pathfinder/app/`, `interfaces/discord/`, test directories
**Files scanned:** 10 source files + 4 test files
**Pattern extraction date:** 2026-04-25
