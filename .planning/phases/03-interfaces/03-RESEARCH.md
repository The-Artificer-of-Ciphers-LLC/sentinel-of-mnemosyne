# Phase 3: Interfaces — Research

**Researched:** 2026-04-10
**Domain:** discord.py v2.7, iMessage bridge, Starlette middleware, Docker networking
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

1. **Discord user_id**: `str(interaction.user.id)` — Discord snowflake ID as string (e.g., `"123456789012345678"`). Satisfies `^[a-zA-Z0-9_-]+$` regex.

2. **Discord slash commands**: `/sent` namespace, `/sentask <message>` for Phase 3. Each call creates a new thread (never reuses). Thread name = first 50 chars of message. Deferred response pattern:
   ```python
   await interaction.response.defer(thinking=True)
   # ... wait for Core ...
   thread = await interaction.followup.send(ai_response, wait=True)
   ```

3. **Apple Messages interface scope**: Fully wired but `IMESSAGE_ENABLED=false` by default. Mac-native process (not Docker). Polls `chat.db`, sends via `macpymessenger`. `user_id` pattern: `imsg_14155551234`.

4. **Auth enforcement**: Global `BaseHTTPMiddleware` in `sentinel-core/app/main.py`. `/health` whitelisted. All other endpoints require `X-Sentinel-Key`. Returns 401 `{"detail": "Unauthorized"}` on failure.

5. **IFACE-01 is already complete** — `MessageEnvelope` (content, user_id) stable from Phase 1.

6. **Docker pattern**: Discord bot = Docker container at `interfaces/discord/`. Apple Messages = Mac-native at `interfaces/imessage/`. Root `docker-compose.yml` includes `interfaces/discord/compose.yml`.

7. **httpx.AsyncClient** for all outbound HTTP from interface containers to Core. Never `requests`.

### Claude's Discretion

None specified — all major decisions locked.

### Deferred Ideas (OUT OF SCOPE)

- `/sentlookup`, `/sentnote`, `/sentrecall` slash commands
- Telegram / Slack interface containers (VIFACE-01, VIFACE-02)
- Discord DM support
- Per-server bot prefix configuration
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| IFACE-01 | Standard Message Envelope defined as Pydantic v2 model — all interfaces produce this shape | Already complete from Phase 1; confirmed in `sentinel-core/app/models.py` |
| IFACE-02 | Discord bot container operational using discord.py v2.7.x — user can send a message and receive AI response | discord.py 2.7.1 verified; bot pattern researched; container structure defined |
| IFACE-03 | Discord slash commands use deferred responses — bot acknowledges within 3 seconds, sends follow-up when AI completes | `interaction.response.defer(thinking=True)` + `interaction.followup.send()` pattern confirmed |
| IFACE-04 | Discord multi-turn conversations use threads — each conversation stays in dedicated thread | Thread creation via `interaction.channel.create_thread()` after defer; followup sends into thread |
| IFACE-05 | Apple Messages bridge operational as feature-flagged tier-2 interface — Mac-native process, HTTP bridge to Core, documented Full Disk Access requirement | `imessage_reader` 0.6.1 + `macpymessenger` 0.2.0 researched; ROWID-polling pattern identified |
| IFACE-06 | All non-health Core endpoints require `X-Sentinel-Key` header authentication | `BaseHTTPMiddleware` pattern confirmed; body-streaming caveat documented; test fixture approach identified |
</phase_requirements>

---

## Summary

Phase 3 adds two interfaces (Discord bot, Apple Messages bridge) and global auth enforcement to sentinel-core. The technical work splits across three distinct components: a Dockerized Python bot consuming discord.py v2.7, a Mac-native Python process bridging iMessage to Core, and a Starlette middleware layer protecting existing Core routes.

The Discord bot is the primary interface. The key technical pattern is: defer within 3 seconds, call Core (which may take 15-30+ seconds for LM Studio), create a thread from the channel, then send the AI response into the thread via followup. Thread creation cannot happen directly from a deferred interaction's followup — the correct pattern is `channel.create_thread()` on the interaction's channel, then send into the thread. The CONTEXT.md's proposed pattern of deriving a thread from `interaction.followup.send(wait=True)` is NOT how Discord's API works for slash commands — followup messages do not become threads. The correct flow is explicitly calling `channel.create_thread()`.

The `BaseHTTPMiddleware` approach for auth enforcement is correct and well-supported in FastAPI/Starlette. The only caveat is that reading the request body inside `dispatch` before calling `call_next` can exhaust the stream. Since the auth middleware only reads headers (not the body), this caveat does not apply here — the pattern in CONTEXT.md is safe.

Docker Compose `include` directive merges all included services into a single application model with a shared default network. The `discord` service can reach `sentinel-core` by hostname `sentinel-core:8000` without any additional network configuration.

**Primary recommendation:** Implement in three waves — (1) auth middleware + test updates, (2) Discord bot container, (3) iMessage bridge.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `discord.py` | 2.7.1 | Discord bot API | Official library, active maintenance, v2.7.x is current stable [VERIFIED: npm/pip registry] |
| `httpx` | >=0.28.1 | Async HTTP client for Core calls | Already project standard; AsyncClient pattern locked |
| `imessage-reader` | 0.6.1 | Read messages from chat.db | Best-maintained reader; handles basic attributedBody [VERIFIED: pip registry] |
| `macpymessenger` | 0.2.0 | Send iMessages via AppleScript | Project-specified library; Python 3.10+ compatible [VERIFIED: wheel METADATA] |
| `starlette` | (via fastapi) | BaseHTTPMiddleware for auth | Already a FastAPI dependency; no additional install needed |

### Version Verification

```bash
# As of 2026-04-10 (verified via pip registry):
# discord.py: 2.7.1
# imessage-reader: 0.6.1
# macpymessenger: 0.2.0
```

**Installation:**

```bash
# Discord bot container (interfaces/discord/):
pip install "discord.py>=2.7.1" "httpx>=0.28.1"

# Apple Messages bridge (interfaces/imessage/) — on host Mac:
pip install "imessage-reader>=0.6.1" "macpymessenger>=0.2.0" "httpx>=0.28.1"
```

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `discord.py` | `py-cord`, `disnake` | Forks from hiatus period; discord.py is active with v2.7.1 momentum — do not use forks [CITED: CLAUDE.md] |
| `imessage-reader` | Direct SQLite queries | imessage_reader handles schema across macOS versions; custom queries require manual attributedBody parsing |
| `macpymessenger` | Raw `osascript` subprocess | macpymessenger is a typed wrapper over osascript; less error surface |

---

## Architecture Patterns

### Recommended Project Structure

```
interfaces/
├── discord/
│   ├── bot.py              # discord.py bot, slash command handlers, httpx Core calls
│   ├── compose.yml         # Docker service definition
│   ├── Dockerfile          # python:3.12-slim, installs discord.py + httpx
│   └── .env                # DISCORD_BOT_TOKEN, SENTINEL_API_KEY, SENTINEL_CORE_URL
└── imessage/
    ├── bridge.py           # polls chat.db, sends to Core, replies via macpymessenger
    ├── launch.sh           # launcher: guard on IMESSAGE_ENABLED, Full Disk Access reminder
    └── README.md           # Full Disk Access setup instructions
```

### Pattern 1: Discord Bot — Defer + Thread + Followup

The CONTEXT.md describes the intent correctly but the exact API needs clarification. `interaction.followup.send()` returns a `Message` object, but that message does NOT automatically become a thread. The correct pattern to create a conversation thread from a slash command:

```python
# Source: discord.py docs + community verification [CITED: discordpy.readthedocs.io]
@bot.tree.command(name="sentask", description="Ask the Sentinel")
@app_commands.describe(message="Your message to the Sentinel")
async def sentask(interaction: discord.Interaction, message: str):
    # 1. Defer within 3 seconds (IFACE-03) — shows "Bot is thinking..."
    await interaction.response.defer(thinking=True)

    # 2. Create a thread from the channel BEFORE calling Core
    #    Thread name = first 50 chars of user message (per CONTEXT.md)
    thread_name = message[:50]
    thread = await interaction.channel.create_thread(
        name=thread_name,
        type=discord.ChannelType.public_thread,
        auto_archive_duration=60,
    )

    # 3. Call Core (may take 15-180 seconds)
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            settings.sentinel_core_url + "/message",
            json={
                "content": message,
                "user_id": str(interaction.user.id),
            },
            headers={"X-Sentinel-Key": settings.sentinel_api_key},
            timeout=200.0,
        )
    ai_response = resp.json()["content"]

    # 4. Send AI response into the thread
    await thread.send(ai_response)

    # 5. Use followup to acknowledge and point to thread (interaction is still open)
    await interaction.followup.send(f"Response in thread: {thread.mention}", ephemeral=True)
```

**Critical note:** `interaction.followup.send(wait=True)` returns a `discord.WebhookMessage`, which does NOT support `.create_thread()`. Thread creation must use `interaction.channel.create_thread()` — a channel-level call, not an interaction-level call.

**Alternative (simpler, no ephemeral ack):** Send response directly in the thread and send one followup into the thread from the interaction:

```python
# Simpler variant — followup goes directly into thread
thread = await interaction.channel.create_thread(name=message[:50], ...)
await thread.send(ai_response)
await interaction.followup.send("Done", ephemeral=True)  # Clears the "thinking" state
```

### Pattern 2: Bot Setup — Command Sync

```python
# Source: discord.py community patterns [CITED: github.com/Rapptz/discord.py/discussions/8170]
import discord
from discord import app_commands

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    # Global sync — takes up to 1 hour to propagate to all guilds
    await tree.sync()
    # For faster testing: sync to a specific guild (instant)
    # await tree.sync(guild=discord.Object(id=YOUR_GUILD_ID))
```

**Command propagation timing [CITED: discord.com/developers/docs/interactions/application-commands]:**
- **Guild commands**: Update instantly
- **Global commands**: Up to 1 hour propagation delay
- Recommended workflow: Use guild-scoped sync during development, switch to global for production

### Pattern 3: Auth Middleware (IFACE-06)

The pattern from CONTEXT.md is correct. The body-stream exhaustion issue (the known `BaseHTTPMiddleware` caveat) does NOT apply here because the auth middleware only reads headers, never the request body.

```python
# Source: Starlette docs + FastAPI patterns [ASSUMED — matches known API]
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse

class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        key = request.headers.get("X-Sentinel-Key", "")
        if key != settings.sentinel_api_key:
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)

# Register BEFORE routes
app.add_middleware(APIKeyMiddleware)
app.include_router(message_router)
```

**Test fixture pattern** — existing tests set `os.environ["SENTINEL_API_KEY"] = "test-key-for-pytest"` in conftest.py before app import. After adding middleware, tests that POST to `/message` must include the header:

```python
# In test calls — add header:
resp = await client.post(
    "/message",
    json={"content": "hello", "user_id": "test"},
    headers={"X-Sentinel-Key": "test-key-for-pytest"},
)
```

The settings singleton picks up `SENTINEL_API_KEY=test-key-for-pytest` from env before app import (already in conftest.py), so middleware will accept `"test-key-for-pytest"` as valid.

### Pattern 4: iMessage Bridge — Polling with ROWID Tracking

`imessage_reader` v0.6.1 reads all messages via `FetchData.get_messages()`. It does NOT provide built-in polling or last-ROWID tracking. The bridge must implement this itself using direct SQLite queries for efficiency, tracking the highest processed `ROWID` in memory.

```python
# Source: chat.db schema knowledge [ASSUMED — standard approach across all iMessage tools]
import sqlite3
import time

DB_PATH = os.path.expanduser("~/Library/Messages/chat.db")
last_rowid = 0  # track highest processed message ROWID

def poll_new_messages():
    global last_rowid
    conn = sqlite3.connect(DB_PATH)
    # Only fetch messages not from me, newer than last_rowid
    rows = conn.execute(
        """
        SELECT m.ROWID, h.id, COALESCE(m.text, '') as text
        FROM message m
        JOIN handle h ON m.handle_id = h.ROWID
        WHERE m.is_from_me = 0
          AND m.ROWID > ?
          AND (m.text IS NOT NULL OR m.attributedBody IS NOT NULL)
        ORDER BY m.ROWID ASC
        """,
        (last_rowid,)
    ).fetchall()
    conn.close()

    for rowid, handle, text in rows:
        last_rowid = max(last_rowid, rowid)
        # handle = phone number or email, e.g. "+14155551234" or "user@example.com"
        yield rowid, handle, text
```

**Ventura+ attributedBody**: On macOS Ventura+, `message.text` can be NULL with the actual content in `attributedBody` (a binary typedstream blob). `imessage_reader` 0.6.1 does NOT handle this transparently — it returns empty strings for attributedBody-only messages. The bridge must handle this gracefully (skip or use `python-typedstream` to decode). For Phase 3, the simplest approach is to skip messages with empty text after coalescing and log a warning, rather than implementing full attributedBody decoding.

**user_id sanitization for iMessage**:
```python
# Phone: "+14155551234" → "imsg_14155551234"
# Email: "user@example.com" → "imsg_userexamplecom"
import re

def sanitize_imessage_handle(handle: str) -> str:
    # Remove non-alphanumeric chars except underscore/hyphen, prepend "imsg_"
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "", handle)
    return f"imsg_{sanitized}"
```

### Pattern 5: Docker Compose Network — Include Directive

Services from all included compose files share the same default bridge network when started via the root `docker-compose.yml`. [CITED: docs.docker.com/compose/how-tos/networking/]

```yaml
# docker-compose.yml (root)
include:
  - path: sentinel-core/compose.yml
  - path: pi-harness/compose.yml
  - path: interfaces/discord/compose.yml  # discord service joins same network

# interfaces/discord/compose.yml
services:
  discord:
    build: .
    env_file: ../../.env
    environment:
      - SENTINEL_CORE_URL=http://sentinel-core:8000  # DNS resolution via shared network
    restart: unless-stopped
    # No depends_on needed — bot handles Core being temporarily unreachable gracefully
```

The `discord` container reaches `sentinel-core` by service name because all services from included files join the same project-level default network. No explicit `networks:` block is needed.

### Pattern 6: macpymessenger Send API

```python
# Source: macpymessenger 0.2.0 wheel METADATA + README [VERIFIED: wheel inspection]
from macpymessenger import Configuration, IMessageClient

configuration = Configuration()  # validates bundled AppleScript at init
client = IMessageClient(configuration)

# Send a message — recipient is phone number (E.164) or email
client.send("+14155551234", "Hello from Sentinel")

# Template variant
client.create_template("response", "{{ content }}")
client.send_template("+14155551234", "response", {"content": ai_response})
```

**Phone number format**: E.164 format (`+1XXXXXXXXXX`). The bridge's `user_id` uses `imsg_` prefix stripping non-alphanumeric chars — sending requires reversing to reconstruct the original handle. Design: store original handle separately from `user_id` during a poll cycle.

### Anti-Patterns to Avoid

- **Calling `interaction.followup.send()` and expecting it to become a thread**: WebhookMessage from followup does not support thread creation. Use `channel.create_thread()` explicitly.
- **Syncing the command tree in `on_ready` on every restart**: This hits Discord's rate limits. Sync once at startup (`setup_hook`), not on every reconnect.
- **Reading request body in `BaseHTTPMiddleware.dispatch()` before `call_next`**: Exhausts the ASGI stream, causing the route handler to receive an empty body. The auth middleware must only read headers.
- **Using `requests` library in async context**: Blocks the event loop. Only `httpx.AsyncClient` is permitted.
- **Using `asyncio.sleep` polling loop with short intervals**: macOS chat.db has file-level locking under heavy iMessage traffic. Use 2-5 second poll intervals minimum.
- **Leaving discord.py `bot.run()` without handling `KeyboardInterrupt`**: The bot will leave stale gateway connections. Use `async with bot:` pattern or handle shutdown in signal handlers.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Discord API interaction | Custom HTTP requests to Discord API | `discord.py` | Handles gateway, rate limiting, reconnection, interaction lifecycle |
| iMessage sending | Direct AppleScript subprocess calls | `macpymessenger` | Typed wrapper with proper error handling; avoids quoting bugs in shell args |
| iMessage reading | Raw SQLite + typedstream parsing | `imessage-reader` for basic text; direct SQLite ROWID query for polling | attributedBody decoding is non-trivial; skip it in Phase 3 |
| Auth header check | Per-route decorators | `BaseHTTPMiddleware` | Single enforcement point; no per-route wiring; future routes auto-protected |

---

## Common Pitfalls

### Pitfall 1: Thread Creation API Confusion

**What goes wrong:** Developer calls `await interaction.followup.send("response", wait=True)` expecting to call `.create_thread()` on the returned object, gets `AttributeError` because `WebhookMessage` does not have `create_thread`.

**Why it happens:** `Message` (from `channel.send()`) has `create_thread()`. `WebhookMessage` (from `followup.send()`) does not.

**How to avoid:** Create the thread via `interaction.channel.create_thread()` before or after calling Core. Then send into the thread directly. The followup is only used to acknowledge the interaction (clear "thinking" state).

**Warning signs:** `AttributeError: 'WebhookMessage' object has no attribute 'create_thread'`

### Pitfall 2: Interaction Timeout (3-Second Rule)

**What goes wrong:** Bot calls Core (which calls LM Studio) synchronously, taking 10-30+ seconds. Discord kills the interaction with "This interaction failed."

**Why it happens:** Discord requires a response within 3 seconds of receiving a slash command. After that, the interaction is dead.

**How to avoid:** `await interaction.response.defer(thinking=True)` MUST be the very first `await` in the command handler — before any external calls, before creating threads, before anything. The defer call buys up to 15 minutes via followup.

**Warning signs:** "This interaction failed" in Discord UI despite bot appearing to process correctly.

### Pitfall 3: Global Command Propagation Delay

**What goes wrong:** Bot deploys globally, commands not visible in Discord for up to 1 hour. Developer thinks code is broken.

**Why it happens:** Global slash commands take up to 1 hour to propagate across all Discord servers. Guild commands are instant.

**How to avoid:** During development and testing, sync to a specific guild: `await tree.sync(guild=discord.Object(id=GUILD_ID))`. Use `copy_global_to()` to copy global commands to a test guild instantly. Switch to `tree.sync()` (no guild) only for production.

### Pitfall 4: BaseHTTPMiddleware Body Stream Exhaustion

**What goes wrong:** Middleware reads `await request.body()` before `call_next(request)`. Route handler receives empty body. POST /message returns 422 (Pydantic validation error for missing content).

**Why it happens:** ASGI body stream can only be consumed once. BaseHTTPMiddleware does not automatically buffer it for reuse in older Starlette versions.

**How to avoid:** The auth middleware must NEVER call `request.body()` or `request.json()`. Only read `request.headers` and `request.url.path`. The pattern in CONTEXT.md is correct.

**Note:** This pitfall exists but does NOT apply to the auth middleware design chosen — headers-only inspection is safe.

### Pitfall 5: iMessage chat.db Locked During Heavy Use

**What goes wrong:** `sqlite3.OperationalError: database is locked` when Messages app is actively syncing a large batch.

**Why it happens:** SQLite WAL mode helps but doesn't eliminate locking under heavy writes.

**How to avoid:** Open the connection with a timeout: `sqlite3.connect(DB_PATH, timeout=5.0)`. Catch `OperationalError` and retry on next poll cycle. Do not hold the connection open between polls.

### Pitfall 6: macpymessenger Requires Script Validation at Init

**What goes wrong:** `ScriptNotFoundError` raised at `Configuration()` if the package's bundled AppleScript file is not found.

**Why it happens:** `Configuration` validates the AppleScript path at initialization time.

**How to avoid:** `pip install macpymessenger` correctly bundles the script. If running in a virtualenv, ensure the env is activated. Do not import macpymessenger in the `IMESSAGE_ENABLED=false` early-exit path — check the flag before importing.

### Pitfall 7: Discord.py `on_ready` Fires Multiple Times

**What goes wrong:** `tree.sync()` called in `on_ready` fires on each reconnect, hammering Discord's API and hitting rate limits.

**Why it happens:** `on_ready` fires on initial connect AND on reconnect after network interruption.

**How to avoid:** Use `setup_hook` (fires once per bot startup) instead of `on_ready` for command syncing:

```python
class SentinelBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()  # called exactly once per process start
```

---

## Code Examples

### Discord Bot — Minimal Working Structure

```python
# interfaces/discord/bot.py
# Source: discord.py 2.7 patterns [ASSUMED — matches documented API]
import os
import discord
from discord import app_commands
import httpx

SENTINEL_CORE_URL = os.environ["SENTINEL_CORE_URL"]
SENTINEL_API_KEY = os.environ["SENTINEL_API_KEY"]
DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]

class SentinelBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.http_client = None

    async def setup_hook(self):
        self.http_client = httpx.AsyncClient(timeout=200.0)
        await self.tree.sync()

    async def close(self):
        if self.http_client:
            await self.http_client.aclose()
        await super().close()

bot = SentinelBot()

@bot.tree.command(name="sentask", description="Ask the Sentinel")
@app_commands.describe(message="Your message to the Sentinel")
async def sentask(interaction: discord.Interaction, message: str):
    # Defer FIRST — must happen within 3 seconds
    await interaction.response.defer(thinking=True)

    # Create thread immediately
    thread = await interaction.channel.create_thread(
        name=message[:50],
        type=discord.ChannelType.public_thread,
        auto_archive_duration=60,
    )

    # Call Core
    try:
        resp = await bot.http_client.post(
            f"{SENTINEL_CORE_URL}/message",
            json={"content": message, "user_id": str(interaction.user.id)},
            headers={"X-Sentinel-Key": SENTINEL_API_KEY},
        )
        resp.raise_for_status()
        ai_response = resp.json()["content"]
    except Exception as exc:
        ai_response = f"Error: {exc}"

    # Send AI response into the thread
    await thread.send(ai_response)

    # Acknowledge the interaction (clears "thinking" state)
    await interaction.followup.send(
        f"Response ready: {thread.mention}",
        ephemeral=True,
    )

bot.run(DISCORD_BOT_TOKEN)
```

### iMessage Bridge — Polling Loop Skeleton

```python
# interfaces/imessage/bridge.py
# Source: chat.db schema [ASSUMED — standard pattern]
import os
import re
import sqlite3
import time
import httpx

IMESSAGE_ENABLED = os.environ.get("IMESSAGE_ENABLED", "false").lower() == "true"
DB_PATH = os.path.expanduser("~/Library/Messages/chat.db")
SENTINEL_CORE_URL = os.environ.get("SENTINEL_CORE_URL", "http://localhost:8000")
SENTINEL_API_KEY = os.environ["SENTINEL_API_KEY"]
POLL_INTERVAL = 3  # seconds

def sanitize_handle(handle: str) -> str:
    return "imsg_" + re.sub(r"[^a-zA-Z0-9_-]", "", handle)

def poll_messages(last_rowid: int):
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    try:
        rows = conn.execute(
            """SELECT m.ROWID, h.id, COALESCE(m.text, '') as text
               FROM message m JOIN handle h ON m.handle_id = h.ROWID
               WHERE m.is_from_me = 0 AND m.ROWID > ?
               ORDER BY m.ROWID ASC""",
            (last_rowid,)
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()
    return rows

def main():
    if not IMESSAGE_ENABLED:
        print("IMESSAGE_ENABLED=false — bridge disabled. Set to true to enable.")
        return

    last_rowid = 0
    with httpx.Client(timeout=200.0) as http:
        while True:
            for rowid, handle, text in poll_messages(last_rowid):
                last_rowid = max(last_rowid, rowid)
                if not text.strip():
                    continue  # skip attributedBody-only messages (Ventura+)
                user_id = sanitize_handle(handle)
                resp = http.post(
                    f"{SENTINEL_CORE_URL}/message",
                    json={"content": text, "user_id": user_id},
                    headers={"X-Sentinel-Key": SENTINEL_API_KEY},
                )
                if resp.ok:
                    # TODO: send ai_response back via macpymessenger
                    pass
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
```

### Auth Middleware Test Fixture Update

After adding `APIKeyMiddleware`, every existing test that POSTs to `/message` must include the auth header:

```python
# sentinel-core/tests/test_message.py — update all POST calls
resp = await client.post(
    "/message",
    json={"content": "hello", "user_id": "test"},
    headers={"X-Sentinel-Key": "test-key-for-pytest"},  # ADD THIS
)
```

The conftest.py already sets `os.environ["SENTINEL_API_KEY"] = "test-key-for-pytest"` before app import, so `settings.sentinel_api_key` == `"test-key-for-pytest"` in all tests. The middleware will accept that value.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `discord.ext.commands` prefix commands | `app_commands.CommandTree` slash commands | discord.py 2.0 | Old `!command` prefix style is deprecated for bots; slash commands are required for verified bots |
| `@bot.on_event("ready")` for setup | `setup_hook()` for one-time init | discord.py 2.0 | `on_ready` fires on reconnect; `setup_hook` is the correct place for command sync |
| `client.loop.create_task()` | `discord.Client` with `async with` context manager | discord.py 2.0 | Modern asyncio patterns |
| `alpaca-trade-api` | `alpaca-py` | 2022 | Old SDK deprecated (not relevant to Phase 3, but noted for future phases) |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Auth middleware with headers-only dispatch is safe from body-stream exhaustion in current Starlette versions | Common Pitfalls #4, Code Examples | Low — body is never touched; stream exhaustion only occurs when body is read |
| A2 | `interaction.channel.create_thread()` is available in guild text channels for bots without special permissions | Architecture Pattern 1 | Medium — bot may need `MANAGE_THREADS` permission in some guild configurations |
| A3 | Discord's default `auto_archive_duration=60` is valid (60 minutes) | Code Examples | Low — valid values are 60, 1440, 4320, 10080; 60 is always valid |
| A4 | `setup_hook()` is the correct single-fire initialization point in discord.py 2.x | Architecture Pattern 2 | Low — well-established pattern in discord.py 2.0+ community |
| A5 | Direct SQLite ROWID query against chat.db is more appropriate than `imessage_reader.get_messages()` for polling | Architecture Pattern 4 | Low — `get_messages()` fetches ALL messages every call; ROWID filtering is standard approach |
| A6 | iMessage attributedBody-only messages (Ventura+) are safe to skip in Phase 3 scope | Common Pitfalls #3, Code Examples | Low — user can retry by typing a plain text message; full typedstream decoding is a future concern |

---

## Open Questions

1. **Bot permission requirements for thread creation**
   - What we know: `create_thread()` on a `TextChannel` requires the bot to have `CREATE_PUBLIC_THREADS` or `MANAGE_THREADS` permission
   - What's unclear: Whether the test guild has this configured; whether a simple invite link covers it
   - Recommendation: Document the required bot scopes in the Discord developer portal setup guide (README): `applications.commands`, `bot` with `CREATE_PUBLIC_THREADS`

2. **iMessage attributedBody handling depth**
   - What we know: Ventura+ stores some message bodies only in `attributedBody` binary column; current bridge design skips these with a warning
   - What's unclear: What percentage of real messages are affected; whether the user's iMessage usage patterns trigger this frequently
   - Recommendation: Skip in Phase 3 with a clear log warning. Add `python-typedstream` in a future phase if the user reports missed messages.

3. **macpymessenger reply threading**
   - What we know: macpymessenger sends new messages; it does not appear to support replying to a specific iMessage thread/conversation context
   - What's unclear: Whether the recipient will see responses as continuation of their conversation thread or as new messages
   - Recommendation: Acceptable for Phase 3. iMessage displays messages from the same number in the same conversation regardless.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | discord container build/run | ✓ | 29.3.1 | — |
| Docker Compose v2 | `docker compose up` | ✓ | v5.1.1 | — |
| Python 3.12 | Dockerfile for discord bot | ✓ (via container) | 3.12 in container | — |
| discord.py 2.7.1 | IFACE-02, IFACE-03, IFACE-04 | ✗ (not installed on host) | — | Will be installed in container |
| imessage-reader 0.6.1 | IFACE-05 | ✗ (not installed on host) | — | Must be installed on host for iMessage bridge |
| macpymessenger 0.2.0 | IFACE-05 | ✗ (not installed on host) | — | Must be installed on host for iMessage bridge |
| Full Disk Access (macOS) | IFACE-05 (chat.db read) | Unknown | — | No fallback — required for iMessage polling |
| Messages app running | IFACE-05 (iMessage receive) | Unknown | — | No fallback — required for iMessage delivery |

**Missing dependencies with no fallback:**
- Full Disk Access for Python/Terminal — required for chat.db read; user must grant manually in System Settings

**Missing dependencies with fallback:**
- `discord.py`, `imessage-reader`, `macpymessenger` — not installed on host, but Discord bot runs in Docker container (discord.py installed there). iMessage libraries need host install only when `IMESSAGE_ENABLED=true`.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.23+ |
| Config file | `sentinel-core/pyproject.toml` — `[tool.pytest.ini_options]` with `asyncio_mode = "auto"` |
| Quick run command | `cd sentinel-core && python3 -m pytest tests/ -q` |
| Full suite command | `cd sentinel-core && python3 -m pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| IFACE-01 | MessageEnvelope validates content + user_id | unit | `pytest tests/test_message.py::test_user_id_rejects_path_traversal tests/test_message.py::test_user_id_accepts_valid_chars -x` | ✅ exists |
| IFACE-06 | Middleware returns 401 for missing/wrong key | unit | `pytest tests/test_message.py::test_auth_required_on_message -x` | ❌ Wave 0 |
| IFACE-06 | Middleware allows /health without key | unit | `pytest tests/test_message.py::test_health_no_auth_required -x` | ❌ Wave 0 |
| IFACE-06 | Existing message tests pass with correct key | unit | `pytest tests/test_message.py -x` | ✅ exists (needs header update) |
| IFACE-02 | Discord bot calls Core with correct payload | unit | `pytest interfaces/discord/tests/test_bot.py -x` | ❌ Wave 0 |
| IFACE-03 | Defer called before Core call (< 3s) | manual | Discord UI observation | manual-only |
| IFACE-04 | Thread created per /sentask invocation | manual | Discord UI observation | manual-only |
| IFACE-05 | iMessage bridge sanitizes handle to user_id | unit | `pytest interfaces/imessage/tests/test_bridge.py::test_sanitize_handle -x` | ❌ Wave 0 |
| IFACE-05 | Bridge exits cleanly when IMESSAGE_ENABLED=false | unit | `pytest interfaces/imessage/tests/test_bridge.py::test_disabled_exits -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `cd sentinel-core && python3 -m pytest tests/ -q`
- **Per wave merge:** `cd sentinel-core && python3 -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `sentinel-core/tests/test_message.py` — add `test_auth_required_on_message`, `test_health_no_auth_required`, update all existing POST calls to include `X-Sentinel-Key` header
- [ ] `interfaces/discord/tests/test_bot.py` — unit tests for bot command handler (mock httpx, mock discord interaction)
- [ ] `interfaces/imessage/tests/test_bridge.py` — unit tests for `sanitize_handle`, IMESSAGE_ENABLED=false guard, ROWID tracking logic

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | X-Sentinel-Key header; `BaseHTTPMiddleware` enforcement |
| V3 Session Management | no | Stateless; no session tokens |
| V4 Access Control | yes | `/health` public; all other routes require valid key |
| V5 Input Validation | yes | Pydantic v2 `MessageEnvelope` validates all incoming content; `user_id` pattern `^[a-zA-Z0-9_-]+$` |
| V6 Cryptography | no | Shared secret (sufficient for personal local-network use per CLAUDE.md constraints) |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Missing auth header | Spoofing | `BaseHTTPMiddleware` returns 401 before route handler runs |
| user_id path traversal (e.g., `../../etc/passwd`) | Tampering | `user_id` regex `^[a-zA-Z0-9_-]+$` on `MessageEnvelope` — already enforced |
| iMessage handle injection in SQL | Tampering | Parameterized SQLite query (`WHERE m.ROWID > ?`); handle sanitized via regex before use as user_id |
| Discord snowflake collision/impersonation | Spoofing | Not a concern for personal single-user deployment; snowflakes are Discord-assigned |
| Oversized message → token guard bypass | Denial of Service | `content: str = Field(..., max_length=32_000)` on MessageEnvelope + token guard in route |

---

## Project Constraints (from CLAUDE.md)

| Directive | Applies to Phase 3 |
|-----------|-------------------|
| Use `httpx.AsyncClient` for all outbound HTTP; never `requests` | Discord bot must use `httpx.AsyncClient` to call Core |
| Use `discord.py`, not `py-cord` / `disnake` / `nextcord` | Confirmed — discord.py 2.7.1 is the library |
| Python 3.12 for Sentinel Core and interfaces | Discord Dockerfile: `python:3.12-slim` |
| Docker Compose `include` directive, never `-f` stacking | Discord `compose.yml` added as an `include` entry in root compose |
| Pydantic v2 syntax (`model_config = {"from_attributes": True}`, not `orm_mode`) | Any new models in interface code must use v2 syntax |
| No SQLite/PostgreSQL for core data — Obsidian is the database | iMessage bridge's chat.db polling is read-only; no new database added |
| Commit directly to `main` (project override — no PRs) | All phase work commits directly to main |
| `sentinel_api_key` in Settings already — enforcement to be added via middleware | Confirmed — `config.py` has `sentinel_api_key: str` with no default |

---

## Sources

### Primary (HIGH confidence)

- `pip registry` — discord.py 2.7.1 current version [VERIFIED]
- `pip registry` — imessage-reader 0.6.1 current version [VERIFIED]
- `macpymessenger-0.2.0.dist-info/METADATA` (wheel inspection) — Python >=3.10, send API, Jinja2 dependency [VERIFIED]
- `sentinel-core/app/config.py` — `sentinel_api_key: str` already present [VERIFIED]
- `sentinel-core/app/models.py` — MessageEnvelope stable [VERIFIED]
- `sentinel-core/app/main.py` — lifespan pattern, middleware registration point [VERIFIED]
- `sentinel-core/tests/conftest.py` — `SENTINEL_API_KEY=test-key-for-pytest` env var setup [VERIFIED]
- `sentinel-core/pyproject.toml` — pytest config, asyncio_mode = "auto" [VERIFIED]
- `sentinel-core/compose.yml` + `pi-harness/compose.yml` — no explicit networks declared (uses default) [VERIFIED]
- `docker-compose.yml` — include directive pattern established [VERIFIED]
- `discord.com/developers/docs/interactions/application-commands` — global command propagation up to 1 hour; guild commands instant [CITED]
- `docs.docker.com/compose/how-tos/networking/` — single default network for all included services [CITED]

### Secondary (MEDIUM confidence)

- discord.py docs (readthedocs.io/en/stable/interactions/api.html) — defer API, WebhookMessage, thinking=True [CITED — 403 on direct fetch, confirmed via search snippet]
- Brave Search results for discord.py thread creation patterns — `channel.create_thread()` is the correct API [MEDIUM]
- `github.com/Rapptz/discord.py/discussions/8170` — `setup_hook` pattern for command sync [CITED]
- Starlette PR #1692 / issue #495 — body stream exhaustion in BaseHTTPMiddleware [CITED]

### Tertiary (LOW confidence)

- WebFetch of macpymessenger docs returned "Python 3.14" — contradicted by wheel METADATA (>=3.10). The WebFetch result was wrong; METADATA is authoritative.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified via pip registry and wheel inspection
- Architecture: MEDIUM — discord.py API confirmed via official docs snippets; thread creation pattern confirmed via community patterns
- Pitfalls: MEDIUM — body stream exhaustion verified from Starlette issue tracker; discord.py timing issues confirmed from official Discord docs
- iMessage patterns: MEDIUM — chat.db ROWID polling is well-established across multiple sources; attributedBody limitation confirmed

**Research date:** 2026-04-10
**Valid until:** 2026-05-10 (stable stack; discord.py updates infrequently)
