# Sentinel of Mnemosyne — Architecture Explanation

**Type:** Explanation (Diataxis)
**Version:** 0.50
**Date:** 2026-05-06
**Scope:** Core system (Path B) — Interface layer, Sentinel Core container, AI provider layer, Module API gateway, Obsidian vault.

For the full API specification, env vars, ports, schemas, and file formats, see [`../reference/api-and-contracts.md`](../reference/api-and-contracts.md).
For the full vault folder and file-format specification, see [`../reference/obsidian-vault.md`](../reference/obsidian-vault.md).

---

## 1. System Overview

The Sentinel of Mnemosyne is a self-hosted, containerised AI assistant platform. Path B is the canonical runtime: sentinel-core calls LiteLLM directly for chat, and acts as the API gateway for all module containers.

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
│  LiteLLMProvider │  │  (v0.50: Pathfinder, │
│  → LM Studio     │  │  Music, Finance, etc)│
│  → Claude API    │  │  Each: FastAPI        │
└──────────────────┘  │  POST /register →    │
                      │  sentinel-core       │
                      └──────────────────────┘

              ┌──────────────────────────┐
              │  OBSIDIAN VAULT (host)   │
              │  REST API plugin         │
              └──────────────────────────┘
```

**v0.51.1 release snapshot:**
- Core route seam uses `RouteContext` (`app.state.route_ctx`) with strict access.
- Startup wiring/policy centralised in `initialize_startup()`.
- Runtime probe, health formatting, message request mapping, module gateway/registry, and sweep orchestration are extracted as deep modules behind thin route adapters.
- Pathfinder module integration is operational via module registry + proxy.

**Chat path:** `POST /message → APIKeyMiddleware → InjectionFilter → LiteLLMProvider → OutputScanner → response`

**Module proxy path:** `POST /modules/{name}/{path} → APIKeyMiddleware → Module Registry lookup → httpx proxy → module container → response`

**The AI layer:** LiteLLMProvider — calls LiteLLM → configured AI provider (LM Studio, Claude API, Ollama, LlamaCpp). No intermediate layer.
**The memory:** Obsidian vault (Mnemosyne) — persists all knowledge as human-readable markdown.
**The gateway:** Sentinel Core — routes messages, proxies module requests, orchestrates Obsidian writes.

---

## 2. Technology Decisions

### ADR-001: LiteLLM-Direct for Chat; Module API Gateway for Extensibility

**Status:** Accepted (2026-04-20)
**Decision:** Use LiteLLM-direct for all chat completions. Implement a module API gateway in sentinel-core.

**Context:** Phase 25 shipped LiteLLM-direct as the working chat path. Phase 27 formalises this as the canonical architecture (Path B). The original design (Path A) described Pi harness as the primary AI execution layer, but Pi was never in the critical message path in the deployed system. Pi harness has been fully removed as of v0.50.2.

**What Path B gives us:**
- Single, direct, auditable chat path: sentinel-core → LiteLLM → AI provider
- Module containers are independently deployable FastAPI apps that register with sentinel-core at startup
- sentinel-core proxies module requests — callers need only know sentinel-core's address

**Rationale:**
- Simpler message path — fewer hops, easier to reason about
- Module containers are independently testable and deployable; sentinel-core is the stable hub
- Path B was already the operational reality as of Phase 25

**Consequences:**
- sentinel-core is the single process that must be running for chat and module routing to work
- Module containers must implement `POST /register` and call it at startup

---

### ADR-002: Obsidian Local REST API for Vault Writes

**Status:** Accepted
**Decision:** Use the [obsidian-local-rest-api](https://github.com/coddingtonbear/obsidian-local-rest-api) community plugin for all programmatic reads and writes to the vault.

**Context:** Obsidian is a local file-based system. External programmes can write `.md` files directly to the vault folder and Obsidian will detect them. However, direct file writes have race conditions and don't integrate with Obsidian's indexing. The Local REST API plugin provides a proper HTTPS API with authentication.

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
./sentinel.sh --discord --pf2e up -d
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
- For the supply-chain pinning requirement, see the LiteLLMProvider section in [`../reference/api-and-contracts.md`](../reference/api-and-contracts.md).

---

## 10. Build Sequence History (v0.1 → v0.50)

### Phases 1–4: Core Loop, Memory, Voice, AI Layer

The foundation was built incrementally across the first four phases. Phase 1 established the sentinel-core FastAPI container and the LiteLLM-direct chat path. Phase 2 introduced Obsidian integration, encoding the design principle that the vault — not a relational database — is the system of record for all persistent knowledge. Phase 3 added the Discord interface container, validating the multi-interface model in which each channel adapter is an independent, replaceable container that speaks the standard message envelope. Phase 4 hardened the AI layer with the token guard, model registry, and ProviderRouter fallback logic. By the end of Phase 4, the core loop was complete and proven in production.

### Phase 11: First Path B Module (v0.50 — Pathfinder 2e)

Phase 11 delivered the first module under the Path B contract. The Pathfinder module container was scaffolded as a standalone FastAPI service exposing NPC management, session capture, and dialogue generation endpoints. The module registered itself with sentinel-core at container startup by calling `POST /modules/register`, which populated the in-memory `ModuleRegistry` with the module's name, reachable URL, and declared routes. A compose fragment (`modules/pathfinder/docker-compose.yml`) was added for the module, and the `sentinel.sh` wrapper was extended with a `--pf2e` flag that maps to the Docker Compose profile `pf2e`. The distinction between the Docker profile name (`pf2e`) and the module registry name (`pathfinder`) was deliberate: profile names are short compose identifiers; registry names are the logical keys used by the proxy router. Proxy correctness was verified by confirming that `POST /modules/pathfinder/npcs` reached the pathfinder container transparently. The phase concluded with `./sentinel.sh --discord --pf2e up -d` bringing up the full stack.

---

## 11. Design Decisions Still Open

| # | Question | Notes | Target |
|---|---|---|---|
| 1 | Module registry persistence | In-memory registry clears on sentinel-core restart; modules re-register on their restart. Is restart ordering reliable enough, or do we need a persistent registry? | v0.50 |
| 2 | Module health checking | Should sentinel-core probe registered modules periodically? Or return 503 on-demand only? | v0.50 |
| 3 | Module API versioning | Should module routes include a version prefix (`/v1/npcs`)? Start without, add if needed. | v0.50 |
| 4 | Pi harness integration depth | v0.7 scope: Pi as a parallel coding environment. Does it share the Obsidian vault context with sentinel-core, or maintain its own? | v0.7 |

---

## Module: Pathfinder Chat Projection

### Concept

When the Foundry VTT module exports a chat log, the Pathfinder module's import endpoint processes each chat record and projects it into the Obsidian vault. The projection writes into two target namespaces: per-player chat-maps (capturing voice patterns, notable moments, party dynamics, and a chronological timeline) and per-NPC notes (appending a row to each NPC's Foundry Chat History section). This makes session dialogue a first-class memory artifact: the next conversation can recover not just what was discussed in abstract but who said what, in what tone, and to whom.

### Idempotency

Idempotency is per-record per-target. Re-running a live import against the same inbox produces zero new vault writes. This guarantee matters because chat exports from Foundry are cumulative — a second export of the same campaign will contain all records from the first export plus any new ones. Without per-record tracking, every re-run would duplicate existing notes. The design therefore tracks each projected record individually rather than by import batch: a record is either in the dedupe set or it is not, regardless of how many times the import endpoint has been called.

### State File

The dedupe state is stored in-place at `<inbox_dir>/.foundry_chat_import_state.json`. This file contains three arrays: `imported_keys` (chat records that have been parsed and classified), `player_projection_keys` (records that have been projected into a player chat-map), and `npc_projection_keys` (records that have been projected into an NPC note). Storing the state file alongside the inbox rather than in the vault or in a database was a deliberate choice: it keeps the import artefacts co-located with their source data, survives vault restructuring without path changes, and remains human-readable and easily inspectable or reset.
