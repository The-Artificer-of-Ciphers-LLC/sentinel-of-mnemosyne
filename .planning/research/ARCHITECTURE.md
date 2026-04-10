# Architecture Research

**Domain:** Self-hosted containerized AI assistant platform
**Researched:** 2026-04-10
**Confidence:** MEDIUM-HIGH

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                      INTERFACE LAYER                                │
│  ┌──────────┐  ┌──────────────┐  ┌──────────┐                      │
│  │ Discord  │  │Apple Messages│  │  curl /  │                      │
│  │   Bot    │  │   Bridge     │  │  future  │                      │
│  └────┬─────┘  └──────┬───────┘  └────┬─────┘                      │
│       │               │               │                            │
│       └───────────────┼───────────────┘                            │
│                       │  HTTP POST /message                        │
│                       │  Standard Message Envelope                 │
│                       ▼                                            │
├─────────────────────────────────────────────────────────────────────┤
│                    ORCHESTRATION LAYER                              │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                   SENTINEL CORE (FastAPI)                    │   │
│  │  ┌──────────┐ ┌──────────────┐ ┌────────────┐ ┌──────────┐ │   │
│  │  │ Router   │ │Context Build │ │  Session   │ │  Module  │ │   │
│  │  │          │ │              │ │  Manager   │ │  Router  │ │   │
│  │  └──────────┘ └──────────────┘ └────────────┘ └──────────┘ │   │
│  └──────┬──────────────┬──────────────────────────────┬────────┘   │
│         │              │                              │            │
├─────────┼──────────────┼──────────────────────────────┼────────────┤
│         │              │                              │            │
│    RPC (JSONL)    REST API                     HTTP (internal)     │
│    stdin/stdout        │                              │            │
│         ▼              ▼                              ▼            │
│  ┌──────────┐  ┌──────────────┐  ┌─────────────────────────────┐  │
│  │    Pi    │  │   Obsidian   │  │      MODULE CONTAINERS      │  │
│  │ Harness  │  │  Local REST  │  │  ┌──────┐ ┌──────┐ ┌─────┐ │  │
│  │(Node.js) │  │     API      │  │  │Pathf.│ │Music │ │Trade│ │  │
│  └────┬─────┘  │  (host Mac)  │  │  └──────┘ └──────┘ └─────┘ │  │
│       │        └──────────────┘  └─────────────────────────────┘  │
│       │                                                           │
│       ▼                                                           │
│  ┌──────────────────────────────────────────────┐                 │
│  │  LM STUDIO (Mac Mini — not containerized)    │                 │
│  │  OpenAI-compatible API · http://[ip]:1234    │                 │
│  └──────────────────────────────────────────────┘                 │
└─────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | Communicates With |
|-----------|----------------|-------------------|
| **Sentinel Core** | Message routing, context assembly, session management, Obsidian read/write | Pi Harness, Obsidian API, all interfaces, all modules |
| **Pi Harness** | AI conversation loop, tool execution, skill dispatch | LM Studio (outbound), Sentinel Core (inbound via RPC) |
| **LM Studio** | LLM inference, model serving | Pi Harness only (OpenAI-compatible API) |
| **Obsidian REST API** | Vault read/write/search, persistent memory | Sentinel Core only |
| **Interface containers** | Channel-specific message translation to/from envelope format | Sentinel Core only |
| **Module containers** | Domain-specific logic (Pathfinder rules, trade execution, etc.) | Sentinel Core via HTTP |

## Research Findings by Question

### 1. Core-to-Pi Communication: stdin/stdout JSONL

**Verdict: JSONL over stdin/stdout is the right call for v0.1. Plan a migration path to SDK mode.**

**Confidence:** MEDIUM-HIGH (verified against pi-mono docs)

Pi-coding-agent supports three modes:
- **Interactive mode** — terminal UI, not useful for programmatic integration
- **RPC mode** — stdin/stdout with LF-delimited JSONL framing
- **SDK mode** — direct TypeScript API (`SessionManager`, `ModelRegistry`, etc.)

The existing architecture doc mentions wrapping Pi as a subprocess with JSONL. This works and is the simplest integration path. The protocol uses strict LF-delimited JSONL, and the pi docs explicitly warn against generic line readers that may split on Unicode separators within JSON payloads.

**Alternatives considered:**

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| stdin/stdout JSONL (RPC mode) | Simplest to start, no web server in Pi container, clean process boundary | Python-to-Node subprocess management adds complexity, error handling is harder across process boundaries, no concurrent requests | **Use for v0.1** |
| HTTP server wrapping Pi | Concurrent requests, standard tooling, health checks | Pi has no built-in HTTP mode — you'd write a Node.js HTTP wrapper around the SDK | **Consider for v0.3+** |
| SDK mode (embed Pi in a Node service) | Full control, concurrent sessions, proper error propagation | Must write a Node.js service that imports Pi SDK, two Node services to maintain | **Best long-term option** |
| gRPC | Typed contracts, streaming, language-agnostic | Overkill for a single-consumer integration, adds protobuf toolchain | **Skip** |
| Unix domain socket | Faster than TCP for co-located containers | Docker volume mount complexity, no real latency benefit given LLM response times | **Skip** |

**Architecture recommendation:** Start with RPC mode (stdin/stdout JSONL) via `asyncio.create_subprocess_exec` in Python. The Pi Harness container runs a thin Node.js wrapper that spawns pi in RPC mode and exposes a simple HTTP endpoint on port 8765 that proxies requests into the JSONL stream. This gives Core a clean HTTP interface while keeping Pi in its native RPC mode.

This is actually what the existing architecture already describes (the `PI_RPC_HOST` and `PI_RPC_PORT` env vars suggest a network endpoint, not a raw subprocess). The Pi container itself handles the subprocess internally. This is the right layering.

**Risk flag:** Pi is under active development. Pin the npm version hard. The JSONL framing details (Unicode separator handling) suggest the protocol has had edge case issues. Budget time for debugging the framing layer.

---

### 2. Context Injection: What Gets Prepended vs. Stored as Tools

**Verdict: Prepend user context and recent session summaries into the system prompt. Register module capabilities as Pi skills (tool/function equivalent).**

**Confidence:** MEDIUM (based on standard RAG patterns, no single authoritative source)

The standard pattern in comparable systems (OpenAI Assistants, LangChain agents, custom RAG pipelines) separates context into two categories:

**Injected into system prompt (prepend):**
- User profile and preferences (from `/core/users/{user_id}.md`)
- Recent session summaries (last 2-3 sessions, not full transcripts)
- Relevant vault excerpts retrieved by search (the RAG component)
- Current date/time and active module context

**Registered as tools/functions (Pi skills):**
- Module-specific actions (create NPC, log practice session, execute trade)
- Vault operations (search vault, write note, read specific file)
- System operations (check status, list available modules)

**What NOT to inject:**
- Full session transcripts (token-expensive, diminishing returns)
- Entire user file if it grows large (summarize or excerpt)
- Module data that the user hasn't asked about

**Pattern to follow:**

```
System Prompt Structure:
1. Core identity ("You are the Sentinel of Mnemosyne...")
2. User context block (from user profile markdown)
3. Retrieved context block (search results from vault, truncated)
4. Active module context (if routing to a specific module)
5. Available skills summary (what tools Pi can call)
---
User message
```

**Token budget approach:** Set a hard ceiling for context injection (e.g., 2000 tokens for user context, 2000 for retrieved vault content). Truncate or summarize if exceeded. This prevents runaway token usage on large vaults.

**Architecture implication:** The Context Builder component in Sentinel Core is the most important piece to get right. It determines response quality more than any other component. Build it as a dedicated module with clear interfaces, not inline in the request handler.

---

### 3. Obsidian Memory Layer: Search Strategy

**Verdict: Start with the Local REST API's built-in search. Plan for hybrid search (BM25 + embeddings) when the vault exceeds ~2,000 notes or when conceptual queries fail.**

**Confidence:** MEDIUM (benchmarks from third-party sources, not official)

**Current state of vault search approaches:**

| Method | Speed | Quality | Vault Size Limit | Notes |
|--------|-------|---------|-------------------|-------|
| Obsidian Local REST API `/search/simple/` | <1s | Keyword match only, no ranking | Works to ~5,000 notes | Built into the plugin, zero setup |
| ripgrep on vault folder | <1s | Unranked file paths | Handles millions of files | Requires vault folder accessible to container |
| OmniSearch plugin | <1s | BM25 ranked | Same as Obsidian | Requires Obsidian running |
| QMD (hybrid + rerank) | 2-21s | Semantic understanding | Scales with embedding store | External tool, more setup |
| Smart Connections plugin | Varies | Vector embeddings, on-device | Requires Obsidian running | Plugin ecosystem, not API-first |

**The breakpoint:** At approximately 2,400 notes, keyword search becomes unreliable for conceptual queries. Searching for "motivation decay" won't find notes about "long-term project fatigue" unless exact phrases match. For a personal assistant that accumulates session notes daily, you'll hit 2,400 notes within 2-3 years of active use.

**Recommended phased approach:**

1. **v0.2 (now):** Use `/search/simple/` from Obsidian Local REST API. Search by user_id tag + keywords from the current message. Return top 5 results with `contextLength=300`. This is sufficient for early use.

2. **v0.4+:** Add a lightweight embedding layer. Generate embeddings for each note on write (using LM Studio's embedding endpoint or a small local model). Store in a SQLite database with a vector extension (sqlite-vss) or a simple FAISS index file. Query both keyword search AND vector similarity, merge results.

3. **v0.6+ (if needed):** Full hybrid with reranking. Use the LLM itself to rerank the top-N results from combined keyword + vector search. Only worth the latency cost if retrieval quality is visibly degrading.

**Architecture implication:** The `obsidian_client.py` should abstract the search strategy behind an interface. Today it calls `/search/simple/`. Later it calls keyword search + vector search and merges. The rest of the system never knows the difference.

---

### 4. Docker Compose Modularity: Override Files vs. Include Directive

**Verdict: Use the `include` directive (Compose v2.20+) instead of override file stacking. It handles path resolution correctly and is Docker's recommended approach for modular applications.**

**Confidence:** HIGH (verified against Docker official documentation)

The existing architecture proposes `-f` flag stacking:
```bash
docker compose -f docker-compose.yml -f interfaces/discord/docker-compose.override.yml up
```

This works but has a significant footgun: **all paths in override files must be relative to the base compose file's directory**, not to the override file's own directory. This breaks when interfaces and modules have their own Dockerfiles in subdirectories.

**The `include` directive** (available since Compose v2.20, mid-2023) solves this:

```yaml
# docker-compose.yml
include:
  - path: ./interfaces/discord/compose.yaml
  - path: ./modules/music/compose.yaml

services:
  sentinel-core:
    # ...
  pi-harness:
    # ...
```

Each included file resolves paths relative to its own directory. Compose reports errors on resource name conflicts (prevents accidental overwrites). You can still use `docker-compose.override.yml` for environment-specific settings on top.

**Service discovery pattern:** Docker Compose's internal DNS resolves service names automatically. All containers on the same network can reach each other by service name. No Consul, no etcd, no service mesh needed for a personal-use system.

**Module registration pattern:** Modules need to tell Core they exist. Two approaches:

| Approach | How | Verdict |
|----------|-----|---------|
| Static config | List modules in Core's env vars or config file | Simple, requires restart to add modules |
| Health-check discovery | Core polls known service names, marks available | More flexible, still requires knowing names |
| Event-based registration | Module POSTs to Core's `/register` endpoint on startup | Most dynamic, modules self-announce |

**Recommendation:** Start with static config (environment variable listing active modules). Move to self-registration (`/register` endpoint) when the module count exceeds what's comfortable in env vars. The existing `sentinel.sh` wrapper handles the Compose file assembly; Core just needs to know what modules are reachable.

**Architecture implication:** Replace `-f` stacking with `include` directive. Update `sentinel.sh` to generate or symlink the include entries rather than building a `-f` chain. The base compose file becomes the single source of truth for what's active.

---

### 5. Apple Messages Bridge

**Verdict: Use `imsg` (steipete/imsg) as the Mac-side component. It is the best available tool for programmatic iMessage interaction in 2025-2026.**

**Confidence:** MEDIUM (active project, but macOS permission model is fragile)

**Approaches evaluated:**

| Approach | Status | Verdict |
|----------|--------|---------|
| **imsg CLI** | Active development (v0.4+), Swift-based, sends via AppleScript, receives via chat.db read | **Use this** |
| Raw AppleScript | Works for sending, no structured receive, no streaming | Fragile, limited |
| Shortcuts automation | Cannot trigger on incoming messages, only manual triggers | Not viable for a bot |
| chat.db SQLite polling | Read-only, no send capability, requires Full Disk Access | Half a solution |
| BlueBubbles / AirMessage | Designed for Android-to-iMessage bridging, heavy dependencies | Wrong tool |
| Beeper / Texts.com | Commercial, not self-hosted | Out of scope |

**imsg architecture:**
- **Sending:** AppleScript controlling Messages.app (no private APIs, Apple-safe)
- **Receiving:** Reads `~/Library/Messages/chat.db` via filesystem event monitoring (FSEvents), debounced at 250ms
- **Output:** JSON-structured, includes attachment metadata
- **Permissions required:** Full Disk Access + Automation permission for terminal

**Bridge architecture:**

```
Mac Mini (host)                          Docker Network
┌─────────────────────┐                 ┌──────────────────┐
│  imsg watch --json  │ ──WebSocket──>  │  Messages Bridge │
│  (runs natively)    │ <──HTTP POST──  │  Container       │
│                     │                 │  (translates to  │
│  Messages.app       │                 │   envelope)      │
└─────────────────────┘                 └────────┬─────────┘
                                                 │
                                        HTTP POST /message
                                                 ▼
                                        ┌──────────────────┐
                                        │  Sentinel Core   │
                                        └──────────────────┘
```

The bridge container runs in Docker but the `imsg` process must run natively on the Mac (it needs Messages.app access). The bridge container connects to imsg's streaming output and translates messages into Sentinel envelopes.

**Risk flags:**
- macOS permission model changes with major OS updates. Full Disk Access for terminal apps has been restricted further in recent macOS versions. Test on the actual target macOS version.
- `imsg` is a one-person project. Evaluate whether to fork and maintain locally if it goes unmaintained.
- iMessage requires an active Apple ID signed into Messages.app. If the Mac reboots, Messages may need manual re-authentication before the bridge works.
- Group messages have different addressing than 1:1 chats. imsg handles this but the bridge needs to account for it.

---

### 6. Session Management: Cross-Interface User Identity

**Verdict: Use a user identity mapping table in Obsidian (`/core/users/identity-map.md` or individual user files). Manual linking at first, with optional automatic correlation later.**

**Confidence:** MEDIUM (standard pattern, but the simple approach has edge cases)

**The problem:** The same person (Tom) might message via Discord (`discord_123456789`) and via iMessage (`+15551234567`). The system needs to know these are the same user to provide consistent context.

**Recommended approach — progressive complexity:**

**Phase 1 (v0.3): Manual identity linking**
The user file at `/core/users/{primary_id}.md` includes an `aliases` field:

```yaml
---
user_id: tom
display_name: Tom
aliases:
  - discord_123456789
  - imessage_+15551234567
last_seen: 2026-04-06T12:00:00Z
---
```

Core maintains a lookup table (in-memory dict, loaded from Obsidian on startup) mapping any alias to the canonical user_id. When a message arrives with `user_id: discord_123456789`, Core resolves it to `tom` and loads that user's context.

**Phase 2 (v0.5+): Prompted linking**
When Core receives a message from an unknown user_id, it checks if the display name or message patterns match an existing user. If confidence is high, it asks: "Are you Tom from Discord?" and links on confirmation.

**Phase 3 (never, unless multi-user): OAuth/OIDC federation**
Only needed if this becomes a multi-user platform. Explicitly out of scope per PROJECT.md.

**Session isolation:** Each interface session is independent. A Discord conversation and an iMessage conversation happening simultaneously are separate sessions with separate session notes. Cross-session context comes from the shared user profile, not from real-time session sharing.

**Architecture implication:** The `user_id` field in the Message Envelope is interface-specific (Discord user ID, phone number). Core must resolve this to a canonical Sentinel user_id before context retrieval. This resolution step belongs in the Router component, before Context Builder runs.

---

### 7. Trading Module: Paper-to-Live Architecture

**Verdict: Same code, different configuration. Alpaca is explicitly designed for this pattern.**

**Confidence:** HIGH (verified against Alpaca official documentation)

Alpaca's API uses identical endpoints for paper and live trading. The only differences:
- **API keys:** Separate key pairs for paper vs. live
- **Base URL:** `paper-api.alpaca.markets` vs. `api.alpaca.markets`
- **A boolean flag:** `paper=True/False` in the client constructor

**Recommended architecture:**

```python
# Single trading service, configured by environment
class TradingService:
    def __init__(self):
        self.client = alpaca.TradingClient(
            api_key=os.environ["ALPACA_API_KEY"],
            secret_key=os.environ["ALPACA_SECRET_KEY"],
            paper=os.environ.get("ALPACA_PAPER", "true").lower() == "true"
        )
```

**Safety architecture (critical):**

| Layer | Mechanism | Purpose |
|-------|-----------|---------|
| Environment config | `ALPACA_PAPER=true` default, must be explicitly set to `false` | Prevents accidental live trading |
| Rules engine | `/trading/rules.md` in Obsidian, checked before every trade | PDT counter, position limits, cash-only enforcement |
| Human approval | Live trades require confirmation via interface before execution | Final safety net |
| Emergency stop | `/stop-trading` command kills all open orders and disables the module | Circuit breaker |
| Audit trail | Every trade decision written to Obsidian with full rationale | Post-mortem capability |

**Do NOT use separate containers for paper vs. live.** Same container, same code, different env vars. This eliminates the "works in paper but not in live" class of bugs caused by code divergence.

**The rules engine deserves its own design pass.** The rules file (`/trading/rules.md`) is loaded and parsed before every trade decision. It contains hard limits (max position size, PDT counter, no margin) that the code enforces programmatically. The LLM proposes trades; the rules engine vetoes them. The rules engine is NOT the LLM — it is deterministic Python code that reads a structured markdown file.

---

## Architectural Patterns

### Pattern 1: Message Envelope as Universal Contract

**What:** All interfaces translate their native message format into a single Sentinel Message Envelope (JSON). Core only speaks Envelope.

**When to use:** Any multi-interface system where the core logic shouldn't know about Discord, iMessage, or any specific platform.

**Trade-offs:** Adds a translation layer per interface (cost). Decouples core from every platform (massive benefit). The envelope must be expressive enough to carry platform-specific metadata without the core needing to understand it (the `metadata` field handles this).

**The existing envelope design is solid.** The `metadata` field for platform-specific pass-through is the right pattern. One addition to consider: a `conversation_id` field distinct from `channel_id` that represents a logical conversation thread, useful for session management.

### Pattern 2: Context Assembly Pipeline

**What:** A multi-stage pipeline that builds the LLM prompt from multiple sources before sending to Pi.

**When to use:** Any RAG-augmented AI system.

```
Message In
    ↓
[1. Resolve User Identity]  →  alias map lookup
    ↓
[2. Load User Profile]      →  /core/users/{user_id}.md
    ↓
[3. Search Relevant Context] →  Obsidian search API
    ↓
[4. Check Active Module]     →  route to module if applicable
    ↓
[5. Assemble System Prompt]  →  identity + profile + context + module
    ↓
[6. Send to Pi]              →  RPC/HTTP to Pi Harness
    ↓
[7. Process Response]        →  extract, format
    ↓
[8. Write Session Note]      →  Obsidian write
    ↓
[9. Update User Profile]     →  append new context
    ↓
Response Out
```

**Trade-offs:** More stages = more latency. Each stage is independently testable. Stages can be skipped for simple queries (e.g., skip vault search for "what time is it?").

### Pattern 3: Module as Skill Pack + Optional Container

**What:** Lightweight modules are just Pi skill files (SKILL.md) mounted into the Pi container. Heavy modules (trading, finance) get their own containers with domain-specific logic, and also register skills that call back to their containers.

**When to use:** When module complexity varies. Pathfinder NPC generation might be a skill file only. Trading needs a persistent service with its own state.

**Trade-offs:** Two integration patterns to maintain (skill-only vs. skill + container). Simpler modules stay simple. Complex modules get proper isolation.

---

## Data Flow

### Request Flow (Happy Path)

```
Interface (Discord)
    │
    │  POST /message  { source: "discord", user_id: "discord_123", content: "..." }
    ▼
Sentinel Core
    │
    ├──→ Resolve user: discord_123 → "tom"
    ├──→ GET /vault/core/users/tom.md  (Obsidian)
    ├──→ GET /search/simple/?query=keywords  (Obsidian)
    ├──→ Assemble prompt: system + user_context + search_results + message
    ├──→ POST to Pi Harness (JSONL over HTTP proxy)
    │         │
    │         ├──→ Pi calls LM Studio /v1/chat/completions
    │         ├──→ Pi may invoke tools (read/write/bash)
    │         └──→ Pi returns structured response
    │
    ├──→ PUT /vault/core/sessions/2026-04-10/tom-143022.md  (Obsidian)
    ├──→ PATCH /vault/core/users/tom.md  (update context)
    │
    └──→ Return response envelope to Discord interface
              │
              └──→ Post to Discord channel
```

### Module Routing Flow

```
User message: "roll initiative for Vareth"
    │
    ├──→ Core detects module keyword or channel context
    ├──→ Routes to Pathfinder module container (if heavy module)
    │    OR routes to Pi with Pathfinder skills loaded (if skill-only)
    ├──→ Module/skill handles domain logic
    └──→ Response flows back through Core to interface
```

### Trading Flow (Paper Mode)

```
Watchlist scan trigger (cron or user request)
    │
    ├──→ Trading module fetches market data (Alpaca API)
    ├──→ Module builds analysis prompt with rules context
    ├──→ Routes through Core to Pi for LLM analysis
    ├──→ Pi returns trade thesis
    ├──→ Rules engine validates: PDT count? Position size? Cash available?
    │    ├── REJECT → log rejection reason to Obsidian
    │    └── APPROVE → execute order via Alpaca API
    ├──→ Write trade record to /trading/trades/2026-04-10/
    └──→ Notify via interface (Discord message with trade details)
```

---

## Anti-Patterns

### Anti-Pattern 1: Letting the LLM Decide Trade Execution

**What people do:** Give the LLM a "execute_trade" tool and let it decide when to call it.
**Why it's wrong:** LLMs hallucinate confidence, misinterpret market data, and have no concept of risk management. One bad prompt injection could drain the account.
**Do this instead:** LLM proposes trades with rationale. Deterministic rules engine validates. Human approves (live mode). The LLM never has direct access to order execution.

### Anti-Pattern 2: Storing Conversation State in Memory Only

**What people do:** Keep session state in Python dicts or Redis, lose everything on restart.
**Why it's wrong:** The core value proposition is persistent memory. In-memory state defeats the purpose.
**Do this instead:** Obsidian is the source of truth. Core's in-memory state is a cache that can be rebuilt from vault files on startup.

### Anti-Pattern 3: Fat Interfaces

**What people do:** Put business logic in the Discord bot (e.g., the bot decides what context to fetch, how to format the prompt).
**Why it's wrong:** Every new interface reimplements the same logic. Changes require updating every interface.
**Do this instead:** Interfaces are dumb translators. They convert platform messages to envelopes and back. All intelligence lives in Core.

### Anti-Pattern 4: Direct Vault File Writes from Multiple Services

**What people do:** Let modules write directly to the Obsidian vault folder, bypassing the REST API.
**Why it's wrong:** Race conditions, no indexing integration, impossible to audit who wrote what.
**Do this instead:** All vault writes go through Sentinel Core (which uses the REST API). Modules request writes via Core's API.

---

## Integration Points

### External Services

| Service | Integration Pattern | Gotchas |
|---------|---------------------|---------|
| LM Studio | OpenAI-compatible HTTP API from Pi container | Must have a model loaded; no auth by default on LAN; only Pi should talk to it |
| Obsidian REST API | HTTPS with bearer token from Core | Obsidian must be running; self-signed cert requires `--insecure` or cert trust; port 27124 |
| Alpaca API | REST API from Trading module | Separate paper/live keys; rate limits (200 req/min); market hours matter |
| Discord API | discord.py or similar in interface container | Bot token management; rate limits; gateway intents required |
| imsg | CLI on host Mac, streamed JSON output | Full Disk Access required; runs outside Docker; macOS version sensitivity |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Interface → Core | HTTP POST, Message Envelope JSON | Auth via `X-Sentinel-Key` header |
| Core → Pi Harness | HTTP to Pi container's proxy endpoint (which internally uses JSONL RPC) | Async, may take 10-60s for LLM responses; needs generous timeouts |
| Core → Obsidian | HTTPS REST API | Core is the sole writer; reads are fast, search may be slow on large vaults |
| Core → Modules | HTTP (Core calls module endpoints) | Modules register capabilities; Core routes relevant requests |
| Module → Core | HTTP (module requests vault writes, Pi access) | Modules never talk to Pi or Obsidian directly |
| Host Mac → Docker | imsg output → Messages bridge container via host networking or port mapping | The one boundary that crosses the container/host divide |

---

## Recommended Project Structure

```
sentinel-of-mnemosyne/
├── docker-compose.yml              # Base: core + pi-harness only
├── .env.example                    # Template (never commit .env)
├── sentinel.sh                     # Convenience wrapper
│
├── sentinel-core/                  # Python/FastAPI
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py                 # FastAPI app, routes
│   │   ├── router.py               # Message routing logic
│   │   ├── context_builder.py      # Context assembly pipeline
│   │   ├── session_manager.py      # Session tracking, user resolution
│   │   ├── pi_client.py            # HTTP client for Pi Harness
│   │   ├── obsidian_client.py      # Obsidian REST API client
│   │   ├── module_router.py        # Route to registered modules
│   │   └── models.py               # Pydantic models (envelope, config)
│   └── tests/
│
├── pi-harness/                     # Node.js wrapper around pi
│   ├── Dockerfile
│   ├── package.json                # Pins @mariozechner/pi-coding-agent
│   ├── src/
│   │   └── server.js               # HTTP proxy → pi RPC subprocess
│   ├── settings.json               # Pi config (LM Studio provider)
│   └── entrypoint.sh               # Starts the HTTP proxy
│
├── interfaces/
│   ├── discord/
│   │   ├── compose.yaml            # include-compatible compose
│   │   ├── Dockerfile
│   │   └── src/
│   └── messages/
│       ├── compose.yaml            # Bridge container
│       ├── Dockerfile
│       ├── src/                     # Bridge that connects to imsg
│       └── host/                    # Scripts/configs for imsg on host Mac
│
├── modules/
│   ├── pathfinder/
│   │   ├── compose.yaml
│   │   ├── skills/                  # Pi SKILL.md files
│   │   └── src/                     # Container code (if needed)
│   ├── music/
│   ├── finance/
│   └── trading/
│       ├── compose.yaml
│       ├── src/
│       │   ├── service.py           # Trading service (Alpaca client)
│       │   └── rules_engine.py      # Deterministic trade validation
│       └── skills/
│
├── skills/                          # Shared/core Pi skills
│   └── core/
│       └── summarize-session.md
│
└── docs/
```

### Structure Rationale

- **`app/` subdirectory in sentinel-core:** Separates application code from Docker/config files. Enables cleaner imports and testing.
- **`src/server.js` in pi-harness:** The Pi container is not just a raw pi process. It's a thin HTTP server that manages the pi subprocess lifecycle and proxies requests. This is the recommended integration layer.
- **`compose.yaml` per module (not `docker-compose.override.yml`):** Named for the `include` directive pattern. Each module is a self-contained compose application with correct path resolution.
- **`skills/` at both module and root level:** Core skills live at the root. Module-specific skills live with the module. Both are mounted into the Pi container's skills volume.

---

## Scaling Considerations

This is a personal-use system. Scaling to more than one concurrent user is explicitly out of scope.

| Concern | Current Scale (1 user) | Watch For |
|---------|----------------------|-----------|
| LLM latency | 5-30s per response (local model) | Acceptable for personal use. If too slow, upgrade Mac Mini RAM or use cloud fallback. |
| Vault search | <1s with keyword search | Degrade at ~2,400+ notes for conceptual queries. Add embeddings then. |
| Concurrent requests | One at a time is fine | If two interfaces fire simultaneously, Core should queue, not crash. Use async with a semaphore. |
| Session note storage | Keep all forever | At 10 sessions/day for 3 years = ~11,000 session files. Obsidian handles this. Archive old sessions yearly if graph view gets slow. |
| Docker resource usage | ~2GB RAM for all containers | Mac Mini with 16GB+ is fine. Trading module may need more during market hours. |

---

## Build Order (Dependency-Driven)

This is the critical output for roadmap planning. Components are ordered by what blocks what.

```
Phase 1: LM Studio + Pi Harness + Core (minimal)
  └── Proves: AI responds to a prompt end-to-end
  └── Blocks: Everything else

Phase 2: Obsidian integration in Core
  └── Proves: Persistent memory works
  └── Blocks: Any module that reads/writes vault data
  └── Depends on: Phase 1

Phase 3: Discord interface + Message Envelope finalization
  └── Proves: The envelope contract works with a real interface
  └── Blocks: All other interfaces, module routing
  └── Depends on: Phase 1 (can parallelize with Phase 2)

Phase 4: Module routing + first module (Pathfinder — skill-only)
  └── Proves: The skill/module pattern works
  └── Blocks: All other modules
  └── Depends on: Phase 2 + Phase 3

Phase 5: Apple Messages bridge
  └── Proves: Non-Discord interface works, imsg integration stable
  └── Depends on: Phase 3 (envelope is stable)

Phase 6: Music module (simple, vault-heavy)
  └── Validates: Vault write patterns at scale
  └── Depends on: Phase 2 + Phase 4

Phase 7: Finance module (OFX import, categorization)
  └── Depends on: Phase 2 + Phase 4

Phase 8: Trading module (paper)
  └── Highest risk, most complex
  └── Depends on: Phase 2 + Phase 4 + rules engine design
  └── Must NOT be rushed

Phase 9: Trading module (live)
  └── Depends on: Phase 8 + 30-day paper validation
```

---

## Assessment of Existing Architecture Decisions

| Decision | Assessment | Notes |
|----------|-----------|-------|
| FastAPI for Core | **Solid** | Right tool for an async HTTP orchestrator. Python ecosystem fits AI/automation. |
| Pi Harness via RPC | **Solid with caveat** | RPC mode is correct for v0.1. The Pi container should expose HTTP internally (wrapping RPC), which the existing env vars already suggest. Pin the version hard. |
| Obsidian Local REST API | **Solid** | The right abstraction for programmatic vault access. Search will need augmentation later but the API is the right entry point. |
| Docker Compose overrides | **Update recommended** | Switch from `-f` flag stacking to `include` directive. Same concept, better path resolution, Docker-recommended. |
| LM Studio as primary provider | **Solid** | OpenAI-compatible API makes provider swap trivial. The operational dependency (model must be loaded) is a known constraint, not a design flaw. |
| Message Envelope format | **Solid** | Clean, extensible. Consider adding `conversation_id` for multi-message thread tracking. |
| stdin/stdout JSONL (direct subprocess) | **Clarify** | The env vars (`PI_RPC_HOST`, `PI_RPC_PORT`) suggest HTTP between Core and Pi container. The ADR text says "stdin/stdout JSONL." These describe different layers: HTTP between containers, JSONL inside the Pi container. Make this explicit in the architecture doc. |
| Alpaca for trading | **Solid** | Paper/live same code, commission-free, algorithmic-trading-friendly. The right choice. |

---

## Sources

- [Node.js Child Process documentation](https://nodejs.org/api/child_process.html)
- [Pi-mono GitHub (badlogic/pi-mono)](https://github.com/badlogic/pi-mono)
- [Pi coding-agent package](https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent)
- [imsg CLI for macOS (steipete/imsg)](https://github.com/steipete/imsg)
- [Obsidian Local REST API (coddingtonbear)](https://github.com/coddingtonbear/obsidian-local-rest-api)
- [Obsidian Semantic Search Benchmarks (Mandalivia)](https://www.mandalivia.com/obsidian/semantic-search-for-your-obsidian-vault-what-i-tried-and-what-worked/)
- [Docker Compose include directive](https://docs.docker.com/compose/how-tos/multiple-compose-files/include/)
- [Docker Compose modularity blog post](https://www.docker.com/blog/improve-docker-compose-modularity-with-include/)
- [Alpaca Paper Trading documentation](https://docs.alpaca.markets/docs/paper-trading)
- [Alpaca Trading API documentation](https://docs.alpaca.markets/docs/trading-api)

---
*Architecture research for: Sentinel of Mnemosyne*
*Researched: 2026-04-10*
