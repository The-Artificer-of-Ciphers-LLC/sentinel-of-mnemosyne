# Requirements: Sentinel of Mnemosyne

**Defined:** 2026-04-10
**Core Value:** A message goes in, an AI response that knows your history comes back — and what mattered gets written to Obsidian so the next conversation starts smarter.

## v1 Requirements

### Core Infrastructure

- [x] **CORE-01**: Pi harness container starts and accepts HTTP POST requests via a Fastify bridge server wrapping the stdin/stdout JSONL subprocess
- [x] **CORE-02**: Pi adapter pattern established — single point of contact with pi-mono, version pinned to exact release, with documented upgrade procedure
- [x] **CORE-03**: Sentinel Core (FastAPI) receives a Message Envelope via POST /message and returns an AI response envelope
- [x] **CORE-04**: LM Studio on Mac Mini confirmed as AI backend — Core can call it and receive a completion response
- [x] **CORE-05**: Token count is calculated before every LM Studio call; calls are rejected before submission if they would exceed context window
- [x] **CORE-06**: `docker compose up` starts the full core system (Core + Pi harness) in a single command
- [x] **CORE-07**: Docker Compose `include` directive pattern established in base compose — no module or interface uses `-f` flag stacking

### Memory Layer

- [x] **MEM-01**: Obsidian Local REST API plugin accessible from Core container; health check detects when Obsidian is not running and degrades gracefully
- [x] **MEM-02**: Core retrieves user context file (`/core/users/{user_id}.md`) before building Pi prompt
- [x] **MEM-03**: Core writes session summary to vault (`/core/sessions/{date}/{user_id}-{timestamp}.md`) after each interaction
- [x] **MEM-04**: System demonstrates cross-session memory — a second conversation references a specific detail from a prior session
- [x] **MEM-05**: Tiered retrieval architecture in place — hot tier (last N interactions always loaded), warm tier (vault search on demand), cold tier (archived, not in context)
- [x] **MEM-06**: Write-selectivity policy defined — not every message exchange writes a session note; threshold documented
- [x] **MEM-07**: Token budget ceiling enforced for context injection (user context + vault search results combined)
- [x] **MEM-08**: Obsidian search interface abstracted behind a class — implementation can switch from keyword to vector search without caller changes

### Interfaces

- [x] **IFACE-01**: Standard Message Envelope defined as a Pydantic v2 model — all interfaces must produce and consume this shape
- [x] **IFACE-02**: Discord bot container operational using discord.py v2.7.x — user can send a message and receive an AI response
- [x] **IFACE-03**: Discord slash commands use deferred responses — bot acknowledges within 3 seconds, sends follow-up when AI completes
- [x] **IFACE-04**: Discord multi-turn conversations use threads — each conversation stays in a dedicated thread
- [x] **IFACE-05**: Apple Messages bridge is operational as a feature-flagged tier-2 interface — Mac-native process using imsg CLI, HTTP bridge to Core, documented Full Disk Access requirement
- [x] **IFACE-06**: All non-health Core endpoints require `X-Sentinel-Key` header authentication

### AI Provider

- [x] **PROV-01**: All provider URLs and API keys configured via environment variables — no hardcoded endpoints anywhere in the codebase
- [x] **PROV-02**: At least two AI providers testable by changing only env vars (LM Studio + Claude API)
- [x] **PROV-03**: Pi client has error handling, retry logic (3 attempts, exponential backoff), and hard 30-second timeout
- [x] **PROV-04**: Model configuration registry maps each model name to its context window size and capabilities
- [x] **PROV-05**: Provider fallback configured — when LM Studio is unavailable, Core can route to Claude API

### AI Security

- [x] **SEC-01**: Prompt injection attack surface documented and mitigations in place — InjectionFilter service guards all vault content and user messages before they reach the model
- [x] **SEC-02**: Sensitive data (API keys, personal context) does not leak through model responses — OutputScanner service scrubs responses before delivery
- [x] **SEC-03**: OWASP LLM Top 10 checklist reviewed and all applicable findings addressed
- [ ] **SEC-04**: Jailbreak resistance baseline documented — automated pen test agent (garak + ofelia) runs weekly and writes results to Obsidian; first executed baseline report present

### Knowledge Migration Tool (2nd Brain)

- [x] **2B-01**: 27-command Discord subcommand system operational — _SUBCOMMAND_PROMPTS (12) + _PLUGIN_PROMPTS (8) wired in bot.py; at least 20 subcommands mapped to vault interaction patterns
- [x] **2B-02**: asyncio.gather() parallel reads 5 self/ files — message.py reads identity.md, methodology.md, goals.md, relationships.md, style.md concurrently before building Pi prompt
- [x] **2B-03**: Thread ID persistence to ops/discord-threads.md — _persist_thread_id() writes channel→thread mappings to vault on each new conversation
- [x] **2B-04**: Thread IDs reloaded on bot startup — setup_hook() reads discord-threads.md and restores channel→thread mapping before accepting commands
- [x] **2B-05**: mnemosyne/self/ vault structure with stub files — identity.md, methodology.md, goals.md, relationships.md present in mnemosyne/self/
- [x] **2B-06**: mnemosyne/notes/, ops/, templates/ directories present — created by Phase 10 with correct vault layout

### Pathfinder 2e Module

- [ ] **PF2E-01**: User can create an NPC record via the interface — name, personality, voice notes saved to `/pathfinder/npcs/{name}.md`
- [ ] **PF2E-02**: User can query an NPC — system retrieves the record and returns relevant details
- [ ] **PF2E-03**: User can capture a session note — saved to `/pathfinder/sessions/{date}.md`
- [ ] **PF2E-04**: Dialogue generation — given an NPC name and a situation, system generates in-character dialogue consistent with the NPC record
- [ ] **PF2E-05**: Module delivered as a Docker Compose `include` file — adding PF2e to a running system requires only adding it to the compose includes

### Music Lesson Module

- [ ] **MUSIC-01**: User can log a practice session via Discord — duration, pieces, focus area written to `/music/practice-log/{date}.md`
- [ ] **MUSIC-02**: User can query practice history in natural language — "what did I work on last week?" returns a useful answer
- [ ] **MUSIC-03**: Vault structure for `/music/` established and documented

### Coder Interface

- [ ] **CODER-01**: Separate Pi harness environment for coding tasks — operates independently from production Sentinel
- [ ] **CODER-02**: Heavy coding tasks route to Claude API — configurable threshold for local vs. cloud routing
- [ ] **CODER-03**: Module scaffolding generator — user can request a new module stub and receive a populated directory structure

### Personal Finance Module

- [ ] **FIN-01**: User can import an OFX file via Discord attachment — system parses it and confirms receipt
- [ ] **FIN-02**: Duplicate transactions are detected and skipped across multiple imports of overlapping date ranges
- [ ] **FIN-03**: Imported transactions are AI-categorized — each transaction gets a category; user can correct with a reply
- [ ] **FIN-04**: User corrections to categories are learned — same merchant categorized correctly on next import without re-asking
- [ ] **FIN-05**: Budget definitions can be set in Obsidian — system alerts when a category approaches or exceeds budget
- [ ] **FIN-06**: User can ask spending questions in natural language — "how much did I spend on dining last month?" returns a correct answer
- [ ] **FIN-07**: Recurring charge detection — charges on a regular cadence are identified and listed; new recurring charges flagged
- [ ] **FIN-08**: Monthly summary report auto-generated to `/finance/reports/{YYYY-MM}-summary.md` at month end

### Autonomous Stock Trader (Paper)

- [ ] **TRADE-01**: Alpaca paper trading API connected using alpaca-py — module can place and query paper trades
- [ ] **TRADE-02**: Personal rules file at `/trading/rules/my-rules.md` is read before every trading decision; rules check included in rationale
- [ ] **TRADE-03**: Watchlist research loop operational — AI generates thesis notes per ticker, writes to `/trading/watchlist/{ticker}.md`
- [ ] **TRADE-04**: Paper trades executed with full rationale written to `/trading/trades/{date}-{ticker}.md`
- [ ] **TRADE-05**: Pre-trade validation layer enforced before every order: PDT counter (rolling 5-business-day window), position size limit, daily trade limit
- [ ] **TRADE-06**: Emergency stop command immediately halts all trading activity — tested and confirmed working
- [ ] **TRADE-07**: 30-day paper trading run completed and logs are human-readable before live trading configuration is even possible

### Live Trading

- [ ] **TRADE-08**: Live Alpaca API keys use separate environment variable names from paper keys — cannot accidentally point live keys at paper endpoint
- [ ] **TRADE-09**: Human approval flow operational — system sends trade proposal via interface, waits for YES confirmation before executing
- [ ] **TRADE-10**: Weekly performance summary delivered via interface — P&L and key statistics written to Obsidian and surfaced to user

### Community & Polish

- [ ] **COMM-01**: External contributor documentation complete — setup guide, architecture overview, contribution guidelines
- [ ] **COMM-02**: MODULE-SPEC.md published — complete guide for authoring a new Sentinel module
- [ ] **COMM-03**: GitHub repository structured for open contribution — issues labeled, PR template present, README accurate

## v2 Requirements

### Advanced Memory

- **VMEM-01**: Vector database integration (ChromaDB or Qdrant) for semantic vault search — add when vault exceeds ~2,400 notes and keyword search quality degrades
- **VMEM-02**: Graph-based memory for entity relationships — NPCs, people, projects linked across modules

### Enhanced Interfaces

- **VIFACE-01**: Telegram interface container
- **VIFACE-02**: Slack interface container
- **VIFACE-03**: SMS interface via Twilio

### Media & Discovery

- **VMEDIA-01**: ListenBrainz integration — pull listening history into music module
- **VMEDIA-02**: Discogs wantlist integration — "I love this track" adds release to Discogs wantlist
- **VMEDIA-03**: Vinyl/CD collection management in Obsidian

### Advanced Gaming

- **VPF2E-01**: Foundry VTT integration — receive real-time combat events, push NPC reactions back
- **VPF2E-02**: Campaign timeline tracking with world state

### Trading Expansion

- **VTRADE-01**: Streaming market data for real-time research (vs. batch REST pulls)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Multi-user / multi-tenant | Personal tool; complexity not justified |
| Mobile app | Discord + Messages cover mobile without native app |
| Web UI dashboard | Open WebUI already exists; Sentinel's value is backend + memory |
| Voice interface | TTS/STT pipeline complexity; Discord text covers the use case |
| Proprietary cloud storage for vault | Defeats "own your data" principle |
| Obsidian Sync (paid) | iCloud sync of vault folder is sufficient |
| Crypto, options, futures, margin trading | Equities/ETFs only in v1; regulatory and technical complexity |
| Direct bank API connections | No credentials stored; OFX export flow is sufficient and safer |
| SQLite/PostgreSQL for core data | Obsidian vault is the database; adding another store creates sync complexity |
| Vector database at launch | Start with full-text search; add vectors when retrieval quality demands it |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CORE-01 | Phase 1 | Complete |
| CORE-02 | Phase 1 | Complete |
| CORE-03 | Phase 1 | Complete |
| CORE-04 | Phase 1 | Complete |
| CORE-05 | Phase 1 | Complete |
| CORE-06 | Phase 1 | Complete |
| CORE-07 | Phase 1 | Complete |
| MEM-01 | Phase 2 | Complete |
| MEM-02 | Phase 2 | Complete |
| MEM-03 | Phase 2 | Complete |
| MEM-04 | Phase 2 | Complete |
| MEM-05 | Phase 7 | Complete |
| MEM-06 | Phase 2 | Complete |
| MEM-07 | Phase 2 | Complete |
| MEM-08 | Phase 7 | Complete |
| IFACE-01 | Phase 3 | Complete |
| IFACE-02 | Phase 6 | Complete |
| IFACE-03 | Phase 6 | Complete |
| IFACE-04 | Phase 6 | Complete |
| IFACE-05 | Phase 3 | Complete |
| IFACE-06 | Phase 3 | Complete |
| PROV-01 | Phase 4 | Complete |
| PROV-02 | Phase 4 | Complete |
| PROV-03 | Phase 4 | Complete |
| PROV-04 | Phase 4 | Complete |
| PROV-05 | Phase 4 | Complete |
| SEC-01 | Phase 5 | Complete |
| SEC-02 | Phase 5 | Complete |
| SEC-03 | Phase 5 | Complete |
| SEC-04 | Phase 5 | Pending |
| PF2E-01 | Phase 11 | Pending |
| PF2E-02 | Phase 11 | Pending |
| PF2E-03 | Phase 11 | Pending |
| PF2E-04 | Phase 11 | Pending |
| PF2E-05 | Phase 11 | Pending |
| MUSIC-01 | Phase 12 | Pending |
| MUSIC-02 | Phase 12 | Pending |
| MUSIC-03 | Phase 12 | Pending |
| CODER-01 | Phase 13 | Pending |
| CODER-02 | Phase 13 | Pending |
| CODER-03 | Phase 13 | Pending |
| FIN-01 | Phase 14 | Pending |
| FIN-02 | Phase 14 | Pending |
| FIN-03 | Phase 14 | Pending |
| FIN-04 | Phase 14 | Pending |
| FIN-05 | Phase 14 | Pending |
| FIN-06 | Phase 14 | Pending |
| FIN-07 | Phase 14 | Pending |
| FIN-08 | Phase 14 | Pending |
| TRADE-01 | Phase 15 | Pending |
| TRADE-02 | Phase 15 | Pending |
| TRADE-03 | Phase 15 | Pending |
| TRADE-04 | Phase 15 | Pending |
| TRADE-05 | Phase 15 | Pending |
| TRADE-06 | Phase 15 | Pending |
| TRADE-07 | Phase 15 | Pending |
| TRADE-08 | Phase 16 | Pending |
| TRADE-09 | Phase 16 | Pending |
| TRADE-10 | Phase 16 | Pending |
| COMM-01 | Phase 17 | Pending |
| COMM-02 | Phase 17 | Pending |
| COMM-03 | Phase 17 | Pending |
| 2B-01 | Phase 10 | Complete |
| 2B-02 | Phase 10 | Complete |
| 2B-03 | Phase 10 | Complete |
| 2B-04 | Phase 10 | Complete |
| 2B-05 | Phase 10 | Complete |
| 2B-06 | Phase 10 | Complete |

**Coverage:**
- v1 requirements: 68 total (58 original + SEC-01..04 added 2026-04-10 + 2B-01..06 added 2026-04-11)
- Mapped to phases: 68
- Unmapped: 0

---
*Requirements defined: 2026-04-10*
*Last updated: 2026-04-11 — Phase 22: extended through Phase 10; added 2B-01..06; STATE.md and Nyquist matrices repaired*
