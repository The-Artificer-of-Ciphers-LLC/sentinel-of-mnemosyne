# Project Research Summary

**Project:** Sentinel of Mnemosyne — v0.6.0 Music Lesson Tracker milestone
**Domain:** Pluggable Docker module for a self-hosted AI assistant — personal music practice journal + pedagogy-driven routine builder
**Researched:** 2026-07-08
**Confidence:** MEDIUM-HIGH (architecture/pitfalls grounded directly in this repo's source; stack/features cross-checked against official docs and multiple independent sources)

## Executive Summary

The Music Lesson Tracker is best built exactly like the existing `modules/pathfinder/` reference implementation: a fully independent Docker Compose service (`modules/music/`, `profiles: ["music"]`) that registers itself with Sentinel Core over the already-generic `POST /modules/register` + proxy seam, requiring **zero changes to Core**. It owns its own thin `ObsidianClient` talking directly to the Obsidian Local REST API — it does **not** import Core's internal `Vault` Protocol (ADR-0002 scopes that to Core only; every existing module, including pf2e, already duplicates this thin client rather than sharing it). `/music/` becomes a brand-new top-level vault namespace, a sibling to `self/`, `notes/`, `ops/`, `inbox/`, `templates/`, and pf2e's own tree — not a PARA-classified subfolder — because its content (practice sessions, lessons, ideas) is structured and module-authored, not freeform captures for the 6 Rs pipeline to classify.

The recommended approach sequences work by hard dependency: module scaffold + registration first (nothing else can exist without it), then core practice/lesson logging (the data foundation), then idea capture (independent but shares scaffolding), then a **deterministic, non-LLM practice-history query engine** (mirrors pf2e's `player_recall_engine.py` precedent — Core's relevance-ranked Recall is architecturally wrong for exact aggregates like "total minutes on this piece"), then the practice-routine builder (start templated/deterministic from a researched pedagogy knowledge base, defer history-adaptive generation), and only then the two explicitly-stretch, feature-flagged, non-load-bearing integrations — a ListenBrainz listening-history poller and a Discogs wantlist/search writer — both hand-rolled `httpx` async clients (never the sync-`requests`-based official libraries) with Discogs-shaped fields reserved in the data model from day one but the actual clients built last.

The single biggest risk is quietly violating one of five hard-won architectural invariants this codebase already enforces: the vault sweeper will relocate any `/music/` note into `_trash/` on the very next scheduled sweep unless `"music/"` is added to `sweep_skip_prefixes` in the *same phase* as the first Vault write (config.py:133-136 already anticipates this exact gap); module registration alone produces **no** Discord command surface (that's a separate hand-wired `command_router.py` branch + dispatch trio in a different container); and this project has already suffered the adapter-to-route payload-drift bug class three times (Phase 37) — every new `:music` Discord verb needs a contract-module test plus one live E2E smoke call, never just mocked unit tests. A secondary risk is scope-creep into the stretch integrations (ListenBrainz/Discogs) before the core logging/query/routine loop is validated — explicitly guard against this in phase sequencing.

## Key Findings

### Recommended Stack

New dependencies are minimal and deliberately boring: `fastapi`, `uvicorn[standard]`, `httpx`, `pydantic-settings`, `pyyaml` — an exact mirror of `modules/pathfinder/pyproject.toml`, already validated in this repo. No new HTTP client libraries and no music-theory library are added.

**Core technologies:**
- `httpx.AsyncClient` — used for the module's own `ObsidianClient` **and** hand-rolled ListenBrainz/Discogs clients — matches the house standard everywhere else (`Vault`, `ObsidianClient`, `SentinelCoreClient`) and avoids introducing a second, blocking sync-IO stack
- Plain YAML frontmatter (`pyyaml`) for chords/keys/progressions — no `music21` or theory library; this codebase has no schema library anywhere, and `music21` solves a different problem (analyzing existing scores, not freeform idea capture)
- **Do NOT add `liblistenbrainz` or `python3-discogs-client`** — both are built on synchronous `requests` (confirmed via PyPI `requires_dist`); calling them from `async def` routes without `asyncio.to_thread` blocks the event loop, a class of bug this codebase has zero instances of. Both target APIs are simple enough (1-2 GET calls, one PUT) that ~30-line hand-rolled `httpx` wrappers are the boring, consistent choice.
- Discogs auth: **Personal Access Token** (`Authorization: Discogs token=<token>` header), not OAuth 1.0a — OAuth is for apps acting on behalf of *other* users, irrelevant for a single-operator tool
- ListenBrainz auth: user token via `Authorization: Token <token>` header; rate-limit is header-driven (`X-RateLimit-*`), must be read and respected, not a fixed published number

### Expected Features

**Must have (table stakes / P1):**
- Practice session logging (duration, instrument, pieces, focus area, freeform notes, mood/energy) → `/music/practice-log/[date]-[instrument].md`
- Structured chord-progression / melody-idea capture → `/music/ideas/[slug].md`
- Practice-history queries ("what did I work on last week", "how long on this piece") via a dedicated deterministic engine, not Core's ambient Recall
- Practice streaks + per-instrument/per-piece rollups (near-free, pure derived query once logging exists)
- Practice-routine builder — v1 scope is **static/templated per instrument**, seeded from researched pedagogy (guitar/bass/synth/keys/production), NOT yet history-adaptive

**Should have (differentiators, P2):**
- History-adaptive routine builder (bias toward neglected/plateaued skills)
- Skill-category time balance view (actual vs. prescribed practice-time split)
- Cross-domain recall tying practice sessions into the rest of the second-brain graph

**Defer (stretch / P2-P3):**
- ListenBrainz listening-history pull (feature-flagged background poller)
- Discogs wantlist writes / related-release suggestions (on-demand route; Discogs has **no** recommendations endpoint — reframe as Discogs search-by-similarity + ListenBrainz `cf/recommendation`)

**Anti-features (explicitly out of scope):** built-in audio recording/tuner/metronome tooling, real-time multi-user/teacher-student sharing, badge/XP gamification beyond simple streaks, audio-to-notation transcription, deep DAW project-file integration.

### Architecture Approach

Music is a full sibling Docker service to `modules/pathfinder/`, communicating with Core only through the already-generic registration/proxy seam and with Discord only through a new hand-wired dispatch trio — Core requires **zero code changes** either way.

**Major components:**
1. `modules/music/app/main.py` + `config.py` + `obsidian.py` — module skeleton, own `ObsidianClient`, registers with Core via `POST /modules/register` with retry+heartbeat (mirrors pf2e exactly)
2. `services/practice_log.py`, `services/idea_store.py` — write structured, `_schema`-footer-carrying notes to `/music/practice-log/`, `/music/lessons/`, `/music/ideas/`
3. `services/practice_query.py` — **deterministic** aggregate engine (lists+parses `_schema` fields directly, sums/filters in Python), explicitly not Core's BM25/semantic Recall — mirrors pf2e's `player_recall_engine.py` precedent
4. `services/routine_builder.py` — pedagogy rules engine per instrument, reads recent practice history via the module's own `ObsidianClient`
5. `services/listenbrainz_poller.py`, `services/discogs_client.py` — feature-flagged, off-by-default, non-load-bearing background/on-demand stretch integrations
6. `interfaces/discord/music_dispatch.py` + `music_bridge.py` + `music_types.py` + a `command_router.py` branch — separate deliverable, structurally identical to the existing pf2e trio

### Critical Pitfalls

1. **`/music/` missing from the sweeper's skip-prefix list** — the vault sweeper walks the entire vault and will (non-destructively but disruptively) relocate practice logs into `_trash/` on the next scheduled sweep unless `"music/"` is added to `sweep_skip_prefixes` in the *same phase/commit* as the first Vault write. `config.py:133-136` already anticipates exactly this scenario.
2. **Module registration ≠ Discord command surface** — `POST /modules/register` only wires the HTTP proxy; `:music` commands require a hand-written dispatch module and an explicit branch in `interfaces/discord/command_router.py`, a separate deliverable with its own acceptance criteria.
3. **Adapter-to-route payload drift** — this exact bug class already hit the codebase three times in Phase 37 (mocked adapter tests pass green while live calls 422). Every new `:music` verb needs a contract-module test validated against the real Pydantic model, plus one live E2E smoke call before verifier PASS.
4. **Practice-log volume degrading warm-tier recall** — decide deliberately whether `/music/` is embedded/searchable by Core's ambient Recall at all; default recommendation is to exclude it and let the module's own deterministic query layer own aggregate answers, keeping sweep cost and warm-tier relevance stable.
5. **External API failures must never break core logging** — ListenBrainz/Discogs calls must be strictly async, best-effort, fire-and-forget, never inline in the practice-log write path (this project already hardened `ops/sessions/` writes against exactly this failure mode once).
6. **Freeform notes can't answer duration/aggregate queries reliably** — pieces need deterministic slugification and structured frontmatter fields (not LLM-normalized text matching) or "how long on Chameleon" silently under/over-counts depending on phrasing.

## Implications for Roadmap

Based on combined research, the dependency-ordered build sequence (converged on independently by ARCHITECTURE and FEATURES, and reinforced by PITFALLS' sequencing pitfall #7) is:

### Phase 1: Module Scaffold + Registration
**Rationale:** Unconditional prerequisite — no other phase can add routes without a running, registered service. Pure mirror of `modules/pathfinder/`'s skeleton; zero new architectural risk.
**Delivers:** `modules/music/` Docker service (`main.py`, `config.py`, `obsidian.py`, `compose.yml` with `profiles: ["music"]`), healthz route, registration payload + heartbeat lifespan.
**Avoids:** Nothing yet to avoid — but must include the `sweep_skip_prefixes` addition as an explicit acceptance criterion the moment any write path is planned (Pitfall 1), even if the first actual write lands in Phase 2.

### Phase 2: Core Practice + Lesson Logging
**Rationale:** The foundational data-producing capability every other feature reads from; must ship with **zero external-API code** in the write path (Pitfall 5).
**Delivers:** `POST /practice/log`, `services/practice_log.py` writing `/music/practice-log/` and `/music/lessons/` with `_schema` footers, deterministic piece slugification (Pitfall 6), `:music log` Discord command (full dispatch/bridge/types trio + `command_router.py` branch).
**Addresses:** Practice session logging, mood/focus rating, per-piece time tracking (FEATURES P1).
**Avoids:** Pitfall 1 (sweep skip-prefix, same commit as first write), Pitfall 2 (Discord surface is its own deliverable, not implied by registration), Pitfall 3 (contract-module test + E2E smoke per verb), Pitfall 5, Pitfall 6.

### Phase 3: Idea Capture
**Rationale:** Independent of practice logging but reuses the Discord dispatch scaffolding built in Phase 2 — sequence right after to avoid duplicating that trio twice.
**Delivers:** `POST /idea/capture`, `services/idea_store.py` writing `/music/ideas/`, `:music idea` command. Includes Discogs-shaped optional fields (release id, related-release suggestions) in the `Idea` model per the milestone's "data model built to hold these fields from day one" directive — schema only, no live integration.
**Uses:** Plain YAML chord/key/progression fields (STACK.md).

### Phase 4: Deterministic Practice-History Query
**Rationale:** Hard dependency on Phase 2 — nothing to query until sessions exist with a stable `_schema` shape.
**Delivers:** `services/practice_query.py` (lists+parses `/music/practice-log/*.md` `_schema` footers, sums/filters in Python — never Core's BM25/RRF Recall), `POST /practice/query`, `:music history` command.
**Implements:** Architecture Pattern 2 (module-owned deterministic query, mirrors pf2e's `player_recall_engine.py`).
**Avoids:** Anti-Pattern 2 (answering aggregate questions via semantic Recall).

### Phase 5: Practice-Routine Builder (templated v1)
**Rationale:** Depends on Phase 2 (reads recent practice history) and benefits from Phase 4's query engine already existing (reuse, don't duplicate the parser). This is the milestone's named differentiator and its highest-complexity feature.
**Delivers:** `services/routine_builder.py` seeded from the researched pedagogy KB (per-instrument skill categories: Technique, Repertoire, Ear Training, Theory, Production Workflow; slow-to-fast tempo progression; spaced-repetition scheduling), `POST /routine/build`, `:music routine <instrument>` command. Scoped to structural practice planning only — gets an `AI-SPEC.md` via `gsd-ai-integration-phase` constraining output away from technique/injury advice (Pitfall 8).
**Addresses:** FEATURES P1 templated routine builder; explicitly defers history-adaptive generation to v1.x.

### Phase 6 (Stretch): ListenBrainz Poller
**Rationale:** No hard dependency beyond the module skeleton and vault-write conventions; sequenced last among "real" features because it's explicitly stretch per PROJECT.md and must never destabilize the shippable core (Pitfall 7).
**Delivers:** Feature-flagged (`MUSIC_LISTENBRAINZ_ENABLED=false` default) background poller task, incremental pull from a stored high-water-mark timestamp, rate-limit-header-aware backoff.
**Implements:** Architecture Pattern 4 (feature-flagged background task, mirrors `_registration_heartbeat`/`_build_rules_index_safely` precedent).

### Phase 7 (Stretch): Discogs Wantlist Writer
**Rationale:** Data-model fields already added in Phase 3; this phase only adds the live API integration behind a flag. Sequenced last for the same reason as Phase 6.
**Delivers:** On-demand `POST /discogs/wantlist-sync` route (idempotent `PUT /users/{username}/wants/{release_id}` — no app-side dedupe needed), Docker-secrets-file token storage.
**Avoids:** Anti-Pattern 3 (making stretch integrations load-bearing), Security Mistake (tokens in `.env`/compose — use `secrets/`).

### Phase Ordering Rationale

- **Dependencies drive the order strictly for Phases 1→2→4→5**: no module without scaffold, no history query without logged data, no reuse-friendly routine builder without the query engine existing first.
- **Idea capture (Phase 3) is architecturally independent but placed early** to avoid building the Discord dispatch trio twice — a scaffolding-reuse optimization, not a hard dependency.
- **Stretch integrations (6, 7) are deliberately last** — PITFALLS' Pitfall 7 explicitly warns that ListenBrainz/Discogs work is the most "interesting" engineering and risks crowding out the milestone's actual named deliverable (the routine builder). Roadmap must gate these behind core-feature UAT completion, not just informal ordering.
- **The sweep-skip-prefix fix and Discord-surface work are not separate phases** — they are acceptance criteria baked into Phases 1/2, per PITFALLS' explicit recommendation not to defer them to a later hardening phase.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 5 (Routine Builder):** ARCHITECTURE explicitly flags this — "Domain research... runs before requirements" — the pedagogy content (per-instrument skill progressions) is the bulk of new logic and was only lightly seeded here; also needs an `AI-SPEC.md` design contract for the technique/injury-advice guardrail (Pitfall 8).
- **Phase 6/7 (ListenBrainz/Discogs):** external API integration details (rate-limit handling, pagination/high-water-mark state, exact idempotency semantics) are MEDIUM confidence from docs-only research; verify against live calls during planning.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Scaffold):** direct mirror of `modules/pathfinder/`, HIGH confidence, no unknowns.
- **Phase 2 (Core Logging), Phase 3 (Idea Capture), Phase 4 (History Query):** established patterns already proven in this codebase (pf2e's `ObsidianClient`, `player_recall_engine.py`, note-schema conventions).

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM | No premium research providers this run; every version claim cross-checked against PyPI JSON API + GitHub/ReadTheDocs; repo-read claims (Vault seam, ObsidianClient shape) are HIGH |
| Features | MEDIUM | PART A cross-checked against 5-6 competitor apps + official ListenBrainz/Discogs docs; PART B pedagogy cross-checked across multiple independent, converging sources per instrument — no single-source claims, but not primary/authoritative pedagogy texts |
| Architecture | HIGH | Grounded directly in inspection of the running reference implementation (`modules/pathfinder/`) and the actual Core seams (`module_registry.py`, `module_gateway.py`, `vault_sweeper.py`) — not general domain convention |
| Pitfalls | HIGH (architecture/integration) / MEDIUM (external APIs) / LOW (music-schema and technique/injury-advice claims) | Architecture pitfalls grounded in this repo's own documented history (Phase 37 payload-drift, `config.py` skip-prefix comment); external-API pitfalls from official docs + forum corroboration; general music-pedagogy-AI-safety claims flagged LOW, no primary source found |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **Discogs "related-release suggestions"** as originally scoped needs reframing — Discogs has no recommendations endpoint; the roadmapper/planner should treat this as "Discogs search-by-similarity + ListenBrainz `cf/recommendation`," not a single Discogs call (STACK.md gap, flagged explicitly).
- **Whether `/music/` should be sweeper-skip-listed but still semantically embedded for ambient Recall** is an open follow-on decision — ARCHITECTURE recommends defaulting to NOT embedded/not in ambient Recall for v0.6.0, revisiting only if usage shows real need; the pre-existing `pf2e/` vs `mnemosyne/pf2e/` skip-prefix string mismatch in `vault_sweeper.py` should be verified at implementation time, not assumed correct.
- **Whether to promote `ObsidianClient` into `shared/sentinel_shared`** to reduce duplication (pf2e + music, and future modules per PROJECT.md) is a legitimate roadmap-level refactor decision, not resolved here — flag for a future phase if a third module makes duplication a real cost.
- **Pedagogy KB depth for the routine builder** — PART B seeds converging, multi-source guidance per instrument but is not exhaustive; Phase 5 planning should treat it as a starting content seed, potentially warranting a dedicated research-phase pass.

## Sources

### Primary (HIGH confidence)
- `sentinel-core/app/vault.py`, `app/services/module_registry.py`, `app/services/module_gateway.py`, `app/routes/modules.py`, `app/services/vault_sweeper.py`, `app/config.py`, `app/services/recall.py`, `app/services/note_schema.py`, `app/services/pipeline_orchestrator.py` — read directly from this repo
- `modules/pathfinder/app/obsidian.py`, `app/main.py`, `pyproject.toml`, `compose.yml`, `app/routes/npc.py`, `app/routes/session.py`, `app/player_recall_engine.py` — read directly, reference implementation
- `interfaces/discord/command_router.py`, `pathfinder_dispatch.py`, `pathfinder_bridge.py`, `pathfinder_types.py`, `core_gateway.py` — read directly
- `.planning/PROJECT.md`, `CONTEXT.md` (Phase 37 `session_issues`, `verifier_blind_spots`, `Pathfinder command contract`, `obsidian_search_invariant`) — this project's own documented history

### Secondary (MEDIUM confidence)
- `https://pypi.org/pypi/liblistenbrainz/json`, `https://pypi.org/pypi/python3-discogs-client/json` — dependency lists, versions
- `https://listenbrainz.readthedocs.io/en/latest/users/api/core.html`, `https://github.com/metabrainz/liblistenbrainz` — API shape, rate limits
- `https://www.discogs.com/developers`, Context7 `/joalla/discogs_client` (215 snippets) — auth model, wantlist endpoint
- Andante, Modacity, Instrumentive, Legato, Athenify, Practis, Better Practice (competitor practice-tracker apps) — feature landscape
- D'Addario, Scott's Bass Lessons, Berklee Take Note, MusicTech, Syntorial, Fundamentals of Piano Practice, Myloops, EDM Tips, Beatportal (per-instrument pedagogy sources, multiple independent sources per instrument)

### Tertiary (LOW confidence)
- General web search on AI-assisted music technique/injury risk — directional caution only, no music-pedagogy-specific primary source
- General web search on music/practice-log schema design and MusicBrainz tag-provenance pattern — design precedent only, not a verified pitfall claim

---
*Research completed: 2026-07-08*
*Ready for roadmap: yes*
