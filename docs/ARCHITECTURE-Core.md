# Sentinel of Mnemosyne — Core Architecture
**Version:** 0.1
**Date:** 2026-04-06
**Scope:** Core system only — Pi harness, Obsidian vault, Sentinel Core container, and base interface layer. Module-specific architecture (Pathfinder, Music, Coder, etc.) documented separately after core is stable.

---

## 1. System Overview

The Sentinel of Mnemosyne is a self-hosted, containerized AI assistant platform. The core has three functional layers:

```
┌─────────────────────────────────────────────────┐
│            INTERFACE LAYER                      │
│   (Discord, Messages, curl — one container each)│
└────────────────────┬────────────────────────────┘
                     │  HTTP POST /message
                     │  X-Sentinel-Key header
                     ▼
┌─────────────────────────────────────────────────┐
│           SENTINEL CORE CONTAINER               │
│   FastAPI router · APIKeyMiddleware             │
│   ModelRegistry · ProviderRouter               │
│   context retrieval · Obsidian writes           │
└──────────┬──────────────┬──────────┬────────────┘
           │  HTTP         │  HTTP    │  REST API
           ▼               ▼          ▼
┌──────────────┐  ┌──────────────────┐  ┌────────────────────────┐
│  PI HARNESS  │  │  AI PROVIDER     │  │  OBSIDIAN LOCAL        │
│  CONTAINER   │  │  LAYER           │  │  REST API              │
│  (primary)   │  │  (fallback)      │  │  (plugin on host Mac)  │
│  coding-agent│  │  ProviderRouter  │  │  Vault on host disk    │
└──────────────┘  │  LiteLLMProvider │  └────────────────────────┘
       │          │  OllamaProvider  │
       ▼          │  LlamaCppProvider│
┌──────────────┐  └──────────────────┘
│  LM STUDIO   │           │
│  (Mac Mini)  │           │ primary → LM Studio (LiteLLM)
│  :1234/v1    │           │ fallback → Claude API
└──────────────┘           │           Ollama (stub)
                           │           llama.cpp (stub)
                           ▼
                  ┌──────────────────┐
                  │  AI BACKENDS     │
                  │  LM Studio       │
                  │  Anthropic Claude│
                  │  Ollama (future) │
                  │  llama.cpp (fut.)│
                  └──────────────────┘
```

**Request path:** Pi harness is tried first (supports tool use and skill dispatch). If Pi is unreachable, `ProviderRouter` calls the configured AI provider directly. Both paths share the same Obsidian memory context injection and session write.

**The brain:** Pi harness + LM Studio — executes AI reasoning, tool use, skill dispatch.
**The heart:** Obsidian vault (Mnemosyne) — persists all knowledge as human-readable markdown.
**The nervous system:** Sentinel Core — routes messages, retrieves context, orchestrates writes.

---

## 2. Technology Decisions

### ADR-001: Pi Harness as AI Execution Layer

**Status:** Accepted
**Decision:** Use [pi-mono/coding-agent](https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent) as the AI orchestration layer.

**Context:** We need an AI execution engine that handles the conversation loop, tool calling, and skill dispatch. Building this from scratch would be significant work and would duplicate what pi already does well.

**What pi gives us:**
- Four built-in tools: `read`, `write`, `edit`, `bash` — exactly the right primitives for a system that needs to interact with files and the shell
- A skill system (SKILL.md files) that directly maps to our pluggable module concept
- RPC mode (stdin/stdout JSONL) for programmatic integration without needing a web server inside the pi container
- SDK mode in TypeScript for tighter integration if needed
- Configurable AI provider via environment variables or `settings.json`

**Integration approach:** Run pi in **RPC mode** inside its container. The Sentinel Core sends prompts as JSONL over stdin, reads responses from stdout. This is cleaner than wrapping a CLI in bash scripts.

**Consequences:**
- We depend on the pi-mono project's maintenance cadence — pin to a specific npm version
- The pi container must be a Node.js container (pi is a TypeScript/Node package)
- Skills we write for modules must follow pi's SKILL.md format

---

### ADR-002: Obsidian Local REST API for Vault Writes

**Status:** Accepted
**Decision:** Use the [obsidian-local-rest-api](https://github.com/coddingtonbear/obsidian-local-rest-api) community plugin for all programmatic reads and writes to the vault.

**Context:** Obsidian is a local file-based system. External programs can write `.md` files directly to the vault folder and Obsidian will detect them. However, direct file writes have race conditions and don't integrate with Obsidian's indexing. The Local REST API plugin provides a proper HTTPS API with authentication.

**Key capabilities this gives us:**
- `PUT /vault/{path}` — create or replace a file
- `PATCH /vault/{path}` — surgical edits (append to section, prepend, replace specific heading)
- `GET /vault/{path}` — read a file
- `GET /search/simple/` — full-text search across the vault
- `GET /tags/` — query all tags and usage counts
- Requires an API key (set once in Obsidian settings, stored as `OBSIDIAN_API_KEY` env var)

**Why not direct file writes?** Direct writes to the vault folder work for the MVP and for bulk import (see §7 on importing existing data). For ongoing production writes, the REST API is cleaner and safer.

**Consequences:**
- Obsidian must be running on the Mac for the REST API to be available
- API key must be configured on first setup
- The vault path must be accessible to both the Mac running Obsidian and the Core container (via network mount or shared volume)

---

### ADR-003: LM Studio as Primary AI Provider

**Status:** Accepted
**Decision:** Target LM Studio running on the Mac Mini as the primary AI backend. Use its OpenAI-compatible API endpoint.

**LM Studio technical details:**
- Runs at `http://[mac-mini-ip]:1234` by default (configurable)
- Exposes OpenAI-compatible API at `/v1/` — same request format as OpenAI's API
- No authentication required for local network use (optional API token available in v0.4+)
- Endpoints we will use:
  - `GET /v1/models` — list loaded models
  - `POST /v1/chat/completions` — send a chat prompt, receive response
  - Supports streaming responses

**Pi harness configuration for LM Studio:**
In the pi container's `settings.json`, LM Studio is added as a custom provider pointing to the Mac Mini's IP. The `LMSTUDIO_BASE_URL` environment variable overrides the base URL at runtime.

**Provider swap path:** Because we use the OpenAI-compatible API format, switching to a different provider (Anthropic, another local model server) requires only changing the base URL and API key environment variables in the Pi container. No code changes.

**Consequences:**
- Mac Mini must be on the same local network as the Docker host
- LM Studio must have a model loaded before the Sentinel can respond
- Model performance depends on Mac Mini hardware (RAM, neural engine)

---

### ADR-004: FastAPI (Python) for Sentinel Core

**Status:** Proposed
**Decision:** Implement the Sentinel Core container in Python using [FastAPI](https://fastapi.tiangolo.com/).

**Context:** The Core is primarily a routing and orchestration layer — it receives HTTP messages, does some context lookup, forwards to pi, handles the response, and writes to Obsidian. It is not computationally intensive.

**Why Python + FastAPI:**
- Python is the language of the AI/automation ecosystem — libraries for everything
- FastAPI is lightweight, fast to write, and produces automatic API documentation (`/docs`)
- Async support handles concurrent interface calls cleanly
- The team has more familiarity with Python than alternatives like Go or Rust

**Why not Node.js (even though pi is Node):** Mixing the Core and the Pi harness into the same container would couple them unnecessarily. Separate containers keep concerns clean.

**Consequences:**
- Two language runtimes in the system (Node for Pi, Python for Core) — acceptable given they're in separate containers
- Core container is a standard Python Docker image

---

### ADR-005: Docker Compose with Override Files for Modularity

**Status:** Accepted
**Decision:** Base system is defined in `docker-compose.yml`. Each interface and module provides its own `docker-compose.override.yml` fragment that adds its service(s) to the running system.

**How Docker Compose overrides work:**
```bash
# Start just the core
docker compose up

# Start core + Discord interface
docker compose -f docker-compose.yml -f interfaces/discord/docker-compose.override.yml up

# Start core + Discord + Music module
docker compose -f docker-compose.yml \
  -f interfaces/discord/docker-compose.override.yml \
  -f modules/music/docker-compose.override.yml up
```

**Why this pattern:**
- Base `docker-compose.yml` never needs to change when adding modules
- Each module is a self-contained unit — its compose fragment, its Dockerfile, its skill files
- Community members can publish and share module compose fragments independently
- No "mega compose file" that becomes hard to manage

**Consequences:**
- Startup commands get verbose with many modules — a wrapper shell script (`./sentinel.sh start --discord --music`) should wrap this for convenience
- All containers must share a Docker network (defined in the base compose file)
- Environment variables for each module live in `.env` files or separate `docker-compose.override.yml` env sections

---

### ADR-006: LiteLLM as Multi-Provider AI Abstraction

**Status:** Accepted
**Decision:** Use [LiteLLM](https://github.com/BerriAI/litellm) as the unified interface for all direct AI provider calls in Sentinel Core.

**Context:** Phase 4 added a direct AI provider path as a fallback when Pi harness is unreachable. We need to call LM Studio, Claude, Ollama, and llama.cpp without writing four separate HTTP clients.

**What LiteLLM gives us:**
- Single `acompletion()` call works across all OpenAI-compatible and native providers
- Consistent error types (`RateLimitError`, `ServiceUnavailableError`, `AuthenticationError`, etc.) regardless of backend
- Built-in timeout and retry support

**Consequences:**
- `litellm` is a large dependency — acceptable for a server-side container
- Supply chain risk: pin `>=1.83.0` (versions 1.82.7–1.82.8 were malicious, March 2026)
- Provider-specific quirks (model string format, api_base shape) are encapsulated in `LiteLLMProvider` constructor — callers use the same `complete(messages)` interface

---

## 3. Container Specifications

### 3.1 Sentinel Core Container

**Language:** Python 3.12
**Framework:** FastAPI
**Base image:** `python:3.12-slim`

**Responsibilities:**
- Receive message envelopes from interface containers (HTTP POST)
- Retrieve relevant context from Obsidian vault (search by keywords, user ID, topic)
- Build the prompt: system context + retrieved vault notes + user message
- Send prompt to Pi harness via RPC
- Receive Pi response
- Write session summary and any new notes back to Obsidian
- Return response to the calling interface

**Environment variables:**
```
# Obsidian
OBSIDIAN_API_URL=http://host.docker.internal:27123  # HTTP mode (port 27123)
OBSIDIAN_API_KEY=<from obsidian plugin settings>

# Pi harness
PI_HARNESS_URL=http://pi-harness:3000               # Docker service name + Fastify port

# Security
SENTINEL_API_KEY=<shared secret for interface auth>
LOG_LEVEL=INFO

# AI provider (Phase 4+)
AI_PROVIDER=lmstudio          # lmstudio | claude | ollama | llamacpp
AI_FALLBACK_PROVIDER=none     # claude | none

# LM Studio (primary default)
LMSTUDIO_BASE_URL=http://host.docker.internal:1234/v1
MODEL_NAME=llama-3.2-8b-instruct

# Claude / Anthropic (optional fallback)
ANTHROPIC_API_KEY=
CLAUDE_MODEL=claude-haiku-4-5

# Ollama (stub — future)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:14b

# llama.cpp (stub — future)
LLAMACPP_BASE_URL=http://localhost:8080
LLAMACPP_MODEL=local-model
```

**Exposed port:** `8000` (internal Docker network)

---

### 3.2 Pi Harness Container

**Language:** Node.js 22 LTS (minimum — do not go lower; `pi-mono` requires >=20.6.0)
**Package:** `@mariozechner/pi-coding-agent` (pinned version)
**Base image:** `node:22-slim`

**Responsibilities:**
- Accept prompts via RPC (stdin/stdout JSONL)
- Execute conversation loop against the configured AI provider (LM Studio)
- Invoke tools (read, write, edit, bash) as needed
- Invoke skills (module capabilities registered as SKILL.md files)
- Return structured response to Core

**Environment variables:**
```
LMSTUDIO_BASE_URL=http://192.168.x.x:1234/v1   # Mac Mini IP
LMSTUDIO_API_KEY=                               # Empty for local use
PI_MODEL=<model-id-as-shown-in-lmstudio>
PI_SKILLS_PATH=/app/skills                      # Mounted skills volume
```

**Pi settings.json (mounted into container):**
```json
{
  "provider": "lmstudio",
  "model": "${PI_MODEL}",
  "baseUrl": "${LMSTUDIO_BASE_URL}",
  "skillsPath": "/app/skills"
}
```

**Note on pi Docker:** Pi does not ship an official Dockerfile. We will write one based on community patterns — install pi globally via npm, mount the skills directory as a volume, run in RPC mode. The base image must be `node:24-slim` or later. Node 24 is the floor; do not use an older image even if it seems to work.

**Exposed port:** `3000` (RPC endpoint, internal network only)

---

### 3.3 Interface Container (base spec)

Each interface is its own container implementing this contract:

**Responsibilities:**
- Monitor the specific messaging channel (Discord, Messages, etc.)
- Translate incoming messages to the standard Sentinel Message Envelope
- HTTP POST the envelope to Sentinel Core at `http://sentinel-core:8000/message`
- Receive the response and post it back to the originating channel

**Required environment variables (all interfaces):**
```
SENTINEL_CORE_URL=http://sentinel-core:8000
SENTINEL_API_KEY=<shared secret>
```

**Plus interface-specific variables** (Discord bot token, etc.)

---

### 3.4 AI Provider Layer (Phase 4)

The AI Provider Layer lives entirely inside the Sentinel Core container. It is used as the **fallback path** when the Pi harness is unreachable, and can be promoted to primary by setting `AI_PROVIDER` accordingly.

#### AIProvider Protocol (`app/clients/base.py`)

All providers implement a single async method:
```python
async def complete(messages: list[dict]) -> str
```
`messages` is an OpenAI-format chat array (`[{"role": "user", "content": "..."}]`).

#### LiteLLMProvider (`app/clients/litellm_provider.py`)

Wraps `litellm.acompletion()`. Supports LM Studio, Claude, Ollama, and llama.cpp through LiteLLM's unified interface.

| Backend | `model_string` | Notes |
|---------|---------------|-------|
| LM Studio | `openai/<model_name>` | `api_base` = LM Studio `/v1` URL |
| Claude | `claude-haiku-4-5` (etc.) | `api_key` = `ANTHROPIC_API_KEY` |
| Ollama | `ollama/<model_name>` | `api_base` = `http://<host>:11434` |
| llama.cpp | `openai/<model_name>` | `api_base` = llama.cpp `/v1` URL |

Retry policy: 3 attempts, exponential backoff 1s→2s→4s on `RateLimitError`, `ServiceUnavailableError`, `ConnectError`, `TimeoutException`. Fatal errors (401, 422, 404) propagate immediately. Hard 30s per-call timeout enforces PROV-03.

> **Supply chain note:** `litellm>=1.83.0` required — versions 1.82.7–1.82.8 were malicious (March 2026).

#### OllamaProvider / LlamaCppProvider (stubs)

Both classes are present in the codebase but `complete()` raises `NotImplementedError`. Do not set `AI_PROVIDER=ollama` or `AI_PROVIDER=llamacpp` until fully implemented.

#### ProviderRouter (`app/services/provider_router.py`)

Routes `complete()` calls to primary, with optional fallback:

```
ProviderRouter.complete(messages)
  → primary.complete(messages)          ← always tried first
    on ConnectError / TimeoutException:
      → fallback.complete(messages)     ← only if fallback configured
        both fail → ProviderUnavailableError → HTTP 503
    on any other exception:
      → propagates immediately (no fallback attempt)
```

HTTP 4xx errors (auth, rate limit, bad request) are **not** fallback triggers — they indicate a configuration problem, not a connectivity failure.

#### ModelRegistry (`app/services/model_registry.py`)

Built at startup. Provides `dict[model_id, ModelInfo]` containing context window sizes used to enforce the token guard.

1. Loads `models-seed.json` (always — offline baseline)
2. Fetches live context window from active provider API (non-fatal on failure):
   - LM Studio: `GET /api/v0/models/{model_name}` → `max_context_length`
   - Claude: Anthropic SDK `models.list()` → `max_input_tokens`
   - Ollama / llama.cpp: seed only (stubs)
3. Live data takes precedence over seed for overlapping model IDs
4. Stored in `app.state.model_registry`; active model's `context_window` stored in `app.state.context_window`

---

## 4. Standard Message Envelope

This is the contract that all interface containers must speak. The Core accepts this format inbound and returns a compatible format outbound. Keeping this contract narrow is what makes the plug-in system work.

### Inbound (Interface → Core)

```json
{
  "content": "the user's message text",
  "user_id": "user-identifier-string",
  "source": "discord",
  "channel_id": "channel-or-thread-identifier"
}
```

**Fields:**
- `content` — (required) the raw text of the user's message
- `user_id` — (required, default `"default"`) stable identifier for the user within the source system; used to look up user context in Obsidian
- `source` — (optional, default `null`) identifies which interface sent this (used for routing and logging)
- `channel_id` — (optional, default `null`) where to post the reply (interface-specific meaning)

**Reserved for future interface expansion (not currently in use):** `id`, `timestamp`, `attachments`, `metadata`. These fields are not accepted by the current `MessageEnvelope` model and will be rejected by Pydantic validation if sent.

### Outbound (Core → Interface)

```json
{
  "id": "uuid-v4",
  "reply_to": "inbound-message-id",
  "source": "sentinel-core",
  "timestamp": "2026-04-06T12:00:01Z",
  "content": "the AI response text",
  "actions": [],
  "metadata": {}
}
```

**`actions` array (reserved for v0.3+):** Interface-specific actions the interface can optionally perform alongside delivering the response. Examples: `{"type": "react", "emoji": "✅"}` for Discord reactions. Interfaces that don't understand an action type should silently ignore it.

---

## 5. Core API Endpoints

The Sentinel Core exposes a minimal HTTP API. Interfaces call `/message`. Everything else is operational tooling.

| Endpoint | Method | Auth | Purpose |
|---|---|---|---|
| `/message` | POST | API key header | Receive a message envelope, return a response envelope |
| `/health` | GET | None | Container health check (used by Docker) |
| `/status` | GET | API key header | System status — Pi reachable? Obsidian reachable? LM Studio reachable? |
| `/context/{user_id}` | GET | API key header | Retrieve recent context for a user (for debugging) |

**Authentication:** All non-health endpoints require `X-Sentinel-Key: <SENTINEL_API_KEY>` header. This is a shared secret between the Core and its interfaces. Not intended as robust security — just enough to prevent accidental open access on a local network.

**`POST /message` flow:**
1. Validate envelope structure and API key (`APIKeyMiddleware`)
2. Retrieve user context from Obsidian: `/core/users/{user_id}.md` (graceful skip on failure)
3. Retrieve last 3 hot-tier session summaries from Obsidian (graceful skip on failure)
4. Build messages array: context injected as user/assistant pair + actual user message
5. Truncate injected context to 25% of model's context window budget (prevents systematic 422s)
6. Token guard — reject with HTTP 422 if total messages exceed context window
7. Forward to Pi harness via `POST /prompt` with messages array (preferred path — supports tool use)
8. If Pi is unreachable, call `ProviderRouter.complete(messages)` directly:
   - Tries primary provider (configured via `AI_PROVIDER`)
   - On `ConnectError`/`TimeoutException` only: tries fallback provider (configured via `AI_FALLBACK_PROVIDER`)
   - Both fail → HTTP 503; non-connectivity errors (auth, rate limit) propagate immediately
9. Write session note to Obsidian as background task: `ops/sessions/{YYYY-MM-DD}/{user_id}-{HH-MM-SS}.md`
10. Return response envelope to caller

---

## 6. Obsidian Vault Integration

### 6.1 Plugin Setup

Install **Obsidian Local REST API** (community plugin) in the vault:
1. Open Obsidian → Settings → Community Plugins → Browse
2. Search "Local REST API" → Install → Enable
3. Note the API key shown in the plugin settings
4. Set `OBSIDIAN_API_URL` and `OBSIDIAN_API_KEY` in Core container environment

Default port: `27124` (HTTPS). The Core connects to this from the Docker network — requires the Obsidian host (your Mac) to be network-accessible from the Docker host.

**If Docker runs on the same Mac as Obsidian:** Use `host.docker.internal:27124` as the API URL.
**If Docker runs on a separate machine (e.g., Mac Mini):** Use the Mac's LAN IP.

### 6.2 Vault Folder Structure

```
mnemosyne/                  ← vault root
├── .obsidian/              ← Obsidian config (do not write here programmatically)
├── core/
│   └── users/
│       └── {user_id}.md   ← per-user context and preferences
├── ops/
│   └── sessions/
│       └── {YYYY-MM-DD}/
│           └── {user_id}-{HH-MM-SS}.md  ← session transcript/summary
├── inbox/                  ← staging area for imported and unprocessed notes
│   └── imports/            ← bulk-imported legacy data lands here first
└── (module folders added later: /pathfinder/, /music/, etc.)
```

### 6.3 User Context File Format

Each user gets one file at `/core/users/{user_id}.md`. The Core reads this before every session and updates it after.

```markdown
---
user_id: discord_123456789
display_name: Tom
source: discord
last_seen: 2026-04-06T12:00:00Z
tags: [user, active]
---

# Tom

## Preferences
- Prefers concise responses
- Working on Pathfinder 2e campaign "The Crimson Path"

## Context
- Has a Mac Mini running LM Studio with Llama 3.2 70B
- Practices guitar, learning jazz chord voicings

## Recent Topics
- [[sessions/2026-04-06/tom-120000]] — Discussed NPC Vareth's backstory
```

### 6.4 Session Note Format

Each conversation gets its own file:

```markdown
---
date: 2026-04-06
user_id: discord_123456789
source: discord
channel_id: general
tags: [session, core]
---

# Session — 2026-04-06 12:00

## Summary
Brief AI-generated summary of what was discussed.

## Key Points
- Point 1
- Point 2

## Follow-ups
Any unresolved questions or things to remember next time.

## Raw Exchange
**User:** the full message text
**Sentinel:** the full response text
```

---

## 7. Importing Existing Obsidian Data

You have an existing Obsidian dataset to bring into Mnemosyne. The approach depends on what the data contains.

### 7.1 Direct Copy (Simplest — Recommended for MVP)

Since Obsidian vaults are plain folders of markdown files, the fastest import is:

```bash
# From the terminal on your Mac
cp -r /path/to/old-vault/* /path/to/mnemosyne/inbox/imports/
```

Obsidian will detect the new files immediately (it watches the vault folder). Your existing notes, links, and frontmatter are preserved exactly as-is.

**Why `inbox/imports/` first?** It creates a clean separation between legacy data and Sentinel-generated data. Once the Core is running, you can review and move notes to their proper module folders (or write a migration skill to do it automatically).

### 7.2 Frontmatter Normalization (If Needed)

If your existing notes have inconsistent frontmatter or need tags added, this is a good first "skill" to build for the Sentinel — a migration skill that reads files in `inbox/imports/` and adds/normalizes frontmatter before moving them to their destination folder.

The Local REST API's `PATCH /vault/{path}` with a `prepend` operation can add frontmatter to files that don't have it without touching the rest of the file.

### 7.3 Wikilink Compatibility

If your existing vault uses wikilinks (`[[note title]]`), they will work as-is in the new vault as long as the file names are preserved. No conversion needed.

### 7.4 Things to Check After Import
- Open Obsidian and verify the Graph View shows your expected note connections
- Check that images and attachments copied over (they'll be wherever your old vault stored them)
- Review the `/inbox/imports/` folder — flag any notes that don't have frontmatter and should

---

## 8. Docker Compose Structure

### 8.1 Base `docker-compose.yml` (Core only)

```yaml
version: "3.9"

networks:
  sentinel-net:
    driver: bridge

volumes:
  pi-skills:       # Mount point for module skills

services:

  sentinel-core:
    build: ./sentinel-core
    container_name: sentinel-core
    restart: unless-stopped
    networks:
      - sentinel-net
    ports:
      - "8000:8000"          # Expose to host for debugging; lock down in production
    environment:
      - OBSIDIAN_API_URL=${OBSIDIAN_API_URL}
      - OBSIDIAN_API_KEY=${OBSIDIAN_API_KEY}
      - PI_RPC_HOST=pi-harness
      - PI_RPC_PORT=3000
      - SENTINEL_API_KEY=${SENTINEL_API_KEY}
      - LOG_LEVEL=INFO
    depends_on:
      - pi-harness
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3

  pi-harness:
    build: ./pi-harness
    container_name: pi-harness
    restart: unless-stopped
    networks:
      - sentinel-net
    ports:
      - "3000:3000"          # RPC port, internal only in production
    volumes:
      - pi-skills:/app/skills
    environment:
      - LMSTUDIO_BASE_URL=${LMSTUDIO_BASE_URL}
      - LMSTUDIO_API_KEY=${LMSTUDIO_API_KEY:-}
      - PI_MODEL=${PI_MODEL}
      - NODE_VERSION=24      # Minimum — do not lower this
    healthcheck:
      test: ["CMD", "node", "-e", "process.exit(0)"]
      interval: 30s
      timeout: 5s
      retries: 3
```

### 8.2 Example Interface Override `interfaces/discord/docker-compose.override.yml`

```yaml
services:
  discord-interface:
    build: ./interfaces/discord
    container_name: sentinel-discord
    restart: unless-stopped
    networks:
      - sentinel-net
    environment:
      - SENTINEL_CORE_URL=http://sentinel-core:8000
      - SENTINEL_API_KEY=${SENTINEL_API_KEY}
      - DISCORD_BOT_TOKEN=${DISCORD_BOT_TOKEN}
      - DISCORD_ALLOWED_CHANNELS=${DISCORD_ALLOWED_CHANNELS}
    depends_on:
      - sentinel-core
```

### 8.3 Environment File `.env`

```bash
# Pi harness
LMSTUDIO_BASE_URL=http://192.168.1.x:1234/v1
LMSTUDIO_API_KEY=
PI_MODEL=llama-3.2-8b-instruct
PI_HARNESS_URL=http://pi-harness:3000

# Sentinel Core — AI provider (direct path / fallback)
AI_PROVIDER=lmstudio          # lmstudio | claude | ollama | llamacpp
AI_FALLBACK_PROVIDER=none     # claude | none
MODEL_NAME=llama-3.2-8b-instruct

# Claude (required if AI_PROVIDER=claude or AI_FALLBACK_PROVIDER=claude)
ANTHROPIC_API_KEY=
CLAUDE_MODEL=claude-haiku-4-5

# Obsidian
OBSIDIAN_API_URL=http://host.docker.internal:27123
OBSIDIAN_API_KEY=your-obsidian-api-key-here

# Security
SENTINEL_API_KEY=change-this-to-a-random-string

# Logging
LOG_LEVEL=INFO

# Discord (only needed if using discord interface)
DISCORD_BOT_TOKEN=
DISCORD_ALLOWED_CHANNELS=
```

### 8.4 Wrapper Script `sentinel.sh`

```bash
#!/bin/bash
COMPOSE_FILES="-f docker-compose.yml"

for arg in "$@"; do
  case $arg in
    --discord)  COMPOSE_FILES="$COMPOSE_FILES -f interfaces/discord/docker-compose.override.yml" ;;
    --messages) COMPOSE_FILES="$COMPOSE_FILES -f interfaces/messages/docker-compose.override.yml" ;;
    --music)    COMPOSE_FILES="$COMPOSE_FILES -f modules/music/docker-compose.override.yml" ;;
  esac
done

docker compose $COMPOSE_FILES "${@: -1}"

# Usage:
# ./sentinel.sh --discord up -d
# ./sentinel.sh --discord --music up -d
# ./sentinel.sh down
```

---

## 9. Repository Structure

```
sentinel-of-mnemosyne/
├── docker-compose.yml              ← base compose (core only)
├── .env.example                    ← template, never commit .env
├── sentinel.sh                     ← convenience wrapper script
│
├── sentinel-core/                  ← Python/FastAPI core container
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── models-seed.json            ← fallback model context-window data
│   └── app/
│       ├── main.py                 ← FastAPI app, lifespan, APIKeyMiddleware
│       ├── config.py               ← pydantic-settings Settings class
│       ├── models.py               ← MessageEnvelope / ResponseEnvelope
│       ├── clients/
│       │   ├── base.py             ← AIProvider Protocol
│       │   ├── litellm_provider.py ← LiteLLM wrapper (LM Studio, Claude)
│       │   ├── ollama_provider.py  ← Ollama stub (future)
│       │   ├── llamacpp_provider.py← llama.cpp stub (future)
│       │   ├── pi_adapter.py       ← HTTP client for Pi harness bridge
│       │   └── obsidian.py         ← Obsidian Local REST API client
│       ├── routes/
│       │   └── message.py          ← POST /message handler
│       └── services/
│           ├── provider_router.py  ← ProviderRouter + ProviderUnavailableError
│           ├── model_registry.py   ← ModelRegistry (live fetch + seed fallback)
│           └── token_guard.py      ← context-window token limit enforcement
│
├── pi-harness/                     ← Node.js 22 LTS pi container
│   ├── Dockerfile
│   ├── package.json                ← pins @mariozechner/pi-coding-agent version
│   ├── settings.json               ← pi configuration
│   └── entrypoint.sh               ← starts pi in Fastify bridge mode
│
├── interfaces/
│   └── discord/
│       ├── Dockerfile
│       ├── docker-compose.override.yml
│       ├── requirements.txt
│       └── bot.py
│
├── modules/                        ← (populated in v0.5+)
│   └── .gitkeep
│
├── skills/                         ← pi skill files shared across modules
│   └── core/
│       └── summarize-session.md
│
└── docs/
    ├── PRD-Sentinel-of-Mnemosyne.md
    ├── ARCHITECTURE-Core.md        ← this file
    └── MODULE-SPEC.md              ← module authoring guide (post-v0.4)
```

---

## 10. MVP Build Sequence (v0.1 → v0.2)

### Phase 1: v0.1 — The Spark (Core Loop)

Goal: Send a message, get an AI response. Prove the plumbing works.

**Step 1 — Stand up LM Studio on the Mac Mini**
- Install LM Studio, load a model (Llama 3.2 8B or similar for testing)
- Start the local server, confirm `curl http://[mac-mini-ip]:1234/v1/models` returns a model list

**Step 2 — Build the Pi harness container**
- Write `pi-harness/Dockerfile`: Node 20 slim, install pi globally via npm at a pinned version
- Write `pi-harness/settings.json` pointing to LM Studio
- Write `pi-harness/entrypoint.sh` to start pi in RPC mode
- Test: `docker compose up pi-harness` → pipe a test JSON prompt via stdin, confirm response

**Step 3 — Build the Sentinel Core container (minimal)**
- Write `sentinel-core/Dockerfile` and `main.py`
- Implement `POST /message` endpoint: receive envelope → forward content to pi via RPC → return response
- No Obsidian integration yet — just the routing loop
- Test: `curl -X POST http://localhost:8000/message -d '{"content": "hello"}'` → AI response

**Step 4 — Wire compose**
- Confirm `docker compose up` brings both containers up
- Confirm Core can reach Pi harness by service name (`pi-harness:3000`)

**v0.1 complete:** Full loop working via curl.

---

### Phase 2: v0.2 — The Memory (Obsidian Integration)

Goal: The system reads context from Obsidian before responding and writes session notes after.

**Step 1 — Install Obsidian Local REST API plugin**
- Install plugin, note API key, confirm `curl https://localhost:27124/vault/` returns vault listing
- Add `OBSIDIAN_API_URL` and `OBSIDIAN_API_KEY` to `.env`

**Step 2 — Import existing Obsidian data**
- Copy existing vault contents to `/inbox/imports/` in the Mnemosyne vault
- Open Obsidian, verify graph view, check links
- Create initial folder structure: `/core/users/`, `ops/sessions/`

**Step 3 — Add Obsidian client to Core**
- Write `obsidian_client.py` wrapping the REST API
- Implement context retrieval: given a user ID and message content, return relevant vault excerpts
- Implement session write: after each response, write session note to `ops/sessions/{date}/`

**Step 4 — Update `/message` handler to use context**
- Pull user context before building Pi prompt
- Append relevant vault excerpts to system prompt
- Write session note after response

**Step 5 — Create first user context file manually**
- Write `/core/users/{your_user_id}.md` with your preferences and context
- Verify the Core reads it and includes it in the Pi prompt

**v0.2 complete:** Ask a question, get a contextually aware answer. Ask again in a new session — prior session is referenced.

---

## 11. Open Questions (Core Scope)

| # | Question | Notes | Target |
|---|---|---|---|
| 1 | Exact RPC protocol for pi in RPC mode | Need to confirm stdin/stdout JSONL format by reading pi source | Before v0.1 |
| 2 | Pi version to pin | Choose a stable release of `@mariozechner/pi-coding-agent` | Before v0.1 |
| 3 | Docker host for Obsidian API | `host.docker.internal` works on Mac Docker Desktop; may differ on Linux Docker | v0.2 |
| 4 | Context retrieval strategy | Start with: search by user ID + keyword. Upgrade to vector search if needed (v0.4+) | v0.2 |
| 5 | Session note retention | How many sessions to keep before archiving? Start with "keep all", revisit when vault gets large | v0.2 |
| 6 | Pi skills directory mounting | Skills volume shared between Core and Pi container — confirm Docker volume mount approach | v0.1 |
| 7 | LM Studio model for development | Pick a model that fits Mac Mini RAM; 8B for testing, step up for production use | v0.1 |

---

## 12. Reference: Key API Formats

### LM Studio — Chat Completion Request
```bash
curl http://[mac-mini-ip]:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-3.2-8b-instruct",
    "messages": [
      {"role": "system", "content": "You are the Sentinel of Mnemosyne."},
      {"role": "user", "content": "Hello, what do you remember about my last session?"}
    ],
    "temperature": 0.7,
    "stream": false
  }'
```

### Obsidian Local REST API — Write a Note
```bash
curl -X PUT https://localhost:27124/vault/ops/sessions/2026-04-06/test.md \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: text/markdown" \
  --insecure \
  -d '---
date: 2026-04-06
tags: [session, test]
---

# Test Session
This is a test note written by the Sentinel Core.'
```

### Obsidian Local REST API — Search the Vault
```bash
curl "https://localhost:27124/search/simple/?query=pathfinder+NPC&contextLength=200" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  --insecure
```

---

*This document covers the core architecture only. Module architecture (Pathfinder, Music, Coder) will be documented separately once the core is stable and the module API contract is finalized. Update the Open Questions table as decisions are made.*
