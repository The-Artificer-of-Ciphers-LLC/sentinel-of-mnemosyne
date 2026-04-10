# Roadmap: Sentinel of Mnemosyne v1.0

## Overview

From bare Docker Compose to a fully-operational personal AI assistant platform. Each phase delivers a testable vertical slice — the system grows from a raw message-in/response-out loop to a multi-interface, memory-aware assistant with specialized modules for gaming, music, finance, and autonomous trading.

## Phases

- [x] **Phase 1: Core Loop** — Pi harness + Sentinel Core FastAPI, end-to-end AI response
- [x] **Phase 2: Memory Layer** — Obsidian integration, context retrieval, session summaries, cross-session memory (completed 2026-04-10)
- [ ] **Phase 3: Interfaces** — Discord bot, Apple Messages bridge, X-Sentinel-Key auth
- [ ] **Phase 4: AI Provider** — Multi-provider support, retry logic, fallback, model registry
- [ ] **Phase 5: Pathfinder 2e Module** — NPC management, session notes, dialogue generation
- [ ] **Phase 6: Music Lesson Module** — Practice logging, history queries, Obsidian vault structure
- [ ] **Phase 7: Coder Interface** — Separate Pi environment, cloud routing, module scaffolding
- [ ] **Phase 8: Personal Finance Module** — OFX import, categorization, budgets, natural language queries
- [ ] **Phase 9: Autonomous Stock Trader (Paper)** — Alpaca paper trading, rules enforcement, 30-day run
- [ ] **Phase 10: Live Trading** — Live keys, human approval flow, weekly performance summary
- [ ] **Phase 11: Community & Polish** — Contributor docs, MODULE-SPEC.md, GitHub structure

## Phase Details

### Phase 1: Core Loop
**Goal**: End-to-end core message loop — a user message goes in, an AI response comes back, system is containerized with Docker Compose include pattern.
**Depends on**: Nothing (first phase)
**Requirements**: CORE-01, CORE-02, CORE-03, CORE-04, CORE-05, CORE-06, CORE-07
**Success Criteria** (what must be TRUE):
  1. `docker compose up` starts Pi harness + Sentinel Core in one command
  2. POST /message returns an AI-generated response end-to-end
  3. Token guard rejects oversized messages with HTTP 422
  4. Pi harness respawns automatically if the subprocess crashes
**Plans**: 3 plans

Plans:
- [x] 01-01: Wave 0 scaffolding — Docker Compose include pattern, Python project, test stubs
- [x] 01-02: Pi harness container — Fastify bridge, pi-adapter.ts, JSONL protocol
- [x] 01-03: Sentinel Core FastAPI — POST /message, token guard, LM Studio client, 11 tests

### Phase 2: Memory Layer
**Goal**: The Sentinel remembers. Before answering, it reads user context from Obsidian. After answering, it writes a session summary. A second conversation can reference what happened in the first.
**Depends on**: Phase 1
**Requirements**: MEM-01, MEM-02, MEM-03, MEM-04, MEM-05, MEM-06, MEM-07, MEM-08
**Success Criteria** (what must be TRUE):
  1. Obsidian health check detects when vault is unavailable and Core degrades gracefully (no crash)
  2. User context file is retrieved and injected into the Pi prompt before each response
  3. Session summary is written to Obsidian after each interaction
  4. A second conversation with the same user_id can demonstrate a specific detail from a prior session
  5. Token budget ceiling enforced — context injection never exceeds configured limit
  6. Write-selectivity threshold documented and enforced
**Plans**: 2 plans

Plans:
- [x] 02-01-PLAN.md — Wave 1: ObsidianClient, config/models/main.py wiring, bridge.ts messages array, test scaffolding
- [x] 02-02-PLAN.md — Wave 2: POST /message Phase 2 flow — context injection, BackgroundTasks write, token budget

### Phase 3: Interfaces
**Goal**: The Sentinel is reachable from Discord and Apple Messages. All Core endpoints require authentication.
**Depends on**: Phase 2
**Requirements**: IFACE-01, IFACE-02, IFACE-03, IFACE-04, IFACE-05, IFACE-06
**Success Criteria** (what must be TRUE):
  1. Discord bot responds in threads with deferred acknowledgement within 3s
  2. Apple Messages bridge functional as tier-2 interface (feature-flagged)
  3. X-Sentinel-Key required on all non-health Core endpoints
  4. Message Envelope format stable and all interfaces conform to it
**Plans**: TBD

### Phase 4: AI Provider
**Goal**: Provider configuration via env vars. Multiple providers switchable. Retry logic and fallback.
**Depends on**: Phase 3
**Requirements**: PROV-01, PROV-02, PROV-03, PROV-04, PROV-05
**Success Criteria** (what must be TRUE):
  1. Switch from LM Studio to Claude API by changing only env vars
  2. Failed Pi calls retry 3 times with exponential backoff before failing
  3. When LM Studio unavailable, Core routes to Claude API automatically
  4. Model registry maps model names to context window sizes
**Plans**: TBD

### Phase 5: Pathfinder 2e Module
**Goal**: DM co-pilot. Create and query NPCs, capture session notes, generate in-character dialogue.
**Depends on**: Phase 3
**Requirements**: PF2E-01, PF2E-02, PF2E-03, PF2E-04, PF2E-05
**Success Criteria** (what must be TRUE):
  1. NPC created via interface, saved to `/pathfinder/npcs/{name}.md`
  2. NPC queried and details returned accurately
  3. Session note captured and structured correctly in vault
  4. Dialogue generated in-character for a named NPC
  5. Module added to system via single compose include entry
**Plans**: TBD

### Phase 6: Music Lesson Module
**Goal**: Practice journal. Log sessions, query history in natural language.
**Depends on**: Phase 3
**Requirements**: MUSIC-01, MUSIC-02, MUSIC-03
**Success Criteria** (what must be TRUE):
  1. Practice session logged via Discord, written to `/music/practice-log/{date}.md`
  2. Natural language query ("what did I work on last week?") returns accurate answer
  3. `/music/` vault structure established and documented
**Plans**: TBD

### Phase 7: Coder Interface
**Goal**: Separate coding environment, cloud routing for heavy tasks, module scaffolding generator.
**Depends on**: Phase 4
**Requirements**: CODER-01, CODER-02, CODER-03
**Success Criteria** (what must be TRUE):
  1. Coder Pi environment isolated from production Sentinel
  2. Heavy tasks route to Claude API based on configurable threshold
  3. User can request a new module stub and receive a populated directory
**Plans**: TBD

### Phase 8: Personal Finance Module
**Goal**: OFX import, AI categorization with learning, budget alerts, natural language queries, monthly reports.
**Depends on**: Phase 3
**Requirements**: FIN-01, FIN-02, FIN-03, FIN-04, FIN-05, FIN-06, FIN-07, FIN-08
**Success Criteria** (what must be TRUE):
  1. OFX file imported via Discord, duplicates skipped across imports
  2. Transactions AI-categorized; user corrections learned for future imports
  3. Budget thresholds trigger alerts
  4. Natural language spending query returns accurate answer
  5. Recurring charges identified; new ones flagged
  6. Monthly summary auto-generated at month end
**Plans**: TBD

### Phase 9: Autonomous Stock Trader (Paper)
**Goal**: 30-day paper trading run. Personal rules enforced. Full rationale audit trail.
**Depends on**: Phase 4
**Requirements**: TRADE-01, TRADE-02, TRADE-03, TRADE-04, TRADE-05, TRADE-06, TRADE-07
**Success Criteria** (what must be TRUE):
  1. Alpaca paper trades placed and queried via alpaca-py
  2. Rules file read before every decision; rules check included in rationale
  3. Watchlist research loop writes thesis notes per ticker
  4. Pre-trade validation enforces PDT counter, position size, daily trade limits
  5. Emergency stop halts all activity immediately
  6. 30-day run completed with human-readable logs
**Plans**: TBD

### Phase 10: Live Trading
**Goal**: Live trading with human approval gate. Separate keys, weekly performance summary.
**Depends on**: Phase 9 (30-day paper run complete)
**Requirements**: TRADE-08, TRADE-09, TRADE-10
**Success Criteria** (what must be TRUE):
  1. Live and paper API keys use distinct env var names (no accidental cross-wiring)
  2. Trade proposals sent via interface; execution waits for YES confirmation
  3. Weekly P&L summary delivered to user and written to Obsidian
**Plans**: TBD

### Phase 11: Community & Polish
**Goal**: Open for contributors. Documented setup, module spec, GitHub structure.
**Depends on**: Phase 10
**Requirements**: COMM-01, COMM-02, COMM-03
**Success Criteria** (what must be TRUE):
  1. New contributor can set up the system from README alone
  2. MODULE-SPEC.md complete — new module authors have a clear contract
  3. GitHub repo has labeled issues, PR template, accurate README
**Plans**: TBD

## Backlog

### Phase 999.1: Pi-mono Upgrade Strategy & Regression Testing (BACKLOG)

**Goal:** Design a safe process for adopting new pi-mono releases — including regression test suite for the pi-harness adapter, red/green migration approach to validate the new version before cutover, and rollback strategy if the upgrade breaks the RPC protocol.

**Context:** pi-mono is under active development and releases breaking changes every 2-4 days (noted in STATE.md). The adapter pattern in Phase 1 isolates pi-mono contact to `pi-adapter.ts`, but there's currently no automated way to detect when an upgrade breaks the RPC contract.

**Ideas to explore:**
- Regression test harness for pi-adapter.ts (mock pi subprocess, verify JSONL protocol)
- Red/green migration: run old and new versions in parallel, compare outputs
- Semantic versioning contract: what constitutes a breaking change in pi-mono?
- Automated upgrade CI: pin → test → promote workflow
- Canary deployment pattern for pi-harness container

**Requirements:** TBD
**Plans:** 2/2 plans complete

Plans:
- [ ] TBD (promote with /gsd-review-backlog when ready)

### Phase 999.2: Messaging Business Registration & Receive-Without-Texting Options (BACKLOG)

**Goal:** Explore alternatives to the personal Apple Messages bridge — investigate registering as a business to send/receive SMS/iMessage programmatically, or other receive mechanisms that don't require texting a known personal number first.

**Ideas to explore:**
- Apple Business Register / Apple Messages for Business — enables rich iMessage conversations with customers without a personal phone number
- Twilio / Bandwidth / Vonage — programmatic SMS send/receive via a dedicated number; no personal iMessage dependency
- Google Voice number as a receive endpoint polled via API
- Short code registration for SMS (higher throughput, regulatory cost)
- WhatsApp Business API — if the user is open to non-iMessage options
- Trade-offs: cost, setup complexity, Apple-ecosystem lock-in vs. cross-platform reach

**Requirements:** TBD
**Plans:** 0 plans

Plans:
- [ ] TBD (promote with /gsd-review-backlog when ready)
