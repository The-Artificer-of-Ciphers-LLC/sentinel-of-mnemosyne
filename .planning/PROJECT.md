# Sentinel of Mnemosyne

## What This Is

A self-hosted, containerized AI assistant platform built for personal use. The Sentinel wires together a local AI engine (LM Studio on a Mac Mini), an Obsidian vault as persistent memory, and pluggable interface/module containers — so the same engine can serve as a DM co-pilot, music practice journal, finance tracker, or autonomous stock trader depending on what you attach to it.

## Core Value

A message goes in, an AI response that knows your history comes back — and what mattered gets written to Obsidian so the next conversation starts smarter.

## Requirements

### Validated

(None yet — ship to validate)

### Active

**Core Infrastructure**
- [ ] Pi harness runs in Docker, accepts prompts via RPC (stdin/stdout JSONL), returns structured responses
- [ ] Sentinel Core container (FastAPI/Python) receives message envelopes, routes to Pi, returns responses
- [ ] LM Studio on Mac Mini confirmed as AI backend via OpenAI-compatible API
- [ ] Docker Compose base structure established with override file pattern
- [ ] Sentinel can receive a message and return an AI response end-to-end (v0.1)

**Memory Layer**
- [ ] Obsidian Local REST API plugin installed and accessible from Core container
- [ ] Core retrieves relevant user context from vault before building Pi prompt
- [ ] Core writes session summaries to vault after each interaction
- [ ] System demonstrates cross-session memory (references a prior conversation) (v0.2)

**Interfaces**
- [ ] Standard Message Envelope format defined and stable
- [ ] Discord bot interface container operational — sends envelopes, posts responses
- [ ] Apple Messages bridge (Mac-side component + HTTP bridge to Core)
- [ ] Docker Compose override pattern validated with first real interface (v0.3)

**AI Layer Polish**
- [ ] Provider configuration via environment variables (no hardcoding)
- [ ] At least two providers testable (LM Studio + one other)
- [ ] Error handling, retry logic, and timeout management in Pi client
- [ ] Pi harness wrapper API finalized — clean contract rest of system depends on (v0.4)

**Pathfinder 2e Module**
- [ ] NPC management — create, update, query NPCs via interface
- [ ] Session note capture with structured Obsidian output
- [ ] Dialogue generation on demand
- [ ] Module delivered as Docker Compose override file (v0.5)

**Music Lesson Module**
- [ ] Log a practice session via Discord or Messages
- [ ] Query practice history in natural language
- [ ] Obsidian structure for `/music/` established (v0.6)

**Coder Interface**
- [ ] Separate Pi environment for coding tasks
- [ ] Routing to cloud model (Claude API) for heavy tasks
- [ ] Module scaffolding generator (v0.7)

**Personal Finance Module**
- [ ] OFX file import pipeline (parse, deduplicate, categorize)
- [ ] AI-assisted transaction categorization with correction learning
- [ ] Budget tracking with alerts
- [ ] Natural language spending queries
- [ ] Monthly summary auto-generated to Obsidian (v0.8)

**Autonomous Stock Trader (Paper)**
- [ ] Alpaca paper trading API connected
- [ ] Personal rules file format established and enforced before every decision
- [ ] Watchlist research loop with thesis notes written to Obsidian
- [ ] Trade execution in paper mode with full rationale audit trail
- [ ] PDT rule counter and hard limits enforced
- [ ] 30-day paper trading run producing readable logs (v0.9)

**Live Trading (Explicit Opt-In)**
- [ ] Live Alpaca API keys configurable separately from paper keys
- [ ] Human approval flow for trades via interface
- [ ] Emergency stop command halts all trading immediately
- [ ] Weekly performance summary via interface (v0.10)

**Polish & Community**
- [ ] External contributor documentation pass
- [ ] MODULE-SPEC.md published for module authoring
- [ ] GitHub repository structured for open contribution (v1.0)

### Out of Scope

- Multi-user / multi-tenant support — personal tool, not a platform; complexity not worth it for v1.0
- Mobile app — Discord and Messages interfaces handle mobile without a native app
- Proprietary cloud storage of Obsidian vault — defeats the "own your data" principle
- Real-time audio/voice interface — interesting future direction, not v1.0
- Non-open-source backend dependencies for any interface — open source first is a design principle
- Obsidian Sync (official) — iCloud sync of vault folder is sufficient if multi-device is needed later
- Crypto, options, futures, margin trading in the trading module — equities and ETFs only, reduces regulatory and technical complexity

## Context

- **Developer:** Tom Boucher, personal project
- **Existing vault:** Has an existing Obsidian dataset to import into Mnemosyne via `inbox/imports/` staging approach
- **Hardware:** Mac Mini running LM Studio (local model serving); Docker host may be the same Mac Mini or a separate machine on the same LAN
- **Repository state:** Greenfield — docs and scaffolding exist (PRD, ARCHITECTURE-Core.md) but no implementation yet
- **Pi harness:** Using [pi-mono/coding-agent](https://github.com/badlogic/pi-mono) — a TypeScript/Node package. Integration approach is RPC mode (stdin/stdout JSONL). Pi version must be pinned; project is under active development.
- **Obsidian API:** Using [obsidian-local-rest-api](https://github.com/coddingtonbear/obsidian-local-rest-api) community plugin for all programmatic vault reads/writes. Obsidian must be running on the Mac for this to work.
- **Two open questions before v0.1:** (1) Confirm exact pi RPC JSONL message format by reading pi source; (2) pin a specific npm version of `@mariozechner/pi-coding-agent`

## Constraints

- **Tech Stack**: Python/FastAPI for Sentinel Core — fits the AI/automation ecosystem, async handles concurrent interfaces cleanly
- **Tech Stack**: Node.js 22 LTS for Pi harness container — pi-mono requires >=20.6.0; Node 22 LTS is the correct choice (Node 24 is not yet LTS)
- **Tech Stack**: Docker Compose with `include` directive (Compose v2.20+) — preferred over `-f` flag stacking; resolves paths relative to each included file's directory
- **Dependencies**: Pi harness is a black box in v0.x — call it cleanly, do not modify it
- **Dependencies**: Obsidian must be running on the Mac for the REST API to be available — cannot be containerized
- **Dependencies**: LM Studio must have a model loaded before the Sentinel can respond — operational dependency, not a code dependency
- **Security**: Shared secret token (`X-Sentinel-Key`) for interface authentication — sufficient for personal local-network use, not enterprise-grade
- **Trading**: Live trading module requires explicit opt-in configuration — cannot be enabled accidentally; paper trading must precede live
- **Trading**: Cash-only, long-only, equities/ETFs only in v1 — no margin, no shorts, no derivatives

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Pi harness as AI execution layer | Handles conversation loop, tool calls, skill dispatch out of the box — avoids rebuilding this infrastructure | — Pending |
| Obsidian Local REST API for vault writes | Avoids race conditions of direct file writes; supports surgical edits (PATCH) and full-text search | — Pending |
| LM Studio as primary AI provider | OpenAI-compatible API makes provider swap frictionless — just change env vars | — Pending |
| FastAPI (Python) for Sentinel Core | Best ecosystem fit for AI/automation; async handles concurrent interfaces | — Pending |
| Docker Compose `include` directive for modularity | Base compose never changes; `include` (Compose v2.20+) resolves paths per-file, cleaner than `-f` stacking | — Pending |
| Pi HTTP bridge inside Pi container | Pi itself is stdin/stdout only — a thin Fastify bridge (~50-100 lines) exposes it over Docker network; not provided by pi-mono | — Pending |
| Alpaca for trading API | Commission-free, paper/live at same endpoints (different keys), built for algorithmic trading | — Pending |
| `ofxtools` for OFX parsing | Well-maintained Python library; open source; handles the XML complexity of OFX format | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-10 after initialization*
