---
gsd_state_version: 1.0
milestone: v0.5
milestone_name: The Dungeon
status: in_progress
stopped_at: Phase 33 (Rules Engine) context gathered — 10 decisions captured (D-01..10) across corpus / cache / scope-filter / output / dispatch; deferred overnight book ingestion + self-healing to Phase 33.x follow-up
last_updated: "2026-04-24T05:00:00Z"
last_activity: 2026-04-24 -- Phase 33 discuss-phase complete. 4 gray areas explored + Discord noun choice. CONTEXT.md ready for /gsd-plan-phase 33. Philosophy: gameplay-fun-first — rules are source of truth, but LLM fallback on corpus miss (never decline). 3-book seed corpus (Player Core + GM Core + Monster Core).
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
**Current focus:** Phase 32 complete — v0.5 The Dungeon 5/9 phases done, next candidates: 33/34/35/36

## Current Position

Phase: 33 (Rules Engine) — CONTEXT gathered, ready for research + planning
Next Plan: /gsd-plan-phase 33 (triggers research → pattern-mapping → PLAN.md → plan-checker)
Prior Phase: 32 (Monster Harvesting) — ✅ COMPLETE + VERIFIED (5/5 plans, 22/22 must-haves, 89/89 + 38/38 unit, 17/17 live UAT)
Milestone: v0.5 The Dungeon — IN PROGRESS (5/9 phases complete)
Status: Phase 32-05 (Wave 4 bot wiring) shipped: interfaces/discord/bot.py gained build_harvest_embed (pure dict→discord.Embed, D-03a single-monster + D-04 batch-aggregated, 1024-char field cap), _pf_dispatch noun-check widened to {npc, harvest}, harvest dispatch branch re-parses args for multi-word monster names (Pitfall 5) + comma-separated batch with whitespace trim, top-level usage string + unknown-noun error updated to list both nouns. interfaces/discord/tests/conftest.py consolidates the discord stub (Client/Intents/Embed/Color/Thread/etc) so per-file setdefault races no longer hide missing attributes. All 7 test_pf_harvest_* flipped GREEN (solo, batch, multi-word, trimmed commas, empty→usage, embed-dict shape, noun-recognised). 38/38 interfaces/discord tests pass + 84/84 pathfinder tests pass + zero Phase 29/30/31 regressions. HRV-01..06 satisfied end-to-end.
Last activity: 2026-04-24 -- Phase 32 fully complete: 5 plans shipped, 22/22 verified, 13/13 code-review fixes applied, 2 live-gap fixes (Dockerfile rapidfuzz, LLM DC fill-when-missing), 17/17 live-stack UAT PASS. 89 pathfinder + 38 discord tests green. Ready for next v0.5 phase.

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

Progress (v0.5): [█████     ] 56% (5/9 phases — 28, 29, 30, 31, 32 complete)

## v0.5 Phase Map

| Phase | Name | Requirements | Depends on | Status |
|-------|------|--------------|------------|--------|
| 28 | pf2e-module Skeleton + CORS | MOD-01, MOD-02 | Phase 26 | ✅ COMPLETE (2026-04-22) |
| 29 | NPC CRUD + Obsidian Persistence | NPC-01..05 | Phase 28 | ✅ COMPLETE (2026-04-22) |
| 30 | NPC Outputs | OUT-01..04 | Phase 29 | ✅ COMPLETE (2026-04-23) |
| 31 | Dialogue Engine | DLG-01..03 | Phase 29 | ✅ COMPLETE (2026-04-23) |
| 32 | Monster Harvesting | HRV-01..06 | Phase 28 | ✅ COMPLETE (2026-04-24) |
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
- [Phase 32-03]: lookup_seed uses fuzz.ratio + head-noun anchor, NOT fuzz.token_set_ratio as RESEARCH prescribed — token_set_ratio scores 'wolf lord' vs 'wolf' at 100 because 'wolf' is a token subset, which breaks the Pitfall 2 boundary test. The two-tier policy (exact match → head-noun anchor → fuzz.ratio at cutoff 85) satisfies all three boundary tests simultaneously.
- [Phase 32-03]: DC_BY_LEVEL imported at function-scope inside generate_harvest_fallback to break the app.llm → app.harvest → app.routes.npc → app.llm import cycle (app.routes.npc imports extract_npc_fields / build_mj_prompt from app.llm at module load).
- [Phase 32-04]: POST /harvest handler uses per-name cache-aside with an explicit LLM-failure anti-pattern guard — cache-miss LLM exception raises 500 AND skips cache write (next call retries). Cache PUT failure degrades gracefully (WARNING logged, 200 still returned). This is the operating contract for D-03b.
- [Phase 32-04]: Module-level singletons `obsidian` and `harvest_tables` in app/routes/harvest.py are set by main.py lifespan (PATTERNS.md §3 Analog D). Tests patch them directly via `patch('app.routes.harvest.{obsidian,harvest_tables,generate_harvest_fallback}')` — same pattern as the NPC routes.
- [Phase 32-05]: Harvest dispatch branch re-parses `args` (not parts[2]/rest) so multi-word monster names survive — space-splitter would drop the second word (Pitfall 5: `:pf harvest Giant Rat` → names=['Giant Rat']). Splits only on commas, trims whitespace per name. Defensive leading-whitespace strip before the explicit-length slice (lstrip('harvest') is unsafe because it'd strip any character in {h,a,r,v,e,s,t}).
- [Phase 32-05]: Consolidated per-file discord stubs (test_subcommands.py / test_live_integration.py / test_thread_persistence.py) into interfaces/discord/tests/conftest.py. Reason: pre-existing `sys.modules.setdefault('discord', ...)` pattern meant the first-collected file's stub won, and later files' added attributes (e.g. Embed/Color) were silently discarded. Centralising in conftest makes the stub deterministic across collection order — required for `test_pf_harvest_returns_embed_dict` to reliably pass in the full suite.

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
Stopped at: Phase 32-05 complete — interfaces/discord/bot.py wired (build_harvest_embed + noun-widen + harvest dispatch branch + updated usage strings); conftest.py consolidated discord stub; 7/7 test_pf_harvest_* flipped GREEN; 38/38 discord tests + 84/84 pathfinder tests green; Phase 32 ready for /gsd-verify-work 32
Resume file: .planning/phases/32-monster-harvesting/32-05-bot-wiring-SUMMARY.md

**In-Progress Phase:** none (Phase 32 implementation complete; awaiting `/gsd-verify-work 32` acceptance gate before formal phase close). Next candidate phases in v0.5: 33 (Rules Engine), 34 (Session Notes), 35 (Foundry VTT Event Ingest), 36 (Foundry NPC Pull Import).

**Completed Phase:** 32 (Monster Harvesting) — 5 plans / 4 waves (Wave 0 RED, Waves 1-3 implementation, Wave 4 bot wiring) — 2026-04-24 — HRV-01..06 shipped end-to-end; previous: 31 (Dialogue Engine) — 5 plans / 4 waves — 2026-04-23T21:30:00.000Z — DLG-01..03 shipped

**Planned Phase:** 32 (Monster Harvesting) — 5 plans / 5 waves serial — 2026-04-23T23:00:00.000Z — plan-checker PASS iter 2/3 → implementation complete 2026-04-24
