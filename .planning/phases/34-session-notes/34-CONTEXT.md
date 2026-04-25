# Phase 34: Session Notes — Context

**Gathered:** 2026-04-25
**Status:** Ready for planning

<domain>
## Phase Boundary

The DM runs `:pf session start` to begin a Pathfinder 2e play session, logs timestamped events with `:pf session log <event>` during play (with optional typed prefixes for combat/dialogue/decisions/discoveries/loot/notes), inspects the running narrative with `:pf session show`, undoes mistypes with `:pf session undo`, and finalizes with `:pf session end`. At end-of-session, the pathfinder module runs a single LLM call that produces a third-person past-tense storyteller-voice recap, extracts NPC and location mentions, and writes a structured note to `mnemosyne/pf2e/sessions/YYYY-MM-DD.md` with both the in-session "story so far" running narrative and the final recap. NPC mentions are wikilinked at log-time (exact slug + name match against `mnemosyne/pf2e/npcs/`) with a final LLM cleanup pass at session-end. Location mentions are LLM-extracted at session-end, wikilinked, and auto-stubbed under `mnemosyne/pf2e/locations/`.

**In scope (SES-01..03):**
- 5-verb Discord command surface: `:pf session {start, log, end, show, undo}`, plus `--retry-recap` flag on `end` and `--recap` flag / settings toggle on `start`
- Active-session state tracked via the session note's frontmatter (`status: open` while live, `status: ended` when finalized)
- Append-on-log persistence: every `:pf session log` immediately PATCHes the open note's `## Events Log` heading via Obsidian REST API (Operation: append)
- LLM-styled "story so far" narrative regenerated on every `:pf session show` call (no caching), persisted into `## Story So Far` section
- Single end-of-session LLM call producing structured JSON output: `{recap, npcs[], locations[], npc_notes_per_character{}}`
- Auto-stub creation for new locations under `mnemosyne/pf2e/locations/` (frontmatter-only placeholders the DM fills later)
- Discord button on `:pf session start` ("Recap last session?") with 180s timeout, plus `--recap` flag and a settings toggle for always-recap
- Failure-mode hardening: skeleton note + `--retry-recap` flag when LLM fails at end; refuse-on-Obsidian-down at start
- Frontmatter `schema_version: 1` field for forward-compatible reads
- 14th entry in `REGISTRATION_PAYLOAD` for the `session` route
- 4th noun in `_PF_NOUNS` (`{npc, harvest, rule, session}`)

**Out of scope (deferred to follow-up phases):**
- Campaign-narrative compiler — a `:pf session story` (or similar) verb that aggregates every session note's recap into a single read-the-adventure document. Phase 34 ensures every session note carries its storyteller-voice recap in frontmatter so a future Phase 34.x or later can compile them; no compilation code in this phase.
- Locations CRUD — a Phase 29-equivalent `:pf location {create, update, show, relate}` command surface. Phase 34 only ships placeholder stubs; full schema (level/region/inhabitants/etc.) is a separate phase.
- In-game time / calendar — wall-clock UTC only in MVP; in-game date markers (e.g., "Calistran 14, evening") explicitly deferred.
- Edit-by-index for events — only `undo` (pops last) in MVP; `:pf session edit <idx>` is deferred.
- Event-thread integration — recap LLM consumes event log + linked NPC frontmatter only. Crawling Phase 31 `:pf npc say` Discord threads for verbatim NPC dialogue is a deferred enhancement (would enrich the recap but adds Discord history wiring).

</domain>

<decisions>
## Implementation Decisions

### Discord command surface
- **D-01 (verbs):** `:pf session {start, log, end, show, undo}`. Five verbs, mirrors the noun+verb shape of `:pf rule {<query>, show, history, list}` from Phase 33.
- **D-02 (noun set extension):** `_PF_NOUNS = frozenset({"npc", "harvest", "rule", "session"})` in `interfaces/discord/bot.py`. Extends the Phase 32/33 pattern (single-line addition).
- **D-03 (registration):** Add `{"path": "session", "description": "DM session notes with timestamped event logging and AI-stylized recap (SES-01..03)"}` to `REGISTRATION_PAYLOAD` in `modules/pathfinder/app/main.py:63`. The pathfinder route handles all 5 verbs internally via a `verb` field in the request body.
- **D-04 (dispatch):** Reuse `_pf_dispatch` from Phase 29 D-02. New branch `elif noun == "session":` parses the verb + args and calls `SentinelCoreClient` against `POST /modules/pathfinder/session`. The pathfinder route receives `{verb: "log", args: "Party arrived in Westcrown", flags: {}}` and dispatches internally.

### Active-session state model
- **D-05 (state lives in the open note):** No in-memory state. The session note IS the source of truth. `:pf session start` PUTs `mnemosyne/pf2e/sessions/YYYY-MM-DD.md` with `status: open` frontmatter and an empty `## Events Log` section. Every `:pf session log` PATCH-appends under `## Events Log`. `:pf session end` flips `status` to `ended` and rewrites the note with the recap, NPCs, locations, story-so-far. Survives container restart by design.
- **D-06 (collision policy):** If today's `YYYY-MM-DD.md` exists with `status: open` → refuse with embed: `"Session already in progress at <path> — use :pf session show or :pf session end."` If `status: ended` → refuse with embed: `"Today's session is already finalized at <path>. Use :pf session start --force to start a second session as YYYY-MM-DD-2.md."` The `--force` flag uses the next available numeric suffix.
- **D-07 (Obsidian-down at start):** If the Obsidian REST API is unreachable when `:pf session start` runs, refuse with diagnostic embed: `"Obsidian REST API unreachable at <base_url>. Start the Obsidian app and retry."` No session is started, no in-memory fallback. Mirrors how Phase 29 NPC commands fail when Obsidian is down — Obsidian IS the database.

### Recap on session start
- **D-08 (button-prompted recap):** When `:pf session start` runs and the most recent prior session note exists (with `status: ended`), the bot replies with a Discord embed showing today's session start confirmation **plus** an interactive `discord.ui.View` containing a single button labeled "Recap last session". The button click triggers a follow-up embed showing the prior session's frontmatter `recap` field rendered as the storyteller text. No new LLM call at start — recap text was generated and stored at the prior session's `end`.
- **D-09 (`--recap` flag):** `:pf session start --recap` skips the button prompt and posts the prior recap embed directly. Useful for autonomy and for the always-on toggle path.
- **D-10 (always-recap setting):** A persistent setting (env var `SESSION_AUTO_RECAP=true|false`, default `false`; researcher confirms whether env or a `mnemosyne/pf2e/sessions/.config.yaml` is the right home) makes start always show the recap without the button. When `true`, behavior matches `--recap`. When `false`, default behavior is the button prompt.
- **D-11 (button timeout 180s):** Default `discord.ui.View` timeout. After expiry, the bot edits its message to plain text: `"Recap timed out — use :pf session start --recap to recap later."` The new session is already started; the recap is just deferred. Researcher picks the exact `discord.ui.View` subclass and persistence behavior across bot restarts.

### Event log model (`:pf session log`)
- **D-12 (freeform with optional typed prefix):** Default form: `:pf session log Party arrived in Westcrown` — freeform single-line text, stored as a `note` event. Typed form: `:pf session log combat: Party fought 3 goblins, Varek dropped to 8 HP`. Recognized types (closed enum, validated): `combat`, `dialogue`, `decision`, `discovery`, `loot`, `note`. Untyped lines default to `note`. Unknown types fall through as part of the freeform text (not validated as a type, no error).
- **D-13 (timestamps — wall-clock UTC, rendered local):** Server stamps each event with `datetime.now(timezone.utc)` and renders it in HH:MM in the configured timezone. Researcher picks the env var (`SESSION_TZ` defaulting to `America/New_York` is a candidate) and confirms how Obsidian renders the timestamp consistently. In-game date markers explicitly deferred.
- **D-14 (per-event line format):** `- HH:MM [type] text` markdown bullet under `## Events Log`. Examples:
  - `- 19:42 [combat] Party fought 3 goblins, Varek dropped to 8 HP`
  - `- 19:55 Party regrouped at the inn` (untyped → no bracket, treated as `note`)
  Bracketed type omitted when untyped to keep the line clean.
- **D-15 (length cap 500 chars per event):** Hard limit per `:pf session log`. Multi-line input rejected (newlines stripped or refused with hint). Mid-play UX favors many short events over rare long ones; a single long narrative belongs in 2-3 follow-up logs.
- **D-16 (persistence — Obsidian PATCH-append):** Each `log` call: `PATCH /vault/<path>` with headers `Target-Type: heading`, `Target: Events Log`, `Operation: append`, body = the formatted line. One Obsidian roundtrip per log; survives container restart. Researcher confirms the heading-target Operation: append is supported on the deployed Obsidian REST API version (CLAUDE.md table claims it; spike if uncertain).
- **D-17 (`undo` verb):** `:pf session undo` reads the open note, removes the last bullet under `## Events Log`, rewrites the section via PATCH with `Operation: replace` (or GET-then-PUT fallback if heading-replace is unsupported). Reply embed: `Removed: <quoted line> (N events remaining).` Refuses if no active session or 0 events with helpful embed.

### `:pf session show` (mid-session narrative)
- **D-18 (LLM-stylized "story so far"):** `:pf session show` reads the open note's `## Events Log`, calls the LLM with a storyteller-voice prompt, returns a Discord embed containing the third-person past-tense narrative recap of the session-to-date. Title: `Story so far — <session date>`. No caching — always regenerate (LLM cost is small per session, on-device LM Studio is free).
- **D-19 (persist running narrative into the note):** Each `:pf session show` also writes the generated narrative into the open note's `## Story So Far` section (overwriting whatever was there). This way the final session note carries both the running narrative (last `show`'s output) and the end-of-session recap. Enables a future campaign-narrative compiler to choose either source.
- **D-20 (slow-query UX):** `:pf session show` may take 2-5s with on-device LM Studio. Reuse Phase 31/33's placeholder→edit pattern: bot posts `"Generating story so far..."` embed immediately, edits with the final narrative when LLM returns. Researcher picks the exact Discord library API (`Message.edit()` vs `Interaction.followup`).

### NPC link resolution
- **D-21 (dual-pass linking):** Two passes.
  - **Log-time fast pass:** Each `:pf session log <text>` runs an exact word-boundary case-insensitive match against the union of all NPC slugs and `name:` frontmatter values from `mnemosyne/pf2e/npcs/*.md`. Recognized names rewrite in-place to `[[<slug>]]` Obsidian wikilinks before the line is appended via PATCH. Conservative — fewer false positives.
  - **Session-end LLM pass:** The end-of-session LLM call sees the full event log AND the NPC roster (slugs + names) AND is instructed to mention any NPCs the slug-match missed (e.g., "the gnome", "the captain", aliases). The LLM-extracted list goes into the frontmatter `npcs[]` array; the recap text uses wikilinks for them too.
- **D-22 (NPC roster cache):** Pathfinder caches the NPC slug+name list in module memory at module startup, refreshed on every `:pf session start` (cheap — listdir + frontmatter read). Avoids a directory scan per `log` call.
- **D-23 (frontmatter aliases — deferred):** Phase 29 NPC frontmatter doesn't have an `aliases:` field. Phase 34 does NOT add it — the LLM session-end pass is the alias-handling mechanism. A future phase can add structured aliases if needed.

### Location link resolution
- **D-24 (LLM extraction at session-end only):** No location detection at log-time. The end-of-session LLM call extracts location mentions from the events and produces a canonical-cased list (e.g., `["Westcrown", "the Sandpoint Cathedral", "Thornwood"]`). Pathfinder normalizes via `slugify(name)` and writes results to the note's frontmatter `locations[]` array AND the `## Locations` section as wikilinks.
- **D-25 (auto-stub creation for new locations):** For each LLM-extracted location whose slug doesn't yet exist under `mnemosyne/pf2e/locations/<slug>.md`, pathfinder creates a stub file with minimal frontmatter:
  ```yaml
  name: Westcrown
  slug: westcrown
  first_seen: 2026-04-25
  mentions: [2026-04-25]
  schema_version: 1
  ```
  Body of the stub: `# Westcrown\n\n_Auto-created from session 2026-04-25 — fill in details when ready._`
  If the stub already exists from a prior session, append today's date to `mentions` via PATCH (frontmatter target).
- **D-26 (location collision with NPC slug):** If a location slug equals an existing NPC slug (e.g., a tavern named "Varek's Rest" → slug `vareks-rest`, vs NPC `varek`) — slugs differ by hyphen-suffix so collision is unlikely. If a true collision occurs (location and NPC share an exact slug), prefer the existing NPC link in the body text and skip the location stub. Log a warning. Researcher proposes a refinement if needed.

### End-of-session LLM call (`:pf session end`)
- **D-27 (single structured-output call):** One LiteLLM call to `{settings.litellm_api_base}/chat/completions` with the full event log + linked NPC frontmatter (personality/mood/relationships) + storyteller-voice system prompt. Response is constrained to JSON schema:
  ```json
  {
    "recap": "<third-person past-tense narrative, 2-4 paragraphs typical>",
    "npcs": ["varek", "baron-aldric"],
    "locations": ["Westcrown", "Thornwood"],
    "npc_notes_per_character": {
      "varek": "Revealed his Thornwood Thieves Guild past; mood shifted from neutral → conflicted",
      "baron-aldric": "First appearance; introduced as the city's magistrate"
    }
  }
  ```
  Researcher picks the exact JSON-schema enforcement mechanism (LiteLLM's `response_format: {type: "json_schema", ...}` if the configured backend supports it; otherwise prompt-only with parse-and-retry).
- **D-28 (storyteller voice — DM third-person past-tense narrative):** System prompt instructs: "You are a Pathfinder 2e DM writing an episode-recap narrative for the players to read between sessions. Use third-person past-tense prose, 2-4 paragraphs typical, evocative but factual. Help readers remember what happened weeks ago. No bullet points. No headings. Reference NPCs by name." Researcher refines the prompt during research; this voice is locked.
- **D-29 (length — unbounded, scales with event count):** No hard word/token cap. The LLM picks length based on the log content. Long sessions produce longer recaps. Researcher monitors during testing and adds a soft cap if recaps trend unreadably long.
- **D-30 (recap input scope — event log + linked NPC frontmatter only in MVP):** The end-of-session LLM sees: the full timestamped events log, and the frontmatter (personality, mood, relationships, backstory) for any NPC whose slug appears in the log. It does NOT crawl Phase 31 `:pf npc say` Discord threads — that's a deferred enhancement for richer recaps. Same input scope applies to the mid-session `:pf session show` LLM call.

### Failure handling
- **D-31 (LLM failure at `end`):** If the end-of-session LLM call fails or times out, pathfinder writes a skeleton note: full frontmatter (status: ended, npcs: [], locations: [], event_count, started_at, ended_at, recap: ""), `## Recap` section with placeholder text `_recap generation failed — run :pf session end --retry-recap to generate later_`, raw `## Events Log` (NPCs/locations unlinked, raw text). Discord embed: `"Session ended. Recap generation failed: <truncated error>. Note written: <path>. Use :pf session end --retry-recap to retry."` Session is closed, the note exists, no events lost.
- **D-32 (`--retry-recap` flag):** `:pf session end --retry-recap` reads an existing session note's `## Events Log` section, runs the recap LLM, and rewrites the `## Recap` section + `recap` frontmatter field + `npcs[]` + `locations[]` + `## NPCs Encountered` + `## Locations` sections (full structured output). Works on any session note (today's or a past one). Useful for recovering from LLM failures days later, and for regenerating recaps if the storyteller voice prompt changes in a future tuning pass.
- **D-33 (Obsidian failure during log/show/undo):** Surface as a Discord error embed identifying which Obsidian operation failed (`PATCH append failed: <status>`). Do not retry automatically. The DM can retry the verb manually. The session stays `status: open` so subsequent `log` calls work once Obsidian recovers.

### Note shape (`mnemosyne/pf2e/sessions/YYYY-MM-DD.md`)
- **D-34 (frontmatter):**
  ```yaml
  schema_version: 1
  date: 2026-04-25
  status: open | ended
  started_at: 2026-04-25T19:00:00-04:00
  ended_at: 2026-04-25T22:30:00-04:00   # null while open
  event_count: 14
  npcs: [varek, baron-aldric]            # slugs only — wikilink resolution is in body
  locations: [westcrown, thornwood]      # slugs only
  recap: ""                              # storyteller text; populated at end
  schema_version: 1
  ```
- **D-35 (section order, top to bottom):**
  1. `## Recap` — final storyteller narrative (mirrors `recap` frontmatter; populated at end). Empty/placeholder while session is open.
  2. `## Story So Far` — running narrative captured at each `:pf session show` (overwritten each call). Empty until first `show`.
  3. `## NPCs Encountered` — auto-built bullet list at end:
     ```markdown
     - [[varek]] — Revealed his Thornwood Thieves Guild past; mood shifted from neutral → conflicted
     - [[baron-aldric]] — First appearance; introduced as the city's magistrate
     ```
     Notes come from `npc_notes_per_character` in the LLM JSON output (D-27).
  4. `## Locations` — auto-built bullet list at end: `- [[westcrown]]`, `- [[thornwood]]`. Wikilinks only; no per-location notes in MVP.
  5. `## Events Log` — append-only log of all events; the live source during the session. Untouched at `end` (the LLM reads it; doesn't modify it).
- **D-36 (forward compatibility):** `schema_version: 1` is read by all session-handling code. Code uses `frontmatter.get('npcs', [])` style defensive reads so older notes without a new field (added in v2) still work. Destructive renames or removals require a version bump and a migration script (no migration in Phase 34).

### LLM model selection
- **D-37 (`SESSION_RECAP_MODEL` env var):** Pathfinder reads `SESSION_RECAP_MODEL` if set; falls back to project-wide `LITELLM_MODEL`. Default fall-through means zero-config works on existing deploys; the env var lets the DM swap to a longer-context model when sessions grow past ~50 events. Mirrors Phase 33's `RULES_EMBEDDING_MODEL` separation pattern. Add to `modules/pathfinder/app/config.py` Settings + `compose.yml` env block + `.env.example`.

### Telemetry
- **D-38 (standard structured logs):** Use `logger.info`/`logger.warning` per the Phase 33 pattern. Per-call `info` logs for `start/log/end/show/undo` with session date + event count (start/end/show/undo only — `log` would be too chatty; log only on PATCH failure). Warning logs for: Obsidian PATCH failures, LLM timeouts/failures, slug-match misses caught by the LLM session-end pass (so the DM can see which NPCs the fast pass needs help with). No new instrumentation framework. No token-count logging in MVP (defer if needed).

### Claude's Discretion
- Exact `discord.ui.View` subclass shape and button callback registration — researcher confirms `discord.py` 2.7.x best practice. Persistent vs ephemeral views.
- Whether the `SESSION_AUTO_RECAP` toggle lives as an env var or in `mnemosyne/pf2e/sessions/.config.yaml` (researcher picks based on whether other PF2e module settings need a similar home).
- Exact LLM prompts (system + user) for `:pf session show` and `:pf session end` — researcher refines during research, planner locks them.
- JSON-schema enforcement mechanism (LiteLLM `response_format: json_schema` vs prompt-only with parse-and-retry) — depends on configured LiteLLM backend.
- Whether `_pf_dispatch` parses `--force`, `--recap`, `--retry-recap` flags inline or sends them as a `flags: {}` object to the route (planner picks consistent style with Phase 32/33).
- Internal pathfinder router file structure (`app/routes/session.py`) and pydantic request/response models for the 5-verb endpoint.
- Timezone env var name and default (`SESSION_TZ`, default `America/New_York`?).
- How `## NPCs Encountered` notes are merged when an NPC appears in multiple events (one summary line vs cumulative).
- Whether `:pf session undo` uses heading-replace PATCH or GET-then-PUT (depends on Obsidian REST API capability).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap / requirements
- `.planning/ROADMAP.md` §Phase 34 — goal, success criteria 1-4, dependency on Phase 29
- `.planning/REQUIREMENTS.md` §Session Notes — SES-01..03 authoritative wording
- `.planning/PROJECT.md` — project value statement, "Obsidian IS the database" architectural decision, tech stack constraints

### Architecture
- `.planning/phases/27-architecture-pivot/27-CONTEXT.md` — Path B module contract (modules call Obsidian directly; sentinel-core is a proxy)
- `.planning/phases/28-pf2e-module-skeleton-cors/28-CONTEXT.md` — D-11 through D-18: module registry name, base_url, Docker profile, registration retry pattern, REGISTRATION_PAYLOAD schema

### Phase 29 — NPC slug + persistence (this phase's main dependency)
- `.planning/phases/29-npc-crud-obsidian-persistence/29-CONTEXT.md` — D-01..D-04 (Discord `:pf <noun> <verb>` dispatch), D-15..D-22 (NPC frontmatter shape, slug = `slugify(name)`, file location `mnemosyne/pf2e/npcs/<slug>.md`), D-27 (pathfinder owns Obsidian client), D-28 (OBSIDIAN_BASE_URL/OBSIDIAN_API_KEY env vars), D-29 (Obsidian PATCH frontmatter pattern)
- `modules/pathfinder/app/obsidian.py` — current `ObsidianClient` capabilities: `get_note`, `put_note`, `list_directory`, `patch_frontmatter_field`. Phase 34 adds heading-target PATCH-append (new method or extends `patch_frontmatter_field` shape).

### Phase 31/33 — LLM patterns this phase reuses
- `.planning/phases/31-dialogue-engine/31-CONTEXT.md` — `:pf npc say` LiteLLM calling pattern, slow-query placeholder→edit Discord UX, Phase 31 stores NPC dialogue in Discord threads (deferred input source — D-30)
- `.planning/phases/33-rules-engine/33-CONTEXT.md` — D-08 (structured JSON response shape), D-10 (verb dispatch under noun), D-11 (slow-query UX), D-13 (frontmatter for embedded data — pattern for session frontmatter)

### Existing patterns to follow
- `interfaces/discord/bot.py:188` — `_PF_NOUNS = frozenset({"npc", "harvest", "rule"})` — extend to add `session`
- `interfaces/discord/bot.py:460-490` — `_pf_dispatch` shape and usage-message derivation from `_PF_NOUNS`
- `modules/pathfinder/app/main.py:63` — `REGISTRATION_PAYLOAD` shape — add `{"path": "session", ...}` entry
- `modules/pathfinder/app/main.py:110-160` — lifespan pattern that wires module-level singletons (NPC roster cache for D-22 follows this pattern)
- `modules/pathfinder/app/routes/npc.py` — request/response pydantic models, FastAPI router structure (template for `app/routes/session.py`)
- `modules/pathfinder/app/routes/rule.py` — single-route-handles-many-verbs dispatch pattern (template for the `session` route handling 5 verbs)
- `sentinel-core/app/clients/obsidian.py:152` — `write_session_summary()` PUT pattern (note: this is for MEM-05 conversation memory under `ops/sessions/`, NOT for Phase 34 PF2e sessions under `mnemosyne/pf2e/sessions/` — terminology overload to flag for downstream agents)

### Obsidian REST API references (researcher to validate)
- CLAUDE.md §Obsidian Local REST API — PATCH supports `Operation: append` with `Target-Type: heading`, `Target: <heading text>`. Researcher must confirm this works for body sections (not just frontmatter) on the deployed plugin version.
- `https://coddingtonbear.github.io/obsidian-local-rest-api/` — interactive Swagger reference for PATCH operations and Target-Type values.

### Discord library reference (researcher to validate)
- `discord.py` 2.7.x docs — `discord.ui.View`, `discord.ui.Button`, view timeout behavior, persistent vs ephemeral views, `Message.edit()` for placeholder→final pattern. Researcher confirms current API; this is the first time Phase work touches interactive components.

### Project memory items (active constraints)
- Memory §`project_dockerfile_deps.md` — adding a Python dep requires dual-shipping in `pyproject.toml` AND `modules/pathfinder/Dockerfile`. If the LLM JSON-schema mechanism needs a new dep, plan for both.
- Memory §`project_obsidian_patch_constraint.md` — `patch_frontmatter_field` only safe for fields existing at note-create time; new fields require GET-then-PUT. Applies to the `mentions` append on existing location stubs (D-25).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `modules/pathfinder/app/obsidian.py:53` — `put_note()` — used for `:pf session start` initial note write and for `:pf session end` full rewrite
- `modules/pathfinder/app/obsidian.py:37` — `get_note()` — used for collision check at start (D-06) and for `--retry-recap` to read the existing events log (D-32)
- `modules/pathfinder/app/obsidian.py:101` — `list_directory()` — used to list `mnemosyne/pf2e/npcs/` for D-22 NPC roster cache and `mnemosyne/pf2e/locations/` for stub-collision detection (D-25)
- `modules/pathfinder/app/obsidian.py:172` — `patch_frontmatter_field()` — used for status flip at end (`status: ended`) and for incrementing `event_count` on each log
- `interfaces/discord/bot.py` `_pf_dispatch` — Phase 29 D-02 helper; new `elif noun == "session":` branch
- `modules/pathfinder/app/llm.py` — existing LiteLLM helpers used by Phase 31 dialogue and Phase 33 rules; reuse for D-27 end-of-session call and D-18 mid-session show call

### Established Patterns
- FastAPI single-route-many-verbs dispatch: `modules/pathfinder/app/routes/rule.py` handles `query/show/history/list` via a `verb` field in the request — `app/routes/session.py` follows the same pattern for `start/log/end/show/undo`
- Module-level singleton wiring in lifespan: `modules/pathfinder/app/main.py:110-160` pattern — Phase 34 adds NPC roster cache and (if extracted as a singleton) session settings (`SESSION_AUTO_RECAP`, `SESSION_TZ`, `SESSION_RECAP_MODEL`)
- Pydantic-settings: extend `modules/pathfinder/app/config.py` Settings with `session_auto_recap: bool = False`, `session_tz: str = "America/New_York"`, `session_recap_model: str | None = None` — add to `compose.yml` env block + `.env.example`
- Discord embed shape: `discord.Embed` with `.add_field()` — same pattern used by Phase 29-33; Phase 34 also introduces `discord.ui.View` (new pattern)
- Slow-query placeholder→edit: Phase 31/33 — Phase 34 reuses for `:pf session show` and `:pf session end`
- Storyteller-voice prompts: lessons from Phase 31 dialogue prompt — apply tonally to D-28 system prompt

### Integration Points
- `interfaces/discord/bot.py` — `_PF_NOUNS` extension (D-02), `_pf_dispatch` new branch (D-04), `discord.ui.View` registration for the recap-on-start button (D-08, D-11)
- `modules/pathfinder/app/main.py` — REGISTRATION_PAYLOAD addition (D-03), lifespan additions (NPC roster cache, settings reading)
- `modules/pathfinder/app/routes/session.py` (NEW) — single FastAPI router, 5-verb dispatch, calls into helpers in `app/session.py` (NEW) for the LLM and Obsidian logic
- `modules/pathfinder/app/session.py` (NEW) — pure helpers: timestamp formatting, NPC slug-match scanner, location stub creator, recap LLM call, JSON-schema validation
- `modules/pathfinder/Dockerfile` — if any new dep is required (e.g., for JSON-schema enforcement, if not stdlib), dual-ship per memory constraint
- `interfaces/discord/tests/test_subcommands.py` — extend to assert `"session"` is in `_PF_NOUNS` and that all 5 verbs dispatch correctly (Phase 33 D-10 test pattern is the template)

</code_context>

<specifics>
## Specific Ideas

- Storyteller voice for `:pf session end` recap and `:pf session show` "story so far": **DM third-person past-tense narrative**, 2-4 paragraphs typical, evocative but factual, helps players remember after weeks. Example: _"Last session, the party arrived in Westcrown and uncovered a smuggling ring. Varek the rogue revealed his connection to the Thornwood Thieves Guild. The night ended on a cliffhanger as a city watch patrol approached."_ No bullet points, no headings inside the recap text.
- Recap on `:pf session start` is button-prompted by default (Discord `discord.ui.View`), with `--recap` flag and `SESSION_AUTO_RECAP=true` setting as opt-out paths to skip the button.
- Both running narrative (`## Story So Far`, regenerated on each `show`) AND final recap (`## Recap`, generated at `end`) persist in the same session note, enabling a future campaign-narrative compiler to choose either source.
- NPC linking is dual-pass: fast exact-match at log-time + LLM cleanup pass at session-end. Aliases like "the gnome" are caught by the LLM, not by a frontmatter `aliases:` list (Phase 29 stays unchanged).
- Locations are LLM-extracted at session-end and auto-stubbed under `mnemosyne/pf2e/locations/<slug>.md` with minimal frontmatter (`name, slug, first_seen, mentions[], schema_version: 1`). The stub body is a placeholder line for the DM to fill later.
- `--retry-recap` flag on `:pf session end` re-reads any session note's events log and regenerates the recap. Useful for recovering from LLM failures and for regenerating old recaps if the storyteller prompt changes.
- `schema_version: 1` is on EVERY new file Phase 34 creates (session notes AND location stubs) so future schema bumps have a clean handle.
- Wall-clock UTC stamping with timezone-rendered display (`SESSION_TZ` env var). In-game date markers are explicitly deferred.

</specifics>

<deferred>
## Deferred Ideas

- **Campaign-narrative compiler** — a `:pf session story` (or similar) verb that aggregates every session note's recap into a single read-the-adventure document. Phase 34 ensures every session note carries its storyteller-voice recap in frontmatter so this compiler is straightforward to build later. Likely Phase 34.x or a future milestone.
- **Locations CRUD module** — Phase 29-equivalent `:pf location {create, update, show, relate}` command surface. Phase 34 only ships placeholder stubs; full schema (level/region/inhabitants/etc.), Discord commands, and link semantics are a separate phase.
- **In-game time / calendar** — wall-clock UTC only in MVP. In-game date markers like "Calistran 14, evening" are deferred. Could reuse the freeform-with-typed-prefix log shape (`time:` type) when implemented.
- **Edit-by-index for events** — only `undo` (pops last) in MVP. `:pf session edit <idx> | <new text>` requires displaying indices in `:pf session show` and is deferred.
- **Phase 31 thread-history integration** — the end-of-session and mid-session LLM calls do NOT crawl `:pf npc say` Discord threads in MVP. Would enrich recaps with verbatim NPC dialogue but adds Discord history wiring. Deferred as a recap-quality enhancement.
- **NPC frontmatter `aliases:` field** — would let "the gnome" → `varek` link via fast pass instead of the LLM cleanup pass. Defer until DM feedback indicates the LLM pass is missing too much.
- **Token-count telemetry** — log prompt/completion tokens per recap LLM call for cost tuning. Defer unless a future tuning phase needs it.
- **Per-location stub enrichment** — when a location is mentioned in N sessions, auto-update the stub body with a "Sessions:" list. Phase 34 only updates the `mentions[]` frontmatter array; richer body updates are deferred.
- **Migration script for schema bumps** — Phase 34 ships `schema_version: 1` and forward-compatible reads, but no migration tooling. First destructive schema change writes its own migration.

</deferred>

---

*Phase: 34-session-notes*
*Context gathered: 2026-04-25*
