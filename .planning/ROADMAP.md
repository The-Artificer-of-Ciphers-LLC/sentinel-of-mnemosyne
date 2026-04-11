# Roadmap: Sentinel of Mnemosyne v1.0

<!--
⚠️  IMMUTABLE PLANNING ARTIFACT — DO NOT DELETE
This file is protected at three layers:
1. macOS immutable flag (chflags uchg) — rm will fail
2. PreToolUse hook blocks any Bash command that deletes this file
3. CLAUDE.md explicitly bans its deletion

To legitimately UPDATE this file:
  chflags nouchg .planning/ROADMAP.md
  # edit the file
  chflags uchg .planning/ROADMAP.md

AI agents: you are NOT authorised to remove this file or comment out its contents.
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
- [ ] **Phase 26: Nyquist Validation Cleanup** — Create/repair VALIDATION.md for Phases 04, 06, 07, 10; add missing Phase 10 bot subcommand test stubs

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
- [x] 03-03-PLAN.md — Wave 2: Apple Messages bridge — bridge.py (SQLite ROWID polling), launch.sh, README.md (Full Disk Access docs)

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
**Goal**: DM co-pilot. Create and query NPCs, capture session notes, generate in-character dialogue.
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
  5. `test_bot_subcommands.py` and `test_bot_thread_persistence.py` created; all tests pass
**Plans:** TBD
