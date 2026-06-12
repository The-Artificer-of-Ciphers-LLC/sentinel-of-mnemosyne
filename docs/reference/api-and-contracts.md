# Sentinel of Mnemosyne — API and Contracts Reference

**Type:** Reference (Diataxis)
**Version:** 0.50
**Date:** 2026-05-06
**Scope:** Core system (Path B) — container specifications, module API contract, message envelopes, core endpoints, vault integration, Docker Compose structure, repository layout, key API formats.

For design rationale and ADRs, see [`../explanation/architecture.md`](../explanation/architecture.md).
For the full vault folder and file-format specification, see [`../reference/obsidian-vault.md`](../reference/obsidian-vault.md).

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

### 3.3 Interface Container (base spec)

Each interface is its own container implementing this contract.

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

### 3.4 Module Containers (v0.50+)

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

This is the contract all interface containers must implement.

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

For plugin setup, see the [Installation Guide](../how-to/install.md).

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
└── (module folders added in v0.50+: /pathfinder/, /music/, etc.)
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
    --pf2e)       PROFILES+=("pf2e") ;;
    --music)      PROFILES+=("music") ;;
    --finance)    PROFILES+=("finance") ;;
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
# ./sentinel.sh --discord --pf2e up -d
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
├── interfaces/
│   └── discord/
│       ├── Dockerfile
│       ├── docker-compose.override.yml
│       ├── requirements.txt
│       └── bot.py
│
├── modules/                        ← (populated in v0.50+)
│   └── .gitkeep
│
└── docs/
    ├── PRD-Sentinel-of-Mnemosyne.md
    ├── explanation/architecture.md ← architecture reference
    └── MODULE-SPEC.md              ← module authoring guide (post-v0.4)
```

---

## 12. Key API Formats

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
