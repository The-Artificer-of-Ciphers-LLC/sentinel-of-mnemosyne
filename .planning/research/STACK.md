# Stack Research

**Domain:** Music Lesson Tracker — new pluggable Docker module for Sentinel of Mnemosyne
**Researched:** 2026-07-07
**Confidence:** MEDIUM (no premium research providers configured for this run — Context7 + WebSearch/WebFetch only; every version-specific claim below was cross-checked against at least two independent sources: PyPI JSON API, GitHub, and/or official ReadTheDocs. Claims sourced by reading this repo's own code directly are called out as HIGH confidence inline.)

This file scopes ONLY the new dependencies/integration points the Music Lesson Tracker module needs. The existing project stack (Python/FastAPI/LiteLLM/Docker Compose, the `Vault` Protocol at `sentinel-core/app/vault.py`, ADR-0002) is validated and NOT re-researched here.

## Ground truth from this repo (read directly, not web-sourced)

Before recommending anything, I read `sentinel-core/app/vault.py` and `modules/pathfinder/app/obsidian.py` to confirm the actual integration seam a new module uses. This matters because it changes the right answer for "how do we write to the Vault":

- **Core does not export `Vault` to modules.** `Vault`/`ObsidianVault` lives in `sentinel-core/app/vault.py` and is Core-internal (ADR-0002). Modules are separate Docker Compose services (`modules/<name>/compose.yml`, `POST /modules/register`) and do **not** import Core code.
- **Every existing module (pf2e) owns its own thin Obsidian REST client**, `modules/pathfinder/app/obsidian.py` — `ObsidianClient` with `get_note`, `put_note`, `put_binary`, `get_binary`, `list_directory`, `patch_heading`, `patch_frontmatter_field`. It talks straight to the Obsidian Local REST API (`OBSIDIAN_BASE_URL=http://host.docker.internal:27123`, `OBSIDIAN_API_KEY`) using `httpx.AsyncClient`, mirroring Core's own `ObsidianVault` adapter shape (`_safe_request` graceful-degrade pattern) but as an independent implementation.
- **`shared/sentinel_shared`** (path-included via `pythonpath = [".", "../../shared"]` in `modules/pathfinder/pyproject.toml`) is a *different* shared surface — LLM-call/embedding helpers (`llm_call.py`, `similarity.py`, `embedding_codec.py`), not vault I/O. It does NOT contain a shared `ObsidianClient`.

**Implication for this module:** the Music module needs its own `ObsidianClient` copied/adapted from `modules/pathfinder/app/obsidian.py` (or, if the roadmap wants to reduce duplication, promoting that client into `shared/sentinel_shared` is a legitimate roadmap-level decision — flagged for the roadmapper, not decided here). Either way, **no direct filesystem writes** anywhere in the module; all persistence goes through this client's `put_note`/`patch_frontmatter_field`/`get_note`, respecting the Vault-seam principle even though the module's copy is architecturally separate from Core's `Vault` Protocol.

## Recommended Stack

### Module scaffolding (reuse the pf2e pattern verbatim)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| fastapi | `>=0.135.0` | Module's own HTTP surface, registered via `POST /modules/register` | Matches `modules/pathfinder/pyproject.toml` exactly — zero new stack surface, same version floor already validated in this repo |
| uvicorn[standard] | `>=0.44.0` | ASGI server for the module container | Same as pf2e |
| httpx | `>=0.28.1` | Async HTTP for the module's own `ObsidianClient` **and** for ListenBrainz/Discogs calls (see below) | Already the house standard everywhere (`Vault`, `ObsidianClient`, `SentinelCoreClient` all use `httpx.AsyncClient`); reusing it for the new external APIs avoids introducing a second, sync HTTP stack |
| pydantic-settings | `>=2.13.0` | Module config (`OBSIDIAN_BASE_URL`, `OBSIDIAN_API_KEY`, `LISTENBRAINZ_TOKEN`, `DISCOGS_TOKEN`) | Same as pf2e's `app/config.py` pattern |
| pyyaml | `>=6.0.0` | YAML frontmatter read/write for `/music/` notes | Already how `join_frontmatter`/`split_frontmatter` and `ObsidianClient.patch_frontmatter_field` work in this repo — no new format |
| litellm | `>=1.83.0` | Only if the practice-routine builder / practice-history NL queries need LLM calls from inside the module | Same as pf2e; omit from `pyproject.toml` if the module ends up calling back through Core's `/provider/complete` instead (architecture decision, not a stack blocker either way) |

### Supporting Libraries — stretch integrations (ListenBrainz, Discogs)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| *(none — hand-rolled httpx clients, see below)* | — | ListenBrainz + Discogs read/write | Recommended path for both integrations |

**Recommendation: do NOT add `liblistenbrainz` or `python3-discogs-client` as dependencies.** Both exist, are current, and are legitimate maintained clients — but both are built on the **synchronous `requests` library**, confirmed directly from each package's PyPI `requires_dist`:

- `liblistenbrainz` **0.7.0** (released 2026-02-23, MetaBrainz Foundation, GPLv3, Python `>=3.8`) → `requires_dist: requests>=2.31.0`.
- `python3-discogs-client` **2.8** (released 2025-02-17, `joalla/discogs_client` — the actively maintained continuation of Discogs' own deprecated-2020 client; confirmed via Context7 `/joalla/discogs_client`, 215 snippets, medium reputation) → `requires_dist: requests, oauthlib, python-dateutil`.

Calling either from inside an `async def` FastAPI route blocks the event loop unless wrapped in `asyncio.to_thread` — an extra failure mode this codebase has consistently avoided (every existing HTTP boundary — `Vault`, `ObsidianClient`, `SentinelCoreClient` — is `httpx.AsyncClient`-native). Both APIs needed here are trivially simple (one GET for listens, one GET for search, one PUT for wantlist-add) and personal-access-token auth requires no request-signing, so `oauthlib`'s OAuth 1.0a machinery is dead weight for a single-operator tool. Writing two ~30-line async clients, in the exact shape of `modules/pathfinder/app/obsidian.py`, is the boring, consistent, dependency-free choice.

**ListenBrainz — read-only "recent listens" (core stretch)**
- Auth: user token from `https://listenbrainz.org/settings/`, sent as `Authorization: Token <token>` header. Reading a **public** user's listens works with no token at all; supplying one just raises your rate ceiling — supply it from day one since this is single-operator.
- Endpoint: `GET https://api.listenbrainz.org/1/user/{mb_username}/listens`
  - Query params: `count` (default 25, max 1000), `max_ts` / `min_ts` (UNIX epoch, mutually exclusive — pick one for pagination), results always descending by `listened_at`.
- Rate limiting: header-driven, not a fixed published number — `X-RateLimit-Limit` / `X-RateLimit-Remaining` / `X-RateLimit-Reset-In` / `X-RateLimit-Reset`; `429` on exceed; authenticated requests get a higher ceiling. Client must read and respect these headers (a 10-line backoff helper, not a library).
- Related endpoint worth flagging for later: `GET /1/cf/recommendation/user/{mb_username}/recording` — ListenBrainz's own collaborative-filtering recommendation feed. Marked experimental by MetaBrainz but relevant to the "related-release suggestions" stretch goal, and it's ListenBrainz's data, not Discogs' — cheaper to use than trying to derive suggestions from Discogs alone.

**Discogs — search + wantlist write (the key stretch write-op)**
- Auth: **Personal Access Token** (`Settings → Developers → Generate new token` on discogs.com), not OAuth 1.0a. Confirmed against Discogs' own docs: OAuth exists for apps acting on behalf of *other* users; a personal access token is explicitly the right, simpler choice for a single-user script/tool. Token passed as `Authorization: Discogs token=<token>` header (or `?token=` query param).
- Search: `GET https://api.discogs.com/database/search?q={query}&type=release&token={token}` — `type` is one of `release|master|artist|label`; also supports `artist`, `title`, `genre`, `style`, `year`, `barcode`, `catno`, etc. as extra filters.
- **Wantlist add (the exact write op):** `PUT https://api.discogs.com/users/{username}/wants/{release_id}` with `Authorization: Discogs token=<token>` header and optional JSON body `{"notes": "...", "rating": 4}`. This is the REST-level equivalent of what `python3-discogs-client`'s docs show as `me.wantlist.add(d.release(id))` (verified via Context7 against `/joalla/discogs_client` docs) — implement it as one `httpx.AsyncClient().put(...)` call instead of pulling in the library.
- Related-release / suggestions: **Discogs has no dedicated "recommendations" endpoint.** The closest signal is `GET /releases/{release_id}` → `.community.want` / `.community.have` counts (popularity proxy) plus same-artist/same-label/same-genre `database/search` calls you construct yourself. For genuine "you might also like" suggestions, prefer ListenBrainz's `cf/recommendation` endpoint above and treat Discogs purely as the catalog/wantlist system of record. Flag this gap for the roadmapper — "Discogs suggestions" as originally scoped may need to be reframed as "Discogs search-by-similarity + ListenBrainz recommendations", not a single Discogs call.
- Rate limits: **60 requests/minute for authenticated (token or OAuth) requests, 25/minute unauthenticated**, sliding 60-second window (resets after 60s idle). Response headers `X-Discogs-Ratelimit` / `X-Discogs-Ratelimit-Used` report the live window. Must set a unique `User-Agent` string to get the full authenticated ceiling.

### Supporting Libraries — structured idea capture (chords/keys/progressions)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| *(none)* | — | Chord/key/progression representation | Never for this module |

**Do not add `music21` or any music-theory library.** `music21` is the standard heavyweight option (computational musicology: harmonic analysis, key detection, MIDI parsing) but it is large, has known MIDI-read performance issues, and its whole value proposition is *analyzing* existing scores — not *authoring* freeform ideas a musician jots down. There is no lightweight, standard dataclass-shaped alternative in the Python ecosystem worth adding either. Represent chords/progressions/keys as **plain YAML scalars and lists in frontmatter** — `key: "A minor"`, `progression: ["Am", "F", "C", "G"]`, `tempo_bpm: 128`. This is boring, human-editable directly in Obsidian, has zero dependency/version risk, and matches how this vault already treats every other structured field (plain YAML via `pyyaml`, parsed by `markdown_frontmatter.py`'s `split_frontmatter`/`join_frontmatter` — no schema library anywhere in this codebase). If chord-quality validation ever becomes a real need (e.g. rejecting `"Zm7b13"` as invalid), that is a ~15-line regex against standard chord-symbol grammar, not a dependency.

## Installation

```bash
# modules/music/pyproject.toml — mirrors modules/pathfinder/pyproject.toml
[project]
name = "music-module"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.135.0",
    "uvicorn[standard]>=0.44.0",
    "httpx>=0.28.1",
    "pydantic-settings>=2.13.0",
    "pyyaml>=6.0.0",
    # litellm>=1.83.0  # only if the module calls an LLM directly rather than via Core's /provider/complete
]

[project.optional-dependencies]
dev = ["pytest>=7.0", "pytest-asyncio>=0.23", "httpx"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = [".", "../../shared"]
```

No `pip install liblistenbrainz` / `pip install python3-discogs-client` / `pip install music21` — see rationale above.

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|--------------------------|
| Hand-rolled `httpx.AsyncClient` wrapper for ListenBrainz | `liblistenbrainz` 0.7.0 (official, MetaBrainz-maintained) | If the module ever needs the *full* ListenBrainz surface (playlists, feed, pinned recordings, submit-listens with retry/dedup logic) rather than just recent-listens reads — at that point the sync-IO cost may be worth the coverage; wrap calls in `asyncio.to_thread` if adopted |
| Hand-rolled `httpx.AsyncClient` wrapper for Discogs | `python3-discogs-client` 2.8 (`joalla/discogs_client`, active fork of the official client) | If the module needs deep Discogs coverage (full collection management, marketplace, multi-step OAuth for a future multi-user scenario) — today's scope (search + wantlist PUT) doesn't justify it |
| Plain YAML fields for chords/keys | `music21` | If a future phase adds real harmonic *analysis* (auto-detect key from a melody, transpose, render notation/MIDI) rather than freeform capture — that is a different, much bigger feature and should be its own researched decision, not bundled into idea-capture |
| Module owns a private `ObsidianClient` copy | Promote `ObsidianClient` into `shared/sentinel_shared` | If a third module is added and the duplication (pf2e + music, soon finance/trading per PROJECT.md's roadmap) becomes a real maintenance cost — worth flagging to the roadmapper as a possible refactor phase, not a Music-module blocker |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|--------------|
| `liblistenbrainz` / `python3-discogs-client` as hard dependencies | Both are `requests`-based (sync/blocking); calling them from an `async def` FastAPI handler without `asyncio.to_thread` blocks the event loop — a class of bug this codebase has zero instances of today | `httpx.AsyncClient`, matching `ObsidianClient`/`Vault`/`SentinelCoreClient` |
| OAuth 1.0a for Discogs | Only needed for apps acting on behalf of *other* Discogs users; adds `oauthlib` + a 3-legged auth flow (request_token → authorize → access_token) for zero benefit in a single-operator tool | Personal Access Token, `Authorization: Discogs token=<token>` header |
| `music21` (or any music-theory library) for idea capture | Heavyweight analysis framework; solves a different problem (parsing/analyzing existing scores) than freeform idea jotting; MIDI-parsing performance issues noted in its own release notes | Plain YAML scalars/lists (`key`, `progression`, `tempo_bpm`) via the already-used `pyyaml` |
| Direct filesystem writes to the vault from the module | Violates the Vault-seam principle (ADR-0002) even though the module's client is architecturally separate from Core's `Vault` Protocol; bypasses whatever sweep/graph/backlink machinery later scans `/music/` | The module's own `ObsidianClient.put_note`/`patch_frontmatter_field` (HTTP to the Obsidian Local REST API), exactly like `modules/pathfinder` |

## Obsidian Data Model (`/music/`)

Grounded in the vault's existing conventions: leading YAML frontmatter (parsed by `markdown_frontmatter.py`), the vault-wide note-quality convention from Phase 45 (H1 claim title + wikilinks + trailing ` ```_schema ` fenced block, so `:graph`/`:stats`/`:check` and the backlink index don't treat `/music/` notes as orphans), and `pyyaml`-only structured fields (no custom schema library anywhere in this repo).

**Reserved-fields rule applied throughout:** every ListenBrainz/Discogs field below is declared **now**, defaulted to `null`/`[]`, and populated by nothing until those stretch phases ship. This means the note shape never has to migrate later — only a background job starts filling in already-declared fields.

### `music/practice-log/[date]-[instrument].md` — one note per practice session

```yaml
---
type: practice-session
date: "2026-07-07"
instrument: electric-guitar        # electric-guitar | electric-bass | synth | keys | production
duration_minutes: 45
focus_area: "arpeggios over ii-V-I"
pieces:
  - title: "Autumn Leaves"
    source: "real book"
  - title: "original sketch #3"
    source: "self"
mood: "focused"                    # optional, freeform
# --- reserved for stretch: ListenBrainz (populated by a future sweep, not this phase) ---
listenbrainz_context:
  tracks_played: []                # [{recording_mbid, track_name, artist_name, listened_at}, ...]
  synced_at: null
# --- reserved for stretch: Discogs (populated by a future sweep, not this phase) ---
discogs_context:
  referenced_release_ids: []       # releases mentioned/practiced-from
  synced_at: null
---

## Notes

Freeform practice notes go here.

## Homework / Next Focus

- [ ] item

[[music/ideas/some-idea]]

```_schema
title: "Practice — 2026-07-07 — electric-guitar"
wikilinks: ["music/ideas/some-idea"]
```
```

### `music/lessons/[date].md` — one note per formal/structured lesson (distinct from ad-hoc practice-log entries: implies curriculum, an instructor or self-directed syllabus, and assigned follow-up)

```yaml
---
type: lesson
date: "2026-07-07"
instrument: synth
teacher: "self-directed"           # or a named instructor
topics_covered:
  - "envelope shaping"
  - "sidechain compression basics"
assigned_homework: "build 3 basslines using sidechain duck"
next_lesson_date: null
related_practice_log:
  - "music/practice-log/2026-07-08-synth.md"
---

## Summary

...

```_schema
title: "Lesson — 2026-07-07 — synth"
wikilinks: []
```
```

### `music/ideas/[slug].md` — structured chord/melody idea capture

```yaml
---
type: music-idea
created: "2026-07-07"
title: "moody techno progression"
key: "A minor"
progression: ["Am", "F", "C", "G"]
tempo_bpm: 128
genre_tags: ["techno", "melodic-techno"]
instrument_origin: synth
status: seed                        # seed | developing | shelved | finished
source_practice_log: "music/practice-log/2026-07-07-synth.md"
# --- reserved for stretch: Discogs (populated by a future sweep, not this phase) ---
discogs_related_releases: []        # [{release_id, title, artist}, ...] — similar-vibe references
discogs_wantlist_synced_at: null
# --- reserved for stretch: ListenBrainz (populated by a future sweep, not this phase) ---
listenbrainz_similar_tracks: []     # [{recording_mbid, track_name, artist_name}, ...] via cf/recommendation
listenbrainz_synced_at: null
---

## Idea

Freeform description, could grow into a full piece.

[[music/practice-log/2026-07-07-synth]]

```_schema
title: "moody techno progression"
wikilinks: ["music/practice-log/2026-07-07-synth"]
```
```

**Why this shape:**
- `practice-log/` vs `lessons/` split matches the milestone's own listed targets literally and gives the practice-history query feature ("what did I work on last week?") a single, narrow, high-frequency note type to scan (`practice-log/`), separate from lower-frequency, richer `lessons/` notes.
- `ideas/` is deliberately decoupled from both — an idea can originate mid-practice-session (`source_practice_log` back-reference) or standalone.
- Every note carries a `[[wikilink]]` to at least one related note and a trailing ` ```_schema ` block so the existing Phase-45 graph/backlink machinery (`:graph`/`:stats`/`:check`) treats `/music/` as a first-class part of the vault graph rather than an island — this was **not asked for explicitly in the question but is a direct consequence of "no local filesystem writes / respect the Vault seam"**: writes have to go through the same note-quality conventions the rest of the second-brain vault enforces, or `:check` will start reporting `/music/` orphans on day one.
- The reserved `listenbrainz_context` / `discogs_context` / `discogs_related_releases` / `listenbrainz_similar_tracks` blocks are the concrete mechanism requested by the milestone ("data model built to hold these fields from day one") — a future sweep only needs to `PATCH` these keys, never restructure the note.

## Version Compatibility

| Package | Compatible With | Notes |
|---------|------------------|-------|
| `httpx>=0.28.1` | ListenBrainz API (`api.listenbrainz.org`), Discogs API (`api.discogs.com`) | Both are plain REST/JSON over HTTPS; no special client requirements beyond setting a descriptive `User-Agent` header (Discogs explicitly asks for one to get full rate limit) |
| `pyyaml>=6.0.0` | Existing `markdown_frontmatter.py` / `ObsidianClient.patch_frontmatter_field` | Same YAML dialect already in use vault-wide; no new parsing path |
| Python `>=3.12` | pf2e module's floor (`requires-python = ">=3.12"`) | Match it — no reason to diverge; both `liblistenbrainz` (if ever adopted) and `python3-discogs-client` only require `>=3.8`, so no upper constraint conflict either way |

## Sources

- `sentinel-core/app/vault.py` (this repo, read directly) — HIGH confidence: Vault Protocol shape, `write_note`/`read_note`/`find` primitives, `join_frontmatter`/`split_frontmatter` convention
- `modules/pathfinder/app/obsidian.py` + `modules/pathfinder/pyproject.toml` (this repo, read directly) — HIGH confidence: confirms modules own a private Obsidian REST client and lists the exact dependency set/versions already validated for a sibling module
- `sentinel-core/app/services/note_schema.py` (this repo, read directly) — HIGH confidence: trailing ` ```_schema ` block convention, wikilink regex shape
- Context7 `/joalla/discogs_client` (215 snippets, medium reputation) — MEDIUM confidence: `wantlist.add`, `search`, `community.want/have`, user-token vs OAuth authentication examples
- `https://pypi.org/pypi/liblistenbrainz/json`, `https://pypi.org/pypi/python3-discogs-client/json` — MEDIUM confidence (WebFetch, cross-checked against WebSearch results and, for python3-discogs-client, Context7): authoritative current versions and `requires_dist` dependency lists
- `https://listenbrainz.readthedocs.io/en/latest/users/api/core.html`, `https://github.com/metabrainz/liblistenbrainz` — MEDIUM confidence: recent-listens endpoint shape, rate-limit header mechanism, client method names
- `https://www.discogs.com/developers`, `https://python3-discogs-client.readthedocs.io/en/latest/authentication.html`, Discogs community forum threads on `/wants` and rate limits — MEDIUM confidence: auth model, exact wantlist PUT endpoint, 60/25 req-per-minute limits
- WebSearch on `music21` / lightweight chord-representation libraries — MEDIUM confidence: no numeric claims, judgment call corroborated by music21's own documented MIDI-performance caveats

---
*Stack research for: Music Lesson Tracker module (v0.6.0 milestone)*
*Researched: 2026-07-07*
