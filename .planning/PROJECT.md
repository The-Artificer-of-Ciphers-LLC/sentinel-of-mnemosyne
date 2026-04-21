# Sentinel of Mnemosyne

## What This Is

A self-hosted, containerized AI assistant platform built for personal use. The Sentinel wires together a LiteLLM-compatible AI provider (LM Studio on a Mac Mini, or any OpenAI-compatible endpoint), an Obsidian vault as persistent memory, and pluggable module containers — so the same engine can serve as a DM co-pilot, music practice journal, finance tracker, or autonomous stock trader depending on what you attach to it.

**Architecture (Path B — v0.40+):** Discord and other interfaces POST to Sentinel Core. Core calls LiteLLM-direct for AI responses. Modules register with Core via `POST /modules/register` and receive proxied requests via `POST /modules/{name}/{path}`. Pi harness is optional (`--pi` profile) for agentic coding tasks.

## Core Value

A message goes in, an AI response that knows your history comes back — and what mattered gets written to Obsidian so the next conversation starts smarter.

## Requirements

### Validated

- ✓ Pi harness container + Fastify bridge, exact version pin, adapter pattern — v0.1
- ✓ POST /message → AI response (LiteLLM-direct in Path B) — v0.1
- ✓ LM Studio as AI backend, OpenAI-compatible API — v0.1
- ✓ Docker Compose `include` directive pattern established — v0.1
- ✓ Obsidian REST API accessible; graceful degradation when unavailable — v0.2
- ✓ Context retrieval from vault before each response — v0.2
- ✓ Session summary written to vault after each interaction — v0.2
- ✓ Cross-session memory demonstrated — v0.2
- ✓ Tiered retrieval: hot/warm/cold tiers + vault search wired — v0.2/v0.4
- ✓ Write-selectivity threshold documented and enforced — v0.2
- ✓ Token budget ceiling for context injection (25% pre-guard) — v0.2
- ✓ Obsidian search abstracted behind a class (search_vault) — v0.4
- ✓ Standard Message Envelope (Pydantic v2, optional source/channel_id) — v0.3
- ✓ Discord bot operational (discord.py v2.7.x), /sen slash command — v0.3
- ✓ Discord deferred responses within 3s, thread-based conversations — v0.3
- ✓ Apple Messages bridge (feature-flagged, macOS Full Disk Access) — v0.3
- ✓ X-Sentinel-Key auth on all non-health endpoints — v0.3
- ✓ LiteLLM-direct, all provider config via env vars — v0.4
- ✓ Two+ providers testable by changing env vars only — v0.4
- ✓ Retry logic, exponential backoff, configurable timeout — v0.4
- ✓ Model registry: name → context window + capabilities — v0.4
- ✓ Provider fallback (LM Studio unavailable → Claude API) — v0.4
- ✓ InjectionFilter: guards vault content + user messages — v0.4
- ✓ OutputScanner: scrubs responses for credential/PII leakage — v0.4
- ✓ OWASP LLM Top 10 checklist reviewed and findings addressed — v0.4
- ✓ Pentest agent (garak + ofelia) wired into compose (SEC-04) — v0.40
- ✓ 27-command Discord subcommand system operational — v0.4
- ✓ asyncio.gather() parallel reads of 5 self/ vault files — v0.4
- ✓ Thread ID persistence and reload across bot restarts — v0.4
- ✓ mnemosyne/ vault structure (self/, notes/, ops/, templates/) — v0.4
- ✓ Module API gateway: POST /modules/register + POST /modules/{name}/{path} — v0.40
- ✓ Pi removed from base stack; optional via `--pi` profile — v0.40
- ✓ sentinel.sh profile-based Docker Compose wrapper — v0.40
- ✓ shared/sentinel_client.py: canonical HTTP client for all interfaces — v0.40
- ✓ GET /status + GET /context/{user_id} routes in sentinel-core — v0.40

### Active

**Pathfinder 2e Module (v0.5)**
- [ ] NPC management — create, update, query NPCs via interface
- [ ] Session note capture with structured Obsidian output
- [ ] Dialogue generation on demand
- [ ] Module delivered as Docker Compose include (Path B reference implementation)

**Music Lesson Module (v0.6)**
- [ ] Log a practice session via Discord or Messages
- [ ] Query practice history in natural language
- [ ] Obsidian structure for `/music/` established

**Coder Interface (v0.7)**
- [ ] Separate Pi environment for coding tasks
- [ ] Routing to cloud model (Claude API) for heavy tasks
- [ ] Module scaffolding generator

**Personal Finance Module (v0.8)**
- [ ] OFX file import pipeline (parse, deduplicate, categorize)
- [ ] AI-assisted transaction categorization with correction learning
- [ ] Budget tracking with alerts
- [ ] Natural language spending queries
- [ ] Monthly summary auto-generated to Obsidian

**Autonomous Stock Trader — Paper (v0.9)**
- [ ] Alpaca paper trading API connected
- [ ] Personal rules file format established and enforced
- [ ] Watchlist research loop with thesis notes to Obsidian
- [ ] Trade execution in paper mode with full rationale audit trail
- [ ] PDT rule counter and hard limits enforced
- [ ] 30-day paper run producing readable logs

**Live Trading (v0.10)**
- [ ] Live Alpaca API keys separate from paper keys
- [ ] Human approval flow for trades via interface
- [ ] Emergency stop halts all trading immediately
- [ ] Weekly performance summary via interface

**Polish & Community (v1.0)**
- [ ] External contributor documentation complete
- [ ] MODULE-SPEC.md published
- [ ] GitHub repository structured for open contribution

### Out of Scope

- Multi-user / multi-tenant support — personal tool, not a platform
- Mobile app — Discord and Messages handle mobile
- Web UI dashboard — Open WebUI exists; Sentinel's value is backend + memory
- Voice interface — TTS/STT pipeline complexity; Discord text covers the use case
- Proprietary cloud storage for vault — defeats "own your data" principle
- Obsidian Sync (paid) — iCloud sync of vault folder is sufficient
- Crypto, options, futures, margin trading — equities/ETFs only in v1
- Direct bank API connections — OFX export flow is sufficient and safer
- SQLite/PostgreSQL for core data — Obsidian vault is the database
- Vector database at launch — start with full-text search; add vectors when quality demands it

## Context

- **Developer:** Tom Boucher, personal project
- **Architecture:** Path B (v0.40+) — LiteLLM-direct chat, module API gateway for extensibility, Pi optional for coding tasks
- **Codebase:** ~109K LOC (Python + TypeScript), 131 sentinel-core tests + 12 Discord tests passing
- **Hardware:** Mac Mini running LM Studio (local model serving); Docker host on the same LAN
- **Existing vault:** Obsidian vault with mnemosyne/self/, notes/, ops/, templates/ structure established
- **Pi harness:** Optional (`sentinel.sh --pi`); demoted from primary AI layer to optional agentic coding tool
- **Obsidian API:** obsidian-local-rest-api plugin; Obsidian must be running on the Mac
- **Module pattern:** Path B reference implementation is Phase 11 (Pathfinder); modules register at startup, receive proxied requests

## Constraints

- **Tech Stack**: Python/FastAPI for Sentinel Core — fits the AI/automation ecosystem, async handles concurrent interfaces cleanly
- **Tech Stack**: Node.js 22 LTS for Pi harness container — pi-mono requires >=20.6.0; Node 22 LTS is the correct choice
- **Tech Stack**: Docker Compose with `include` directive (Compose v2.20+) — preferred over `-f` flag stacking
- **Architecture**: Path B — LiteLLM-direct is the canonical AI call path; Pi is optional, not in the message route
- **Dependencies**: Pi harness is a black box in v0.x — call it cleanly via sentinel.sh --pi, do not modify it
- **Dependencies**: Obsidian must be running on the Mac for the REST API to be available — cannot be containerized
- **Dependencies**: LM Studio must have a model loaded before the Sentinel can respond — operational dependency
- **Security**: Shared secret token (`X-Sentinel-Key`) for interface authentication — sufficient for personal local-network use
- **Modules**: Module containers must implement `POST /healthz` and call `POST /modules/register` at startup
- **Trading**: Live trading module requires explicit opt-in configuration — paper trading must precede live
- **Trading**: Cash-only, long-only, equities/ETFs only in v1

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Pi harness as AI execution layer (v0.1) | Handles conversation loop, tool calls out of the box | Implemented v0.1; demoted to optional v0.7+ per Path B pivot |
| Obsidian Local REST API for vault writes | Avoids race conditions; supports surgical edits and search | Implemented |
| LM Studio as primary AI provider | OpenAI-compatible API makes provider swap frictionless | Implemented; LiteLLM-direct wraps it |
| FastAPI (Python) for Sentinel Core | Best ecosystem fit for AI/automation; async handles concurrent interfaces | Implemented |
| Docker Compose `include` directive for modularity | Base compose never changes; Compose v2.20+ resolves paths per-file | Implemented |
| Pi HTTP bridge inside Pi container | Pi is stdin/stdout only — thin Fastify bridge exposes it over Docker network | Implemented |
| **Path B: LiteLLM-direct (v0.40)** | Architecture crisis — Pi was bypassed in Phase 25 message route; full replan executed | Pi removed from base stack; LiteLLM-direct is canonical AI call path |
| **Module API gateway (v0.40)** | Path B extensibility model — modules register at startup, receive proxied requests | POST /modules/register + proxy implemented; Phase 11 is reference impl |
| **shared/sentinel_client.py (v0.40)** | DUP-04: call_core() was inline in both interfaces; shared package eliminates duplication | SentinelCoreClient used by all interfaces |
| Alpaca for trading API | Commission-free, paper/live at same endpoints (different keys), built for algorithmic trading | Pending |
| `ofxtools` for OFX parsing | Well-maintained Python library; handles XML complexity of OFX format | Pending |

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
*Last updated: 2026-04-21 after v0.40 milestone — Path B architecture pivot, module gateway, 35 requirements validated*
