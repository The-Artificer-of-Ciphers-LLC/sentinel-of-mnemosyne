# Pitfalls Research

**Domain:** Pluggable "Music Lesson Tracker" module added to Sentinel of Mnemosyne (Python/FastAPI/Docker, Obsidian Vault via `Vault` Protocol seam, module registration over `POST /modules/register`, Discord command routing, 6 Rs pipeline, vault sweeper)
**Researched:** 2026-07-08
**Confidence:** HIGH for architecture/integration pitfalls (grounded directly in current `sentinel-core`/`interfaces/discord` source and `.planning/` history); MEDIUM for external-API pitfalls (official ListenBrainz/Discogs docs plus forum corroboration, not independently cross-checked against a live call); LOW for general music-schema/pedagogy claims (no authoritative primary source found — flagged inline)

This module is being grafted onto a system with five hard-won architectural invariants from prior
phases: the `Vault` Protocol seam (ADR-0002), non-destructive sweeper moves (`_trash/` only, never
delete), module isolation (Core never imports module code — modules attach via
`POST /modules/register` and a hand-wired Discord dispatch table), the three-space vault taxonomy
(`self/ notes/ ops/ inbox/ templates/`) that the PARA classifier and sweeper both assume, and the
recall pipeline's fail-soft, budget-bounded design. Nearly every pitfall below is a way of quietly
violating one of these five invariants, not a generic "watch out for APIs" warning.

## Critical Pitfalls

### Pitfall 1: `/music/` isn't in the sweeper's skip-prefix denylist by default

**What goes wrong:**
The vault sweeper (`sentinel-core/app/services/vault_sweeper.py`) walks the *entire* vault on every
sweep and classifies/relocates anything it doesn't recognize as noise or misplaced-topic into
`_trash/{date}/`. It already hardcodes `pf2e/` and `mnemosyne/` into `SWEEP_SKIP_PREFIXES` /
`settings.sweep_skip_prefixes` specifically because the Pathfinder module owns that subtree and the
sweeper must never "helpfully" reclassify module-owned content. If the Music module starts writing
to `/music/lessons/`, `/music/practice-log/`, `/music/ideas/` without a matching skip-prefix entry,
the very next sweep will walk into those notes, run noise/duplicate/misplaced-topic heuristics
against them, and (non-destructively, but disruptively) relocate practice logs into `_trash/`.

**Why it happens:**
The Core-side skip-prefix list is not auto-derived from `POST /modules/register` — there is no
mechanism today by which a module announces "this subtree is mine, don't sweep it." It's a
hand-maintained `tuple[str, ...]` in `app/config.py` that every prior module (Pathfinder) had to be
added to manually. It's easy to build the whole Music module, get it working end-to-end in manual
testing, and never notice the gap until the first scheduled sweep runs days later.

**How to avoid:**
Add `"music/"` to `settings.sweep_skip_prefixes` (env-overridable per the existing pattern — see the
comment at `sentinel-core/app/config.py:133-136`: *"Override via env SWEEP_SKIP_PREFIXES (JSON list)
when a new module mounts a curated dir"*) as part of the phase that ships the first `/music/` write.
Do this in the same phase/commit as the first Vault write, not as a follow-up — there is no test
today that would catch the omission other than a live sweep.

**Warning signs:**
A scheduled or manually-triggered `:vault-sweep` run reports moves for paths under `music/`; a
practice log that existed yesterday is missing from `/music/practice-log/` today (check `_trash/`).

**Phase to address:**
The phase that ships the first `/music/` Vault write (Obsidian integration / practice logging
phase) — add the skip-prefix as an explicit acceptance criterion, not an afterthought.

---

### Pitfall 2: assuming module registration alone exposes a Discord command surface

**What goes wrong:**
`POST /modules/register` only tells Sentinel Core "proxy HTTP calls to this base_url" — it does
*not* wire a Discord verb. The `:pf` verb exists because `interfaces/discord/command_router.py`
hand-branches `if subcmd == "pf": return await pf_dispatch(...)`, backed by a bespoke
`pathfinder_dispatch.py` and per-noun contract modules (see `Pathfinder command contract` in
`CONTEXT.md`). Building the full Music module and registering its routes with Core will not produce
a `:music` command in Discord — that requires a parallel, hand-written dispatch module and an
explicit branch in `command_router.py`, in a *different* container/codebase
(`interfaces/discord/`) than the module itself.

**Why it happens:**
Module isolation (Core never imports module code) makes it easy to assume the module is "fully
integrated" once `/modules/register` succeeds and `curl` against its routes works. The Discord
surface is a second, independent integration point that lives outside both `sentinel-core` and the
new module's own repo tree.

**How to avoid:**
Treat "Discord command surface" as its own deliverable with its own acceptance criteria, mirroring
the Pathfinder pattern exactly: a `music_dispatch.py` in `interfaces/discord/`, a
`subcmd == "music"` branch in `command_router.py`, and entries in the `subcommand_prompts` /
`plugin_prompts` dicts and the `/sen` help text. Reuse the `Pathfinder command contract` pattern
(noun-specific payload/route modules with tests that validate generated payloads against the
route's Pydantic request model) — this project already paid for that lesson once (see Pitfall 3).

**Warning signs:**
`:music <anything>` in Discord falls through to `call_core` (freeform chat) instead of hitting the
module; `USER-GUIDE.md` documents fewer `:music` verbs than the module actually ships (this project
has a documented history of exactly this gap — see `CONTEXT.md` DOC-002/DOC-003).

**Phase to address:**
A dedicated "Discord command surface" phase or plan, sequenced after the module's HTTP routes are
stable — do not fold it silently into the module-build phase where it's easy to skip.

---

### Pitfall 3: adapter-to-route payload drift (422s that unit tests won't catch)

**What goes wrong:**
This exact failure mode already happened three times in this codebase during Phase 37
(`PHASE37-A`, `PHASE37-C`/`E` in `CONTEXT.md`'s `session_issues` log): a Discord adapter command
posts a payload shape that doesn't match the route's Pydantic request model (`{question}` vs
`{text}`, missing required fields), and every live invocation 422s — while adapter unit tests pass
green because they mock `post_to_module` and never validate against the real schema. For the Music
module this is a near-certainty risk given the same architecture (Discord adapter → HTTP proxy →
module route) will be reused for practice logging, idea capture, and routine-builder commands.

**Why it happens:**
Unit tests at the adapter boundary mock the HTTP call itself, so they only prove "the adapter calls
`post_to_module` with *some* dict" — never that the dict matches the route's actual Pydantic model.
The contract lives in two places (adapter-constructed payload, route-declared schema) with no shared
source of truth.

**How to avoid:**
Follow the `Pathfinder command contract` fix already adopted in this codebase: dedicated,
noun-specific contract modules that own the route string and payload shape, with tests that
construct a contract payload and validate it against the actual route's Pydantic request model
(not a mock). At minimum, run one real end-to-end `curl`/live-container smoke test per new Discord
verb before calling a plan done — this project's own `verifier_blind_spots` note states the rule
explicitly: *"trust-but-verify must pull at least one E2E curl through the real container before
accepting verifier PASS for shipped HTTP features."*

**Warning signs:**
Adapter unit tests are 100% green but a manual Discord command returns a generic error/422; the
route's request model was edited without a corresponding contract-module update.

**Phase to address:**
Every phase that ships a new Discord verb for the Music module — bake the contract-module pattern
and the E2E smoke check into the phase's own verification loop, don't defer to a later hardening
phase.

---

### Pitfall 4: practice-log volume degrades warm-tier recall relevance for everything else

**What goes wrong:**
`RecallConfig.exclude_prefixes` (`ops/`, `_trash/`, `self/`, `inbox/`) does **not** include `music/`
by default, and there is no existing reason it should — practice-history queries need `/music/` to
be searchable. But that means every practice-log note the module writes becomes part of the same
BM25 + semantic corpus the Sentinel searches for *every* unrelated conversation, and the vault
sweeper embeds every non-skipped note on every sweep. If practice logging is frequent
(daily/per-session) and low-signal ("30 min, worked on scales, felt tired"), two things degrade
over time: (1) sweep cost grows roughly linearly with the number of practice notes, since the
sweeper re-walks and (re-)embeds the whole non-skipped vault; (2) semantically similar,
high-frequency, low-information notes can crowd out more relevant results in warm-tier recall for
non-music conversations, especially given Obsidian's search is conjunctive-AND-only (per the
`obsidian_search_invariant` note in `CONTEXT.md`) — more terms means fewer, more brittle matches.

**Why it happens:**
The existing recall/sweep design was tuned against Pathfinder's content (a few dozen NPC/session
notes) and the Sentinel's own conversational journal — not a module that could plausibly write one
note per practice session, potentially several times a week, indefinitely.

**How to avoid:**
Decide deliberately, in the phase that designs the `/music/` note format, whether practice logs
should be warm-tier-searchable at all, or whether they belong in a namespace closer to `ops/`
semantics (operational, excluded from warm recall, but still sweeper-visible for the module's own
history queries which go through the module's own storage/query layer, not Recall). If they must be
searchable, keep per-session note bodies short and let the module's own practice-history query
endpoint do structured aggregation instead of relying on Sentinel warm-tier recall to answer "how
long on this piece" questions — that's a job for the module's own data layer (see Pitfall 6), not
for BM25/vector search over freeform notes.

**Warning signs:**
Warm-tier search results for unrelated queries start surfacing practice-log notes; sweep duration
grows measurably after the Music module ships; `:vault-sweep` embedding step takes noticeably
longer session over session.

**Phase to address:**
The Obsidian integration / note-format phase (decide the namespace's Recall exposure up front) and
the practice-history-query phase (make sure aggregate queries don't depend on warm-tier recall
quality).

---

### Pitfall 5: external API downtime or auth failure breaking the core journal path

**What goes wrong:**
ListenBrainz pull and Discogs writes are explicitly STRETCH features layered on top of core
practice-logging. If the module's practice-log write path calls out to either external API
synchronously (e.g., "enrich this session with a Discogs suggestion before saving"), any API
downtime, rate-limit (429), or auth failure (expired/revoked token) blocks or corrupts the
non-negotiable core behavior — logging a practice session. This project has already hit this class
of bug once: `Session summary` writes are explicitly documented as "best-effort — write failure
does not fail the response" specifically to prevent Vault-write failures from breaking `POST
/message`. A synchronous external-API dependency in the practice-log write path reintroduces the
exact failure mode that pattern was built to avoid.

**Why it happens:**
It's tempting to build the "enrichment" and the "core write" as one code path, especially since
Discogs/ListenBrainz calls feel like they belong "next to" the practice log they annotate.

**How to avoid:**
Core practice-session logging (duration, pieces, focus area, notes) must succeed and persist to the
Vault independent of any external API call. Treat ListenBrainz/Discogs calls as async, best-effort,
fire-and-forget enrichment (background task via the existing `task_runner.py` seam, mirroring the
sweeper's background-scheduling pattern) that can fail silently (logged, not raised) without
touching the write that already happened. Build and verify core logging with zero external-API
calls in the phase before either stretch integration is attempted (this also directly serves the
"don't over-invest in stretch before core works" concern — see Pitfall 7).

**Warning signs:**
A practice log fails to save when Wi-Fi/ListenBrainz/Discogs is unreachable; error logs show
`httpx.TransportError` or `429` originating from inside a request that also wrote the Vault note;
manual testing "forgets" to try logging a session with the external APIs unreachable.

**Phase to address:**
Core practice-logging phase must ship and pass verification with zero external-API code in the
write path. Whichever phase adds ListenBrainz/Discogs must add them as a strictly additive,
failure-isolated background step — never inline in the save path.

---

### Pitfall 6: freeform practice notes can't answer "how long on this piece" without a real data model

**What goes wrong:**
"How long have I spent on this piece across all sessions?" and "what did I work on last week?" are
explicitly required practice-history queries. If practice sessions are stored as freeform markdown
notes (mirroring the Sentinel's own journal style) with piece names typed inconsistently
session-to-session ("Chameleon", "chameleon (Herbie Hancock)", "Chameleon - HH"), there is no
reliable way to aggregate duration by piece without either (a) an LLM re-parsing every note at query
time (slow, non-deterministic, and breaks the "no per-note HTTP call at query time" principle this
project already established for embeddings — see the Embedding sidecar index glossary entry) or (b)
silently under/over-counting because slug variants don't match.

**Why it happens:**
Freeform markdown is the Sentinel's native idiom (journal entries, session summaries), so it's the
default reach for a new module — but table-stakes aggregate queries need structured fields
(piece slug, duration, instrument, date), not prose the Sentinel has to re-interpret every time.

**How to avoid:**
Model pieces as a first-class slugged entity (deterministic slugify, not LLM-normalized, so the
same piece always resolves to the same slug regardless of how the operator typed it that day) with
practice-session rows/frontmatter referencing the slug plus a duration and date. Store the
structured data (piece slug, duration, focus area, instrument) in frontmatter or a sidecar
index — mirroring the `embedding_sidecar_index.py` / `links-index.json` pattern this project already
uses for structured derived data alongside markdown — rather than depending on free-text parsing at
query time. Keep the freeform notes for narrative content ("felt tired," "breakthrough on the bridge
section") separate from the structured fields the aggregate queries actually run against.
*(General music-schema pitfall corroboration is LOW confidence — no authoritative primary source
found beyond generic DB-design guidance; the slug/aggregation risk itself is HIGH confidence,
directly derived from this project's own `embedding_sidecar_index.py` "no query-time parsing"
precedent.)*

**Warning signs:**
"How long on this piece" queries return different totals depending on note phrasing; two notes
about the same piece don't link to each other; the module has to call an LLM to answer a duration
question it should be able to answer with arithmetic.

**Phase to address:**
The data-modeling phase for practice sessions/pieces, before the practice-history query phase is
built on top of it — get the slug/structured-field decision right first, because query logic and
Obsidian note format both depend on it.

---

### Pitfall 7: over-building the stretch integrations before the core module proves out

**What goes wrong:**
ListenBrainz pull and Discogs wantlist writes are explicitly marked STRETCH in `PROJECT.md`, but
they're also the most "interesting" engineering work (OAuth 1.0a, rate-limit-aware pagination,
external data reconciliation) compared to the comparatively mundane core loop (log a session, write
a note, answer a query). It's easy to burn a disproportionate share of the milestone on the stretch
integrations — including reserving Discogs/ListenBrainz-shaped fields in the data model "for
later" — while the core practice-logging/routine-builder loop that the milestone is actually named
for stays half-built.

**Why it happens:**
External API integration work has a satisfying, bounded shape (read docs, write client, handle
auth) that's easy to scope and estimate, whereas "make practice-history queries good" and "make the
routine builder actually useful" are open-ended, judgment-heavy problems that are easy to
under-scope.

**How to avoid:**
Sequence phases so core logging, idea capture, history queries, and the routine builder ship and
get UAT'd *before* any ListenBrainz/Discogs phase starts. It's fine to reserve schema fields for
`listenbrainz_id` / `discogs_release_id` day one (cheap, low-risk, avoids a later migration) — but
do not build the client, auth flow, or write path for either integration until the core module is
validated end-to-end. Explicitly gate the stretch phases behind the milestone's core success
criteria in the roadmap, not just informally.

**Warning signs:**
Roadmap/phase ordering puts ListenBrainz or Discogs work before the routine builder or history
queries; schema has populated Discogs/ListenBrainz fields but no operator has yet used the
core practice-log flow for a week of real sessions.

**Phase to address:**
Roadmap sequencing decision, made explicit at roadmap-creation time — core phases (logging, idea
capture, history queries, routine builder) ordered strictly before stretch phases (ListenBrainz,
Discogs).

---

### Pitfall 8: LLM-generated practice routines given unearned authority on technique/injury

**What goes wrong:**
The practice-routine builder is explicitly instrument-specific (electric guitar, electric bass,
synth, piano/keys, production/sampler) and genre-oriented (EDM/techno/melodic techno). An LLM asked
to "build me a routine" will readily generate confident-sounding technique instructions (hand
position, stretching, repetition counts) that it has no grounding to validate for a specific
player's physical situation — and, per general findings on AI-assisted music instruction, this kind
of advice is specifically flagged as unreliable "without seeing a musician's actual playing," with
real risk when it strays into posture/tension/pain territory (musculoskeletal strain is a known
issue in instrumental practice). A generic, ungrounded routine also just tends to be *useless* even
setting safety aside — reused boilerplate ("practice scales for 10 minutes, then arpeggios") that
ignores the operator's actual skill level, instrument, and stated goals.

**Why it happens:**
Routine generation is an attractive target for "just ask the LLM" because it's low-effort to wire
up and produces plausible-looking output immediately — the failure mode (generic or subtly unsafe
advice) doesn't show up in a quick manual test, only after repeated real use.

**How to avoid:**
Two-part mitigation: (1) ground routine generation in structured domain input, not a bare prompt —
feed it the operator's actual practice history (from Pitfall 6's structured data), stated skill
level/goals, and instrument, and constrain output to routine *structure* (warm-up → technical
focus → repertoire → cool-down, time-boxed per section) rather than open-ended technique
instruction; (2) explicitly scope the routine builder to *practice planning*, not technique
correction — any output touching posture, hand position, or pain/tension should either be omitted
or carry an explicit "this is not injury/technique guidance, consult a teacher" framing, mirroring
the general finding that AI works best as a practice-structure assistant, not a
technique-correction authority. *(This finding is corroborated by general web sources at LOW/MEDIUM
confidence — no music-pedagogy-specific primary source was found; treat as a design-caution
principle, not a verified clinical claim.)*

**Warning signs:**
Generated routines are near-identical across different instruments/skill levels/goals; routines
include specific physical/technique instructions (hand position, stretches) rather than structural
planning; UAT feedback says "this routine doesn't fit what I actually need to work on."

**Phase to address:**
The practice-routine-builder phase — bake the structured-input grounding and the
scope-to-planning-not-technique constraint into the phase's design contract (`AI-SPEC.md` via
`gsd-ai-integration-phase`) before generation logic is built, not as a post-hoc guardrail.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|-----------------|------------------|
| Store practice sessions as freeform markdown only, no structured slug/duration fields | Fastest to ship, matches Sentinel's native journal idiom | Aggregate history queries ("how long on this piece") become unreliable or require LLM re-parsing at query time | Never for the history-query features — acceptable only for the idea-capture freeform notes, not session logs |
| Skip the `music/` sweep-skip-prefix "for now, add it later" | One less config line in the first phase | Silent, non-obvious data relocation into `_trash/` on the first scheduled sweep after ship | Never — this is a one-line change with a known, documented pattern; there's no reason to defer it |
| Build ListenBrainz/Discogs clients before core logging is UAT-validated | Satisfying, bounded engineering work up front | Milestone risk: core deliverable (the thing the milestone is named for) ships late or incomplete | Never — explicitly out of order per Pitfall 7 |
| Let the LLM freely generate technique/injury-adjacent advice in routines | Routine builder feels "smarter," less scoping work | Unearned authority on physical technique with no grounding in the player's actual movement | Acceptable only if every such output is explicitly framed as non-authoritative and points to a teacher |
| Inline Discogs/ListenBrainz calls in the practice-log write path | Simpler control flow, one request | Reintroduces the exact "external dependency breaks core write" failure mode `ops/sessions/` writes are already hardened against | Never |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|-----------------|-------------------|
| ListenBrainz (read) | Polling without honoring `X-RateLimit-Remaining`/429 backoff, or re-fetching the full history every pull instead of paginating from a stored high-water-mark timestamp | Respect rate-limit headers with backoff on 429; pull incrementally using ListenBrainz's timestamp-based pagination (max 100 items/GET) from the last successfully-processed listen, stored in module state |
| Discogs (write) | Assuming wantlist "add" needs an app-side duplicate check | Discogs' add-to-wantlist endpoint is `PUT /users/{username}/wants/{release_id}` — PUT is naturally idempotent because `release_id` is the resource key in the URL; re-adding the same release is a no-op by HTTP semantics, not something the module needs to defend against itself. Only *new-release-id* duplicates (e.g. two different Discogs release IDs for what's musically "the same" reissue) need app-side handling |
| Discogs/ListenBrainz auth | Storing personal-access/user tokens in `.env` alongside non-secret config, or baking them into the compose file's `environment:` block | Follow the existing `sentinel-core`/Pathfinder pattern: Docker secrets file (`secrets/<name>`) referenced via the compose `secrets:` block, never a plaintext env value in `compose.yml` (see `modules/pathfinder/compose.yml`'s `sentinel_api_key` pattern) |
| Sentinel Core `/modules/register` proxy | Assuming a registered module survives a Core restart | The module registry is an in-memory `dict` on `app.state.module_registry` — it is rebuilt from each module's own re-registration on startup (with backoff retry, per Pathfinder's `main.py` lifespan pattern). The Music module must replicate that same registration-with-retry lifespan behavior, or a Core restart silently drops it from `/modules` until the Music container itself restarts |
| Sentinel Core module proxy POST timeout | Assuming module calls can run indefinitely | `proxy_module` enforces a 120s timeout on proxied POSTs (`app/routes/modules.py`); any routine-builder LLM call or Discogs/ListenBrainz batch pull invoked synchronously through the proxy must complete within that window or return `504` — long-running work belongs in a background task with a polling status endpoint (mirroring `note_sweep_runner`'s start/status pattern), not a single blocking proxied call |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|-----------------|
| Sweeper re-embeds the growing `/music/` corpus every sweep | Sweep duration creeps up session over session; `:vault-sweep` embedding step dominates total sweep time | Keep per-session note bodies short; consider whether `/music/` needs semantic embedding at all if history queries go through the module's own structured store instead of Recall | Noticeable once practice-log note count reaches the low hundreds, given no incremental-embedding skip beyond model-mismatch/frontmatter checks already in `embedding_sidecar_index.py` |
| Warm-tier BM25 search degraded by high-frequency, low-signal notes | Unrelated Sentinel conversations start surfacing practice-log snippets; relevance feels worse after Music module ships | Exclude `/music/` from `RecallConfig.exclude_prefixes` deliberately if history queries don't need warm-tier recall, or keep note bodies terse and structured-field-first | As soon as practice logging becomes a regular (multiple-times-weekly) habit |
| Discogs/ListenBrainz pull done as a full-history re-fetch each run | Slow syncs, rate-limit exhaustion, redundant writes | Store a high-water-mark (last listen timestamp / last wantlist state) and pull incrementally | Immediately, once listening/collection history exceeds a handful of pages |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| ListenBrainz/Discogs tokens stored in `.env` or committed compose files | Token leak via git history or shared `.env`, same class of risk `secrets/sentinel_api_key` was already designed to avoid | Use Docker secrets files under `secrets/`, referenced via compose `secrets:`, matching the existing `sentinel_api_key` pattern exactly |
| Music module trusts unauthenticated requests to its own routes | Any container on the Docker network (or a misconfigured proxy) could write/query practice data | Require the same `X-Sentinel-Key` header check pattern already used by Pathfinder's inbound routes (e.g. `foundry.py`'s `X-Sentinel-Key` validation) |
| Routine builder or idea-capture endpoints pass raw user text straight into external-API-bound fields (e.g. a Discogs search query built from freeform practice notes) | Injection into third-party API query params, unexpected external calls driven by uncontrolled input | Validate/sanitize any user-supplied text before it becomes part of an outbound external-API request; treat freeform note content as untrusted input to the same degree the `untrusted-input-boundary` guidance already requires for other user-supplied content in this project |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|------------------|
| Practice-history queries only understand exact piece-title matches | "How long on Chameleon" returns nothing because a session was logged as "chameleon" | Deterministic slugification (not fuzzy LLM matching) at write time so the same piece always resolves the same way regardless of casing/typing variance |
| Routine builder produces one generic routine regardless of stated goal/instrument/history | Routines feel copy-pasted, operator stops using the feature | Ground generation in the operator's actual recent practice history and stated focus areas (Pitfall 8) |
| Discord `:music` verbs use different argument conventions than the established `:pf` pattern | Operator has to relearn command syntax per module | Reuse the pipe-separated / verb-noun conventions already established for `:pf` (`interfaces/discord/pathfinder_dispatch.py`) unless there's a concrete reason to diverge |

## "Looks Done But Isn't" Checklist

- [ ] **`/music/` Vault writes:** Often missing the sweeper skip-prefix — verify a live `:vault-sweep` run doesn't relocate any `music/` note into `_trash/`
- [ ] **Discord `:music` commands:** Often stops at "module routes respond to curl" — verify an actual Discord message through `command_router.py` reaches the module (not just the HTTP route directly)
- [ ] **Adapter payloads:** Often validated only against a mocked HTTP call in adapter unit tests — verify the payload against the real route's Pydantic request model (or run a live E2E curl) before calling a plan done
- [ ] **Practice-history queries:** Often demoed against a handful of hand-entered clean examples — verify aggregation still works with realistic messy piece-name variance across many sessions
- [ ] **Core practice logging:** Often only tested with all external services reachable — verify a practice log still saves successfully with ListenBrainz/Discogs unreachable (unplug network to those hosts, or point config at a bad URL)
- [ ] **Discogs wantlist writes:** Often assumed to need app-side dedupe — verify the actual endpoint semantics (PUT-by-release-id is idempotent) before building unnecessary dedupe logic
- [ ] **Routine builder output:** Often eyeballed once for "looks reasonable" — verify routines actually vary meaningfully across different instruments/skill levels/stated goals, and that no output implies clinical/technique authority

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|----------------|------------------|
| Sweeper relocated `music/` notes to `_trash/` before the skip-prefix was added | LOW | Sweeper is non-destructive by design — restore the moved files from `_trash/{date}/` back to their original `music/` path, then add the skip-prefix before running another sweep |
| Discord `:music` verb shipped with adapter/route payload drift (422s in production) | LOW–MEDIUM | Same fix pattern already used for `PHASE37-A`/`E`: correct the adapter payload to match the route's Pydantic model, add a contract-module test that validates against the real schema, ship a point fix |
| Practice history unreliable due to inconsistent piece slugs already in the vault | MEDIUM | Write a one-time backfill pass that deterministically re-slugifies existing session notes/frontmatter and merges duplicate piece entities; this is exactly the kind of migration this project already has precedent for (Phase 47's flat-7 → PARA backfill) |
| Warm-tier recall degraded by accumulated practice-log volume | MEDIUM | Retroactively add `music/` to `RecallConfig.exclude_prefixes` (config-only change, no data migration) and rely on the module's own structured-query layer for history questions going forward |
| Discogs/ListenBrainz token committed to `.env`/git history | MEDIUM–HIGH | Revoke and rotate the token immediately at the provider, purge from git history if committed, migrate to the Docker-secrets-file pattern |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|-------------------|---------------|
| Sweeper sweeps unrecognized `/music/` content | Phase that ships first `/music/` Vault write | Live `:vault-sweep` run after the note exists; confirm `music/` paths appear in the active `sweep_skip_prefixes` and are absent from sweep move reports |
| No Discord command surface despite module registration | Discord command-surface phase (after module routes stabilize) | Manual `:music <verb>` message through the real Discord bot reaches the module and returns expected content, not a fallthrough to freeform chat |
| Adapter/route payload drift | Every phase shipping a new `:music` verb | Contract-module test validates payload against the real Pydantic request model; one live E2E curl/smoke test per verb before verifier PASS |
| Practice-log volume degrades warm recall / inflates sweep cost | Obsidian note-format design phase | Decide and document `/music/` Recall-exposure policy explicitly in the phase's design notes; monitor sweep duration post-ship |
| External API failure breaks core logging | Core practice-logging phase (must ship with zero external-API code in the write path) | Manual test: log a session with ListenBrainz/Discogs config pointed at an unreachable host; confirm the note still saves |
| Freeform notes can't answer duration/aggregate queries | Practice-session/piece data-modeling phase | Query "how long on X" against sessions logged with inconsistent piece-name casing/phrasing; confirm correct aggregation via slug, not text match |
| Stretch integrations built before core validated | Roadmap sequencing (roadmap-creation time) | Roadmap phase order places ListenBrainz/Discogs strictly after core logging, idea capture, history queries, and routine builder |
| LLM routine builder gives ungrounded technique/injury advice | Practice-routine-builder phase | AI-SPEC design contract constrains output to practice-planning structure; UAT checks routines vary meaningfully by instrument/skill/goal and contain no unframed technique/injury claims |

## Sources

- `sentinel-core/app/services/vault_sweeper.py`, `sentinel-core/app/config.py` (`SWEEP_SKIP_PREFIXES` / `settings.sweep_skip_prefixes`) — HIGH confidence, current source read directly
- `sentinel-core/app/services/recall.py` (`RecallConfig.exclude_prefixes`), `sentinel-core/app/services/embedding_sidecar_index.py` — HIGH confidence, current source
- `sentinel-core/app/routes/modules.py`, `sentinel-core/app/services/module_registry.py`, `modules/pathfinder/compose.yml`, `modules/pathfinder/app/main.py` (registration/retry, secrets pattern, proxy timeout) — HIGH confidence, current source
- `interfaces/discord/command_router.py`, `CONTEXT.md` (`Pathfinder command contract`, `session_issues` log entries `PHASE37-A/C/E/F`, `verifier_blind_spots`, `DOC-002/DOC-003`) — HIGH confidence, current source and documented project history
- `.planning/PROJECT.md` — HIGH confidence, current milestone constraints and prior architecture decisions
- [ListenBrainz API documentation](https://listenbrainz.readthedocs.io/en/latest/users/api/index.html) — MEDIUM confidence, official docs via web search
- [ListenBrainz API Usage Examples](https://listenbrainz.readthedocs.io/en/latest/users/api-usage.html) — MEDIUM confidence, official docs via web search
- [Discogs API Documentation](https://www.discogs.com/developers) and Discogs API forum threads on wantlist/rate-limiting — MEDIUM/LOW confidence, official docs plus community forum corroboration via web search
- General web search results on AI-assisted music technique/injury risk (Practis blog, Stanford Engineering piano-injury-risk coverage, guitar-AI blogs) — LOW confidence, no music-pedagogy-specific primary source found; treated as directional caution, not verified clinical guidance
- General web search results on music/practice-log database schema design and MusicBrainz's tag/tag_raw provenance-separation pattern — LOW confidence, no authoritative pitfalls-specific source found; used only as a design precedent, not a verified claim

---
*Pitfalls research for: Music Lesson Tracker module (Sentinel of Mnemosyne v0.6.0)*
*Researched: 2026-07-08*
