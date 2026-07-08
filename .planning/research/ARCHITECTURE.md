# Architecture Research

**Domain:** Pluggable module integration for an existing self-hosted AI assistant (Sentinel of Mnemosyne v0.6.0 — Music Lesson Tracker)
**Researched:** 2026-07-07
**Confidence:** HIGH — based on direct inspection of the running reference implementation (`modules/pathfinder/`) and the Core seams it integrates through, not general domain conventions.

This is an **integration** research doc, not a greenfield architecture doc. Every recommendation below cites the actual existing file/pattern in the repo it reuses or mirrors. "New" means genuinely new code; everything else is reuse.

## Standard Architecture (as it exists today — Music module fits into it)

### System Overview

```
┌───────────────────────────────────────────────────────────────────────────┐
│  interfaces/discord  (discord-bot container)                                │
│  command_router.py → handle_subcommand(subcmd=="music") → music_dispatch.py │
│  music_bridge.py → sentinel_client.post_to_module("music/...", payload)     │
└───────────────────────────────┬───────────────────────────────────────────┘
                                 │ HTTP + X-Sentinel-Key
                                 ▼
┌───────────────────────────────────────────────────────────────────────────┐
│  sentinel-core (FastAPI, port 8000)                                        │
│  routes/modules.py                                                         │
│    POST /modules/register        ← music-module calls this at startup     │
│    POST /modules/music/{path}    → proxies to music-module base_url        │
│    GET  /modules/music/{path}    → proxies to music-module base_url        │
│  app/services/module_registry.py + module_gateway.py (generic proxy, ALREADY built — zero new Core code) │
│  app/vault.py — Vault Protocol (Obsidian REST) — music-module does NOT call this directly │
│  app/services/recall.py — RecallConfig / RecalledContext (ambient hot/warm tier)│
│  app/services/vault_sweeper.py — SWEEP_SKIP_PREFIXES gate (embeds or skips music/) │
│  app/services/pipeline_orchestrator.py — 6 Rs, scoped to inbox/→notes/ only│
└───────────────────────────────┬───────────────────────────────────────────┘
                                 │ Core does NOT import module code (hard constraint)
                                 ▼
┌───────────────────────────────────────────────────────────────────────────┐
│  modules/music/  (NEW Docker service, "music-module", profile "music")    │
│  app/main.py — FastAPI app, lifespan registers with Core (retry+heartbeat) │
│  app/routes/{practice,idea,routine,listenbrainz,discogs}.py               │
│  app/services/{practice_log,idea_store,routine_builder}.py                │
│  app/obsidian.py — OWN ObsidianClient instance (module-local, mirrors pf2e)│
│    writes to /music/lessons/, /music/practice-log/, /music/ideas/          │
└───────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Reused / New |
|-----------|----------------|---------------|
| `routes/modules.py`, `module_registry.py`, `module_gateway.py` (Core) | Registration + generic HTTP proxy `/modules/{name}/{path}` | **Reused verbatim** — zero Core changes needed |
| `music-module` FastAPI service | Owns all music domain logic, its own `ObsidianClient`, its own vault writes | **New** — mirrors `modules/pathfinder/` structure exactly |
| `music-module`'s `app/obsidian.py` | Direct Obsidian REST client instance, module-local (not through Core's `Vault` Protocol) | **New file, but copy of pf2e's established pattern** — pf2e does not call Core's `app/vault.py` either; each module owns its own thin Obsidian REST client instance, configured from the same `OBSIDIAN_BASE_URL`/`OBSIDIAN_API_KEY` env vars |
| `interfaces/discord/music_dispatch.py` + `music_bridge.py` + `music_types.py` | Noun/verb command registry + response-kind rendering, mirrors `pathfinder_dispatch.py`/`pathfinder_bridge.py`/`pathfinder_types.py` | **New**, structurally identical to the pf2e trio |
| `sentinel_client.post_to_module()` (Discord `core_gateway.py`) | Generic call-out from Discord container → Core's `/modules/{name}/{path}` proxy | **Reused verbatim** — already generic, not pf2e-specific |
| `app/services/recall.py` `RecallConfig` | Ambient ChatRecall hot/warm tier for free-chat questions | **Reused for ambient/loose queries** IF `music/` is not added to `sweep_skip_prefixes`; **not used** for precise aggregate queries (see Pattern 2 below) |
| A dedicated `PracticeQuery` service inside `music-module` | Deterministic aggregate practice-history answers ("how long on this piece total?") | **New**, mirrors pf2e's `player_recall_engine.py` — pf2e already established the precedent that a module owns its own deterministic recall/query logic separate from Core's ambient `Recall` |
| `app/services/vault_sweeper.py` `SWEEP_SKIP_PREFIXES` | Decides whether `music/` notes get embedded (and therefore reachable via Core's semantic/keyword warm-tier recall) | **One-line addition** — an explicit decision, not automatic (see Decision below) |
| `app/services/pipeline_orchestrator.py` (6 Rs) | Reduce/Reflect/Reweave/Verify/Rethink | **Not involved** for structured practice-log/idea data — scoped to `inbox/`→`notes/` only. Optionally reusable if the operator wants raw jam-session voice-memo transcripts routed through `:capture` into `inbox/` for classification, but that is a stretch UX path, not the primary flow |

## Recommended Project Structure

```
modules/music/                       # NEW top-level Docker module dir (sibling to modules/pathfinder/)
├── app/
│   ├── main.py                      # FastAPI app + lifespan (register + heartbeat, copy pf2e/app/main.py pattern)
│   ├── config.py                    # Settings: SENTINEL_CORE_URL, OBSIDIAN_BASE_URL/API_KEY, LISTENBRAINZ_*, DISCOGS_*
│   ├── obsidian.py                  # Module-local ObsidianClient (copy pf2e/app/obsidian.py)
│   ├── models.py                    # PracticeSession, Idea, RoutineSpec, InstrumentProfile (pydantic)
│   ├── routes/
│   │   ├── practice.py              # POST /practice/log, POST /practice/query (PRACTICE-01..0N)
│   │   ├── idea.py                  # POST /idea/capture, GET /idea/list (IDEA-01..0N)
│   │   ├── routine.py               # POST /routine/build (ROUTINE-01..0N)
│   │   ├── listenbrainz.py          # STRETCH — POST /listenbrainz/sync (feature-flagged, see below)
│   │   └── discogs.py               # STRETCH — POST /discogs/wantlist-sync (feature-flagged, see below)
│   ├── services/
│   │   ├── practice_log.py          # Vault-shape: write /music/practice-log/{date}.md, /music/lessons/{date}.md
│   │   ├── practice_query.py        # Deterministic aggregate engine over _schema footers — NOT embedding-based
│   │   ├── idea_store.py            # Vault-shape: write /music/ideas/{slug}.md
│   │   ├── routine_builder.py       # Pedagogy rules engine per instrument (guitar/bass/synth/keys/production)
│   │   ├── listenbrainz_poller.py   # STRETCH — background task, off by default
│   │   └── discogs_client.py        # STRETCH — wantlist writer, off by default
│   └── note_schema.py               # Music module's own `_schema` footer shape (mirrors Core's note_schema.py conventions, kept separate — modules do not import Core code)
├── compose.yml                      # profiles: ["music"] — mirrors modules/pathfinder/compose.yml
├── Dockerfile
├── pyproject.toml
└── tests/
```

### Structure Rationale

- **`modules/music/` as a full sibling of `modules/pathfinder/`, not a Core subpackage:** this is the only shape consistent with the stated hard constraint "Core does not import module code" and the existing reference implementation. There is no partial-integration option in this codebase — modules are either fully separate Docker services registering via HTTP, or they are Core code. Music is scoped as "pluggable" in `PROJECT.md`, so it must be the former.
- **`app/obsidian.py` duplicated rather than shared:** pf2e already made this call (it does not import `sentinel-core`'s `app/vault.py`, it has its own `ObsidianClient` built directly against the Obsidian Local REST API using the same `OBSIDIAN_BASE_URL`/`OBSIDIAN_API_KEY` env vars). This is consistent with the module-isolation constraint — a shared Python import would violate "Core does not import module code" symmetrically (module importing Core internals is just as much a violation of the isolation boundary in spirit, and ADR-0002 scopes the `Vault` Protocol to Core's own routes/services, not to external module processes).
- **`practice_query.py` as a separate deterministic service, not just Core `Recall`:** aggregate questions ("how long on this piece total?", "what did I work on last week?") need to sum/filter structured `_schema` fields across many notes precisely. BM25/semantic recall (Core's `RecallConfig`) returns *relevant snippets*, not *aggregates* — it is architecturally the wrong tool for exact totals. pf2e already solved an analogous problem with `player_recall_engine.py` (PVL-03: "Deterministic per-player recall") — a module-owned, non-embedding query path over its own vault subtree. Music mirrors that pattern exactly.

## Architectural Patterns

### Pattern 1: Module registration + generic proxy (reuse, zero Core changes)

**What:** The module's `lifespan()` posts a `REGISTRATION_PAYLOAD` (`name`, `base_url`, `routes: [{path, description}]`) to `POST /modules/register` at startup, with 5-attempt exponential backoff (1s→16s), and re-registers every 30s via a heartbeat task so a Core restart self-heals. Core stores it in an in-memory `dict[str, ModuleRegistration]` (`app.state.module_registry`) and proxies `GET|POST /modules/{name}/{path}` to `{base_url}/{path}` with the `X-Sentinel-Key` header forwarded.

**When to use:** Always, for every new module. This is the *only* registration seam in the codebase — do not invent a second one.

**Trade-offs:** In-memory registry means a Core restart forgets registrations until the next heartbeat (~30s gap) — acceptable for a personal single-operator tool; do not add persistence for this.

**Example (from `modules/pathfinder/app/main.py`, to mirror for music):**
```python
REGISTRATION_PAYLOAD = {
    "name": "music",
    "base_url": "http://music-module:8000",
    "routes": [
        {"path": "healthz", "description": "music module health check"},
        {"path": "practice/log", "description": "Log a practice session (PRACTICE-01)"},
        {"path": "practice/query", "description": "Query practice history (PRACTICE-02)"},
        {"path": "idea/capture", "description": "Capture a musical idea (IDEA-01)"},
        {"path": "routine/build", "description": "Build a practice routine (ROUTINE-01)"},
    ],
}
```

### Pattern 2: Module-owned deterministic query path, separate from Core's ambient Recall

**What:** Core's `Recall` module (`RecallConfig`/`RecalledContext`, RRF-merged BM25+semantic) answers "what's relevant to this message" for the *general chat* hot/warm tier. It is not designed for, and should not be pressed into, exact aggregation ("total minutes on 'Blue in Green' this month"). pf2e's `player_recall_engine.py` already establishes that a module builds its **own** deterministic query engine directly over its own vault subtree via its own `ObsidianClient` (e.g. list `/music/practice-log/*.md`, parse each note's `_schema` footer, filter/sum in Python).

**When to use:** Every "practice-history query" (PRACTICE-02-shaped) and every "how much time on X" aggregate. Use Core's ambient Recall only for loosely-relevant free-chat mentions of music (e.g. user says "remind me what I was working on" mid-conversation with no explicit `:music` command) — that only works if `music/` is *not* added to `vault_sweeper.SWEEP_SKIP_PREFIXES` (see Decision below).

**Trade-offs:** Deterministic query path is more code (a small parser/filter service) but gives correct, explainable totals; ambient Recall is free but approximate and unsuitable for numeric answers.

**Example (shape, mirrors `player_recall_engine.py`):**
```python
async def query_practice_history(
    obsidian: ObsidianClient, *, since: date | None, piece: str | None,
) -> PracticeQueryResult:
    notes = await obsidian.list_notes(prefix="music/practice-log/")
    sessions = [parse_schema_block(n.body) for n in notes if in_range(n, since)]
    if piece:
        sessions = [s for s in sessions if piece in s.get("pieces", [])]
    return PracticeQueryResult(
        total_minutes=sum(s["duration_minutes"] for s in sessions),
        sessions=sessions,
    )
```

### Pattern 3: Discord `:music` noun/verb dispatch (reuse the pf2e trio shape)

**What:** `command_router.py` already dispatches any `:pf ...` subcommand to `pf_dispatch`. Add a symmetric `:music ...` branch that dispatches to a new `music_dispatch.py` (noun/verb registry: `music log`, `music idea`, `music routine`, `music history`), which calls `music_bridge.py`, which converts a `MusicResponse` (text/embed/file) into Discord output exactly as `pathfinder_bridge.py` does for `PathfinderResponse`. Every command calls `sentinel_client.post_to_module("music/<path>", payload, http_client)` — this Discord-side call helper is **already generic**, not pf2e-specific, so it needs zero changes.

**When to use:** For every user-facing music command. Do not build a parallel HTTP client — reuse `core_gateway.py`'s `sentinel_client`.

**Trade-offs:** None significant — this is a pure structural mirror of a pattern already proven across ~30 pf2e commands.

### Pattern 4: Feature-flagged background poller for stretch integrations (mirrors existing env-flag + async-task conventions)

**What:** pf2e already has the exact shape needed for ListenBrainz/Discogs: (a) an env-var boolean flag defaulting to disabled (`SESSION_AUTO_RECAP=false` is the existing precedent), and (b) a cancellable `asyncio.create_task()` background loop started/stopped inside `lifespan()` (the `_registration_heartbeat` task is the existing precedent for a periodic background loop with clean shutdown via `task.cancel()` + `await task` inside a `try/except asyncio.CancelledError`).

**When to use:** `MUSIC_LISTENBRAINZ_ENABLED=false` / `MUSIC_DISCOGS_ENABLED=false` by default; only start the poller task if the flag is true. Both integrations are **non-load-bearing**: `main.py`'s `_build_rules_index_safely` establishes the precedent that *optional* external-dependency subsystems must degrade to "endpoint returns 503 / feature no-ops" on failure — they must never crash-loop the whole module (Docker's `restart: unless-stopped` would otherwise take down practice logging over a ListenBrainz API hiccup).

**Trade-offs:** A background poller inside the same container is simpler to build/deploy than a separate microservice, and Docker Compose profiles already give per-feature opt-in at the *module* level (`--music` flag) — a *second* profile for stretch integrations is unnecessary; an env flag inside the one music-module container is sufficient and matches the granularity already used elsewhere (`SESSION_AUTO_RECAP`).

## Data Flow

### Key Data Flows

1. **Log a practice session:** Discord `:music log <args>` → `music_dispatch.py` (noun=`log`) → `music_bridge.py` builds `MusicRequest` → `sentinel_client.post_to_module("music/practice/log", payload)` → Core `POST /modules/music/practice/log` (generic proxy, unchanged) → `music-module`'s `routes/practice.py` → `services/practice_log.py` validates + writes `/music/practice-log/{date}.md` (with a `_schema` footer: duration, pieces, focus_area, notes) AND appends a same-day summary line to `/music/lessons/{date}.md` via the module's own `ObsidianClient` → response embeds session summary back through the same chain.

2. **Capture an idea:** Discord `:music idea <text>` → same dispatch chain → `POST /modules/music/idea/capture` → `services/idea_store.py` writes `/music/ideas/{slug}.md` with structured `_schema` (chord progression / melody fields, `discogs_related` placeholder field built-in from day one per the milestone's stretch note, even though unused until Discogs ships).

3. **Query practice history:** Discord `:music history [filters]` → `POST /modules/music/practice/query` → `services/practice_query.py` (Pattern 2, deterministic, not Core Recall) lists+parses `/music/practice-log/*.md` and returns aggregated `PracticeQueryResult` → rendered as a Discord embed via `music_bridge.py`'s response-kind conversion (mirrors `render_say_response`/`build_harvest_embed` builders in pf2e).

4. **Generate a practice routine:** Discord `:music routine <instrument>` → `POST /modules/music/routine/build` → `services/routine_builder.py` (pure domain logic — pedagogy rules per instrument: guitar/bass/synth/keys/production, oriented to EDM/techno/melodic-techno per the milestone) optionally reads recent `/music/practice-log/` entries via the module's own `ObsidianClient` to skew the routine toward under-practiced skills, then writes the routine to `/music/practice-log/routines/{date}.md` and returns it.

5. **(Ambient, optional) Free-chat mention of music:** User asks Sentinel in normal chat "what have I been working on musically?" with no `:music` command → Core's `MessageProcessor` → `Recall` (`RecallConfig`) → warm tier — **only reachable if `music/` is intentionally excluded from `vault_sweeper.SWEEP_SKIP_PREFIXES`** (default recommendation: exclude it, i.e. skip embedding, same as `pf2e/`/`ops/sessions/` — keep the ambient chat context small and force precision-critical queries through the dedicated `:music history` path; revisit only if usage shows a real need for loose ambient recall of music content).

## Anti-Patterns

### Anti-Pattern 1: Reaching into Core's `app/vault.py` `Vault` Protocol from the music module process

**What people do:** Import `sentinel-core`'s `Vault` Protocol / `ObsidianVault` adapter directly from the module, to "reuse" the existing code instead of duplicating a thin Obsidian REST client.
**Why it's wrong:** The module runs as a separate Docker container/process — there's no shared Python runtime to import across. More importantly, ADR-0002 scopes the `Vault` Protocol as Core's internal persistence seam; pf2e already establishes that modules get their **own** lightweight Obsidian client hitting the same REST API directly, not a cross-process import of Core internals.
**Do this instead:** Build `modules/music/app/obsidian.py` as a small, module-local Obsidian REST client (copy pf2e's `app/obsidian.py` shape), configured from the same `OBSIDIAN_BASE_URL`/`OBSIDIAN_API_KEY` env vars via `env_file`.

### Anti-Pattern 2: Answering "how long on this piece?" via Core's semantic/keyword Recall

**What people do:** Assume that because Core has a working hybrid-retrieval `Recall` module, it can answer aggregate/numeric practice-history questions by retrieving "relevant" notes and having the LLM eyeball a total.
**Why it's wrong:** BM25/RRF retrieval is relevance-ranked, not exhaustive or numerically reliable — it can silently omit sessions below the relevance threshold, and LLM summation over retrieved snippets is not trustworthy for a stats feature the milestone explicitly calls out ("aggregate recall").
**Do this instead:** Build the deterministic `practice_query.py` service (Pattern 2) that lists and parses every `/music/practice-log/*.md` note's `_schema` footer directly and computes exact aggregates in Python.

### Anti-Pattern 3: Making ListenBrainz/Discogs load-bearing for core logging

**What people do:** Wire the ListenBrainz poller or Discogs client into the same startup path as practice logging, so a network hiccup to an external API crashes the whole module (Docker `restart: unless-stopped` then crash-loops practice logging too).
**Why it's wrong:** The milestone explicitly scopes these as "Stretch" and non-essential; pf2e already hit this exact failure mode with its rules-RAG embedding index and had to retrofit `_build_rules_index_safely` to stop a single optional subsystem from taking the whole module down.
**Do this instead:** Feature-flag both integrations off by default (`MUSIC_LISTENBRAINZ_ENABLED`, `MUSIC_DISCOGS_ENABLED`), start their background tasks only if enabled, and make failures inside them log-and-continue (never raise out of `lifespan`).

### Anti-Pattern 4: Filing music/ under the PARA `notes/`/`ops/` classifier taxonomy

**What people do:** Route practice logs through the existing `note_classifier.py` seven-slug taxonomy (`learning`/`journal`/`accomplishment`/etc.) because "that's how notes get filed here."
**Why it's wrong:** That taxonomy exists to classify *unstructured free-form captures* into PARA locations for the 6 Rs pipeline to later enrich. Practice sessions and ideas are already structured, module-authored data with their own schema — forcing them through the classifier adds an LLM call and a routing indirection for no benefit, and would incorrectly scatter music data across `ops/journal`, `ops/observations`, etc. instead of one coherent `/music/` namespace a human (and the routine builder) can browse.
**Do this instead:** `music-module` writes directly to `/music/lessons/`, `/music/practice-log/`, `/music/ideas/` via its own `ObsidianClient`, exactly as pf2e writes directly to `mnemosyne/pf2e/npcs/`, `mnemosyne/pf2e/sessions/` without going through the classifier.

## Integration Points

### External Services (stretch)

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| ListenBrainz | Background poller task inside `music-module`, feature-flagged off by default, calls ListenBrainz's public listen-history API on a timer, writes summarized listening context to `/music/practice-log/listening/{date}.md` (or similar) | Non-load-bearing — mirrors Pattern 4 / `_build_rules_index_safely`'s degrade-safely precedent. No Core involvement — entirely internal to the module. |
| Discogs | On-demand route (`POST /modules/music/discogs/wantlist-sync`) rather than a background poller — wantlist writes are naturally user-triggered ("add this to my wantlist"), not continuously polled | Data model (`Idea`/routine models) should carry optional Discogs-shaped fields (release id, related-release suggestions) from day one per the milestone, even while the route itself ships later — this avoids a schema migration when the stretch phase lands. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Discord container ↔ Core | HTTP, `sentinel_client.post_to_module()` → `POST/GET /modules/{name}/{path}` | Already generic — zero changes needed for a third module beyond adding the `:music` dispatch branch in `command_router.py` |
| Core ↔ music-module | HTTP proxy via `module_gateway.py`, `X-Sentinel-Key` header forwarded | Already generic — zero Core code changes; only the registration payload (module-side) is new |
| music-module ↔ Obsidian vault | Direct HTTP to Obsidian Local REST API via a module-local `ObsidianClient` (NOT through Core's `Vault` Protocol) | Same external service (`OBSIDIAN_BASE_URL`) as Core and pf2e, but a separate client instance per process — this is the established pattern, not a shortcut |
| music-module ↔ Core's `Recall`/6 Rs pipeline | **None**, by default (see Decision below) | Deliberate: structured module data does not need the classifier or the 6 Rs pipeline; ambient recall is opt-in via a one-line sweeper-prefix decision, not automatic |

## Key Decision: is `/music/` a new top-level vault space, or does it map under `self/notes/ops/inbox/templates`?

**Decision: `/music/` is a new, independent, module-owned top-level namespace — a sibling to `self/`, `notes/`, `ops/`, `inbox/`, `templates/`, and to pf2e's own `mnemosyne/pf2e/`. It does not map under any PARA folder.**

**Rationale, grounded in the existing precedent, not invented from scratch:**
1. The milestone's own target paths (`/music/lessons/[date].md`, `/music/practice-log/`, `/music/ideas/`) already specify this — PROJECT.md's "Target features" section states the vault layout explicitly as a top-level `/music/` tree, matching pf2e's own top-level module tree.
2. PARA's `self/notes/ops/inbox/templates` taxonomy (VAULT-01/VAULT-02, `note_classifier.py`'s `TOPIC_VAULT_PATH`) exists specifically to route *unstructured, LLM-classified* captures. Practice logs, idea captures, and routines are structured, module-authored data with fixed shapes — they are architecturally closer to pf2e's NPCs/sessions (`mnemosyne/pf2e/npcs/`, `mnemosyne/pf2e/sessions/`) than to a `:capture`'d journal entry.
3. `vault_sweeper.py`'s `SWEEP_SKIP_PREFIXES` already special-cases `pf2e/` as a module-owned subtree the sweeper does not walk/relocate/dedup — the same treatment (`music/` added to the skip list) is the correct default for the new module, keeping the sweeper's relocate/dedup logic scoped to genuinely unstructured PARA content.

**Verify at implementation time, do not assume:** `vault_sweeper.SWEEP_SKIP_PREFIXES` currently reads `("_trash/", "pf2e/", "ops/sessions/", "ops/sweeps/")`, while pf2e's actual write paths are `mnemosyne/pf2e/npcs/...` and `mnemosyne/pf2e/sessions/...` — a bare-prefix `path.startswith("pf2e/")` check does NOT match a path beginning `mnemosyne/pf2e/...`. This looks like a pre-existing mismatch in the skip-list (either the skip prefix is stale, or pf2e's actual vault root moved and the skip-list was never updated). Whichever it is, do not copy the string blindly — confirm at build time whether `mnemosyne/pf2e/` content is actually being embedded/walked today (it may not be receiving the skip treatment the docstring claims), and choose the `music/` skip-prefix value (`"music/"`, matching the milestone's literal `/music/...` paths) deliberately rather than assuming the pf2e precedent works as documented.

**Follow-on decision needed at phase-planning time (flag for roadmap, not resolved here):** whether `music/` should also be *embedded* (walked by the sweeper for the semantic index) despite being skip-listed for relocation — these are two independent concerns bundled into one skip-list in the current sweeper code. Recommend defaulting to **not embedded / not in ambient Recall** for v0.6.0 (all music queries go through the dedicated deterministic `:music history` path), and revisiting ambient ChatRecall inclusion as a follow-up if real usage shows a need for Sentinel to reference practice history unprompted in ordinary chat.

## Suggested Build Order (dependency-ordered, for roadmap phase sequencing)

1. **Module scaffold + registration** — `modules/music/` Docker service skeleton (`main.py`, `config.py`, `obsidian.py`, `compose.yml` with `profiles: ["music"]`, healthz route, registration payload + heartbeat). Depends on nothing new; pure mirror of `modules/pathfinder/`'s skeleton. Must land first — every other phase needs a running, registered service to add routes to.
2. **Core logging: practice sessions + lessons** — `routes/practice.py` (`POST /practice/log`), `services/practice_log.py` (write `/music/practice-log/`, `/music/lessons/`), `_schema` footer shape, Discord `:music log` command (dispatch/bridge/types trio + `command_router.py` branch). This is the foundational data-producing capability everything else reads.
3. **Idea capture** — `routes/idea.py`, `services/idea_store.py` (write `/music/ideas/`), Discord `:music idea` command. Independent of practice logging but reuses the same dispatch/bridge scaffolding from step 2 — sequence after 2 to avoid duplicating the Discord trio twice. Include the Discogs-shaped optional fields (release id, related-release suggestions) in the `Idea` model here, per the milestone's "data model built to hold these fields from day one" note.
4. **Practice-history query (deterministic)** — `services/practice_query.py` (Pattern 2), `routes/practice.py` (`POST /practice/query`), Discord `:music history` command. **Hard dependency on step 2** — there is nothing to query until sessions are being logged with a stable `_schema` shape.
5. **Practice-routine builder** — `services/routine_builder.py`, `routes/routine.py`, Discord `:music routine <instrument>` command. Depends on step 2 (routine builder should be able to read recent practice history to skew toward under-practiced skills) and benefits from step 4's query engine already existing (reuse rather than duplicate the practice-log parser). Domain pedagogy content (per-instrument skill progressions for guitar/bass/synth/keys/production, EDM/techno-oriented) is the bulk of new logic here — flag for deeper phase-specific research per the milestone's own note ("Domain research... runs before requirements").
6. **Stretch: ListenBrainz poller** — feature-flagged background task (Pattern 4). No hard dependency on 2-5 beyond the module skeleton (step 1) and vault-write conventions (step 2), but sequence last among "real" features since it's explicitly stretch and non-load-bearing.
7. **Stretch: Discogs wantlist writer** — on-demand route, feature-flagged. Data-model fields already added in step 3; this phase only adds the live API integration behind the flag.

**Ordering rationale:** 1 is an unconditional prerequisite (no module, no routes). 2 before 3/4 because idea capture is independent but shares scaffolding, and history-query is meaningless without logged data. 4 before 5 so the routine builder can reuse the query engine instead of re-deriving it. 6 and 7 last because they are explicitly stretch, external-API-dependent, and must not block or destabilize the core (already-shippable) logging/query/routine feature set — consistent with the milestone's own "Stretch" labeling and the module-isolation principle that these integrations must never become load-bearing.

## Sources

- Direct inspection of `sentinel-of-mnemosyne` repo (this project), specifically: `sentinel-core/app/routes/modules.py`, `sentinel-core/app/services/module_registry.py`, `sentinel-core/app/services/module_gateway.py`, `sentinel-core/app/vault.py`, `sentinel-core/app/services/recall.py`, `sentinel-core/app/services/vault_sweeper.py`, `sentinel-core/app/services/note_classifier.py`, `sentinel-core/app/services/pipeline_orchestrator.py`, `sentinel-core/app/services/note_schema.py`
- `modules/pathfinder/app/main.py` (registration payload, retry/heartbeat, safe-degrade pattern for optional subsystems), `modules/pathfinder/app/routes/npc.py` and `session.py` (module-owned top-level vault paths `mnemosyne/pf2e/...`), `modules/pathfinder/compose.yml` (Docker profile pattern)
- `interfaces/discord/command_router.py`, `pathfinder_dispatch.py`, `pathfinder_bridge.py`, `pathfinder_types.py`, `pathfinder_registry.py`, `core_call_bridge.py` (Discord noun/verb dispatch + Core proxy call pattern)
- `.planning/PROJECT.md` (v0.6.0 milestone scope, constraints, module-isolation constraint, PARA namespace history VAULT-01..05)
- `docker-compose.yml`, `modules/pathfinder/compose.yml` (Compose `include:` + profile activation pattern)

---
*Architecture research for: Music Lesson Tracker module integration into Sentinel of Mnemosyne*
*Researched: 2026-07-07*
