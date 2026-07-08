# Requirements: Sentinel of Mnemosyne — v0.6.0 Music Lesson Tracker

**Defined:** 2026-07-07
**Core Value:** The Vault persists everything the system learns and generates; the Sentinel retrieves relevant context on every message — so conversations (and now practice) are always informed by history, never starting cold.

> **Scope note:** the operator chose maximum scope — nothing deferred, nothing excluded except multi-user (which stays out because it contradicts the project-wide single-operator foundation). Heavy audio/ML capabilities (AUDIO, DAW) are committed v1 requirements; the roadmapper sequences them into later phases so the core tracker ships first.

## v1 Requirements

Requirements for the v0.6.0 Music Lesson Tracker milestone. Numbering continues from phase 47 → phases start at 48.

### Module Foundation

- [ ] **MUS-01**: The Music module runs as a standalone Docker service (own FastAPI app, `compose.yml` with `profiles: ["music"]`) and registers with Core via `POST /modules/register` — Core needs no code changes to host it (mirrors `modules/pathfinder/`).
- [ ] **MUS-02**: The module persists to a new top-level `music/` vault namespace through its own thin `ObsidianClient` (Obsidian Local REST API) — it does not import Core's `Vault` Protocol.
- [ ] **MUS-03**: `music/` is added to `vault_sweeper.py` `sweep_skip_prefixes` (day one) so the sweeper never relocates or mangles module-authored music notes.
- [ ] **MUS-04**: A `:music` Discord command surface (own `music_dispatch.py` + `command_router.py` branch) routes music subcommands, built on the pf2e contract-module + live-E2E-smoke pattern to avoid payload drift.
- [x] **MUS-05**: Every music note carries a trailing `_schema` block + wikilinks so `/music/` participates in the `:graph`/`:check` machinery with no orphans.

### Practice Logging

- [ ] **LOG-01**: User can log a practice session capturing duration, pieces/exercises worked, focus area, and freeform notes → `music/practice-log/[date]-[instrument].md`.
- [ ] **LOG-02**: User can record a lesson (teacher or self, topics covered, assignments) → `music/lessons/[date].md`.
- [ ] **LOG-03**: A practice-log entry captures tempo/BPM progress per piece or exercise.
- [ ] **LOG-04**: A practice-log entry captures mood and energy level.
- [ ] **LOG-05**: A practice-log entry captures a pre-session goal and a post-session reflection.
- [ ] **LOG-06**: A practice-log entry can link a recording/audio reference (vault path or URL).
- [ ] **LOG-07**: Pieces are stored with a deterministic slug so the same piece across many sessions aggregates correctly (no title-collision drift).

### Idea Capture

- [ ] **IDEA-01**: User can capture a chord progression or melody idea in a structured, queryable form (plain-text chord grid, plain-YAML frontmatter) → `music/ideas/[slug].md`.
- [ ] **IDEA-02**: An idea note reserves `discogs_*` reference fields (e.g. related release) from day one, populated later by the Discogs integration.
- [ ] **IDEA-03**: User can link an idea to pieces, instruments, or sessions via wikilinks.

### Practice History

- [ ] **HIST-01**: User can query total time spent on a given piece across all sessions ("how long have I been working on this piece?").
- [ ] **HIST-02**: User can query what was practiced over a time window ("what did I work on last week?").
- [ ] **HIST-03**: User can see practice streaks and time-on-instrument / time-on-skill rollups.
- [ ] **HIST-04**: History queries are served by a dedicated deterministic query engine (exhaustive/numeric), not Core's relevance-ranked Recall (precedent: pf2e `player_recall_engine.py`).

### Routine Builder

- [ ] **RTN-01**: User can generate an instrument-specific practice routine (electric guitar, electric bass, synthesizer/sound-design, piano/keys, sampler, and EDM/techno/melodic-techno production) grounded in the pedagogy knowledge base.
- [ ] **RTN-02**: Routines are LLM-generated using the pedagogy KB as context, constrained by an `AI-SPEC.md` to structural practice planning only — never technique-correction or injury/health advice.
- [ ] **RTN-03**: A generated routine covers named skill categories (warmups, technique, repertoire/pieces, ear-training, theory, production-workflow as applicable) with metronome/tempo progression.
- [ ] **RTN-04**: A generated routine adapts to the user's recent practice history (surfacing under-practiced skills/pieces) via the HIST query engine.
- [ ] **RTN-05**: A generated routine can be saved to the vault and later logged against as a practice session.
- [ ] **RTN-06**: User can generate multi-week progressive practice plans (periodization across sessions), not just single-session routines.
- [ ] **RTN-07**: User can rate a routine's effectiveness, and those ratings feed back into future routine generation.

### ListenBrainz Integration

- [ ] **LBZ-01**: The module pulls the user's recent ListenBrainz listening history via an async, feature-flagged poller (`GET /1/user/{username}/listens`).
- [ ] **LBZ-02**: Listening data enriches practice/idea notes via reserved `listenbrainz_*` fields; ListenBrainz downtime or errors never block or crash core practice logging.
- [ ] **LBZ-03**: User can get listening-based recommendations via the ListenBrainz `cf/recommendation` endpoint.

### Discogs Integration

- [ ] **DSC-01**: User can flag a loved song/release and the module adds it to their Discogs wantlist via the idempotent `PUT /users/{username}/wants/{release_id}` (Personal Access Token auth).
- [ ] **DSC-02**: User can get related vinyl/CD suggestions via Discogs similarity search (paired with ListenBrainz recs, since Discogs exposes no native recommendations endpoint).
- [ ] **DSC-03**: Discogs operations are async and feature-flagged, never block core logging, and handle secrets via environment configuration (never written to the vault).

### Audio Tools

> Heavy — real-time audio + ML. Sequenced into later phases; each likely needs phase-specific research.

- [ ] **AUDIO-01**: A built-in metronome (configurable tempo + time signature) is usable during a logged practice session.
- [ ] **AUDIO-02**: A built-in instrument tuner (pitch detection) is available to the user.
- [ ] **AUDIO-03**: The module can run audio DSP analysis on a recording (e.g. pitch/tempo/level analysis) and attach the results to a practice/idea note.
- [ ] **AUDIO-04**: User can capture audio of an idea or session and the module produces structured notation/chords via audio-to-notation transcription.

### Gamification

- [ ] **GAME-01**: The module awards achievements/badges beyond streaks (e.g. "10 hours on a piece", "30-day streak", "first routine completed").
- [ ] **GAME-02**: User can set practice goals/challenges with progress tracking toward them.

### DAW Integration

- [ ] **DAW-01**: The module can parse a DAW project file to extract worked-on material (tempo, tracks, plugins) into a practice/idea note.
- [ ] **DAW-02**: User can link a DAW project to a session or idea, with the DAW/project type detected and recorded.

### Ambient Recall

- [ ] **RCL-01**: `music/` notes can be embedded into Core's ambient Recall (feature-flagged) so free-chat mentions surface practice context — distinct from, and in addition to, the deterministic HIST query engine.

### Cross-Module

- [x] **XMOD-01**: The duplicated per-module `ObsidianClient` is promoted into a shared `sentinel_shared` package (pf2e + music consume the shared client instead of each owning a copy).

## v2 Requirements

None — the operator pulled all previously-deferred scope into v1.

## Out of Scope

Explicitly excluded.

| Feature | Reason |
|---------|--------|
| Real-time multi-user / sharing | Contradicts the project-wide single-operator foundation (load-bearing across Vault, recall, and every module); operator chose to keep single-operator |

## Locked Implementation Decisions (not requirements)

Recorded so they aren't re-litigated at plan time; these are *how*, not *what*.

| Decision | Rationale |
|----------|-----------|
| Hand-roll `httpx.AsyncClient` wrappers for ListenBrainz + Discogs (no `liblistenbrainz` / `python3-discogs-client`) | Both libs wrap sync `requests`; hand-rolled async wrappers match the house `Vault`/`ObsidianClient`/`SentinelCoreClient` pattern |
| Plain YAML for chords/keys/progressions (no `music21`) | Heavy music-theory dep is overkill for structured-text capture |

## Traceability

Which phases cover which requirements. Populated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| MUS-01 | Phase 48 | Pending |
| MUS-02 | Phase 48 | Pending |
| MUS-05 | Phase 48 | Complete |
| XMOD-01 | Phase 48 | Complete |
| MUS-03 | Phase 49 | Pending |
| MUS-04 | Phase 49 | Pending |
| LOG-01 | Phase 49 | Pending |
| LOG-02 | Phase 49 | Pending |
| LOG-03 | Phase 49 | Pending |
| LOG-04 | Phase 49 | Pending |
| LOG-05 | Phase 49 | Pending |
| LOG-06 | Phase 49 | Pending |
| LOG-07 | Phase 49 | Pending |
| IDEA-01 | Phase 50 | Pending |
| IDEA-02 | Phase 50 | Pending |
| IDEA-03 | Phase 50 | Pending |
| HIST-01 | Phase 51 | Pending |
| HIST-02 | Phase 51 | Pending |
| HIST-03 | Phase 51 | Pending |
| HIST-04 | Phase 51 | Pending |
| RCL-01 | Phase 51 | Pending |
| RTN-01 | Phase 52 | Pending |
| RTN-02 | Phase 52 | Pending |
| RTN-03 | Phase 52 | Pending |
| RTN-04 | Phase 52 | Pending |
| RTN-05 | Phase 52 | Pending |
| RTN-06 | Phase 52 | Pending |
| RTN-07 | Phase 52 | Pending |
| LBZ-01 | Phase 53 | Pending |
| LBZ-02 | Phase 53 | Pending |
| LBZ-03 | Phase 53 | Pending |
| DSC-01 | Phase 54 | Pending |
| DSC-02 | Phase 54 | Pending |
| DSC-03 | Phase 54 | Pending |
| AUDIO-01 | Phase 55 | Pending |
| AUDIO-02 | Phase 55 | Pending |
| AUDIO-03 | Phase 55 | Pending |
| AUDIO-04 | Phase 55 | Pending |
| DAW-01 | Phase 56 | Pending |
| DAW-02 | Phase 56 | Pending |
| GAME-01 | Phase 57 | Pending |
| GAME-02 | Phase 57 | Pending |

**Coverage:**

- v1 requirements: 42 total (MUS ×5, LOG ×7, IDEA ×3, HIST ×4, RTN ×7, LBZ ×3, DSC ×3, AUDIO ×4, GAME ×2, DAW ×2, RCL ×1, XMOD ×1)
- Mapped to phases: 42/42 ✓ (Phases 48–57)
- Unmapped: 0

---
*Requirements defined: 2026-07-07*
*Last updated: 2026-07-08 after roadmap creation — 10-phase structure (Phases 48–57), 100% v1 coverage*
