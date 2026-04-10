# Roadmap: Sentinel of Mnemosyne

## Overview

The Sentinel evolves from a bare core loop (message in, AI response out) through persistent memory, a Discord interface, provider hardening, and five domain modules -- culminating in a community-ready open-source platform. Each phase delivers a verifiable capability; later phases depend on earlier ones and no module work begins until the core+memory+interface stack is proven.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Core Loop** - Pi harness + Sentinel Core deliver end-to-end message-to-AI-response flow
- [ ] **Phase 2: Memory Layer** - Obsidian vault integration gives the Sentinel cross-session memory
- [ ] **Phase 3: Discord Interface + Envelope** - Discord bot and stable message envelope make the Sentinel usable by a human
- [ ] **Phase 4: AI Provider Polish** - Multi-provider support, fallback, and stable Pi client contract
- [ ] **Phase 5: Pathfinder 2e Module** - First domain module validates the module pattern with TTRPG tools
- [ ] **Phase 6: Music Module** - Practice logging and history queries via the Sentinel
- [ ] **Phase 7: Coder Interface** - Separate coding Pi environment with cloud model routing
- [ ] **Phase 8: Finance Module** - OFX import, AI categorization, budgets, and spending queries
- [ ] **Phase 9: Paper Trader** - Alpaca paper trading with rules enforcement and full audit trail
- [ ] **Phase 10: Live Trading** - Real-money trading with human approval and emergency controls
- [ ] **Phase 11: Polish & Community** - Documentation and open-source readiness

## Phase Details

### Phase 1: Core Loop
**Goal**: A user can send a message to the Sentinel and receive a coherent AI response end-to-end
**Depends on**: Nothing (first phase)
**Requirements**: CORE-01, CORE-02, CORE-03, CORE-04, CORE-05, CORE-06, CORE-07
**Success Criteria** (what must be TRUE):
  1. User sends a JSON message via curl to POST /message and receives a coherent AI response within 30 seconds
  2. `docker compose up` starts the full system (Core + Pi harness) with zero manual steps beyond having LM Studio running
  3. Changing the LM Studio model URL requires only an environment variable change, no code edits
  4. A message that would exceed the model's context window is rejected with a clear error before being sent to LM Studio
  5. Pi harness version is pinned and an adapter layer isolates the rest of the system from Pi internals
**Plans**: TBD
**UI hint**: no

**Research flags:**
- Pi HTTP bridge has limited documentation -- read pi-mono sdk.md and rpc.md before writing the bridge
- Budget time for JSONL framing edge cases (U+2028/U+2029)

### Phase 2: Memory Layer
**Goal**: The Sentinel remembers prior conversations and uses that context to give better responses
**Depends on**: Phase 1
**Requirements**: MEM-01, MEM-02, MEM-03, MEM-04, MEM-05, MEM-06, MEM-07, MEM-08
**Success Criteria** (what must be TRUE):
  1. User has a conversation, starts a new session, and the Sentinel references a specific detail from the prior session without being prompted
  2. When Obsidian is not running, the Sentinel still responds to messages (degraded, without memory) instead of crashing
  3. Not every trivial exchange produces a vault note -- the write-selectivity policy is observable (e.g., a "hello" does not generate a session file)
  4. Vault search can be swapped from keyword to a different backend without changing any calling code
  5. Context injection into prompts stays within a documented token budget ceiling regardless of vault size
**Plans**: TBD

**Research flags:**
- Monitor retrieval quality from this phase; the ~2,400-note degradation threshold is from third-party benchmarks
- Tiered memory (hot/warm/cold) must be designed here; retrofitting is expensive

### Phase 3: Discord Interface + Envelope
**Goal**: A human can talk to the Sentinel through Discord and the message envelope contract is stable for all future interfaces
**Depends on**: Phase 2
**Requirements**: IFACE-01, IFACE-02, IFACE-03, IFACE-04, IFACE-05, IFACE-06
**Success Criteria** (what must be TRUE):
  1. User sends a Discord message and receives an AI response that reflects their conversation history
  2. Slash commands acknowledge within 3 seconds even when the AI takes 30 seconds to respond
  3. Multi-turn conversations stay in dedicated Discord threads without mixing context
  4. An unauthenticated request to any non-health Core endpoint is rejected
  5. Apple Messages bridge works end-to-end when feature-flagged on (tier-2, best-effort)
**Plans**: TBD
**UI hint**: yes

**Research flags:**
- imsg is a one-person project; evaluate fork/maintain-locally risk before committing
- Have fallback plan (raw AppleScript + chat.db polling) for Messages bridge

### Phase 4: AI Provider Polish
**Goal**: The AI layer is stable, multi-provider, and resilient -- modules can be built on a foundation that will not shift
**Depends on**: Phase 3
**Requirements**: PROV-01, PROV-02, PROV-03, PROV-04, PROV-05
**Success Criteria** (what must be TRUE):
  1. User can switch from LM Studio to Claude API by changing only environment variables -- no code changes, no redeployment
  2. When LM Studio is unavailable, the Sentinel automatically falls back to Claude API and the user gets a response (possibly noting the fallback)
  3. Pi client retries failed requests with exponential backoff and gives up cleanly after 3 attempts with a user-facing error
  4. Each model's context window size is known to the system and enforced before prompt submission
**Plans**: TBD

**Research flags:**
- LM Studio OpenAI-compatible API compatibility is incomplete -- test streaming, function calling, and embedding endpoints against each model

### Phase 5: Pathfinder 2e Module
**Goal**: A GM can manage NPCs, capture session notes, and generate in-character dialogue through the Sentinel
**Depends on**: Phase 4
**Requirements**: PF2E-01, PF2E-02, PF2E-03, PF2E-04, PF2E-05
**Success Criteria** (what must be TRUE):
  1. User creates an NPC via the interface and later queries it -- the NPC's personality and voice notes come back accurately
  2. User captures a session note and it appears in the vault at the expected path with structured content
  3. User requests dialogue for a named NPC in a given situation and receives in-character speech consistent with that NPC's record
  4. Adding the PF2e module to a running system requires only adding an include line to Docker Compose -- no base compose changes
**Plans**: TBD
**UI hint**: yes

### Phase 6: Music Module
**Goal**: A musician can log practice sessions and query their history through natural conversation
**Depends on**: Phase 4
**Requirements**: MUSIC-01, MUSIC-02, MUSIC-03
**Success Criteria** (what must be TRUE):
  1. User logs a practice session via Discord specifying duration, pieces, and focus area -- the data appears in the vault under /music/practice-log/
  2. User asks "what did I work on last week?" and receives an accurate summary drawn from vault records
  3. The /music/ vault structure is documented and consistent across all practice entries
**Plans**: TBD
**UI hint**: yes

### Phase 7: Coder Interface
**Goal**: A developer can use a separate coding-focused Sentinel environment with cloud model routing for heavy tasks
**Depends on**: Phase 4
**Requirements**: CODER-01, CODER-02, CODER-03
**Success Criteria** (what must be TRUE):
  1. Coding tasks use a separate Pi harness instance that does not interfere with the production Sentinel
  2. A heavy coding request automatically routes to Claude API instead of the local model -- the user observes better results for complex tasks
  3. User can generate a new module scaffold and receives a populated directory structure matching the module spec
**Plans**: TBD

**Research flags:**
- Routing heuristics for when to escalate to cloud model may need a design pass

### Phase 8: Finance Module
**Goal**: A user can import bank transactions, get AI-assisted categorization, track budgets, and ask spending questions in plain English
**Depends on**: Phase 4
**Requirements**: FIN-01, FIN-02, FIN-03, FIN-04, FIN-05, FIN-06, FIN-07, FIN-08
**Success Criteria** (what must be TRUE):
  1. User uploads an OFX file via Discord and receives confirmation of imported transactions with categories assigned
  2. Uploading the same OFX file again produces no duplicate transactions
  3. User corrects a category ("that Whole Foods charge is groceries, not dining") and the next import categorizes the same merchant correctly without asking
  4. User asks "how much did I spend on dining last month?" and receives an accurate dollar amount
  5. A monthly summary report appears in the vault at /finance/reports/ at month end
**Plans**: TBD
**UI hint**: yes

**Research flags:**
- Test OFX exports from at least 3 different banks (formatting varies significantly)
- Vault schema should support cross-module queries with trading module

### Phase 9: Paper Trader
**Goal**: The Sentinel can autonomously research stocks, propose trades, and execute them in paper mode with full rules enforcement and audit trail
**Depends on**: Phase 4
**Requirements**: TRADE-01, TRADE-02, TRADE-03, TRADE-04, TRADE-05, TRADE-06, TRADE-07
**Success Criteria** (what must be TRUE):
  1. User can see the Sentinel's watchlist research with thesis notes written to /trading/watchlist/ in the vault
  2. Paper trades execute with full rationale documented in /trading/trades/ -- every trade file shows which personal rules were checked
  3. A trade that would violate PDT limits, position size limits, or daily trade limits is blocked before submission with a clear explanation
  4. Emergency stop command immediately halts all trading activity -- confirmed by attempting a trade after stop
  5. A 30-day paper trading run produces human-readable logs before live trading configuration is even possible
**Plans**: TBD

**Research flags:**
- Wash sale detection edge cases; "substantially identical securities" is legally ambiguous -- document the interpretation used
- alpaca-py >=0.43.0 required (alpaca-trade-api is deprecated)

### Phase 10: Live Trading
**Goal**: The Sentinel can execute real trades with mandatory human approval and emergency safeguards
**Depends on**: Phase 9
**Requirements**: TRADE-08, TRADE-09, TRADE-10
**Success Criteria** (what must be TRUE):
  1. Live API keys use completely separate environment variable names from paper keys -- configuration cannot accidentally cross
  2. Before any live trade executes, the user receives a proposal via Discord and must explicitly approve it
  3. Weekly performance summary is delivered via interface with P&L and key statistics also written to the vault
**Plans**: TBD
**UI hint**: yes

### Phase 11: Polish & Community
**Goal**: The project is documented and structured so an external contributor can understand, run, and extend it
**Depends on**: Phase 10
**Requirements**: COMM-01, COMM-02, COMM-03
**Success Criteria** (what must be TRUE):
  1. A new developer can clone the repo, follow the setup guide, and have the Sentinel running within a single session
  2. MODULE-SPEC.md is complete enough that a developer can author a new module without reading Sentinel Core source code
  3. GitHub repository has labeled issues, a PR template, and an accurate README
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10 -> 11

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Core Loop | 0/0 | Not started | - |
| 2. Memory Layer | 0/0 | Not started | - |
| 3. Discord Interface + Envelope | 0/0 | Not started | - |
| 4. AI Provider Polish | 0/0 | Not started | - |
| 5. Pathfinder 2e Module | 0/0 | Not started | - |
| 6. Music Module | 0/0 | Not started | - |
| 7. Coder Interface | 0/0 | Not started | - |
| 8. Finance Module | 0/0 | Not started | - |
| 9. Paper Trader | 0/0 | Not started | - |
| 10. Live Trading | 0/0 | Not started | - |
| 11. Polish & Community | 0/0 | Not started | - |
