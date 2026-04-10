# Project Research Summary

**Project:** Sentinel of Mnemosyne
**Domain:** Self-hosted containerized AI assistant platform with persistent memory and pluggable domain modules
**Researched:** 2026-04-10
**Confidence:** HIGH (stack and pitfalls HIGH; features and architecture MEDIUM-HIGH)

## Executive Summary

Sentinel of Mnemosyne is a personal AI assistant platform distinguished by three things no comparable tool combines: Obsidian vault as the memory substrate (human-readable, git-versionable, portable), multi-interface access from a single AI core (Discord first, Apple Messages second), and domain-specific modules (Pathfinder, music, finance, trading) that share memory rather than living in silos. The architecture is a FastAPI orchestration layer (Sentinel Core) backed by a Node.js Pi harness for AI execution, with Obsidian as the operational database. The right build sequence is Core then Memory Loop then Discord Interface then Modules, in that order. Everything else is blocked by those four layers completing.

Two architecture decisions in PROJECT.md require immediate correction before implementation begins. First, the Node.js constraint of "24+ minimum" is wrong: pi-mono requires >=20.6.0 and Node 22 LTS is the correct production choice (Node 24 is not yet LTS). Second, Pi RPC mode communicates over stdin/stdout JSONL and has no native network port. The "port 8765" in the existing architecture docs describes a thin HTTP bridge server that wraps the Pi subprocess inside the Pi container; this bridge must be written explicitly and is not provided by pi-mono.

The single highest risk in the entire project is pi-mono release velocity: it ships breaking changes every 2-4 days on a pre-1.0 API. The entire integration strategy for the Pi layer must be built around an adapter pattern from day one, with a pinned version and a documented fallback to direct LM Studio calls if Pi becomes unusable. The second-highest risk is vault noise at scale: without a selective write policy and tiered retrieval architecture, the memory layer degrades within months. Both must be addressed in Phases 1 and 2 respectively; retrofitting them later is significantly more expensive.

---

## Key Findings

### ADR Corrections (act on these before any implementation)

| Correction | Current ADR | Correct Approach | Severity |
|------------|-------------|------------------|----------|
| Node.js version | "24+ minimum, pi-mono requirement" | Node 22 LTS (pi-mono requires >=20.6.0; Node 24 is not yet LTS) | MEDIUM |
| Pi RPC transport | "stdin/stdout JSONL, no web server required in Pi container" | Pi uses stdin/stdout internally, but a thin HTTP bridge (~50-100 lines Fastify) is required inside the Pi container so Sentinel Core can reach it over the Docker network. Port 8765 belongs to this bridge, not to pi itself. | MEDIUM |
| Docker Compose modularity | -f flag stacking | include directive (Compose v2.20+) resolves paths relative to each included file's directory, not the base file. Fix before the first module override lands. | LOW |
| Discord library | not explicitly decided | discord.py v2.7.1 -- the "discord.py is dead" era is over; forks (py-cord, disnake, nextcord) are redundant | LOW |
| Trading SDK | not explicitly decided | alpaca-py >=0.43.0 -- alpaca-trade-api is officially deprecated by Alpaca | LOW |

### Recommended Stack

The stack is well-determined with HIGH confidence. Python 3.12 with FastAPI/uvicorn/Pydantic v2 is correct for Sentinel Core: async-native, handles concurrent interface calls cleanly, dominant stack in the Python AI/automation ecosystem. Use pydantic-settings (not python-dotenv alone) for configuration -- it validates and type-checks all env vars at startup. Use httpx.AsyncClient (never requests) for all outbound HTTP calls.

**Core technologies:**
- Python 3.12 / FastAPI >=0.135.0: Sentinel Core -- async-native, Pydantic v2 integration, OpenAPI docs auto-generated
- uvicorn[standard] >=0.44.0: ASGI server -- [standard] extra installs uvloop for production throughput
- Pydantic v2 >=2.7.0: message envelope models and config validation -- use model_config = {"from_attributes": True}, not deprecated orm_mode
- httpx >=0.28.1: all async HTTP calls to Obsidian REST API and LM Studio -- singleton AsyncClient via FastAPI lifespan handler
- discord.py >=2.7.0: Discord bot interface -- actively maintained (v2.7.1 March 2026), forks are redundant
- alpaca-py >=0.43.0: trading API -- official SDK; alpaca-trade-api is deprecated
- ofxtools >=0.9.5: OFX bank export parsing -- only serious Python OFX library; OFX spec is stable
- Node.js 22 LTS / @mariozechner/pi-coding-agent pinned to 0.66.1: Pi harness -- pin exact npm version; releases break the API every 2-4 days
- Docker Compose v2 with include directive: module orchestration -- use "docker compose" (no hyphen); include not -f stacking

**What not to use:** requests (blocks event loop), alpaca-trade-api (deprecated), py-cord/disnake/nextcord (redundant forks), Pydantic v1 syntax, python-dotenv alone, docker-compose v1 CLI, readline for Pi JSONL parsing (splits on Unicode line separators U+2028/U+2029), SQLite/PostgreSQL for core data (Obsidian is the database).

### Expected Features

The core value proposition is the memory loop: message arrives, relevant vault context retrieved, prompt assembled with context, LLM responds, session summary written back to vault. Every other feature depends on this loop being solid. Do not start building modules until cross-session memory is demonstrated end-to-end.

**Must have (table stakes):**
- Multi-provider LLM support (LM Studio local + Claude API fallback) -- users expect provider flexibility
- Conversation history persistence in Obsidian vault -- without it the assistant has amnesia
- Cross-session context recall -- the Mnemosyne value prop; must work before any interface ships
- Streaming responses -- waiting for full completion feels broken in 2026
- Structured message envelope with Pydantic validation -- all interfaces depend on this contract
- Error handling with user-facing feedback -- health checks for LM Studio, Obsidian, Pi
- docker compose up single-command startup -- standard self-hosted tool expectation

**Should have (differentiators):**
- Write-back memory loop with session summaries -- most AI tools retrieve but do not write back
- Obsidian vault as human-readable, git-friendly memory substrate -- no vendor lock-in on your own memories
- Docker Compose include-based module system -- full-stack modules with own containers
- Discord bot with slash commands, thread conversations, deferred responses
- Domain modules sharing the same memory (cross-module vault queries)
- AI-assisted transaction categorization with user-correction learning
- Stock research thesis notes written to Obsidian with full audit trail

**Defer to v2+:**
- Voice interface -- TTS/STT pipeline complexity not worth it when Discord exists
- Web UI dashboard -- Open WebUI and AnythingLLM already exist; value is in the backend
- Vector database (ChromaDB/Qdrant) -- start with Obsidian REST API full-text search; add vectors when vault exceeds ~2,400 notes and conceptual retrieval degrades
- Real-time market data streaming -- REST API batch pulls sufficient for paper trading
- Crypto/options/margin trading -- equities and ETFs only for v1 per PROJECT.md

### Architecture Approach

The architecture is a clean three-layer system: interface layer (dumb translators converting platform messages to/from the Sentinel Message Envelope), orchestration layer (Sentinel Core handles routing, context assembly, session management, and all Obsidian reads/writes), and execution layer (Pi harness wraps LM Studio via a thin HTTP bridge that proxies to stdin/stdout JSONL subprocess internally). All interfaces are stateless translators; all business logic lives in Core; modules communicate with Core via HTTP and never touch Obsidian or Pi directly.

**Major components:**
1. Sentinel Core (FastAPI) -- receives message envelopes, resolves user identity, runs 9-stage context assembly pipeline, routes to Pi or module, writes session notes and user profile updates to vault
2. Pi Harness container (Node.js) -- thin Fastify HTTP server (~50-100 lines) accepting POST from Core, proxying to pi subprocess via stdin/stdout JSONL; pin @mariozechner/pi-coding-agent to exact version
3. Obsidian Local REST API (host Mac) -- vault reads, writes, and full-text search via HTTPS port 27124; self-signed cert requires verify=False in httpx; Obsidian desktop app must be running
4. Interface containers (Discord, Messages) -- Discord bot uses discord.py with deferred responses and 2000-char chunking; Messages bridge is a Mac-native process (cannot be containerized) using imsg CLI + HTTP bridge pattern
5. Module containers -- lightweight modules are Pi skill files only; heavy modules (finance, trading) get own containers that register with Core; all vault writes requested through Core

**Key patterns:**
- Context assembly pipeline is the most important component to build well: 9-stage pipeline from identity resolution through response write-back
- Token budget hard ceiling per retrieval (2000 tokens user context + 2000 tokens vault results) prevents runaway token usage
- Obsidian search interface must be abstracted -- today calls /search/simple/, later adds vector search; rest of system never knows
- Trading: LLM proposes trades, deterministic rules engine vetoes them, human approves in live mode -- LLM never has direct access to order execution

### Critical Pitfalls

1. **Pi-mono dependency churn** -- releases every 2-4 days with breaking changes (v0.65.0 removed session events, v0.63.0 changed API key methods). Prevention: pin exact npm version from day 1, build adapter layer as single point of contact with Pi, write integration tests against JSONL contract not Pi internals, document fallback to direct LM Studio API. Must be established in Phase 1.

2. **Vault noise degrades memory quality** -- every interaction writing to vault creates noise; at ~2,400 notes keyword search fails for conceptual queries; a 500-note vault is already 375K tokens. Prevention: tiered memory architecture (hot = last N interactions always loaded; warm = semantic search on demand; cold = archive never in context), write-selectivity policy, token budget ceiling on context injection. Architecture must be designed in Phase 2; cannot be retrofitted.

3. **LM Studio context window crashes** -- LM Studio crashes rather than truncating gracefully on context overflow; context length detection is unreliable across model switches. Prevention: token counting before every LM Studio call (tiktoken); pre-flight validation at 85% of context window; hard 30s API timeout; model configuration registry. Basic token counting in Phase 1; full model registry in Phase 4.

4. **Apple Messages bridge is tier-2 at best** -- Apple has no iMessage API; AppleScript automation breaks with macOS updates; TCC permissions can be silently revoked. Prevention: treat Messages as feature-flagged best-effort tier-2; Discord must be fully working before any time is spent on Messages; accept that macOS major updates will break it.

5. **Trading regulatory violations from AI autonomy** -- PDT rule violations, wash sale violations (repurchasing at a loss within 30 days), duplicate orders from connectivity glitches. Prevention: deterministic pre-trade validation layer (PDT counter + wash sale 61-day window + duplicate order detection + position limits) must exist before the first paper trade; 30-day paper validation minimum before live.

6. **Docker Compose override path resolution bugs** -- with -f flag stacking, paths must be relative to base compose file directory, causing silent failures in module subdirectories. Prevention: use include directive (Compose v2.20+); establish naming conventions and base compose contract before any module lands.

---

## Implications for Roadmap

The research supports the 10-phase structure in PROJECT.md. The ordering is dependency-driven and correct. Key refinements from research:

### Phase 1: Core Loop (v0.1)
**Rationale:** Everything is blocked until a message can enter and an AI response can exit.
**Delivers:** Sentinel Core + Pi harness container + end-to-end message to AI response flow
**Must address in this phase:**
- Pi adapter pattern (not inline code) -- the single point of contact with Pi; absorbs breaking changes
- Exact Pi version pin (0.66.1) with documented upgrade procedure
- Pi HTTP bridge server written (Fastify, ~50-100 lines) inside Pi container -- this is build scope, not provided by pi-mono
- Node 22 LTS (not 24) in Pi harness Dockerfile
- Basic token counting before LM Studio calls (tiktoken)
- 30-second hard timeout on Pi/LM Studio calls
- pydantic-settings for all configuration -- no hardcoded URLs
- Docker Compose v2 include directive structure established in base compose
**Pitfalls to avoid:** Pi-mono churn (adapter pattern), LM Studio context crashes (token counting), hardcoded config
**Research flag:** The Pi HTTP bridge has limited documentation -- read pi-mono sdk.md and rpc.md before writing the bridge; budget time to test JSONL framing edge cases.

### Phase 2: Memory Layer (v0.2)
**Rationale:** Core loop exists but has no memory. This phase completes the core value proposition.
**Delivers:** Obsidian REST API integration, context retrieval pipeline, session summary write-back, demonstrated cross-session memory
**Must address in this phase:**
- Tiered memory architecture from the start (hot/warm/cold) -- retrofitting is expensive
- Abstracted retrieval interface in obsidian_client.py -- today calls /search/simple/, later adds vector search without system knowing
- Write-selectivity policy defined -- not every interaction writes to vault
- Token budget ceiling for context injection (2000 tokens user context + 2000 tokens vault results)
- Hook points for future vector embedding layer even if not implemented yet
- httpx.AsyncClient as singleton via FastAPI lifespan for Obsidian client
- Health check: detect when Obsidian is not running and degrade gracefully
**Pitfalls to avoid:** Vault noise at scale, full vault search on every message
**Research flag:** The ~2,400-note degradation threshold is from third-party benchmarks; monitor retrieval quality in practice and be prepared to add vector embeddings earlier than Phase 4 if needed.

### Phase 3: Discord Interface + Envelope Finalization (v0.3)
**Rationale:** Discord is the primary interface; finalizing the envelope with a real interface validates the contract all future interfaces and modules depend on.
**Delivers:** Discord bot container, stable Message Envelope format, Apple Messages bridge (feature-flagged, tier-2)
**Must address in this phase:**
- discord.py v2.7.1 (not forks)
- Deferred responses for slash commands (must acknowledge within 3s; LLM takes 5-30s)
- 2000-character response chunking at natural boundaries
- Typing indicator during inference
- Thread-based multi-turn conversations
- Per-interface X-Sentinel-Key authentication (not a shared key across all interfaces)
- Apple Messages: feature flag, tier-2 designation, imsg CLI on host Mac, HTTP bridge container, Full Disk Access documented, macOS-version-specific testing
- conversation_id field added to envelope for thread tracking
**Pitfalls to avoid:** Fat interfaces (Discord bot must be a dumb translator), Discord 2000-char limit, 3-second slash command timeout
**Research flag:** imsg is a one-person project; evaluate fork/maintain-locally risk before committing; have fallback plan (raw AppleScript + chat.db polling).

### Phase 4: Provider Polish + Pi Client Finalization (v0.4)
**Rationale:** Before domain modules are added, the AI layer contract must be stable and provider story complete. Modules must not be built on a shifting foundation.
**Delivers:** Finalized Pi client API, multi-provider support (LM Studio + Claude API fallback), model configuration registry, error handling and retry logic
**Must address in this phase:**
- Model configuration registry: maps model name to context window, token limits, capabilities
- Provider fallback: local LM Studio to Claude API when local model cannot handle the query
- Pi process supervision: restart on crash, circuit breaker fallback to direct LM Studio
- Full integration test suite for Pi harness JSONL contract
**Research flag:** LM Studio OpenAI-compatible API compatibility is incomplete -- test streaming, function calling, and embedding endpoints against each model.

### Phase 5: Pathfinder 2e Module (v0.5)
**Rationale:** First domain module validates the module contract. Pathfinder is skill-only (no heavy container), keeping it simple.
**Delivers:** PF2e module as skill-only Pi integration, NPC management, session notes, dialogue generation, validated module pattern
**Must address in this phase:**
- Docker Compose include directive integration -- validate path resolution works correctly
- Module naming convention (pathfinder- service prefix)
- Compose validation script: merges all overrides, checks for port conflicts and network mismatches
- PF2e rules grounded in actual SRD data -- do not rely on LLM training data for game mechanics; hallucinated rules are a documented UX pitfall
- MODULE-SPEC.md design work starts here so internal modules validate the spec before it is published at v1.0

### Phase 6: Music Module (v0.6)
**Rationale:** Simplest domain module; validates write-back at scale; low risk second module test.
**Delivers:** Practice session logging, history queries, /music/ vault structure

### Phase 7: Coder Interface (v0.7)
**Rationale:** Separate Pi environment for coding tasks + cloud model routing.
**Delivers:** Coding-focused Pi session, Claude API routing for heavy tasks, module scaffolding generator
**Research flag:** Routing heuristics for when to escalate to cloud model may need a design pass.

### Phase 8: Finance Module (v0.8)
**Rationale:** High personal value, complex OFX import pipeline. Depends on stable memory layer and proven module pattern.
**Delivers:** OFX import with deduplication, AI-assisted categorization, correction learning, natural language spending queries, monthly summaries
**Must address in this phase:**
- Test OFX exports from at least 3 different banks (formatting varies significantly)
- Duplicate transaction detection across multiple imports of the same file
- Correction learning stored as vault documents the LLM reads at categorization time (in-context learning, not fine-tuning)
- Vault schema designed to support cross-module queries with Stock Research module

### Phase 9: Autonomous Stock Trader -- Paper (v0.9)
**Rationale:** Highest complexity and risk module. Paper trading validates the full stack before any real money is involved. 30-day minimum paper run is mandatory.
**Delivers:** Alpaca paper trading, watchlist research loop, thesis notes in Obsidian, PDT enforcement, full audit trail
**Must address in this phase:**
- alpaca-py >=0.43.0 (not alpaca-trade-api)
- ALPACA_PAPER=true as default env var; live requires explicit ALPACA_PAPER=false override
- Pre-trade validation layer: PDT counter (rolling 5-business-day window), wash sale detector (61-day window), duplicate order detector, position size limit
- Validation layer has unit tests with edge cases before first paper trade
- Emergency stop command implemented and tested
- Rules engine is deterministic Python reading /trading/rules.md -- LLM proposes, rules engine vetoes, never the reverse
**Research flag:** Wash sale detection edge cases; "substantially identical securities" is legally ambiguous -- document the interpretation used in the rules engine.

### Phase 10: Live Trading (v0.10)
**Rationale:** Live trading only after 30-day paper validation. Same code, different configuration.
**Delivers:** Live trading with human approval flow, emergency stop, weekly performance summaries
**Must address in this phase:**
- Separate API key variable names for live vs. paper (not same variable with different values)
- Human approval flow via Discord before any live order execution
- Emergency stop verified in active paper trading before live cutover
- Partial fill position tracking

### Phase 11: Polish and Community (v1.0)
**Delivers:** MODULE-SPEC.md finalized, external contributor documentation, GitHub structured for open contribution

### Phase Ordering Rationale

- Core before memory before interfaces: no interface is useful until the memory loop works; no module is useful until interfaces work
- Discord before Messages: Discord is containerized and testable without Mac-native permissions; validate the interface pattern with Discord before the fragile Mac-native bridge
- Pathfinder before Finance before Trading: modules increase in complexity and risk -- skill-only, then vault-heavy, then external APIs with fake money, then real money
- Provider polish (Phase 4) before modules (Phase 5): modules must be built on a stable Pi/LLM contract

### Research Flags

Phases likely needing deeper research or design work:
- **Phase 1:** Pi HTTP bridge implementation -- read pi-mono sdk.md and rpc.md before writing the bridge; JSONL framing edge cases (U+2028/U+2029) are documented but may have undocumented variants
- **Phase 3:** imsg project stability -- evaluate one-person project risk before committing; check for active forks
- **Phase 4:** LM Studio API compatibility matrix -- test streaming, function calling, and embedding against each model before declaring multi-provider support complete
- **Phase 9:** Wash sale detection edge cases -- document the interpretation of "substantially identical securities" used in the rules engine

Phases with standard, well-documented patterns:
- **Phase 2:** Obsidian REST API integration -- official docs and Swagger spec are complete
- **Phase 6:** Music module -- simple vault write patterns; no external API complexity
- **Phase 8:** OFX parsing -- ofxtools is well-documented; OFX spec is stable
- **Phase 10:** Live trading configuration -- Alpaca paper/live pattern is explicit in their SDK

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All core libraries verified against official sources. Version matrix confirmed. ADR corrections verified against pi-mono package.json and Docker Compose official docs. |
| Features | MEDIUM-HIGH | Table stakes derived from well-documented competitors. Differentiator claims are reasonable but unvalidated in practice -- write-back memory loop quality will only be known after building it. |
| Architecture | MEDIUM-HIGH | Core patterns (FastAPI lifespan, httpx singleton, Pi subprocess management) are standard. Pi HTTP bridge design is inferred from pi-mono docs and needs validation against actual behavior. Docker Compose include directive is HIGH confidence. |
| Pitfalls | HIGH | Pi-mono release frequency verified against release history. LM Studio context overflow crash is a documented GitHub issue. Vault noise scaling documented by third parties. All trading and Discord limits from official docs. |

**Overall confidence:** HIGH for build order and stack choices. MEDIUM for retrieval quality claims and Pi bridge implementation specifics.

### Gaps to Address

- **Obsidian vault search quality at scale:** The ~2,400-note degradation threshold is from third-party benchmarks. Monitor retrieval quality from Phase 2 and be prepared to add vector embeddings earlier than Phase 4 if needed.
- **Pi HTTP bridge implementation details:** The bridge design is inferred from the architecture. Validate actual JSONL framing behavior, event ordering, and error handling against pi-mono source before writing production code.
- **imsg reliability on target macOS version:** Confirm it works on the actual target macOS version before Phase 3 commits to it. Have a fallback plan (raw AppleScript + chat.db polling).
- **LM Studio function calling support:** Function calling support varies by model. Test the specific models planned for use before Phase 4 declares multi-model support complete.
- **Cross-module vault queries:** The vault schema enabling Finance and Stock modules to share financial context has not been designed. Needs a design pass before Phase 8.

---

## Sources

### Primary (HIGH confidence)
- [pi-mono GitHub](https://github.com/badlogic/pi-mono) -- RPC protocol docs, package.json Node.js requirement, release history
- [pi-mono RPC protocol docs](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/rpc.md) -- JSONL framing, command schema
- [FastAPI release notes](https://fastapi.tiangolo.com/release-notes/) -- version, Python requirements
- [discord.py PyPI](https://pypi.org/project/discord.py/) and [GitHub](https://github.com/Rapptz/discord.py) -- v2.7.1 active status confirmed
- [Obsidian Local REST API](https://github.com/coddingtonbear/obsidian-local-rest-api) -- endpoints, auth, rate limits, v3.6.1
- [alpaca-py GitHub](https://github.com/alpacahq/alpaca-py) -- official SDK confirmation, alpaca-trade-api deprecation
- [Alpaca paper trading docs](https://docs.alpaca.markets/docs/paper-trading) -- paper/live same API pattern
- [Alpaca PDT protection](https://alpaca.markets/support/pattern-day-trading-protection) -- PDT rule enforcement
- [Docker Compose include directive docs](https://docs.docker.com/compose/how-tos/multiple-compose-files/include/) -- path resolution behavior
- [LM Studio context overflow bug](https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/1620) -- crash behavior documented
- [Discord rate limits](https://docs.discord.com/developers/topics/rate-limits) -- 2000-char limit, interaction timeouts

### Secondary (MEDIUM confidence)
- [imsg CLI (steipete/imsg)](https://github.com/steipete/imsg) -- iMessage bridge tool evaluation
- [macpymessenger](https://github.com/ethan-wickstrom/macpymessenger) -- iMessage sending library
- [ofxtools docs](https://ofxtools.readthedocs.io/en/latest/) -- usage patterns; maintenance status unclear
- [Obsidian vault AI memory scaling](https://limitededitionjonathan.substack.com/p/stop-calling-it-memory-the-problem) -- 2400-note threshold, token math
- [Obsidian semantic search benchmarks](https://www.mandalivia.com/obsidian/semantic-search-for-your-obsidian-vault-what-i-tried-and-what-worked/) -- search quality comparison
- [FastAPI best practices](https://github.com/zhanymkanov/fastapi-best-practices) -- production patterns
- Competitor feature analysis: Open WebUI, AnythingLLM, SillyTavern, Home Assistant AI

### Tertiary (LOW confidence)
- Apple Messages AppleScript limitations -- community discussions only, no official Apple documentation
- Alpaca wash trade rules -- forum post, not official docs; verify interpretation independently

---
*Research completed: 2026-04-10*
*Ready for roadmap: yes*
