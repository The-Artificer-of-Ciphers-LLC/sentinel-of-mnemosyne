---
gsd_state_version: 1.0
milestone: v0.5
milestone_name: — The Dungeon
status: executing
stopped_at: Phase 33 live UAT executed — 16/17 PASS. Stack rebuilt + restarted with Phase 33 code (4 containers: sentinel-core, pf2e-module, discord, ofelia/pentest-agent). pf2e-module lifespan loaded 148 corpus chunks, built embedding index shape (148, 768), 22 topics. UAT exercised PF1 decline + corpus hit + corpus miss + cache hit + bot 4 sub-verbs + D-11 placeholder UX + D-15 Monster-Core-generates-not-declines. Live UAT also caught and fixed two new bugs (commits 9f1f65b + eb364a8): litellm provider-prefix missing in embed_texts (lifespan crashed), and `docker exec` vs `docker compose exec` container name mismatch in uat_phase33.sh. ONE remaining UAT failure: UAT-8 reuse-match ≥0.80 — empirical paraphrase cosine 0.7765 < D-05-locked 0.80 on text-embedding-nomic-embed-text-v1.5; D-05 is user-locked and cannot be changed unilaterally per AI Deferral Ban. Pending: (a) operator decides UAT-8 outcome (accept / re-tune D-05 / different embedding model — see 33-UAT-RESULT.md), (b) Task 33-05-06 in-Discord visual verification still required for D-08 colors / D-11 UX / D-13-14 frontmatter.
last_updated: "2026-04-25T00:30:00.000Z"
last_activity: 2026-04-25 -- Phase 33 live UAT 16/17 PASS; UAT-8 awaits D-05 operator decision; Discord visual still pending
progress:
  total_phases: 35
  completed_phases: 16
  total_plans: 55
  completed_plans: 56
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-21)

**Core value:** A message goes in, an AI response that knows your history comes back -- and what mattered gets written to Obsidian so the next conversation starts smarter.
**Current focus:** Phase 33 — Rules Engine

## Current Position

Phase: 33 (Rules Engine) — EXECUTING
Plan: 5 of 5 (Plans 33-01..05 code complete; live UAT 16/17 PASS; UAT-8 D-05 decision + Task 33-05-06 in-Discord visual remain)
Next Plan: Operator decides UAT-8 outcome (see 33-UAT-RESULT.md §"UAT-8 — Calibration Failure") + runs in-Discord visual verification (Task 33-05-06)
Prior Phase: 32 (Monster Harvesting) — ✅ COMPLETE + VERIFIED (5/5 plans, 22/22 must-haves, 89/89 + 38/38 unit, 17/17 live UAT)
Milestone: v0.5 The Dungeon — IN PROGRESS (5/9 phases — 33 awaiting D-05 decision + Discord visual)
Status: Phase 33 live UAT 16/17 PASS; awaiting operator on UAT-8 + in-Discord checks
Last activity: 2026-04-25 -- Phase 33 live UAT executed (16/17 PASS); 2 bugs caught + fixed during UAT (litellm prefix + docker exec name); UAT-8 D-05 reuse threshold blocker

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
- [Phase 33-01]: Wave 0 RED stubs use function-scope symbol imports (inside each test body) so pytest collection succeeds before Waves 1-3 land app.rules / app.llm / app.routes.rule. Pattern reused from Phase 32-01. Two smoke tests (test_numpy_importable + test_bs4_importable) are the Phase 32 G-1 Dockerfile-dep-dual-ship regression guard — they must pass inside the pf2e-module container after Wave 1's pyproject.toml + Dockerfile update.
- [Phase 33-01]: StatefulMockVault extended with list_directory(prefix) — enables D-05 reuse-match scan tests without live Obsidian. Phase 32's class had only get_note/put_note.
- [Phase 33-01]: Discord conftest Color shim extended centrally with red + blue classmethods (alongside pre-existing dark_green + dark_gold). L-5 prevention: never add per-file Color attribute assignments; collection-order races broke Phase 32 until consolidated.
- [Phase 33-01]: D-15 scope lock enforced at test layer — zero Monster Core / GM Core rules-prose references in test .py files. RESEARCH §Threshold Calibration fixture preserves one "GM Core — DCs by Level" expected_source entry in the calibration data; at Phase 33 runtime this query falls through to [GENERATED — verify] per D-15 (Player-Core-only MVP). Not a scope violation — fixture is Wave 1 calibration data.
- [Phase 33-01]: uat_phase33.sh adds a hard 14-route registration gate (Step 3) — fails fast on Phase 32 G-1 regression class (stale container images where REGISTRATION_PAYLOAD lags source changes). uat_rules.py adds an L-10 pre-check (POST LM Studio /v1/embeddings with text-embedding-nomic-embed-text-v1.5) so missing embeddings-model config is caught upfront with a clear error, not 15 cascading assertion failures.

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
