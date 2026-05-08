# Roadmap: Sentinel of Mnemosyne v1.0

<!--
⚠️  PLANNING ARTIFACT — DO NOT DELETE / RENAME / MOVE / OVERWRITE
This file is protected by a PreToolUse Bash hook that blocks any
rm / mv / cp-overwrite / git rm / worktree-move operation targeting
this path. Editing the file in place via Edit/Write tools IS allowed
(and required — phase status here is load-bearing for the rest of the
workflow, including STATE.md, /gsd-progress, and milestone advancement).

Deletion incidents (recovered manually): three before 2026-04-23 by AI
agents running worktree merges that touched this file. The hook is the
prevention. The chflags-uchg layer that previously sat alongside the
hook was removed 2026-04-25 because it blocked legitimate edits and
the hook is sufficient on its own.

AI agents: you ARE authorised to edit this file in place. You are NOT
authorised to delete, rename, move, or overwrite it.
-->

## Overview

From bare Docker Compose to a fully-operational personal AI assistant platform. Each phase delivers a testable vertical slice — the system grows from a raw message-in/response-out loop to a multi-interface, memory-aware assistant with specialized modules for gaming, music, finance, and autonomous trading.

## Phases

- [x] **Phase 1: Core Loop** — Pi harness + Sentinel Core FastAPI, end-to-end AI response
- [x] **Phase 2: Memory Layer** — Obsidian integration, context retrieval, session summaries, cross-session memory (completed 2026-04-10)
- [x] **Phase 3: Interfaces** — Discord bot, Apple Messages bridge, X-Sentinel-Key auth (completed 2026-04-10)
- [x] **Phase 4: AI Provider** — Multi-provider support, retry logic, fallback, model registry (completed 2026-04-10)
- [x] **Phase 5: AI Security** — Prompt injection hardening, OWASP LLM Top 10 audit, sensitive data leakage review (completed 2026-04-10)
- [x] **Phase 6: Discord Deployment Regression Fix** — Restore Discord container include (IFACE-02/03/04 regression)
- [x] **Phase 7: Phase 2 Verification + MEM-08 + MEM-05 Warm Tier** — Generate Phase 2 VERIFICATION.md, wire search_vault() callers
- [ ] **Phase 8: Requirements Traceability Repair** — Superseded by Phase 22. See 08-CONTEXT.md.
- [ ] **Phase 9: Tech Debt Cleanup** — Fix Pi bare except, remove dead send_prompt()
- [x] **Phase 10: Knowledge Migration Tool** — Import from Notion/Roam/Logseq, classify, review, restructure to Sentinel vault conventions
- [ ] **Phase 11: Pathfinder 2e Module** — NPC management, session notes, dialogue generation
- [ ] **Phase 12: Music Lesson Module** — Practice logging, history queries, Obsidian vault structure
- [ ] **Phase 13: Coder Interface** — Separate Pi environment, cloud routing, module scaffolding
- [ ] **Phase 14: Personal Finance Module** — OFX import, categorization, budgets, natural language queries
- [ ] **Phase 15: Autonomous Stock Trader (Paper)** — Alpaca paper trading, rules enforcement, 30-day run
- [ ] **Phase 16: Live Trading** — Live keys, human approval flow, weekly performance summary
- [ ] **Phase 17: Community & Polish** — Contributor docs, MODULE-SPEC.md, GitHub structure
- [ ] **Phase 18: Messaging Alternatives** — Business registration, Twilio/Vonage, Apple Messages for Business, receive-without-texting options
- [ ] **Phase 19: README & Licensing** — Keep README current as phases ship, audit dependency licenses, MIT vs Apache 2.0 vs AGPL
- [ ] **Phase 20: Pi-mono Upgrade Strategy** — Regression test harness for pi-adapter.ts, red/green migration, rollback strategy
- [x] **Phase 21: Production Recovery — Security Pipeline + Discord** — Restore InjectionFilter, OutputScanner, and Discord include deleted by commit 6cfb0d3 (completed 2026-04-11)
- [x] **Phase 22: Requirements Traceability Repair** — Execute Phase 08 scope (never run) + extend through Phase 10; fix checkboxes, Nyquist matrices, STATE.md count (completed 2026-04-11)
- [x] **Phase 23: Pi Harness /reset Route** — Add POST /reset to bridge.ts, restore configurable timeout_s; closes CORE-07 PARTIAL gap (completed 2026-04-11)
- [x] **Phase 24: Pentest Agent Wire + Missing Verification Artifacts** — Wire pentest-agent compose include (SEC-04); generate VERIFICATION.md for Phases 02, 05, 07 (completed 2026-04-11)
- [x] **Phase 25: v0.40 Pre-Beta Refactoring** — Eliminate duplicates (DUP-01–05), complete stubs (STUB-01–08), fix architecture contradictions (CONTRA-01–04), implement RD-01–RD-10 (completed 2026-04-11)
- [x] **Phase 26: Nyquist Validation Cleanup** — Create/repair VALIDATION.md for Phases 04, 06, 07, 10; add missing Discord subcommand test stubs (completed 2026-04-21)
- [x] **Phase 28: pf2e-module Skeleton + CORS** — pf2e-module FastAPI scaffold, sentinel-core proxy include, CORS for Foundry VTT (completed 2026-04-21)
- [x] **Phase 29: NPC CRUD + Obsidian Persistence** — `:pf npc create/update/show/relate/import` with Obsidian PUT/PATCH persistence (completed 2026-04-22)
- [x] **Phase 30: NPC Outputs** — Token-image generation, dialogue prompt extraction, NPC export (completed 2026-04-23)
- [x] **Phase 31: Dialogue Engine** — `:pf say` + multi-turn history, conversation persistence (completed 2026-04-23)
- [x] **Phase 32: Monster Harvesting** — `:pf harvest` with components, Medicine DCs, craftable item rendering (completed 2026-04-24)
- [x] **Phase 33: Rules Engine** — `:pf rule` PF2e Remaster rules Q&A with citation, generation, decline, and reuse-cache. D-05 reuse threshold calibrated 0.80→0.70 in Phase 33.1. (completed 2026-04-25)
- [x] **Phase 34: Session Notes** — Structured session-end notes to Obsidian with NPC/location auto-tagging, real-time event log, RecapView Discord button, LLM recap with skeleton fallback (completed 2026-04-25)
- [x] **Phase 35: Foundry VTT Event Ingest** — Live event stream from Foundry → Sentinel for context awareness (completed 2026-04-25)
- [ ] **Phase 36: Foundry NPC Pull Import** — Import existing Foundry NPCs into the Sentinel vault
- [ ] **Phase 37: PF2E Per-Player Memory** — Per-player vault namespace, onboarding, recall, canonization, and deterministic Foundry chat memory projection (combines Player Interaction Vault + Foundry Chat Memory PRDs)

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
**Plans**: 3 plans

Plans:
- [x] 03-01-PLAN.md — Wave 1: APIKeyMiddleware in sentinel-core, test_auth.py (4 tests), update 31 existing tests with X-Sentinel-Key header
- [x] 03-02-PLAN.md — Wave 2: Discord bot container — bot.py, Dockerfile, compose.yml, /sentask slash command with defer+thread+Core call
- [x] 03-03-PLAN.md — Wave 3: Apple Messages bridge — bridge.py (SQLite ROWID polling), launch.sh, README.md (Full Disk Access docs)

### Phase 4: AI Provider
**Goal**: Provider configuration via env vars. Multiple providers switchable. Retry logic and fallback.
**Depends on**: Phase 3
**Requirements**: PROV-01, PROV-02, PROV-03, PROV-04, PROV-05
**Success Criteria** (what must be TRUE):
  1. Switch from LM Studio to Claude API by changing only env vars
  2. Failed Pi calls retry 3 times with exponential backoff before failing
  3. When LM Studio unavailable, Core routes to Claude API automatically
  4. Model registry maps model names to context window sizes
**Plans**: 4 plans

Plans:
- [x] 04-01-PLAN.md — Wave 1: pyproject.toml deps (litellm>=1.83.0, tenacity, anthropic), Settings provider env vars, models-seed.json
- [x] 04-02-PLAN.md — Wave 2: AIProvider Protocol (base.py), LiteLLMProvider with tenacity retry, Ollama/LlamaCpp stubs, delete LMStudioClient
- [x] 04-03-PLAN.md — Wave 3: ModelRegistry (hybrid live-fetch + seed), ProviderRouter (ConnectError-only fallback)
- [x] 04-04-PLAN.md — Wave 4: Wire main.py lifespan + message.py, update tests, full suite green

### Phase 5: AI Security
**Goal:** Audit the Sentinel for AI-specific attack surfaces — prompt injection via Obsidian vault content, user messages, or session notes; jailbreak patterns reaching the model; sensitive data leakage in context; and other OWASP LLM Top 10 risks. Harden accordingly.
**Depends on:** Phase 2
**Requirements:** SEC-01, SEC-02, SEC-03, SEC-04
**Success Criteria** (what must be TRUE):
  1. Prompt injection attack surface documented and mitigations in place
  2. Sensitive data (API keys, personal context) does not leak through model responses
  3. OWASP LLM Top 10 checklist reviewed and findings addressed
  4. Jailbreak resistance baseline documented
**Plans:** 3 plans

Plans:
- [x] 05-01-PLAN.md — Wave 1: InjectionFilter service + tests, OutputScanner service + tests, OWASP LLM Top 10 checklist
- [x] 05-02-PLAN.md — Wave 2: Wire InjectionFilter + OutputScanner into main.py lifespan and POST /message pipeline
- [x] 05-03-PLAN.md — Wave 3: Pen test agent container (garak + ofelia), docker-compose.yml include entry

### Phase 6: Discord Deployment Regression Fix
**Goal:** Restore the Discord container to the live docker-compose.yml. The include was verified uncommented at Phase 3 close but was commented out during Phase 5 work. `docker compose up` must start the Discord bot.
**Depends on:** Phase 5
**Gap Closure:** Closes IFACE-02, IFACE-03, IFACE-04 regression; restores cross-phase integration from docker-compose.yml root to interfaces/discord/compose.yml
**Requirements:** IFACE-02, IFACE-03, IFACE-04
**Success Criteria** (what must be TRUE):
  1. `docker compose up` starts the Discord bot container without manual intervention
  2. A Discord message receives an AI response end-to-end
  3. Slash command deferred acknowledgement completes within 3 seconds
**Plans:** 2 plans

Plans:
- [x] 06-01-PLAN.md — Wave 1: Uncomment discord include in docker-compose.yml
- [x] 06-02-PLAN.md — Wave 2: Integration test for IFACE-02/03/04 + DISCORD_TEST_CHANNEL_ID in .env.example

### Phase 7: Phase 2 Verification + MEM-08 + MEM-05 Warm Tier
**Goal:** Close the three Phase 2 open items: generate the missing VERIFICATION.md artifact, wire search_vault() into the production message pipeline (satisfies MEM-08 and activates the warm tier for MEM-05), and confirm tiered retrieval is actually functional end-to-end.
**Depends on:** Phase 5
**Gap Closure:** Closes Phase 2 VERIFICATION.md blocker; closes MEM-08 (search abstraction with production callers); closes MEM-05 warm tier gap (search_vault wired, not just defined)
**Requirements:** MEM-05, MEM-08
**Success Criteria** (what must be TRUE):
  1. Phase 2 VERIFICATION.md exists and passes gsd-verifier checks
  2. search_vault() is called from the production message pipeline (warm tier active)
  3. Hot → warm tier escalation path exercised in at least one test
  4. MEM-08 checkbox updated to `[x]` in REQUIREMENTS.md
**Plans:** TBD

### Phase 8: Requirements Traceability Repair (SUPERSEDED)
**Status:** SUPERSEDED by Phase 22. Phase 08 has only a CONTEXT.md — no PLAN.md, SUMMARY.md, or VERIFICATION.md were ever produced. Phase 22 executes this scope extended through Phase 10.
**Goal:** Make REQUIREMENTS.md an accurate, complete record of the milestone. Fix all stale checkboxes and run Nyquist validation on the three non-compliant phases.
**Depends on:** Phase 6, Phase 7

### Phase 9: Tech Debt Cleanup
**Goal:** Fix code quality issues identified in the v1.0 audit. Must be resolved before implementing any new features.
**Depends on:** Phase 6, Phase 7
**Gap Closure:** Closes 2 medium/low severity tech debt items from audit
**Requirements:** — (no new requirements; correctness fixes to existing code)
**Success Criteria** (what must be TRUE):
  1. `message.py` bare `except Exception` replaced with targeted exception handling — `KeyError` on malformed Pi JSON surfaces as a protocol error, not a silent fallthrough to ai_provider
  2. Dead method `send_prompt()` removed from `pi_adapter.py`; no callers existed, deletion confirmed by grep
**Plans:** TBD

### Phase 10: Knowledge Migration Tool
**Goal:** Build a migration pipeline that ingests data from existing personal knowledge systems (Notion, Roam Research, Logseq, legacy Obsidian vaults, nanoclaw, etc.), classifies and categorizes content, presents it for user review, then restructures it to match Sentinel vault conventions.
**Depends on:** Phase 9
**Requirements:** TBD
**Success Criteria** (what must be TRUE):
  1. Source data from at least one system (Notion JSON export or Logseq markdown) parsed without data loss
  2. Classified content presented for user review in batches via Discord before any vault write
  3. Approved items written to correct Sentinel vault paths with proper frontmatter
  4. Duplicate detection prevents re-importing already-present content
  5. Dry-run mode shows what would be written without committing
**Plans:** TBD

### Phase 11: Pathfinder 2e Module
**Goal**: Deliver the first module under the Path B contract. A FastAPI container that registers with sentinel-core via POST /modules/register at startup, exposes NPC management and session note endpoints, and is added to the stack via a single `docker compose --profile pathfinder` entry. This is the v0.5 reference implementation for all future modules.
**Depends on**: Phase 9
**Requirements**: PF2E-01, PF2E-02, PF2E-03, PF2E-04, PF2E-05
**Success Criteria** (what must be TRUE):
  1. NPC created via interface, saved to `/pathfinder/npcs/{name}.md`
  2. NPC queried and details returned accurately
  3. Session note captured and structured correctly in vault
  4. Dialogue generated in-character for a named NPC
  5. Module added to system via single compose include entry
**Plans**: TBD

### Phase 12: Music Lesson Module
**Goal**: Practice journal. Log sessions, query history in natural language.
**Depends on**: Phase 9
**Requirements**: MUSIC-01, MUSIC-02, MUSIC-03
**Success Criteria** (what must be TRUE):
  1. Practice session logged via Discord, written to `/music/practice-log/{date}.md`
  2. Natural language query ("what did I work on last week?") returns accurate answer
  3. `/music/` vault structure established and documented
**Plans**: TBD

### Phase 13: Coder Interface
**Goal**: Separate coding environment, cloud routing for heavy tasks, module scaffolding generator.
**Depends on**: Phase 9
**Requirements**: CODER-01, CODER-02, CODER-03
**Success Criteria** (what must be TRUE):
  1. Coder Pi environment isolated from production Sentinel
  2. Heavy tasks route to Claude API based on configurable threshold
  3. User can request a new module stub and receive a populated directory
**Plans**: TBD

### Phase 14: Personal Finance Module
**Goal**: OFX import, AI categorization with learning, budget alerts, natural language queries, monthly reports.
**Depends on**: Phase 9
**Requirements**: FIN-01, FIN-02, FIN-03, FIN-04, FIN-05, FIN-06, FIN-07, FIN-08
**Success Criteria** (what must be TRUE):
  1. OFX file imported via Discord, duplicates skipped across imports
  2. Transactions AI-categorized; user corrections learned for future imports
  3. Budget thresholds trigger alerts
  4. Natural language spending query returns accurate answer
  5. Recurring charges identified; new ones flagged
  6. Monthly summary auto-generated at month end
**Plans**: TBD

### Phase 15: Autonomous Stock Trader (Paper)
**Goal**: 30-day paper trading run. Personal rules enforced. Full rationale audit trail.
**Depends on**: Phase 9
**Requirements**: TRADE-01, TRADE-02, TRADE-03, TRADE-04, TRADE-05, TRADE-06, TRADE-07
**Success Criteria** (what must be TRUE):
  1. Alpaca paper trades placed and queried via alpaca-py
  2. Rules file read before every decision; rules check included in rationale
  3. Watchlist research loop writes thesis notes per ticker
  4. Pre-trade validation enforces PDT counter, position size, daily trade limits
  5. Emergency stop halts all activity immediately
  6. 30-day run completed with human-readable logs
**Plans**: TBD

### Phase 16: Live Trading
**Goal**: Live trading with human approval gate. Separate keys, weekly performance summary.
**Depends on**: Phase 15 (30-day paper run complete)
**Requirements**: TRADE-08, TRADE-09, TRADE-10
**Success Criteria** (what must be TRUE):
  1. Live and paper API keys use distinct env var names (no accidental cross-wiring)
  2. Trade proposals sent via interface; execution waits for YES confirmation
  3. Weekly P&L summary delivered to user and written to Obsidian
**Plans**: TBD

### Phase 17: Community & Polish
**Goal**: Open for contributors. Documented setup, module spec, GitHub structure.
**Depends on**: Phase 16
**Requirements**: COMM-01, COMM-02, COMM-03
**Success Criteria** (what must be TRUE):
  1. New contributor can set up the system from README alone
  2. MODULE-SPEC.md complete — new module authors have a clear contract
  3. GitHub repo has labeled issues, PR template, accurate README
**Plans**: TBD

### Phase 18: Messaging Alternatives
**Goal:** Evaluate and implement alternatives to the personal Apple Messages bridge — business SMS/iMessage registration, dedicated number options, or cross-platform messaging that doesn't require texting a personal number first.
**Depends on:** Phase 9
**Requirements:** TBD
**Success Criteria** (what must be TRUE):
  1. Options evaluated: Apple Messages for Business, Twilio/Vonage, WhatsApp Business API
  2. Chosen option implemented as a Sentinel interface container
  3. Receive-without-texting-first capability confirmed working
**Plans:** TBD

### Phase 19: README & Licensing
**Goal:** Keep README.md accurate as phases ship and lock in the right open-source license given the dependency stack (pi-mono, discord.py, alpaca-py) and potential contributor community.
**Depends on:** Phase 16
**Requirements:** TBD
**Success Criteria** (what must be TRUE):
  1. License chosen and committed (MIT, Apache 2.0, or AGPL) with rationale documented
  2. Dependency license audit complete — no incompatibilities
  3. README covers setup, architecture, and interface configuration accurately for the shipped phases
  4. CONTRIBUTING.md and CODE_OF_CONDUCT.md present (can be stubs ahead of Phase 17)
**Plans:** TBD

### Phase 20: Pi-mono Upgrade Strategy
**Goal:** Safe, repeatable process for adopting new pi-mono releases — regression test suite for the JSONL RPC adapter, red/green parallel validation, and documented rollback path.
**Depends on:** Phase 13
**Requirements:** TBD
**Success Criteria** (what must be TRUE):
  1. Regression test harness covers pi-adapter.ts RPC protocol (mock pi subprocess, verify JSONL contract)
  2. Red/green migration: old and new versions run in parallel, outputs compared before cutover
  3. Rollback procedure documented and tested
  4. Upgrade CI workflow: pin → test → promote
**Plans:** TBD

### Phase 21: Production Recovery — Security Pipeline + Discord
**Goal:** Restore the production system to a working state after commit 6cfb0d3 deleted the security pipeline and Discord include. POST /message must handle requests without AttributeError, InjectionFilter and OutputScanner must be wired into the lifespan, and the Discord container include must be active in docker-compose.yml.
**Depends on:** Phase 6
**Gap Closure:** Closes production regression introduced by 6cfb0d3; restores SEC-01, SEC-02, IFACE-02, IFACE-03, IFACE-04
**Requirements:** SEC-01, SEC-02, CORE-03, IFACE-02, IFACE-03, IFACE-04
**Status:** COMPLETE (verified 2026-04-11, 7/7 truths verified)
**Plans:** 1 plan

Plans:
- [x] 21-01-PLAN.md — Restore InjectionFilter, OutputScanner, Discord include; 107 tests passing

### Phase 22: Requirements Traceability Repair
**Goal:** Execute the work originally scoped for Phase 08 (never run). Repair all stale documentation artifacts so that REQUIREMENTS.md, PROJECT.md, per-phase VALIDATION.md files, and STATE.md accurately reflect what has actually been shipped through Phases 1–10.
**Depends on:** Phase 21
**Gap Closure:** Closes GAP-03 from v0.1-v0.4 milestone audit; supersedes Phase 08
**Requirements:** (documentation only — no new requirements)
**Success Criteria** (what must be TRUE):
  1. REQUIREMENTS.md checkboxes reflect actual Phase 1–10 completion state
  2. PROJECT.md phase checkboxes match actual completed phases
  3. 01-VALIDATION.md and 03-VALIDATION.md have nyquist_compliant: true with Nyquist matrices
  4. STATE.md completed_phases count accurate
  5. 08-CONTEXT.md annotated as superseded by Phase 22
**Plans:** 2 plans

Plans:
- [ ] 22-01-PLAN.md — Restore REQUIREMENTS.md (2B-01..06), fix STATE.md count, annotate 08-CONTEXT.md
- [ ] 22-02-PLAN.md — Restore PROJECT.md, create 01-VALIDATION.md and 03-VALIDATION.md with Nyquist matrices

### Phase 23: Pi Harness /reset Route
**Goal:** Add a `POST /reset` route to `bridge.ts` so that `pi_adapter.py`'s reset-after-exchange call succeeds (200) instead of silently returning 404. Without this, the Pi harness accumulates full session history across every exchange, risking LM Studio RAM exhaustion after approximately 5 calls.
**Depends on:** Phase 22
**Gap Closure:** Closes GAP-04; completes CORE-07 (currently PARTIAL)
**Requirements:** CORE-07
**Success Criteria** (what must be TRUE):
  1. POST /reset returns HTTP 200 with `{ status: 'ok' }`
  2. Pi subprocess receives `{"type":"new_session"}` on each reset call
  3. pi_adapter.py reset_session() confirmed calling correct URL
  4. configurable timeout_s restored with PI_TIMEOUT_S env var support
  5. Integration test for /reset passes
**Plans:** TBD

### Phase 24: Pentest Agent Wire + Missing Verification Artifacts
**Goal:** Wire the pentest agent into `docker-compose.yml` (SEC-04) and generate missing VERIFICATION.md artifacts for Phases 02, 05, and 07.
**Depends on:** Phase 21, Phase 22
**Gap Closure:** Closes GAP-05 (SEC-04 compose wire), GAP-06 (missing VERIFICATION.md for phases 02/05/07)
**Requirements:** SEC-04
**Success Criteria** (what must be TRUE):
  1. security/pentest-agent/compose.yml active include in docker-compose.yml
  2. No service name conflicts or port conflicts
  3. 02-VERIFICATION.md created for Phase 02 (Memory Layer)
  4. 05-VERIFICATION.md created for Phase 05 (AI Security)
  5. 07-VERIFICATION.md created for Phase 07 (MEM-08/Warm Tier)
**Plans:** TBD

### Phase 25: v0.40 Pre-Beta Refactoring
**Goal:** Eliminate all duplicates (DUP-01–05), complete all stubs (STUB-01–08), fix architecture contradictions (CONTRA-01–04), and implement RD-01 through RD-10 as defined in V040-REFACTORING-DIRECTIVE.md. Ships when all 10 acceptance criteria in Section 10 are true.
**Depends on:** Phase 23, Phase 24
**Requirements:** SEC-04
**Success Criteria** (what must be TRUE):
  1. `grep -rn "def call_core"` returns 0 results in interfaces/
  2. `grep -rn "NotImplementedError"` returns 0 results in app/
  3. `pytest` in sentinel-core exits 0; `vitest run` in pi-harness exits 0
  4. All test files listed in V040-REFACTORING-DIRECTIVE.md §9 exist and pass
  5. `docker compose config` succeeds with no warnings
  6. `security/pentest/jailbreak_baseline.py` passes; SEC-04 checkbox checked in REQUIREMENTS.md
  7. Every architecture contradiction in V040-REFACTORING-DIRECTIVE.md §4 resolved (docs match code)
  8. `shared/sentinel_client.py` exists and is imported by both interfaces; no inline `call_core()` remains
  9. All 10 directives (RD-01–RD-10) implemented per V040-REFACTORING-DIRECTIVE.md §5
  10. Route registry matches §7 exactly: 4 routes in sentinel-core, 3 in pi-harness
**Plans:** 4/4 plans complete

### Phase 26: Nyquist Validation Cleanup
**Goal:** Bring Nyquist compliance to the 4 phases that shipped without it — create VALIDATION.md for Phases 04 and 06, repair the non-compliant VALIDATION.md files for Phases 07 and 10, and add the two missing Phase 10 bot subcommand test stubs. Closes all remaining LOW-severity tech debt from the v0.1–v0.4 audit.
**Depends on:** Phase 22, Phase 25
**Gap Closure:** Closes Nyquist tech debt from v0.1–v0.4 audit (phases 04, 06, 07, 10); closes missing test stubs for 2B-01 and 2B-03
**Requirements:** — (quality/documentation only; no new feature requirements)
**Success Criteria** (what must be TRUE):
  1. `04-VALIDATION.md` exists with `nyquist_compliant: true` and a Nyquist test matrix
  2. `06-VALIDATION.md` exists with `nyquist_compliant: true` and a Nyquist test matrix
  3. `07-VALIDATION.md` updated: `nyquist_compliant: true`, `status: complete`
  4. `10-VALIDATION.md` updated: `nyquist_compliant: true`, `status: complete`
  5. `test_subcommands.py` and `test_thread_persistence.py` expanded; 12 tests pass
**Status:** COMPLETE (verified 2026-04-21, 5/5 must-haves, human UAT passed)
**Plans:** 3/3 plans complete

Plans:
- [x] 26-01-PLAN.md — Discord test suite expansion (4 unit tests + 1 integration stub, conftest fixture)
- [x] 26-02-PLAN.md — Repair 07-VALIDATION.md and 10-VALIDATION.md (Nyquist compliance)
- [x] 26-03-PLAN.md — Create 04-VALIDATION.md and 06-VALIDATION.md from scratch

---

## Milestone v0.5 — The Dungeon

### Phase 28: pf2e-module Skeleton + CORS
**Goal:** Stand up the pf2e-module FastAPI container, register it with Sentinel Core's module gateway, and add CORS middleware to Core — proving the Path B module pattern with a health check and unlocking all downstream phases.
**Depends on:** Phase 26 / Phase 27
**Requirements:** MOD-01, MOD-02
**Success Criteria** (what must be TRUE):
  1. `docker compose --profile pf2e up` starts pf2e-module container without errors
  2. `POST /modules/register` from pf2e-module succeeds at startup; `GET /modules` returns `pathfinder` in the list
  3. `GET /modules/pathfinder/healthz` returns 200 via Core proxy
  4. Foundry browser `fetch()` to Sentinel Core with `X-Sentinel-Key` does not fail with a CORS error
  5. `allow_origins` in CORSMiddleware uses an explicit LAN IP list (not wildcard — wildcard blocks credential headers)
**Status:** ✅ COMPLETE (2026-04-21)
**Plans:** 3 plans (28-01 module skeleton + register, 28-02 CORS, 28-03 healthz proxy)

### Phase 29: NPC CRUD + Obsidian Persistence
**Goal:** Create, update, query, relate, and bulk-import NPCs via Discord commands, with all NPC data persisted as structured YAML-frontmatter notes under `mnemosyne/pf2e/npcs/`.
**Depends on:** Phase 28
**Requirements:** NPC-01, NPC-02, NPC-03, NPC-04, NPC-05
**Success Criteria** (what must be TRUE):
  1. `/pf npc create` creates an Obsidian note at `mnemosyne/pf2e/npcs/{slug}.md` with YAML frontmatter
  2. `/pf npc update` surgically PATCHes the note frontmatter without overwriting prose sections
  3. `/pf npc show` returns a Discord embed with NPC summary
  4. NPC note includes a `relationships:` frontmatter block after `/pf npc relate`
  5. Bulk import from a Foundry actor list JSON creates corresponding Obsidian notes for each actor
**Status:** ✅ COMPLETE (2026-04-22)
**Plans:** 5 plans (29-01..05 covering CRUD endpoints, Discord wiring, relations, bulk import)

### Phase 30: NPC Outputs
**Goal:** Produce all four NPC output formats from a stored Obsidian NPC profile: Foundry VTT PF2e actor JSON, Midjourney token prompt text, formatted stat block, and PDF stat card.
**Depends on:** Phase 29
**Requirements:** OUT-01, OUT-02, OUT-03, OUT-04
**Success Criteria** (what must be TRUE):
  1. `:pf npc export <name>` attaches a `.json` file; imported into Foundry VTT without errors
  2. Exported JSON passes Foundry PF2e actor schema validation (schema derived from live actor export)
  3. `:pf npc token <name>` returns a copyable `/imagine` prompt string in Discord
  4. `:pf npc stat <name>` returns a formatted stat block as a Discord embed
  5. `:pf npc pdf <name>` attaches a printable PDF stat card
**Status:** ✅ COMPLETE (2026-04-23)
**Plans:** 3 plans (30-01 helper modules + RED tests, 30-02 endpoints + REGISTRATION_PAYLOAD, 30-03 Discord bot wiring)
**Tests:** 23 module tests + 19 Discord subcommand tests + 12 shared client tests, all green

### Phase 31: Dialogue Engine
**Goal:** Enable in-character NPC dialogue grounded in Obsidian profiles, with persistent mood state and support for multi-NPC scenes.
**Depends on:** Phase 29
**Requirements:** DLG-01, DLG-02, DLG-03
**Success Criteria** (what must be TRUE):
  1. `/pf say [npc] party says [X]` returns an in-character reply that reflects the NPC's documented personality
  2. Mood state is stored in NPC frontmatter and updated after significant interactions
  3. An aggressive encounter shifts mood toward hostile; a successful persuasion shifts toward friendly
  4. `/pf scene [npc1] [npc2] party says [X]` returns distinct replies from each NPC in their own voice
**Status:** ✅ COMPLETE (2026-04-23)
**Plans:** 5 plans (31-01..05 covering dialogue endpoint, mood persistence, multi-NPC scenes, Discord wiring)

### Phase 32: Monster Harvesting
**Goal:** Given a killed monster, produce a complete harvest report: components, Medicine DCs, craftable items with Crafting DCs, and PF2e vendor values — with batch support for multi-monster encounters.
**Depends on:** Phase 28
**Requirements:** HRV-01, HRV-02, HRV-03, HRV-04, HRV-05, HRV-06
**Success Criteria** (what must be TRUE):
  1. `/pf harvest [monster]` returns at least one harvestable component with a Medicine DC
  2. Each component lists craftable outputs (potion/poison/armor) with item level and gp/sp/cp value
  3. Each craftable item includes a Crafting skill DC
  4. For monsters not in the harvest tables, AI-generated components are marked `[GENERATED — verify]`
  5. `/pf harvest [m1] [m2] [m3]` returns an aggregated report covering all monsters
**Status:** ✅ COMPLETE (2026-04-24)
**Plans:** 5 plans (32-01..05 covering harvest engine, Medicine DC, craftable items, Discord dispatch, live UAT)
**Tests:** 89 unit + 38 module + 17/17 live UAT, all green

### Phase 33: Rules Engine
**Goal:** Answer PF2e Remaster rules questions with sourced citations, reason from rules when no direct source exists, persist every ruling to Obsidian, and decline pre-Remaster or PF1 queries.
**Depends on:** Phase 28
**Requirements:** RUL-01, RUL-02, RUL-03, RUL-04
**Success Criteria** (what must be TRUE):
  1. `/pf rules [question]` returns a ruling with a `[SOURCED: ...]` citation for a documented mechanic
  2. An edge-case question returns a ruling marked `[GENERATED — verify]` with reasoning shown
  3. The ruling is saved to `mnemosyne/pf2e/rulings/` with `verified: false` frontmatter
  4. A second identical question returns the cached ruling from Obsidian, not a new LLM call
  5. A PF1 or pre-Remaster query returns a clear decline message explaining the scope constraint
**Status:** ✅ COMPLETE (2026-04-25)
**Plans:** 5 plans (33-01 RED scaffolding, 33-02 pure transforms + corpus, 33-03 LLM adapters + threshold calibration, 33-04 HTTP routes + lifespan, 33-05 Discord bot + live UAT) + Phase 33.1 D-05 calibration gap-closure
**Tests:** 142/142 pathfinder pytest + 48/48 discord pytest + 17/17 live UAT + 16/16 in-Discord visual UAT, all green
**Notes:** D-05 reuse threshold calibrated 0.80→0.70 (F1-max) in Phase 33.1 after live UAT-8 surfaced empirical mismatch. Two bugs caught + fixed by live UAT (litellm provider prefix in embed_texts, docker compose exec name resolution).

### Phase 34: Session Notes
**Goal:** Capture structured session notes to Obsidian at session end, with auto-tagging of NPC and location links and a real-time event log with timestamps.
**Depends on:** Phase 29
**Requirements:** SES-01, SES-02, SES-03
**Success Criteria** (what must be TRUE):
  1. `/pf session end` writes a note to `mnemosyne/pf2e/sessions/YYYY-MM-DD.md` with recap, NPCs, decisions
  2. NPC names in the session note are wiki-linked to their `mnemosyne/pf2e/npcs/` pages
  3. `/pf session log [event]` appends a timestamped entry to the active session log
  4. Session notes use a consistent template structure across multiple sessions
**Status:** ✅ COMPLETE (2026-04-25)
**Plans:** 5/5 plans complete
**Tests:** 22/22 session unit + 8/8 integration + 50/50 Discord + 9/9 live UAT, all green
Plans:
- [x] 34-01-PLAN.md — Wave 0 RED test scaffolding (unit stubs, integration stubs, conftest, UAT)
- [x] 34-02-PLAN.md — Wave 1 session pure helpers + ObsidianClient.patch_heading + config settings
- [x] 34-03-PLAN.md — Wave 2 FastAPI session route (5-verb router) + LLM helpers
- [x] 34-04-PLAN.md — Wave 3 main.py registration + lifespan wiring + compose.yml env vars
- [x] 34-05-PLAN.md — Wave 4 bot.py Discord wiring (_PF_NOUNS, session branch, RecapView)

### Phase 35: Foundry VTT Event Ingest
**Goal:** A Foundry VTT JavaScript module hooks into chat messages and dice rolls, POSTs events to Sentinel Core, and receives Discord responses with roll interpretations.
**Depends on:** Phase 28
**Requirements:** FVT-01, FVT-02, FVT-03
**Success Criteria** (what must be TRUE):
  1. Foundry module installs from a zip and activates without console errors in Foundry v14+
  2. A chat message with the trigger prefix POSTs to `POST /modules/pathfinder/foundry/event` successfully
  3. A dice roll result in Foundry chat produces a hit/miss/DC interpretation in the DM's Discord channel
  4. `X-Sentinel-Key` is stored in Foundry world settings (GM-only) and sent on every POST
  5. Module declares explicit `compatibility.verified` for the installed Foundry version
**Status:** COMPLETE (2026-04-25) — all 6 plans done, FVT-01..03 requirements satisfied
**Plans:** 6 plans (6/6 complete)

Plans:
- [x] 35-01-PLAN.md — Wave 0 RED test stubs (test_foundry.py + test_discord_foundry.py + conftest gold())
- [x] 35-02-PLAN.md — Wave 1 Python backend (app/foundry.py helpers + app/routes/foundry.py + config.py)
- [x] 35-03-PLAN.md — Wave 1 Discord bot internal listener (aiohttp server + build_foundry_roll_embed)
- [x] 35-04-PLAN.md — Wave 3 main.py wiring (REGISTRATION_PAYLOAD + StaticFiles + lifespan + compose env)
- [x] 35-05-PLAN.md — Wave 4 Foundry JS module (module.json + sentinel-connector.js + package.sh + UAT)
- [x] 35-06-PLAN.md — Wave 5 Forge connectivity gap closure (webhook-first fallback + PNACORSMiddleware)

### Phase 36: Foundry NPC Pull Import
**Goal:** Enable the Foundry VTT module to pull NPC actor JSON directly from Sentinel — one click imports the actor into the world with no file attachment or copy-paste.
**Depends on:** Phase 30, Phase 35
**Requirements:** FVT-04
**Success Criteria** (what must be TRUE):
  1. `GET /modules/pathfinder/npcs/{slug}/foundry-actor` returns valid PF2e actor JSON
  2. The Foundry module presents an "Import from Sentinel" button in the actor directory
  3. Clicking the button imports the NPC actor directly into the Foundry world without errors
  4. The imported actor is identical in content to the Phase 30 file-attachment export
**Status:** In progress
**Plans:** 3 plans

Plans:
- [ ] 36-01-PLAN.md — Wave 0 RED test stubs (test_npcs.py, 7 tests covering FVT-04a..f)
- [ ] 36-02-PLAN.md — Wave 1 Python backend (routes/npcs.py + main.py wiring — CORS fix, router, REGISTRATION_PAYLOAD, lifespan)
- [ ] 36-03-PLAN.md — Wave 2 Foundry JS module (SentinelNpcImporter dialog + renderActorDirectory hook + module.json 1.1.0 + zip)

### Phase 37: PF2E Per-Player Memory
**Goal:** Players can capture notes, questions, and per-NPC knowledge during PF2E sessions into per-player vault namespaces, with deterministic recall and idempotent Foundry chat projection. Combines Player Interaction Vault (capture/recall/onboarding/canonization) and Foundry Chat Memory (post-import player-map and NPC-history projection) into one shared `mnemosyne/pf2e/players/{slug}/` schema so the two writers don't collide.
**Depends on:** Phase 29 (NPC CRUD), Phase 35 (Foundry event ingest), Phase 36 (Foundry import flow)
**Requirements:** PVL-01, PVL-02, PVL-03, PVL-04, PVL-05, PVL-06, PVL-07, FCM-01, FCM-02, FCM-03, FCM-04, FCM-05
**Source PRDs:**
- `docs/plans/PF2E-Player-Interaction-Vault-Plan.md`
- `docs/plans/PF2E-Foundry-Chat-Memory-Plan.md`
- `docs/plans/PF2E-Per-Player-Memory-Combined.md` (merged express PRD)
**Success Criteria** (what must be TRUE):
  1. First player interaction triggers onboarding and persists `profile.md` (character name, preferred name, style preset)
  2. `:pf player note|ask|npc|recall|todo|style|canonize` commands write/read to per-player paths with no cross-player leakage (`start` triggers onboarding implicitly on first use)
  3. Player recall returns concise results scoped to the requesting player's vault only
  4. Yellow rule outcomes can be canonized to green/red and recorded in `canonization.md` with provenance
  5. Foundry chat import projects player chat lines into `players/{slug}.md` (Voice Patterns, Notable Moments, Party Dynamics, Chat Timeline) deterministically
  6. Foundry chat import appends NPC-attributed lines to `## Foundry Chat History` on the matching NPC note
  7. Re-running Foundry import on the same source produces zero duplicate player or NPC entries (dedupe via `_id` or content hash key)
  8. Dry-run produces identical metric shape without mutating vault files
  9. All new behavior covered by Wave 0 RED tests written before implementation (TDD)
**Status:** ✅ COMPLETE (2026-05-07)
**Plans:** 14/14 plans executed

Plans:
- [x] 37-01-PLAN.md — Wave 0 RED tests for player_identity_resolver, player_vault_store, memory_projection_store
- [x] 37-02-PLAN.md — Wave 0 RED tests for /player/* routes and player_interaction_orchestrator
- [x] 37-03-PLAN.md — Wave 0 RED tests for foundry_memory_projection + idempotency + state-file backcompat
- [x] 37-04-PLAN.md — Wave 0 RED tests for Discord pathfinder_player_adapter command classes
- [x] 37-05-PLAN.md — Wave 0 probe test: Obsidian client accepts underscore-prefixed _aliases.json path
- [x] 37-06-PLAN.md — Wave 1 shared seam: identity resolver + vault_markdown util + player_vault_store + memory_projection_store + npc_matcher
- [x] 37-07-PLAN.md — Wave 2 orchestrator + onboard/style/state routes + main.py wiring
- [x] 37-08-PLAN.md — Wave 3 capture routes (note, ask store-only, npc per-player, todo)
- [x] 37-09-PLAN.md — Wave 4 deterministic recall engine + /player/recall route
- [x] 37-10-PLAN.md — Wave 5 canonization route + provenance back to question_id
- [x] 37-11-PLAN.md — Wave 6 foundry_memory_projection module (FCM-01..05 core)
- [x] 37-12-PLAN.md — Wave 7 Foundry import route integration + projection flags + state-file in-place extension
- [x] 37-13-PLAN.md — Wave 7 Discord adapter (pathfinder_player_adapter + dispatch + PF_NOUNS)
- [x] 37-14-PLAN.md — Wave 8 integration tests (isolation regression + idempotency end-to-end) + USER-GUIDE + architecture map (also fixed routes/foundry resolver-shape bug from plan 37-12)

### Phase 38: PF2E Multi-Step Onboarding Dialog
**Goal:** `:pf player start` becomes a stateful conversational onboarding flow — the bot asks the player for their character name, preferred name, and style preset across multiple Discord messages, persisting transient progress until the profile is complete.
**Depends on:** Phase 37
**Requirements:** PVL-01 (extension — multi-step UX layer over existing `/player/onboard` route)
**Background:** Phase 37 shipped `/player/onboard` as an atomic 4-field POST and `PlayerStartCommand` posting `{user_id}` only. Live `:pf player start` therefore 422'd until commit `2026-05-07` mitigation parsed pipe-separated args (`character_name | preferred_name | style_preset`). 37-CONTEXT.md line 129 originally specified: "until `profile.md` shows `onboarded: true` (frontmatter), `:pf player <verb>` other than `start`/`style` should redirect into onboarding completion." Phase 38 delivers that missing redirect.
**Success Criteria** (what must be TRUE):
  1. `:pf player start` with no args asks the player a question (e.g., "What is your character's name?") and persists transient state keyed by `(channel_id, user_id)`
  2. The player's next message in the same channel is interpreted as the answer (not a new `:pf` command) until the dialog completes
  3. After all three questions are answered, `/player/onboard` is called with the assembled payload and `profile.md` is created with `onboarded: true`
  4. Mid-dialog `:pf player cancel` clears transient state without writing the profile
  5. Mid-dialog reconnect (bot restart) recovers the in-flight dialog from the vault — transient state survives bot restart for at least 24h
  6. Existing pipe-separated one-shot syntax from the v0.5 mitigation continues to work unchanged (regression coverage)
  7. All new behavior covered by Wave 0 RED tests (TDD)
**Status:** Planned (not yet started)
**Plans:** TBD via /gsd-spec-phase 38
