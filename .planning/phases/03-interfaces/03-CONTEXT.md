---
phase: 03
name: Interfaces
created: "2026-04-10T19:00:00Z"
status: final
---

# Phase 03: Interfaces — Discussion Context

## Phase Goal

The Sentinel is reachable from Discord and Apple Messages. All Core endpoints require authentication.

## Canonical Refs

- `.planning/REQUIREMENTS.md` — IFACE-01 through IFACE-06 (full requirement text)
- `.planning/phases/01-core-loop/01-CONTEXT.md` — Phase 01 locked decisions (Docker patterns, tech stack)
- `.planning/phases/02-memory-layer/02-CONTEXT.md` — Phase 02 locked decisions (user_id on envelope, Obsidian patterns)
- `sentinel-core/app/main.py` — lifespan pattern, app.state, existing route registration
- `sentinel-core/app/models.py` — MessageEnvelope (content, user_id) — all interfaces must produce this
- `sentinel-core/app/config.py` — Settings pattern; `sentinel_api_key` already present
- `sentinel-core/app/routes/message.py` — POST /message integration point for interfaces

## Prior Decisions (from Phases 01–02)

- **Docker Compose `include` directive.** Each interface is its own container with its own `compose.yml`. Root `docker-compose.yml` includes it. No `-f` flag stacking.
- **`MessageEnvelope` is stable.** `content: str`, `user_id: str` (pattern `^[a-zA-Z0-9_-]+$`). All interfaces must produce this shape.
- **`httpx.AsyncClient` for all outbound HTTP from interface containers to Core.**
- **`sentinel_api_key` is already in `Settings`.** Value is read from env at startup — enforcement just needs to be added.
- **IFACE-01 (Message Envelope) is already complete** from Phase 1.

## Decisions

### 1. Discord User Identity → user_id

**Decision:** `user_id = str(interaction.user.id)` — Discord snowflake ID as string.

**Example:** `"123456789012345678"`

**Rationale:** Stable and unique — Discord snowflake IDs never change even if the user changes their username. This means the Obsidian profile file is at `core/users/123456789012345678.md`, which the user creates manually if they want memory context for Discord.

**Constraint:** `user_id` regex `^[a-zA-Z0-9_-]+$` — Discord snowflake IDs are numeric strings, so they satisfy this pattern.

### 2. Discord Slash Command Design

**Decision:** `/sent` prefix namespace for all Sentinel commands.

**Phase 3 command:** `/sentask <message>` — the primary interaction command.

**Behavior:**
- `/sentask <message>` creates a new thread in the channel where invoked
- Thread name: first 50 chars of the user's message
- Bot defers the interaction within 3s (IFACE-03 compliance)
- Bot sends follow-up in the thread when AI response is ready
- Replies inside the thread continue the conversation (same thread_id → same context)
- Each `/sentask` call creates a fresh thread (never reuses existing threads)

**Future commands** (not in Phase 3): `/sentlookup`, `/sentnote`, `/sentrecall` — the `/sent` prefix keeps them namespaced and discoverable together.

**Deferred reply pattern:**
```python
await interaction.response.defer(thinking=True)  # within 3s
# ... wait for Core response ...
thread = await interaction.followup.send(ai_response, wait=True)
# thread is created automatically from the followup message
```

### 3. Apple Messages Interface Scope

**Decision:** Fully wired but disabled by default (`IMESSAGE_ENABLED=false` in `.env`).

**Implementation:**
- Mac-native Python process (not a Docker container — iMessage requires access to macOS APIs and chat.db)
- Polls `~/Library/Messages/chat.db` for new incoming messages (SQLite)
- Sends AI responses back via AppleScript / `macpymessenger`
- HTTP bridge to Core POST /message (same pattern as Discord)
- `IMESSAGE_ENABLED=false` → process exits immediately on startup with a clear message
- When enabled: requires Full Disk Access granted to Python interpreter in System Settings

**Compose pattern:** The iMessage bridge is a Mac-native process, not a Docker container. It runs directly on the host Mac. It gets its own directory (`interfaces/imessage/`) with a launcher script, documented Full Disk Access requirement, and a `.env` integration (same `SENTINEL_API_KEY`).

**Key libraries:** `imessage_reader` for chat.db reading (handles Ventura+ attributedBody), `macpymessenger` for sending. Both documented in CLAUDE.md tech stack.

**MEM-XX integration:** iMessage bridge passes `user_id` derived from the sender's phone number/handle, sanitized to match the `^[a-zA-Z0-9_-]+$` pattern (e.g., `imsg_14155551234`).

### 4. Auth Enforcement — X-Sentinel-Key

**Decision:** Global Starlette middleware in `sentinel-core/app/main.py`.

**Whitelist:** `/health` is the only unauthenticated endpoint.

**Behavior:**
- Request arrives → middleware checks for `X-Sentinel-Key` header
- Header matches `settings.sentinel_api_key` → pass through to route handler
- Missing or wrong key → 401 `{"detail": "Unauthorized"}`
- `/health` path → bypass check, always pass through

**Implementation pattern:**
```python
from starlette.middleware.base import BaseHTTPMiddleware

class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        key = request.headers.get("X-Sentinel-Key", "")
        if key != settings.sentinel_api_key:
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)

app.add_middleware(APIKeyMiddleware)
```

**Rationale:** Single enforcement point — all current and future routes get auth automatically without per-route wiring. Eliminates the risk of accidentally shipping an unprotected endpoint.

**Note:** Existing tests use `app.state` injection and will need the middleware bypassed in test setup (inject a test client that includes the header, or set `settings.sentinel_api_key = "test-key"` in fixtures).

## Architecture Notes (for researcher + planner)

### New containers / processes

| Component | Type | Location |
|-----------|------|----------|
| Discord bot | Docker container | `interfaces/discord/` |
| Apple Messages bridge | Mac-native process | `interfaces/imessage/` |

### Discord bot structure

Pattern: same as Pi harness — Fastify-style but in Python with discord.py.

Key files:
- `interfaces/discord/bot.py` — discord.py bot, slash command handlers
- `interfaces/discord/compose.yml` — Docker service definition
- `interfaces/discord/Dockerfile` — Python 3.12, installs discord.py + httpx
- `interfaces/discord/.env` — `DISCORD_BOT_TOKEN`, `SENTINEL_API_KEY`, `SENTINEL_CORE_URL`

**Bot startup:** Registers `/sentask` globally (not guild-specific — takes up to 1hr to propagate, but works everywhere).

**Core URL from bot:** `SENTINEL_CORE_URL=http://sentinel-core:8000` — same internal Docker network.

### Apple Messages bridge structure

| File | Purpose |
|------|---------|
| `interfaces/imessage/bridge.py` | Main process: polls chat.db, sends to Core, replies via AppleScript |
| `interfaces/imessage/launch.sh` | Launcher with guard for IMESSAGE_ENABLED |
| `interfaces/imessage/README.md` | Full Disk Access setup instructions |

### Modified: sentinel-core auth

- `sentinel-core/app/main.py` — add `APIKeyMiddleware` before route registration
- `sentinel-core/tests/` — update test fixtures to include `X-Sentinel-Key` header

### New config fields

```python
# Already in Settings:
sentinel_api_key: str  # enforcement now added via middleware

# New for Discord:
discord_bot_token: str = ""  # blank = Discord disabled
discord_allowed_channels: str = ""  # comma-separated channel IDs; blank = all

# New for iMessage:
imessage_enabled: bool = False  # explicit opt-in
```

Both already present as comments in `.env.example` under "Discord Interface" and "Apple Messages".

## Deferred Ideas

- `/sentlookup`, `/sentnote`, `/sentrecall` — future slash commands (other phases)
- Telegram / Slack interface containers (VIFACE-01, VIFACE-02) — v2 requirements
- Discord DM support — keep it simple in Phase 3, guild channels + threads only
- Per-server bot prefix configuration — not needed for single-user deployment

## Discussion Log

| Area | Decision | Rationale |
|------|----------|-----------|
| Discord user_id | `str(interaction.user.id)` snowflake | Stable, unique, satisfies user_id regex |
| Discord commands | `/sent` prefix namespace, `/sentask` for Phase 3 | Namespaced for future commands, always new thread per invocation |
| Apple Messages | Fully wired, `IMESSAGE_ENABLED=false` | User wants it built, just opt-in |
| Auth enforcement | Global Starlette middleware, `/health` whitelisted | Single point, automatic coverage for future routes |
