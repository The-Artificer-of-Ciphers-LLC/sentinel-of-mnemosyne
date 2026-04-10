# Stack Research

**Domain:** Self-hosted containerized AI assistant platform
**Researched:** 2026-04-10
**Confidence:** HIGH (most choices verified against official sources)

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.12 | Sentinel Core runtime | FastAPI requires 3.10+; 3.12 is the stable sweet spot (3.13 works but 3.12 has wider ecosystem testing) |
| FastAPI | ~0.135.x | HTTP API framework for Sentinel Core | Async-native, auto-generated OpenAPI docs, Pydantic v2 integration, dominant in the Python AI/automation space. No real competitor for this use case. |
| Node.js | 22 LTS | Pi harness container runtime | pi-mono requires >=20.6.0 (verified from package.json engines field). Node 22 is the current LTS. See ADR flag below regarding the Node 24 constraint. |
| Docker Compose | v2 (current) | Multi-service orchestration | Override file pattern is well-supported. Use `docker compose` (v2, no hyphen), not `docker-compose` (v1, deprecated). |

### Supporting Libraries -- Python (Sentinel Core)

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `fastapi` | >=0.135.0 | Web framework | Current stable. Includes streaming JSONL support and strict content-type checking. |
| `uvicorn[standard]` | >=0.44.0 | ASGI server | The `[standard]` extra installs uvloop + httptools for production performance. |
| `pydantic` | >=2.7.0 | Data validation, message envelope models | Required by FastAPI. v2 is 5-50x faster than v1. Use `model_config = {"from_attributes": True}` not old `orm_mode`. |
| `pydantic-settings` | >=2.13.0 | Environment variable configuration | Loads .env files, validates config at startup, type-safe settings. Replaces hand-rolled `os.getenv()` patterns. |
| `httpx` | >=0.28.1 | Async HTTP client | For calling Obsidian REST API and LM Studio. Use `httpx.AsyncClient()` as a context manager for connection pooling. Do NOT use `requests` (blocking). |
| `discord.py` | >=2.7.0 | Discord bot interface | See Discord section below. |
| `alpaca-py` | >=0.43.0 | Alpaca trading API (paper + live) | Official SDK, replaces deprecated `alpaca-trade-api`. |
| `ofxtools` | >=0.9.5 | OFX file parsing | See OFX section below. |

### Supporting Libraries -- Node.js (Pi Harness)

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `@mariozechner/pi-coding-agent` | Pin to 0.66.1 | AI execution layer | Latest stable as of 2025-04-08. Pin exactly; project is under active development. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `pytest` + `pytest-asyncio` | Testing | FastAPI + async requires pytest-asyncio for `async def test_*` functions |
| `httpx` | Test client | FastAPI's recommended test client (`from httpx import AsyncClient`) |
| `ruff` | Linting + formatting | Replaces black + flake8 + isort. Single tool, fast (Rust-based). |
| `mypy` | Type checking | Use with pydantic plugin (`pydantic.mypy`) for model validation |
| `docker compose watch` | Dev hot-reload | Rebuilds containers on file change. Use instead of volume-mounting source in production. |

## Installation

```bash
# Sentinel Core (Python)
pip install "fastapi>=0.135.0" "uvicorn[standard]>=0.44.0" "httpx>=0.28.1" \
  "pydantic>=2.7.0" "pydantic-settings>=2.13.0"

# Discord interface
pip install "discord.py>=2.7.0"

# Finance module
pip install "ofxtools>=0.9.5"

# Trading module
pip install "alpaca-py>=0.43.0"

# Dev dependencies
pip install pytest pytest-asyncio ruff mypy

# Pi harness (Node.js)
npm install @mariozechner/pi-coding-agent@0.66.1
```

## Detailed Findings by Question

### 1. FastAPI Production Stack (HIGH confidence)

**Verified:** FastAPI 0.135.x is current (April 2026). Requires Python 3.10+.

The standard FastAPI production stack in 2025-2026:

- **FastAPI** -- framework
- **Uvicorn** -- ASGI server (use `[standard]` extra for uvloop)
- **Pydantic v2** -- models, validation, settings
- **httpx** -- async HTTP client (replaces `requests`)
- **pydantic-settings** -- env var management (separate package since Pydantic v2)

**Pattern for this project:** The Sentinel Core is a lightweight orchestration layer, not a data-heavy API. Skip SQLAlchemy, skip Alembic, skip any ORM. The "database" is Obsidian accessed via REST API.

**Key architectural pattern:** Use `httpx.AsyncClient` as a singleton with connection pooling for the Obsidian and LM Studio clients. Create it in FastAPI's lifespan handler, share via `app.state`:

```python
from contextlib import asynccontextmanager
import httpx

@asynccontextmanager
async def lifespan(app):
    app.state.obsidian_client = httpx.AsyncClient(
        base_url=settings.obsidian_api_url,
        headers={"Authorization": f"Bearer {settings.obsidian_api_key}"},
        verify=False,  # self-signed cert from Obsidian REST API
    )
    yield
    await app.state.obsidian_client.aclose()
```

### 2. Pi Harness Container -- RPC Mode (HIGH confidence)

**Verified from source:** The `@mariozechner/pi-coding-agent` package.json specifies `"node": ">=20.6.0"`.

**ADR FLAG: The PROJECT.md and ARCHITECTURE-Core.md state "Node.js 24+ minimum -- do not use lower versions." This is stricter than the actual requirement.** pi-mono only requires >=20.6.0. Node 22 is the current LTS (supported through April 2027). Node 24 is not yet LTS and enters LTS in October 2026. Using Node 24 is fine but unnecessary; Node 22 LTS is the safer production choice. Recommend updating the constraint to "Node.js 22 LTS or later."

**RPC Protocol (verified from official docs):**

Start: `pi --mode rpc [--provider <name>] [--model <pattern>]`

Communication is strict JSONL over stdin/stdout (LF-delimited, NOT readline-compatible due to U+2028/U+2029).

**Key commands:**
- `{"type": "prompt", "content": "user message"}` -- send a prompt
- `{"type": "abort"}` -- stop current operation
- `{"type": "new_session"}` -- fresh conversation
- `{"type": "get_state"}` -- retrieve session state
- `{"type": "set_model", "provider": "...", "modelId": "..."}` -- switch model

**Events emitted (stdout):**
- `agent_start` / `agent_end` -- conversation lifecycle
- `message_update` -- streaming text chunks
- `tool_execution_start/update/end` -- tool calls
- `turn_start` / `turn_end` -- reasoning turns

**All commands support an optional `id` field** for request/response correlation.

**Python integration pattern:** Use `asyncio.create_subprocess_exec` to spawn pi and communicate via stdin/stdout. Read stdout line-by-line, parse each as JSON. Write commands as JSON + `\n` to stdin.

```python
import asyncio
import json

proc = await asyncio.create_subprocess_exec(
    "pi", "--mode", "rpc", "--provider", "lmstudio",
    stdin=asyncio.subprocess.PIPE,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)

# Send a prompt
cmd = json.dumps({"type": "prompt", "content": "Hello", "id": "req-1"}) + "\n"
proc.stdin.write(cmd.encode())
await proc.stdin.drain()

# Read events
async for line in proc.stdout:
    event = json.loads(line.decode())
    if event.get("type") == "agent_end":
        break
```

**Architecture decision:** The ARCHITECTURE-Core.md mentions Pi exposing port 8765 for RPC. But pi's RPC mode is stdin/stdout, not a network port. Two options:

1. **Subprocess (recommended for v0.1):** Sentinel Core spawns pi as a child process inside the same container or via docker exec. Simpler, no network overhead.
2. **Thin HTTP wrapper (recommended for v0.2+):** Write a small Node.js HTTP server inside the pi-harness container that accepts HTTP POST requests and proxies them to a pi subprocess via stdin/stdout. This enables the two-container architecture described in the ARCHITECTURE doc.

The second approach preserves container isolation. A ~50-line Fastify server wrapping the pi subprocess is the right bridge.

### 3. Discord Bot Library (HIGH confidence)

**Verified:** discord.py v2.7.1 was released March 3, 2026. It is actively maintained.

**Use discord.py.** The "discord.py is dead" narrative is outdated. After a period of inactivity, discord.py resumed active development and is now the most up-to-date and widely-used Python Discord library. v2.x supports:
- Slash commands (app_commands)
- Buttons, select menus, modals (ui components)
- Voice support
- Components v2 (latest Discord UI features)

**Do NOT use:**
- `py-cord` -- Fork created during the hiatus. Now redundant; less popular, smaller contributor pool.
- `disnake` -- Same story. Good library but unnecessary when discord.py is active again.
- `nextcord` -- Same story.

All three forks were created because discord.py stopped development. Now that it's back, using the original avoids fork-specific quirks and has the largest community.

### 4. Apple Messages / iMessage Integration (MEDIUM confidence)

Apple provides NO official API for iMessage. All approaches are Mac-only hacks. This is inherently fragile.

**Recommended approach -- two-layer bridge:**

**Sending (outbound):**
- `macpymessenger` (v0.2.0) -- modern, typed Python library wrapping AppleScript. Sends messages via the Messages app. Install: `pip install macpymessenger`
- Alternative: raw `osascript` calls from Python. macpymessenger is a thin wrapper over this.

**Receiving (inbound):**
- Poll `~/Library/Messages/chat.db` (SQLite) for new messages. This is how every iMessage integration works -- there is no push notification API.
- `imessage_reader` (PyPI) -- reads from chat.db, handles macOS Ventura's `attributedBody` hidden text issue.
- Alternative: `imessage-tools` -- similar, also handles Ventura+ attributedBody parsing.

**Architecture:** This CANNOT run inside a Docker container. It must run as a native macOS process (needs Full Disk Access for chat.db, needs Messages.app for sending). The architecture doc already anticipates this: "Mac-side bridge process that connects to the Core container via HTTP."

**Implementation:**
1. Native Python process on Mac, polling chat.db every N seconds
2. On new message: POST to Sentinel Core's /message endpoint
3. Receive response, send via macpymessenger/AppleScript

**Gotchas:**
- Full Disk Access must be granted to the Python interpreter (or Terminal.app) in System Settings
- chat.db schema changes between macOS versions -- Ventura changed where message body text lives
- No way to detect message delivery/read status programmatically
- Group chats have different handle formats

### 5. Obsidian Local REST API (HIGH confidence)

**Verified:** Plugin v3.6.1 (released April 9, 2026), actively maintained.

**Default port:** 27124 (HTTPS with self-signed certificate)

**Authentication:** Bearer token via `Authorization: Bearer <API_KEY>` header. Key is generated in Obsidian plugin settings.

**Key endpoints:**

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/vault/{path}` | Read a file |
| PUT | `/vault/{path}` | Create or replace a file |
| PATCH | `/vault/{path}` | Surgical edit (append, prepend, replace heading, update frontmatter) |
| DELETE | `/vault/{path}` | Delete a file |
| GET | `/vault/` | List vault contents |
| POST | `/search/simple/?query=...` | Full-text fuzzy search |
| POST | `/search/` | Dataview DQL or JsonLogic queries |
| GET | `/tags/` | List all tags with usage counts |
| GET | `/active/` | Get currently open file |
| POST | `/commands/` | Run an Obsidian command |
| GET | `/open/{path}` | Open a file in the Obsidian UI |

**Gotchas:**
1. **Self-signed certificate:** All requests need `verify=False` (Python httpx) or `--insecure` (curl). You can download and trust the cert from `https://127.0.0.1:27124/obsidian-local-rest-api-certificate.crt` for proper TLS verification.
2. **Obsidian must be running:** The API is served by the Obsidian desktop app. If Obsidian is closed, the API is down. This is an operational dependency -- consider a health check in the Core that detects this.
3. **Docker networking:** From a container on the same Mac, use `https://host.docker.internal:27124`. From a different machine on the LAN, use the Mac's IP. The plugin docs warn against exposing to the internet.
4. **PATCH operations are powerful:** Can target a specific heading (`heading=Some Heading`), a block reference, or frontmatter field without rewriting the entire file. Use this for updating user context files.
5. **Content-Type for writes:** Use `text/markdown` for PUT/PATCH operations, not `application/json`.
6. **Search returns context:** The `contextLength` parameter on search controls how many characters of surrounding context are returned with each match.

### 6. OFX Parsing -- ofxtools (MEDIUM confidence)

**Verified:** ofxtools 0.9.5 is the latest on PyPI. The project has no formal GitHub releases, but versions are published to PyPI. Snyk flags it as "Inactive" which means low commit frequency, not abandoned.

**Use ofxtools.** It remains the only serious Python OFX library. The alternatives (`ofxparse`) are less maintained.

**Why it's still fine:**
- OFX is a stable specification (hasn't changed significantly in years)
- ofxtools handles both OFXv1 (SGML) and OFXv2 (XML)
- Zero external dependencies (stdlib only)
- Converts OFX to native Python objects with proper types

**Usage pattern:**
```python
from ofxtools.Parser import OFXTree

parser = OFXTree()
parser._feed(ofx_file)
ofx = parser.convert()
for stmt in ofx.statements:
    for txn in stmt.transactions:
        # txn.dtposted, txn.trnamt, txn.name, txn.memo
        pass
```

**Risk mitigation:** If ofxtools truly goes unmaintained and a future OFX spec change lands, you would need to fork or find a replacement. For a personal project parsing bank exports, this is a non-issue -- banks are very conservative about changing export formats.

### 7. Alpaca Trading SDK (HIGH confidence)

**Use `alpaca-py` (>=0.43.0).** It is the official SDK. `alpaca-trade-api` is deprecated -- Alpaca's own docs recommend migrating.

**Key differences from the old SDK:**
- OOP design with request/response models (Pydantic-based)
- Unified SDK covering Trading API, Market Data API, and Broker API
- Async support via httpx under the hood

**Paper vs Live:** Same API, different keys. Set via environment variables:
```python
from alpaca.trading.client import TradingClient

client = TradingClient(api_key, secret_key, paper=True)  # paper=False for live
```

**Do NOT use:** `alpaca-trade-api` -- deprecated, no longer receiving updates.

### 8. Python-to-Node.js IPC Pattern (HIGH confidence)

For the two-container architecture (Python Sentinel Core communicating with Node.js Pi harness):

**Recommended: Thin HTTP bridge inside the Pi container.**

The pi harness uses stdin/stdout JSONL for RPC. Since Docker containers communicate over the network (not shared stdin/stdout), a thin HTTP wrapper is needed.

**Pattern:**
```
Sentinel Core (Python)  --HTTP-->  Pi Bridge (Node.js HTTP server)  --stdin/stdout-->  pi process
```

The bridge is a small Node.js HTTP server (~50-100 lines) that:
1. Accepts POST requests with a JSON body (the prompt)
2. Writes the command to pi's stdin as JSONL
3. Collects stdout events
4. Returns the final response as HTTP response (or streams via SSE)

**Use Fastify** (not Express) for the bridge -- faster, lighter, TypeScript-native. For a thin proxy this simple, even Node's built-in `http` module works.

**Alternative: SDK mode.** Pi offers an `AgentSession` class importable in TypeScript. The bridge could use this directly instead of spawning a subprocess:
```typescript
import { AgentSession } from "@mariozechner/pi-coding-agent";
// Use the SDK API directly -- no subprocess needed
```

This is cleaner if the bridge is TypeScript. Check the SDK docs at `packages/coding-agent/docs/sdk.md`.

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| FastAPI | Flask | Never for this project. Flask is sync-first; FastAPI's async is essential for concurrent interface handling. |
| httpx | requests | Never in async code. `requests` blocks the event loop. |
| httpx | aiohttp | httpx has a cleaner API, better Pydantic integration, and is FastAPI's recommended test client. |
| discord.py | py-cord / disnake | Only if discord.py development stops again (unlikely given v2.7.1 momentum). |
| ofxtools | ofxparse | ofxparse is less maintained and handles fewer OFX edge cases. |
| alpaca-py | alpaca-trade-api | Never. The old SDK is deprecated. |
| Pydantic Settings | python-dotenv | python-dotenv only loads .env files. pydantic-settings validates, type-checks, and documents all configuration. |
| Fastify (bridge) | Express | Express works fine but Fastify is faster and has better TypeScript support for new code. |
| Node 22 LTS | Node 24 | Use Node 24 if you need cutting-edge V8 features. Otherwise, Node 22 LTS is the production-safe choice. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `requests` library | Blocks the async event loop. Will cause timeouts under concurrent load. | `httpx` with `AsyncClient` |
| `alpaca-trade-api` | Officially deprecated by Alpaca | `alpaca-py` |
| `py-cord` / `disnake` / `nextcord` | Forks created during discord.py's hiatus. Now redundant -- discord.py is active again with v2.7.x | `discord.py` |
| Pydantic v1 syntax | FastAPI dropped v1 support. `class Config: orm_mode = True` will break. | Pydantic v2: `model_config = {"from_attributes": True}` |
| `python-dotenv` alone | No validation, no type safety, silent failures on missing vars | `pydantic-settings` (loads .env AND validates) |
| `docker-compose` (v1, hyphen) | Deprecated. Docker Compose v1 is no longer maintained. | `docker compose` (v2, space, built into Docker CLI) |
| SQLite/PostgreSQL for core data | Obsidian vault IS the database. Adding a traditional DB creates data split and defeats the "human-readable markdown" principle. | Obsidian REST API for all reads/writes |
| Node.js `readline` for RPC parsing | readline splits on U+2028 and U+2029 (Unicode line separators), which are valid inside JSON strings. This breaks JSONL protocol compliance. | Manual line splitting on `\n` only |

## ADR Flags and Concerns

### Flag 1: Node.js Version Constraint (MEDIUM severity)

**Current ADR says:** "Node.js 24+ for Pi harness container -- pi-mono minimum requirement, do not use lower versions"

**Actual requirement:** pi-mono's package.json specifies `"node": ">=20.6.0"`. Node 24 is NOT required.

**Recommendation:** Change constraint to "Node.js 22 LTS or later." Node 22 is in active LTS until April 2027. Node 24 enters LTS in October 2026 -- using it now means running a non-LTS version in production.

### Flag 2: Pi RPC Port 8765 (LOW severity)

**Current architecture says:** Pi exposes port 8765 for RPC.

**Actual RPC mode:** Pi uses stdin/stdout JSONL, not a network port. A thin HTTP bridge server is needed to expose this over the network. Port 8765 is fine for that bridge server, but it's the bridge's port, not pi's native port.

### Flag 3: Obsidian HTTPS Self-Signed Cert (LOW severity)

Every HTTP client talking to Obsidian will need to disable certificate verification or trust the self-signed cert. This is fine for local network use but every new developer will hit this. Document it prominently.

### Flag 4: iMessage Interface is Mac-Native Only (MEDIUM severity)

Cannot be containerized. Requires Full Disk Access. Breaks the "everything is a Docker container" pattern. The architecture doc acknowledges this, but implementation will need a separate deployment/monitoring story.

## Version Compatibility Matrix

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| FastAPI >=0.135.0 | Python >=3.10 | 3.12 recommended |
| FastAPI >=0.135.0 | Pydantic >=2.7.0 | Pydantic v1 NOT supported |
| Pydantic >=2.7.0 | pydantic-settings >=2.0.0 | Separate package since Pydantic v2 |
| uvicorn >=0.44.0 | Python >=3.10 | Use `[standard]` extra for uvloop |
| discord.py >=2.7.0 | Python >=3.8 | aiohttp is a dependency |
| alpaca-py >=0.43.0 | Python >=3.8 | Uses httpx internally |
| pi-coding-agent 0.66.1 | Node.js >=20.6.0 | Pin exact version |

## Sources

- [FastAPI release notes](https://fastapi.tiangolo.com/release-notes/) -- version and Python requirements (HIGH confidence)
- [FastAPI best practices repo](https://github.com/zhanymkanov/fastapi-best-practices) -- production patterns (MEDIUM confidence)
- [pi-mono GitHub repo](https://github.com/badlogic/pi-mono) -- RPC docs, package.json, releases (HIGH confidence)
- [pi-mono RPC protocol docs](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/rpc.md) -- JSONL protocol (HIGH confidence)
- [pi-mono npm page](https://www.npmjs.com/package/@mariozechner/pi-coding-agent) -- version info (HIGH confidence)
- [discord.py PyPI](https://pypi.org/project/discord.py/) -- v2.7.1, March 2026 (HIGH confidence)
- [discord.py GitHub](https://github.com/Rapptz/discord.py) -- active development confirmed (HIGH confidence)
- [Obsidian Local REST API GitHub](https://github.com/coddingtonbear/obsidian-local-rest-api) -- endpoints, auth, v3.6.1 (HIGH confidence)
- [Obsidian Local REST API interactive docs](https://coddingtonbear.github.io/obsidian-local-rest-api/) -- Swagger/OpenAPI spec (HIGH confidence)
- [ofxtools PyPI](https://pypi.org/project/ofxtools/) -- v0.9.5 (MEDIUM confidence -- maintenance status unclear)
- [ofxtools docs](https://ofxtools.readthedocs.io/en/latest/) -- usage patterns (HIGH confidence)
- [alpaca-py GitHub](https://github.com/alpacahq/alpaca-py) -- v0.43.2, Nov 2025 (HIGH confidence)
- [Alpaca SDKs docs](https://docs.alpaca.markets/docs/sdks-and-tools) -- official recommendation to use alpaca-py (HIGH confidence)
- [macpymessenger GitHub](https://github.com/ethan-wickstrom/macpymessenger) -- iMessage sending (MEDIUM confidence)
- [imessage_reader PyPI](https://pypi.org/project/imessage-reader/) -- iMessage reading from chat.db (MEDIUM confidence)
- [httpx PyPI](https://pypi.org/project/httpx/) -- v0.28.1 (HIGH confidence)
- [pydantic-settings GitHub](https://github.com/pydantic/pydantic-settings) -- v2.13.1 (HIGH confidence)

---
*Stack research for: Sentinel of Mnemosyne*
*Researched: 2026-04-10*
