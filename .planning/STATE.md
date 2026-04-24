---
gsd_state_version: 1.0
milestone: v0.5
milestone_name: The Dungeon
status: in_progress
stopped_at: Phase 32 Plan 01 (RED test stubs) COMPLETE — 31 stubs collected + RED; Plan 02 (rapidfuzz + seed YAML) up next
last_updated: "2026-04-24T01:45:21Z"
last_activity: 2026-04-24 -- Phase 32-01 executed: 21 unit stubs + 3 integration stubs + 7 bot dispatch stubs = 31 RED, all collect cleanly; Waves 1-3 implement against this contract
progress:
  total_phases: 26
  completed_phases: 13
  total_plans: 37
  completed_plans: 44
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-21)

**Core value:** A message goes in, an AI response that knows your history comes back -- and what mattered gets written to Obsidian so the next conversation starts smarter.
**Current focus:** Phase 31 complete — v0.5 The Dungeon 4/9 phases done, next candidates: 32/33/34/35

## Current Position

Phase: 32 (Monster Harvesting) — IN PROGRESS (Plan 01/05 complete)
Next Plan: 32-02 (rapidfuzz dep + seed YAML scaffold)
Milestone: v0.5 The Dungeon — IN PROGRESS
Status: Phase 32-01 (Wave 0) shipped 31 RED test stubs (21 unit + 3 integration + 7 bot dispatch) against app.harvest.*, app.routes.harvest.*, app.llm.generate_harvest_fallback, bot.build_harvest_embed — Waves 1-4 implement against this contract.
Last activity: 2026-04-24 -- Phase 32-01 executed: 3 atomic test commits (e62d56c, 563f191, 8b38a25); all 31 stubs collect cleanly and fail on run for expected reason (ModuleNotFoundError/AttributeError/unknown-noun).

## Milestone Progress

| Milestone | Name | Phases | Status |
|-----------|------|--------|--------|
| v0.1 | The Spark | 01 | ✅ COMPLETE |
| v0.2 | The Memory | 02 | ✅ COMPLETE |
| v0.3 | The Voice | 03 | ✅ COMPLETE |
| v0.4 | Functional Alpha | 04–10 | ✅ COMPLETE |
| v0.40 | Pre-Beta Refactoring | 21–26 | ✅ COMPLETE |
| v0.5 | The Dungeon | 28–36 | 🔜 IN PROGRESS |
| v0.6 | The Practice Room | TBD | — |
| v0.7 | The Workshop | TBD | — |
| v0.8 | The Ledger | TBD | — |
| v0.9 | The Trader (paper) | TBD | — |
| v0.10 | The Trader Goes Live | TBD | — |
| v1.0 | Community Release | TBD | — |

Progress (v0.5): [████      ] 44% (4/9 phases — 28, 29, 30, 31 complete)

## v0.5 Phase Map

| Phase | Name | Requirements | Depends on | Status |
|-------|------|--------------|------------|--------|
| 28 | pf2e-module Skeleton + CORS | MOD-01, MOD-02 | Phase 26 | ✅ COMPLETE (2026-04-22) |
| 29 | NPC CRUD + Obsidian Persistence | NPC-01..05 | Phase 28 | ✅ COMPLETE (2026-04-22) |
| 30 | NPC Outputs | OUT-01..04 | Phase 29 | ✅ COMPLETE (2026-04-23) |
| 31 | Dialogue Engine | DLG-01..03 | Phase 29 | ✅ COMPLETE (2026-04-23) |
| 32 | Monster Harvesting | HRV-01..06 | Phase 28 | Not started |
| 33 | Rules Engine | RUL-01..04 | Phase 28 | Not started |
| 34 | Session Notes | SES-01..03 | Phase 29 | Not started |
| 35 | Foundry VTT Event Ingest | FVT-01..03 | Phase 28 | Not started |
| 36 | Foundry NPC Pull Import | FVT-04 | Phase 30, Phase 35 | Not started |

## Performance Metrics

**Velocity:**

- Total plans completed: 7
- Average duration: ~5 min
- Total execution time: 0.2 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 (in progress) | 2/3 | ~10 min | ~5 min |
| 27 | 5 | - | - |

**Recent Trend:**

- Last 5 plans: 01-01 ✓, 01-02 ✓
- Trend: on track

*Updated after each plan completion*
| Phase 02-memory-layer P02 | -244 | 2 tasks | 3 files |
| Phase 23-pi-harness-reset-route P01 | 3 | 2 tasks | 7 files |

## Accumulated Context

### Roadmap Evolution

- Phase 25 added: V0.40 pre-beta refactoring — eliminate duplicates (DUP-01–05), complete stubs (STUB-01–08), fix architecture contradictions (CONTRA-01–04), implement RD-01 through RD-10
- v0.5 Phases 28–36 added: 9-phase Pathfinder 2e module roadmap (31 requirements)

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: 11-phase structure derived from requirement categories
- [Phase 01]: docker-compose include directive pattern locked (never -f flag stacking)
- [Phase 01]: depends_on uses condition: service_started (not service_healthy)
- [Phase 01]: LMSTUDIO_BASE_URL uses host.docker.internal per single Mac Mini topology
- [Phase 01]: Pi harness uses Fastify bridge + pi-adapter.ts, node:22-alpine, pinned @mariozechner/pi-coding-agent@0.66.1
- [Phase 02-memory-layer]: 25% context budget enforced before token guard — prevents large Obsidian profiles from causing systematic 422s
- [Phase 02-memory-layer]: BackgroundTasks (not asyncio.create_task) for session write — FastAPI-idiomatic, response sent before write begins
- [Phase 23-pi-harness-reset-route]: buildApp() factory pattern for Fastify bridge — separates construction from startup, enables vitest app.inject() testing without port binding
- [Phase 23-pi-harness-reset-route]: vitest.config.ts passWithNoTests: true added — vitest 2.x exits code 1 with no test files (plan assumption was incorrect)
- [v0.5 ADR]: Midjourney bot-to-bot DM is architecturally impossible (Discord API hard block). OUT-02 implements prompt-text-only output (Option A). No Midjourney automation code will be written.
- [v0.5 ADR]: CORS must use explicit allow_origins (Foundry LAN IP + localhost:30000); allow_origins=["*"] breaks X-Sentinel-Key credential header delivery.
- [v0.5 ADR]: PF2e NPC JSON schema must be derived from a live Foundry export on Phase 30 day one — documentation lags PF2e system releases; system.details.alignment removed in 2023 Remaster.

### Pending Todos

- Apply v0.5 phase checklist entries and Phase Detail sections to .planning/ROADMAP.md (blocked by uchg flag; human must run `chflags nouchg .planning/ROADMAP.md` first)

### Blockers/Concerns

- Pi-mono releases breaking changes every 2-4 days -- adapter pattern in Phase 1 is the mitigation
- ROADMAP.md has macOS uchg flag; v0.5 phase content was produced as text output for manual apply

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260410-ort | github community health files: contributing/issues/pr templates, security disclosure, branch protection prep | 2026-04-10 | 3778e6f | [260410-ort-github-community-health-files-contributi](.planning/quick/260410-ort-github-community-health-files-contributi/) |
| 260410-p7o | verify and close PROV-03 gap — tenacity @retry confirmed on PiAdapterClient.send_messages(), 62 tests pass | 2026-04-10 | — | [260410-p7o-fix-prov-03-gap](.planning/quick/260410-p7o-fix-prov-03-gap/) |
| 260411-c70 | Replan milestones to match PRD: v0.4 Functional Alpha COMPLETE (phases 01–10), module milestones v0.5–v1.0 restored | 2026-04-11 | — | [260411-c70-replan-milestones-based-on-architecture-](.planning/quick/260411-c70-replan-milestones-based-on-architecture-/) |
| 260411-kdc | Remove duplicate reset_session() from pi_adapter.py — close Phase 23 SC-3 gap, 23-VERIFICATION.md 5/5 PASS | 2026-04-11 | 2e91e92 | [260411-kdc-restore-reset-session-to-pi-adapter-py-p](.planning/quick/260411-kdc-restore-reset-session-to-pi-adapter-py-p/) |
| 260411-q4h | convert from .env for secrets to docker secrets — 9 secrets migrated to /run/secrets/ files | 2026-04-11 | a1a8322 | [260411-q4h](.planning/quick/260411-q4h-convert-from-env-for-secrets-to-docker-s/) |
| 260420-xbc | Fix discord thread tracking restart bug and build bulletproof pytest integration and discord uat test suite | 2026-04-21 | 5326de5 | [260420-xbc-fix-discord-thread-tracking-restart-bug-](.planning/quick/260420-xbc-fix-discord-thread-tracking-restart-bug-/) |
| 260421-nm2 | update all documentation for 0.40 release — README Path B architecture, secrets setup, Discord subcommands, sentinel.sh flags, secrets/README.md full rewrite | 2026-04-21 | 49e40aa | [260421-nm2-update-all-documentation-for-0-40-releas](.planning/quick/260421-nm2-update-all-documentation-for-0-40-releas/) |
| 260421-nzr | update contributing.md to reflect current v0.40 design, it still references the pi interface | 2026-04-21 | 7d9a26e | [260421-nzr-update-contributing-md-to-reflect-curren](.planning/quick/260421-nzr-update-contributing-md-to-reflect-curren/) |
| 260423-mdl | registry-aware LLM model selector — query LM Studio /v1/models + litellm.get_model_info to pick best model per task kind (chat/structured/fast); pathfinder-only scope | 2026-04-23 | 0f80c42 | [260423-mdl-llm-model-selector-registry-aware](.planning/quick/260423-mdl-llm-model-selector-registry-aware/) |
| 260423-tki | npc token image upload (OUT-02 ext) + PDF embed — `:pf npc token-image <name>` stores PNG at mnemosyne/pf2e/tokens/<slug>.png and updates frontmatter; `:pf npc pdf` embeds it in header; 42/42 tests pass | 2026-04-23 | (this commit) | [260423-tki-npc-token-image-pdf-embed](.planning/quick/260423-tki-npc-token-image-pdf-embed/) |

## Session Continuity

Last session: 2026-04-24
Stopped at: Phase 32-01 complete — 31/31 RED stubs collected; next plan is 32-02 (rapidfuzz + seed YAML)
Resume file: .planning/phases/32-monster-harvesting/32-01-red-test-stubs-SUMMARY.md

**In-Progress Phase:** 32 (Monster Harvesting) — 1/5 plans complete — Plan 32-02 next (rapidfuzz dep + seed YAML scaffold)

**Completed Phase:** 31 (Dialogue Engine) — 5 plans / 4 waves — 2026-04-23T21:30:00.000Z — DLG-01..03 shipped

**Planned Phase:** 32 (Monster Harvesting) — 5 plans / 5 waves serial — 2026-04-23T23:00:00.000Z — plan-checker PASS iter 2/3
