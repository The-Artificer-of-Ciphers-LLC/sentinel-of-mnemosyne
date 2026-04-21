# Sentinel of Mnemosyne — Core Architecture
**Version:** 0.2
**Date:** 2026-04-20
**Scope:** Core system (Path B) — Interface layer, Sentinel Core container, AI provider layer, Module API gateway, Obsidian vault. Pi harness is optional (v0.7 scope, `--pi` flag only).

---

## 1. System Overview

The Sentinel of Mnemosyne is a self-hosted, containerized AI assistant platform. Path B is the canonical runtime: sentinel-core calls LiteLLM directly for chat, and acts as the API gateway for all module containers.

```
┌─────────────────────────────────────────────────┐
│            INTERFACE LAYER                      │
│   (Discord /sen, Messages — one container each) │
└────────────────────┬────────────────────────────┘
                     │  HTTP POST /message
                     │  X-Sentinel-Key header
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                 SENTINEL CORE CONTAINER                         │
│   FastAPI router · APIKeyMiddleware                             │
│   ModelRegistry · ProviderRouter · Module Registry              │
│   POST /message (chat) · POST /modules/register                 │
│   POST /modules/{name}/{path} (proxy)                           │
└──────────┬─────────────────┬───────────────────────────────────┘
           │                 │
           │ LiteLLM         │ httpx proxy (registered modules)
           ▼                 ▼
┌──────────────────┐  ┌──────────────────────┐
│  AI PROVIDER     │  │  MODULE CONTAINERS   │
│  LiteLLMProvider │  │  (v0.5+: Pathfinder, │
│  → LM Studio     │  │  Music, Finance, etc)│
│  → Claude API    │  │  Each: FastAPI        │
└──────────────────┘  │  POST /register →    │
                      │  sentinel-core       │
                      └──────────────────────┘

              ┌──────────────────────────┐
              │  OBSIDIAN VAULT (host)   │
              │  REST API plugin         │
              └──────────────────────────┘

[ Pi Harness ] — optional, only with sentinel.sh --pi flag, v0.7 scope
```

**Chat path:** `POST /message → APIKeyMiddleware → InjectionFilter → LiteLLMProvider → OutputScanner → response`

**Module proxy path:** `POST /modules/{name}/{path} → APIKeyMiddleware → Module Registry lookup → httpx proxy → module container → response`

**The AI layer:** LiteLLMProvider — calls LiteLLM → configured AI provider (LM Studio, Claude API, Ollama, LlamaCpp). No intermediate layer.
**The memory:** Obsidian vault (Mnemosyne) — persists all knowledge as human-readable markdown.
**The gateway:** Sentinel Core — routes messages, proxies module requests, orchestrates Obsidian writes.

---

## 2. Technology Decisions

### ADR-001: LiteLLM-Direct for Chat; Module API Gateway for Extensibility

**Status:** Accepted (2026-04-20)
**Decision:** Use LiteLLM-direct for all chat completions. Implement a module API gateway in sentinel-core. Demote Pi harness to an optional advanced tool scoped to v0.7.

**Context:** Phase 25 shipped LiteLLM-direct as the working chat path. Phase 27 formalizes this as the canonical architecture (Path B). The original design (Path A) described Pi harness as the primary AI execution layer, but Pi was never in the critical message path in the deployed system. Continuing to maintain Path A documentation creates confusion for AI agents reading these docs as source of truth.

**What Path B gives us:**
- Single, direct, auditable chat path: sentinel-core → LiteLLM → AI provider
- Module containers are independently deployable FastAPI apps that register with sentinel-core at startup
- sentinel-core proxies module requests — callers need only know sentinel-core's address
- No dependency on Pi harness for core chat functionality
- Pi harness remains available as an advanced coding tool via `./sentinel.sh --pi` (v0.7 scope)

**Rationale:**
- Simpler message path — fewer hops, easier to reason about
- Module containers are independently testable and deployable; sentinel-core is the stable hub
- Pi harness is a powerful but heavy dependency for core chat; LiteLLM-direct is lighter and already working
- Path B was already the operational reality as of Phase 25

**Consequences:**
- sentinel-core is the single process that must be running for chat and module routing to work
- Module containers must implement `POST /register` and call it at startup
- Pi harness is not started unless `--pi` flag is passed to `sentinel.sh`

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

**Consequences:**
- Obsidian must be running on the Mac for the REST API to be available
- API key must be configured on first setup

---

### ADR-003: LM Studio as Primary AI Provider

**Status:** Accepted
**Decision:** Target LM Studio running on the Mac Mini as the primary AI backend. Use its OpenAI-compatible API endpoint via LiteLLM.

**LM Studio technical details:**
- Runs at `http://[mac-mini-ip]:1234` by default (configurable)
- Exposes OpenAI-compatible API at `/v1/` — same request format as OpenAI's API
- Endpoints: `GET /v1/models`, `POST /v1/chat/completions`

**LiteLLM configuration for LM Studio:**
```python
# model_string: "openai/<model_name>"
# api_base: LMSTUDIO_BASE_URL
```

**Provider swap path:** Because LiteLLM abstracts provider differences, switching to Claude, Ollama, or llama.cpp requires only changing environment variables. No code changes.

**Consequences:**
- Mac Mini must be on the same local network as the Docker host
- LM Studio must have a model loaded before the Sentinel can respond

---

### ADR-004: FastAPI (Python) for Sentinel Core

**Status:** Accepted
**Decision:** Implement the Sentinel Core container in Python using [FastAPI](https://fastapi.tiangolo.com/).

**Why Python + FastAPI:**
- Async-native — handles concurrent interface calls and module proxy requests cleanly
- FastAPI produces automatic API documentation (`/docs`)
- Pydantic v2 integration for request/response validation
- Python is the standard AI/automation ecosystem language

**Consequences:**
- Single Python container serves chat, module registry, and module proxy
- Standard Python 3.12 Docker image (`python:3.12-slim`)

---

### ADR-005: Docker Compose with `include` Directive for Modularity

**Status:** Accepted
**Decision:** Base system in `docker-compose.yml`. Each interface and module provides its own compose fragment included via the `include` directive (Compose v2.20+).

**How it works:**
```bash
# Start just the core
docker compose up

# Start core + Discord interface + Pathfinder module
./sentinel.sh --discord --pathfinder up -d
```

`sentinel.sh` builds the compose invocation from flags. The `include` directive resolves paths relative to each included file's directory — no `-f` flag stacking.

**Consequences:**
- Adding a module never touches `docker-compose.yml`
- Each module compose fragment is self-contained

---

### ADR-006: LiteLLM as Multi-Provider AI Abstraction

**Status:** Accepted
**Decision:** Use [LiteLLM](https://github.com/BerriAI/litellm) as the unified interface for all AI provider calls in Sentinel Core.

**What LiteLLM gives us:**
- Single `acompletion()` call works across LM Studio, Claude, Ollama, llama.cpp
- Consistent error types regardless of backend
- Built-in timeout and retry support

**Consequences:**
- `litellm` is a large dependency — acceptable for a server-side container
- **Supply chain note:** Pin `>=1.83.0` — versions 1.82.7–1.82.8 were malicious (March 2026)

---

## 3. Container Specifications

### 3.1 Sentinel Core Container

**Language:** Python 3.12
**Framework:** FastAPI
**Base image:** `python:3.12-slim`

**Responsibilities:**
- Receive message envelopes from interface containers (`POST /message`)
- Retrieve relevant context from Obsidian vault
- Build prompt: system context + retrieved vault notes + user message
- Call LiteLLMProvider directly for chat completions
- Write session summary to Obsidian as a background task
- Maintain module registry: accept `POST /modules/register` at startup from module containers
- Proxy module requests: `POST /modules/{name}/{path}` → module container via httpx
- Return response to calling interface

**Environment variables:**
```
# Obsidian
OBSIDIAN_API_URL=http://host.docker.internal:27123
OBSIDIAN_API_KEY=<from obsidian plugin settings>

# Security
SENTINEL_API_KEY=<shared secret for interface auth>
LOG_LEVEL=INFO

# AI provider
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

### 3.2 Pi Harness Container (Optional — v0.7 scope)

**Status:** Optional. Not started unless `./sentinel.sh --pi` flag is passed.
**Language:** Node.js 22 LTS
**Package:** `@mariozechner/pi-coding-agent` (pinned version)
**Base image:** `node:22-slim`

The Pi harness is an advanced coding tool for interactive code-generation tasks. It is **not** in the standard chat message path. When activated, it runs as a parallel environment alongside sentinel-core.

**Environment variables:**
```
LMSTUDIO_BASE_URL=http://192.168.x.x:1234/v1
LMSTUDIO_API_KEY=
PI_MODEL=<model-id-as-shown-in-lmstudio>
PI_SKILLS_PATH=/app/skills
```

**Exposed port:** `3000` (RPC endpoint, internal network only — Fastify bridge)

---

### 3.3 Interface Container (base spec)

Each interface is its own container implementing this contract:

**Responsibilities:**
- Monitor the specific messaging channel (Discord, Messages, etc.)
- Translate incoming messages to the standard Sentinel Message Envelope
- HTTP POST the envelope to Sentinel Core at `http://sentinel-core:8000/message`
- Receive the response and post it back to the originating channel

**Required environment variables:**
```
SENTINEL_CORE_URL=http://sentinel-core:8000
SENTINEL_API_KEY=<shared secret>
```

---

### 3.4 Module Containers (v0.5+)

Each module (Pathfinder, Music, Finance, etc.) is a self-contained FastAPI container.

**Responsibilities:**
- Call `POST /modules/register` on sentinel-core at container startup
- Expose the endpoints declared in its registration payload
- Respond to proxied requests from sentinel-core

**Environment variables (all modules):**
```
SENTINEL_CORE_URL=http://sentinel-core:8000
SENTINEL_API_KEY=<shared secret>
MODULE_NAME=<module-name>
MODULE_BASE_URL=http://<module-service-name>:<port>
```

---

### 3.5 AI Provider Layer

The AI Provider Layer lives entirely inside the Sentinel Core container. LiteLLM-direct is the primary and default path.

#### AIProvider Protocol (`app/clients/base.py`)

All providers implement:
```python
async def complete(messages: list[dict]) -> str
```
`messages` is an OpenAI-format chat array (`[{"role": "user", "content": "..."}]`).

#### LiteLLMProvider (`app/clients/litellm_provider.py`)

Wraps `litellm.acompletion()`. Supports LM Studio, Claude, Ollama, and llama.cpp.

| Backend | `model_string` | Notes |
|---------|---------------|-------|
| LM Studio | `openai/<model_name>` | `api_base` = LM Studio `/v1` URL |
| Claude | `claude-haiku-4-5` (etc.) | `api_key` = `ANTHROPIC_API_KEY` |
| Ollama | `ollama/<model_name>` | `api_base` = `http://<host>:11434` |
| llama.cpp | `openai/<model_name>` | `api_base` = llama.cpp `/v1` URL |

Retry policy: 3 attempts, exponential backoff 1s→2s→4s on `RateLimitError`, `ServiceUnavailableError`, `ConnectError`, `TimeoutException`. Fatal errors (401, 422, 404) propagate immediately. Hard 30s per-call timeout.

> **Supply chain note:** `litellm>=1.83.0` required — versions 1.82.7–1.82.8 were malicious (March 2026).

#### ProviderRouter (`app/services/provider_router.py`)

```
ProviderRouter.complete(messages)
  → primary.complete(messages)
    on ConnectError / TimeoutException:
      → fallback.complete(messages)     ← only if fallback configured
        both fail → ProviderUnavailableError → HTTP 503
    on any other exception:
      → propagates immediately (no fallback attempt)
```

#### ModelRegistry (`app/services/model_registry.py`)

Built at startup. Provides `dict[model_id, ModelInfo]` containing context window sizes used to enforce the token guard.

1. Loads `models-seed.json` (always — offline baseline)
2. Fetches live context window from active provider API (non-fatal on failure)
3. Live data takes precedence over seed for overlapping model IDs
4. Stored in `app.state.model_registry`

---

## 4. Module API Contract

Every module container must implement this contract to integrate with sentinel-core.

### Registration (module → sentinel-core at startup)

```
POST /modules/register
  Payload: {
    "name": str,           # unique module identifier (e.g. "pathfinder")
    "base_url": str,       # module's reachable URL (e.g. "http://pathfinder:8001")
    "routes": [
      { "path": str, "description": str }
    ]
  }
  Response: { "status": "registered" }
  Call: module container calls this at startup
```

### Module Proxy (interface/client → sentinel-core → module)

```
POST /modules/{name}/{path}
  sentinel-core receives, looks up module.base_url from registry,
  proxies request body via httpx to module.base_url/{path}

  Returns 503 { "error": "module unavailable" } if module is unreachable
  Returns 404 if module is not registered
```

**Module startup pattern:**
```python
# In module's FastAPI lifespan
async with httpx.AsyncClient() as client:
    await client.post(
        f"{SENTINEL_CORE_URL}/modules/register",
        json={
            "name": MODULE_NAME,
            "base_url": MODULE_BASE_URL,
            "routes": [
                {"path": "/npcs", "description": "NPC management"},
                {"path": "/sessions", "description": "Session notes"},
            ]
        },
        headers={"X-Sentinel-Key": SENTINEL_API_KEY},
    )
```

---

## 5. Standard Message Envelope

This is the contract all interface containers must speak.

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
- `user_id` — (required, default `"default"`) stable identifier for the user
- `source` — (optional, default `null`) identifies which interface sent this
- `channel_id` — (optional, default `null`) where to post the reply

### Outbound (Core → Interface)

```json
{
  "id": "uuid-v4",
  "reply_to": "inbound-message-id",
  "source": "sentinel-core",
  "timestamp": "2026-04-20T12:00:01Z",
  "content": "the AI response text",
  "actions": [],
  "metadata": {}
}
```

---

## 6. Core API Endpoints

| Endpoint | Method | Auth | Purpose |
|---|---|---|---|
| `/message` | POST | API key header | Receive a message envelope, return a response envelope |
| `/health` | GET | None | Container health check |
| `/status` | GET | API key header | System status — Obsidian reachable? LM Studio reachable? |
| `/context/{user_id}` | GET | API key header | Retrieve recent context for a user (debugging) |
| `/modules/register` | POST | API key header | Module self-registration at startup |
| `/modules/{name}/{path}` | POST | API key header | Proxy request to registered module |

**`POST /message` flow:**
1. Validate envelope structure and API key (`APIKeyMiddleware`)
2. Retrieve user context from Obsidian: `/core/users/{user_id}.md` (graceful skip on failure)
3. Retrieve last 3 hot-tier session summaries from Obsidian (graceful skip on failure)
4. Build messages array: context injected as user/assistant pair + actual user message
5. Truncate injected context to 25% of model's context window budget (prevents systematic 422s)
6. Token guard — reject with HTTP 422 if total messages exceed context window
7. Call `ProviderRouter.complete(messages)` via LiteLLM-direct:
   - Tries primary provider (configured via `AI_PROVIDER`)
   - On `ConnectError`/`TimeoutException` only: tries fallback (`AI_FALLBACK_PROVIDER`)
   - Both fail → HTTP 503
8. Write session note to Obsidian as background task: `ops/sessions/{YYYY-MM-DD}/{user_id}-{HH-MM-SS}.md`
9. Return response envelope to caller

---

## 7. Obsidian Vault Integration

### 7.1 Plugin Setup

Install **Obsidian Local REST API** (community plugin):
1. Open Obsidian → Settings → Community Plugins → Browse
2. Search "Local REST API" → Install → Enable
3. Note the API key shown in the plugin settings
4. Set `OBSIDIAN_API_URL` and `OBSIDIAN_API_KEY` in Core container environment

Default port: `27124` (HTTPS). If Docker runs on the same Mac as Obsidian, use `host.docker.internal:27124`.

### 7.2 Vault Folder Structure

```
mnemosyne/
├── .obsidian/
├── core/
│   └── users/
│       └── {user_id}.md
├── ops/
│   └── sessions/
│       └── {YYYY-MM-DD}/
│           └── {user_id}-{HH-MM-SS}.md
├── inbox/
│   └── imports/
└── (module folders added in v0.5+: /pathfinder/, /music/, etc.)
```

### 7.3 User Context File Format

```markdown
---
user_id: discord_123456789
display_name: Tom
source: discord
last_seen: 2026-04-20T12:00:00Z
tags: [user, active]
---

# Tom

## Preferences
- Prefers concise responses

## Context
- Has a Mac Mini running LM Studio with Llama 3.2 70B

## Recent Topics
- [[sessions/2026-04-06/tom-120000]] — Discussed NPC Vareth's backstory
```

### 7.4 Session Note Format

```markdown
---
date: 2026-04-20
user_id: discord_123456789
source: discord
channel_id: general
tags: [session, core]
---

# Session — 2026-04-20 12:00

## Summary
Brief AI-generated summary of what was discussed.

## Key Points
- Point 1

## Follow-ups
Any unresolved questions or things to remember next time.

## Raw Exchange
**User:** the full message text
**Sentinel:** the full response text
```

---

## 8. Docker Compose Structure

### 8.1 Base `docker-compose.yml` (Core only)

```yaml
networks:
  sentinel-net:
    driver: bridge

services:
  sentinel-core:
    build: ./sentinel-core
    container_name: sentinel-core
    restart: unless-stopped
    networks:
      - sentinel-net
    ports:
      - "8000:8000"
    environment:
      - OBSIDIAN_API_URL=${OBSIDIAN_API_URL}
      - OBSIDIAN_API_KEY=${OBSIDIAN_API_KEY}
      - SENTINEL_API_KEY=${SENTINEL_API_KEY}
      - AI_PROVIDER=${AI_PROVIDER:-lmstudio}
      - LMSTUDIO_BASE_URL=${LMSTUDIO_BASE_URL}
      - MODEL_NAME=${MODEL_NAME}
      - LOG_LEVEL=INFO
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
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

### 8.3 Example Module `modules/pathfinder/docker-compose.yml`

```yaml
services:
  pathfinder:
    build: ./modules/pathfinder
    container_name: sentinel-pathfinder
    restart: unless-stopped
    networks:
      - sentinel-net
    environment:
      - SENTINEL_CORE_URL=http://sentinel-core:8000
      - SENTINEL_API_KEY=${SENTINEL_API_KEY}
      - MODULE_NAME=pathfinder
      - MODULE_BASE_URL=http://pathfinder:8001
    depends_on:
      - sentinel-core
```

### 8.4 Environment File `.env`

```bash
# Sentinel Core — AI provider
AI_PROVIDER=lmstudio          # lmstudio | claude | ollama | llamacpp
AI_FALLBACK_PROVIDER=none
MODEL_NAME=llama-3.2-8b-instruct
LMSTUDIO_BASE_URL=http://host.docker.internal:1234/v1

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

### 8.5 Wrapper Script `sentinel.sh`

```bash
#!/bin/bash
# Uses Docker Compose profiles + include directive (NOT -f stacking).
# Profiles are declared in each service's compose.yml via `profiles: [name]`.
PROFILES=()
ARGS=()

for arg in "$@"; do
  case "$arg" in
    --discord)    PROFILES+=("discord") ;;
    --pathfinder) PROFILES+=("pathfinder") ;;
    --music)      PROFILES+=("music") ;;
    --finance)    PROFILES+=("finance") ;;
    --pi)         PROFILES+=("pi") ;;
    *)            ARGS+=("$arg") ;;
  esac
done

PROFILE_FLAGS=()
for p in "${PROFILES[@]}"; do
  PROFILE_FLAGS+=("--profile" "$p")
done

docker compose "${PROFILE_FLAGS[@]}" "${ARGS[@]}"

# Usage:
# ./sentinel.sh --discord up -d
# ./sentinel.sh --discord --pathfinder up -d
# ./sentinel.sh --pi up -d          # activate Pi harness (v0.7 scope)
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
│   ├── models-seed.json
│   └── app/
│       ├── main.py                 ← FastAPI app, lifespan, APIKeyMiddleware
│       ├── config.py               ← pydantic-settings Settings class
│       ├── models.py               ← MessageEnvelope / ResponseEnvelope
│       ├── clients/
│       │   ├── base.py             ← AIProvider Protocol
│       │   ├── litellm_provider.py ← LiteLLM wrapper (LM Studio, Claude)
│       │   ├── ollama_provider.py  ← Ollama stub (future)
│       │   ├── llamacpp_provider.py← llama.cpp stub (future)
│       │   └── obsidian.py         ← Obsidian Local REST API client
│       ├── routes/
│       │   ├── message.py          ← POST /message handler
│       │   └── modules.py          ← POST /modules/register, POST /modules/{name}/{path}
│       └── services/
│           ├── provider_router.py  ← ProviderRouter + ProviderUnavailableError
│           ├── model_registry.py   ← ModelRegistry (live fetch + seed fallback)
│           ├── module_registry.py  ← ModuleRegistry (in-memory, populated at runtime)
│           └── token_guard.py      ← context-window token limit enforcement
│
├── pi-harness/                     ← optional Node.js 22 LTS pi container (v0.7)
│   ├── Dockerfile
│   ├── docker-compose.yml          ← included only with --pi flag
│   ├── package.json
│   ├── settings.json
│   └── entrypoint.sh
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
└── docs/
    ├── PRD-Sentinel-of-Mnemosyne.md
    ├── ARCHITECTURE-Core.md        ← this file
    └── MODULE-SPEC.md              ← module authoring guide (post-v0.4)
```

---

## 10. Build Sequence (v0.1 → v0.5)

### Phase 1–4: Core Loop, Memory, Voice, AI Layer (Complete)

The foundation is built: sentinel-core FastAPI container, LiteLLM-direct chat, Obsidian integration, Discord interface, token guard, model registry. See phase summaries in `.planning/phases/`.

### Phase 11: First Path B Module (v0.5 — Pathfinder 2e)

Goal: Deliver a module under the Path B contract.

**Step 1 — Scaffold module container**
- Create `modules/pathfinder/` with Dockerfile, `requirements.txt`, FastAPI app
- Implement `POST /npcs`, `POST /sessions/capture`, `POST /dialogue/generate`

**Step 2 — Registration at startup**
- Module calls `POST /modules/register` on sentinel-core with `name`, `base_url`, `routes`
- sentinel-core stores registration in `ModuleRegistry`

**Step 3 — Compose integration**
- Add `modules/pathfinder/docker-compose.yml`
- Add `--pathfinder` case to `sentinel.sh`

**Step 4 — Verify proxy**
- `POST /modules/pathfinder/npcs` via sentinel-core → proxied to pathfinder container

**Phase complete:** `./sentinel.sh --discord --pathfinder up -d` starts the full stack.

---

## 11. Open Questions (Path B Scope)

| # | Question | Notes | Target |
|---|---|---|---|
| 1 | Module registry persistence | In-memory registry clears on sentinel-core restart; modules re-register on their restart. Is restart ordering reliable enough, or do we need a persistent registry? | v0.5 |
| 2 | Module health checking | Should sentinel-core probe registered modules periodically? Or return 503 on-demand only? | v0.5 |
| 3 | Module API versioning | Should module routes include a version prefix (`/v1/npcs`)? Start without, add if needed. | v0.5 |
| 4 | Pi harness integration depth | v0.7 scope: Pi as a parallel coding environment. Does it share the Obsidian vault context with sentinel-core, or maintain its own? | v0.7 |

---

## 12. Reference: Key API Formats

### Chat Completion Request (LiteLLM → LM Studio)
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

### Module Registration
```bash
curl -X POST http://sentinel-core:8000/modules/register \
  -H "X-Sentinel-Key: ${SENTINEL_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "pathfinder",
    "base_url": "http://pathfinder:8001",
    "routes": [
      {"path": "/npcs", "description": "NPC management"},
      {"path": "/sessions/capture", "description": "Session note capture"},
      {"path": "/dialogue/generate", "description": "In-character dialogue generation"}
    ]
  }'
```

### Obsidian Local REST API — Write a Note
```bash
curl -X PUT https://localhost:27124/vault/ops/sessions/2026-04-20/test.md \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: text/markdown" \
  --insecure \
  -d '---
date: 2026-04-20
tags: [session, test]
---

# Test Session
This is a test note written by the Sentinel Core.'
```

---

*This document describes the Path B canonical architecture. Module-specific architecture (Pathfinder, Music, Finance) is documented separately in MODULE-SPEC.md once the first module ships in Phase 11.*
