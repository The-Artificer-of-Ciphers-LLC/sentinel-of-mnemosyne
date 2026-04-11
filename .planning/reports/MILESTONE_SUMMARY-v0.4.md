# Sentinel of Mnemosyne — Project Summary (Through v0.4 Functional Alpha)

**Generated:** 2026-04-11
**Status:** v0.1–v0.4 complete. v0.5+ planned.
**Purpose:** Team onboarding and project review

---

## 1. Project Overview

**Sentinel of Mnemosyne** is a self-hosted, containerized AI assistant platform built for personal use on a Mac Mini. It wires together a local AI engine (LM Studio + the Pi coding agent), an Obsidian vault as persistent memory, and pluggable interface/module containers — so the same core engine can serve as a DM co-pilot, music practice journal, finance tracker, or autonomous stock trader depending on which modules you attach.

**Core value:** A message goes in, an AI response that knows your history comes back — and what mattered gets written to Obsidian so the next conversation starts smarter.

**What's unique:**
- All inference is **local** (LM Studio + Pi harness on Mac Mini). No cloud AI dependency for production.
- The **Obsidian vault is the database** — no SQL, no Redis. Human-readable markdown that persists knowledge across every conversation.
- **Pluggable modules** via Docker Compose `include` — each new capability (gaming, music, finance, trading) is a self-contained container that snaps into the compose tree without modifying core files.

**Current state:** v0.1–v0.4 complete. The system is fully operational for its primary use cases: Discord bot, memory layer, multi-provider AI routing, security hardening, and 2nd brain commands. The platform is now ready for module development (v0.5+).

---

## 2. Milestone Structure

| Milestone | Name | Phases | Status |
|-----------|------|--------|--------|
| v0.1 | The Spark | 01 | ✅ COMPLETE |
| v0.2 | The Memory | 02 | ✅ COMPLETE |
| v0.3 | The Voice | 03 | ✅ COMPLETE |
| v0.4 | Functional Alpha | 04–10 + 21–23 | ✅ COMPLETE |
| v0.5 | The Dungeon (Pathfinder 2e module) | 11 | 🔜 NEXT |
| v0.6 | The Practice Room (music module) | 12 | — |
| v0.7 | The Workshop (coder interface) | 13 | — |
| v0.8 | The Ledger (finance module) | 14 | — |
| v0.9 | The Trader (paper trading) | 15 | — |
| v0.10 | The Trader Goes Live | 16 | — |
| v1.0 | Community Release | 17–20 | — |

**Cross-cutting (infrastructure) phases:**
- Phase 18: Messaging Alternatives (business SMS/iMessage for Business)
- Phase 19: README & Licensing
- Phase 20: Pi-mono Upgrade Strategy
- Phase 24: Pentest Agent Wire + Missing Verification Artifacts (pending)

---

## 3. Phases Delivered

| # | Phase | Milestone | Plans | Status | What It Delivered |
|---|-------|-----------|-------|--------|-------------------|
| 01 | Core Loop | v0.1 | 3 | ✅ | Docker Compose + Pi harness (Fastify) + Sentinel Core FastAPI; POST /message end-to-end; token guard |
| 02 | Memory Layer | v0.2 | 2 | ✅ | Obsidian context injection before every response; session summary written after every exchange; 25% token budget |
| 03 | Interfaces | v0.3 | 3 | ✅ | Discord bot (/sentask slash command); iMessage bridge (SQLite polling); X-Sentinel-Key auth on all Core endpoints |
| 04 | AI Provider | v0.4 | 4 | ✅ | LiteLLM multi-provider; tenacity retry (3× exponential); ProviderRouter fallback; ModelRegistry |
| 05 | AI Security | v0.4 | 3 | ✅ | InjectionFilter + OutputScanner pipeline; OWASP LLM Top 10 review; pentest agent container scaffolded |
| 06 | Discord Regression Fix | v0.4 | 2 | ✅ | Restored Discord compose include after Phase 5 regression; integration test for IFACE-02/03/04 |
| 07 | Phase 2 Verification + MEM-08 | v0.4 | 1 | ✅ | Phase 2 VERIFICATION.md; search_vault() wired into production pipeline (warm tier active) |
| 08 | Requirements Traceability | — | 0 | ⏭️ SUPERSEDED | Scope absorbed by Phase 22 |
| 10 | Knowledge Migration Tool | v0.4 | 3 | ✅ | Import pipeline for Notion/Roam/Logseq; batch user review via Discord; dry-run mode; duplicate detection |
| 21 | Production Recovery | v0.4 | 1 | ✅ | Restored InjectionFilter + OutputScanner + Discord after commit 6cfb0d3 deleted them; 107 tests green |
| 22 | Requirements Traceability Repair | v0.4 | 2 | ✅ | REQUIREMENTS.md checkboxes repaired; PROJECT.md phase state corrected; Nyquist matrices for phases 01 + 03 |
| 23 | Pi Harness /reset Route | v0.4 | 1 | ✅ | POST /reset on bridge.ts; sendReset() in pi-adapter.ts; buildApp() factory export; PI_TIMEOUT_S env var; reset_session() in Python client — closes GAP-04/CORE-07 |

**Not yet executed:** Phase 9 (tech debt cleanup), Phase 11–20, Phase 24.

---

## 4. Architecture & Technical Decisions

### Core Architecture Pattern

```
User (Discord / iMessage)
       │  POST with X-Sentinel-Key
       ▼
Sentinel Core (FastAPI / Python 3.12)
  ├── InjectionFilter — strips prompt injection from user input
  ├── Obsidian context fetch — hot (user profile) + warm (recent sessions) + search
  ├── Token budget truncation — 25% of context_window reserved for injected context
  ├── Token guard — rejects messages exceeding model context window
  ├── Pi adapter HTTP client — calls Pi harness /prompt
  │       └── ProviderRouter fallback — if Pi down, routes to ai_provider.complete()
  ├── OutputScanner — strips sensitive data leakage before returning response
  └── BackgroundTasks — writes session summary to Obsidian after HTTP response sent

Pi Harness (Fastify / Node.js 22)
  └── pi-adapter.ts — wraps @mariozechner/pi-coding-agent@0.66.1 over JSONL stdin/stdout
       └── sendReset() — sends {"type":"new_session"} to prevent RAM exhaustion

Obsidian Vault (local, Mac host)
  └── Local REST API (plugin) — GET/PUT/PATCH/DELETE vault files; search/simple
```

### Key Technical Decisions

- **Docker Compose `include` directive (not `-f` flag stacking)**
  - Why: `include` resolves paths relative to each included file's directory. `-f` stacking creates fragile relative path hell. Locked in Phase 1.
  - Phase: 01

- **Pi harness adapter pattern (`pi-adapter.ts` abstraction layer)**
  - Why: pi-mono releases breaking changes every 2–4 days. Isolating all pi-mono contact to one file means upgrades never reach Sentinel Core.
  - Phase: 01

- **`depends_on: condition: service_started` (not `service_healthy`)**
  - Why: Healthcheck probing Pi harness is impractical given its startup time. `service_started` is the correct choice for this topology.
  - Phase: 01

- **`LMSTUDIO_BASE_URL: host.docker.internal` for Mac Mini topology**
  - Why: LM Studio runs on the Mac host, not in a container. `host.docker.internal` is the correct bridge from any container to the Mac host on Docker for Mac/Linux.
  - Phase: 01

- **25% token budget truncation before token guard**
  - Why: Users with large Obsidian profile files would hit systematic 422s if context injection wasn't bounded. The truncation marker `[...context truncated to fit token budget]` preserves Pi's awareness that context was cut.
  - Phase: 02

- **BackgroundTasks (not `asyncio.create_task`) for session writes**
  - Why: FastAPI-idiomatic. Response is sent to the caller before the Obsidian write begins — no latency impact on the hot path.
  - Phase: 02

- **Direct SQLite ROWID polling for iMessage bridge (not `imessage_reader`)**
  - Why: `imessage_reader` has no built-in polling and doesn't handle Ventura+ `attributedBody` transparently. Direct ROWID cursor initialized to `MAX(ROWID)` on startup avoids processing historical messages.
  - Phase: 03

- **LiteLLM for multi-provider AI routing (replaces direct LM Studio client)**
  - Why: LiteLLM provides a single API surface across LM Studio, Claude, Ollama, and LlamaCpp. Provider switching becomes an env var change, not a code change.
  - Phase: 04

- **Tenacity `@retry` on `send_messages()` only (not `send_prompt()`)**
  - Why: `send_messages()` is the production path (called from the POST /message pipeline). `send_prompt()` is a legacy method. Retry coverage where it matters.
  - Phase: 04

- **`InjectionFilter` + `OutputScanner` as standalone services wired in lifespan**
  - Why: Security pipeline runs before Pi and after Pi — filters user input for injection patterns, scans model output before returning to caller. Wired in `main.py` lifespan so they're always present.
  - Phase: 05

- **`buildApp()` factory export in bridge.ts (Fastify testability pattern)**
  - Why: Calling `start()` at module import time makes the bridge untestable (spawnPi + port bind on import). Factory pattern separates construction from startup — tests call `buildApp()` + `app.inject()` without port binding.
  - Phase: 23

- **`PI_TIMEOUT_S` env var (replaces hardcoded 190.0)**
  - Why: Different local models have different TTFT (time-to-first-token). Configurable timeout lets you tune without a code change.
  - Phase: 23

---

## 5. Requirements Coverage

### CORE requirements (Phase 01)
| ID | Requirement | Status |
|----|-------------|--------|
| CORE-01 | `docker compose up` starts all services | ✅ |
| CORE-02 | Pi harness adapter pattern — no direct pi-mono imports in Core | ✅ |
| CORE-03 | FastAPI app with asynccontextmanager lifespan | ✅ |
| CORE-04 | LM Studio async HTTP client with context window fetch | ✅ |
| CORE-05 | Token guard (tiktoken cl100k_base) rejects oversized messages | ✅ |
| CORE-06 | pydantic-settings config — startup fails fast on missing vars | ✅ |
| CORE-07 | Pi session reset after each exchange (prevents RAM exhaustion) | ✅ Complete (Phase 23) |

### MEM requirements (Phase 02)
| ID | Requirement | Status |
|----|-------------|--------|
| MEM-01 | ObsidianClient with health check | ✅ |
| MEM-02 | User context file retrieved and injected before each response | ✅ |
| MEM-03 | Session summary written after each interaction | ✅ |
| MEM-04 | Cross-session memory — second conversation references prior session | ✅ |
| MEM-05 | Tiered retrieval: hot (user profile) + warm (recent sessions) | ✅ |
| MEM-06 | Session write via BackgroundTasks (non-blocking) | ✅ |
| MEM-07 | Token budget ceiling — context injection ≤ 25% of context_window | ✅ |
| MEM-08 | search_vault() wired into production pipeline (warm tier) | ✅ (Phase 07) |

### IFACE requirements (Phase 03)
| ID | Requirement | Status |
|----|-------------|--------|
| IFACE-01 | Message Envelope format stable across all interfaces | ✅ |
| IFACE-02 | Discord bot container starts via compose include | ✅ |
| IFACE-03 | Discord /sentask slash command responds in thread | ✅ |
| IFACE-04 | Discord deferred acknowledgement within 3s | ✅ |
| IFACE-05 | iMessage bridge (Mac-native, feature-flagged) | ✅ |
| IFACE-06 | X-Sentinel-Key required on all non-health Core endpoints | ✅ |

### PROV requirements (Phase 04)
| ID | Requirement | Status |
|----|-------------|--------|
| PROV-01 | Switch providers by changing env vars only | ✅ |
| PROV-02 | ProviderRouter with Pi primary + ai_provider fallback | ✅ |
| PROV-03 | Retry 3× exponential backoff on ConnectError/TimeoutException | ✅ |
| PROV-04 | ModelRegistry (live-fetch + seed fallback) | ✅ |
| PROV-05 | Provider configuration validated at startup | ✅ |

### SEC requirements (Phase 05)
| ID | Requirement | Status |
|----|-------------|--------|
| SEC-01 | InjectionFilter — strips injection patterns from user input | ✅ |
| SEC-02 | OutputScanner — scans model output before returning to caller | ✅ |
| SEC-03 | OWASP LLM Top 10 checklist reviewed and findings addressed | ✅ |
| SEC-04 | Pentest agent container wired in docker-compose.yml | ⚠️ Scaffolded — compose include wire pending (Phase 24) |

### Future requirements (v0.5+)
| Group | Requirements | Status |
|-------|-------------|--------|
| PF2E-01..05 | Pathfinder 2e module | 🔜 Phase 11 |
| MUSIC-01..03 | Music lesson module | — Phase 12 |
| CODER-01..03 | Coder interface | — Phase 13 |
| FIN-01..08 | Finance module | — Phase 14 |
| TRADE-01..10 | Trading (paper + live) | — Phase 15–16 |
| COMM-01..03 | Community & polish | — Phase 17 |

---

## 6. Tech Debt & Deferred Items

### Active gaps (not yet closed)

| Gap ID | Description | Phase to close |
|--------|-------------|---------------|
| GAP-05 | SEC-04: pentest-agent compose include not yet wired in docker-compose.yml | Phase 24 |
| GAP-06 | VERIFICATION.md missing for Phases 02, 05, 07 | Phase 24 |
| Tech debt | `message.py` bare `except Exception` — `KeyError` on malformed Pi JSON falls through silently | Phase 9 |
| Tech debt | Dead `send_prompt()` method in `pi_adapter.py` — no callers exist | Phase 9 |

### Closed gaps (for reference)

| Gap ID | Description | Closed in |
|--------|-------------|-----------|
| GAP-01 | PROV-03 retry coverage | Quick task 260410-p7o |
| GAP-02 | Discord compose include regression | Phase 21 |
| GAP-03 | Requirements traceability (stale REQUIREMENTS.md) | Phase 22 |
| GAP-04 | Pi /reset 404 causing LM Studio RAM exhaustion after ~5 exchanges | Phase 23 |

### Known limitations

- **iMessage Ventura+ `attributedBody`**: Messages where the text is only in `attributedBody` (not `text` column) are skipped with a warning. Plain-text messages work correctly. Decoding `attributedBody` is deferred to a future phase.
- **Pi-mono breaking changes**: pi-mono releases every 2–4 days with breaking changes. The adapter pattern (all pi-mono contact in `pi-adapter.ts`) is the mitigation — upgrades are isolated.
- **LM Studio / Obsidian must be running**: Both are operational dependencies on the Mac host. The system degrades gracefully (503 on Pi calls, context injection skipped on Obsidian unavailability) but requires both to be running for full functionality.

---

## 7. Getting Started

### Prerequisites

- Docker Desktop with Compose v2
- LM Studio running on Mac host with a model loaded
- Obsidian with the Local REST API plugin enabled and running

### Run the system

```bash
# Copy and fill in environment variables
cp .env.example .env

# Start all services
docker compose up

# Core is live at:
curl -H "X-Sentinel-Key: $SENTINEL_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"content": "hello", "user_id": "me"}' \
     http://localhost:8000/message
```

### Key directories

```
sentinel-of-mnemosyne/
├── sentinel-core/          # Python FastAPI — core message pipeline
│   ├── app/
│   │   ├── main.py         # FastAPI lifespan, service wiring
│   │   ├── routes/message.py # POST /message — 7-step memory pipeline
│   │   ├── clients/        # Pi adapter, Obsidian client, AI providers
│   │   └── services/       # Token guard, InjectionFilter, OutputScanner, ModelRegistry
│   └── tests/              # pytest — 107 tests
├── pi-harness/             # Node.js Fastify bridge to Pi subprocess
│   ├── src/bridge.ts       # HTTP routes (POST /prompt, /health, /reset)
│   └── src/pi-adapter.ts   # All pi-mono contact isolated here
├── interfaces/
│   ├── discord/            # Discord bot (Dockerfile + compose.yml include)
│   └── imessage/           # Mac-native iMessage bridge (feature-flagged)
├── security/
│   └── pentest-agent/      # Scheduled security scan container (scaffolded)
└── docker-compose.yml      # Root compose — includes all active service composes
```

### Run tests

```bash
# Python (sentinel-core)
python3 -m pytest sentinel-core/tests/ -x -q

# Node.js (pi-harness)
cd pi-harness && NODE_ENV=test npm test
```

### Where to look first

- **Core message pipeline**: `sentinel-core/app/routes/message.py` — the 7-step flow
- **Memory layer**: `sentinel-core/app/clients/obsidian.py` — Obsidian REST API client
- **Pi protocol**: `pi-harness/src/pi-adapter.ts` — all JSONL RPC calls to pi-mono
- **Security pipeline**: `sentinel-core/app/services/injection_filter.py` + `output_scanner.py`
- **Module pattern**: `interfaces/discord/` — reference for building new interface modules

---

## 8. Stats

- **Timeline:** 2026-04-10 → 2026-04-11 (2 days of active development)
- **Milestones complete:** v0.1, v0.2, v0.3, v0.4
- **Phases complete:** 12 (Phases 01, 02, 03, 04, 05, 06, 07, 10, 21, 22, 23 + Phase 08 superseded)
- **Plans executed:** 24
- **Commits (since 2026-04-01):** 111
- **Files in first push:** 81 files, 14,425 insertions
- **Test suites:** 107 Python (pytest) + 2 Node.js (vitest)
- **Contributors:** Tom Boucher

---

## 9. Next Up: v0.5 The Dungeon

**Phase 11 — Pathfinder 2e Module** is the next milestone.

The module pattern is established: create a new directory under `/modules/` or `/interfaces/`, define a `compose.yml` include, and wire into the Obsidian vault structure. The Sentinel will serve as DM co-pilot: NPC management, session notes, and in-character dialogue generation.

Before v0.5 begins, Phase 9 (tech debt cleanup) and Phase 24 (pentest agent + missing VERIFICATION.md artifacts) should be resolved to keep the platform in a clean state.
