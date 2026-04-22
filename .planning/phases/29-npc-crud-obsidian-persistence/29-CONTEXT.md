# Phase 29: NPC CRUD + Obsidian Persistence — Context

**Gathered:** 2026-04-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Create, update, query, relate, and bulk-import NPCs via Discord prefix commands, with all NPC data
persisted as structured notes under `mnemosyne/pf2e/npcs/`. NPC commands route from `bot.py` directly
to pathfinder module endpoints — bypassing the AI pipeline for structured CRUD operations.

**What this phase delivers:**
1. `:pf npc create <name> | <description>` — AI-parses description into frontmatter + random-fills unspecified fields from PF2e Remaster valid options
2. `:pf npc update <name> | <correction>` — AI-parses freeform correction, surgically PATCHes frontmatter or replaces stats block
3. `:pf npc show <name>` — Discord embed: identity + key stats (AC, HP, Perception, saves)
4. `:pf npc relate <name> <relation> <target>` — Appends to `relationships:` frontmatter list; validates relation type
5. `:pf npc import` (file attachment) — Reads Foundry actor list JSON, creates identity-only notes for each actor

**What this phase explicitly does NOT do:**
- Implement Foundry VTT stat block export (Phase 30)
- Full stat extraction from Foundry JSON (Phase 30 derives canonical PF2e schema)
- Dialogue engine or mood-state transitions (Phase 31)
- Any new Discord slash commands — all NPC commands use existing `:prefix` pattern inside `/sen`

</domain>

<decisions>
## Implementation Decisions

### Discord Command Routing

- **D-01:** NPC commands use the existing `:prefix` pattern inside the `/sen` slash command — NOT new app_commands slash commands. Command form: `:pf npc <verb> <args>`.
- **D-02:** `bot.py` gets a new `_pf_dispatch(verb, args, user_id)` helper that pattern-matches `:pf <noun> <verb>` and calls `SentinelCoreClient` with the corresponding module proxy path (e.g., `POST /modules/pathfinder/npc/create`).
- **D-03:** CRUD operations route directly to pathfinder module endpoints — NOT through `POST /message` AI pipeline. No LLM token cost for CRUD.
- **D-04:** `_pf_dispatch` is called from the existing `handle_sentask_subcommand` function when the subcommand prefix is `pf`.

### NPC Create Input

- **D-05:** Command syntax: `:pf npc create <name> | <description>` — pipe separator splits name from optional freeform description.
- **D-06:** Pathfinder module sends name + description to LLM with a structured extraction prompt. LLM returns a JSON object with all NPC frontmatter fields populated.
- **D-07:** For any field the user did not describe, the LLM randomly selects a valid PF2e Remaster option (e.g., unspecified ancestry → random from Gnome, Human, Elf, Dwarf, Halfling, Goblin, etc.). This applies to: ancestry, class, level (defaults to 1 if not specified), traits.
- **D-08:** Description-only creation is allowed: `:pf npc create Varek | young gnome rogue, nervous` — name is always the first positional arg before the pipe.

### NPC Update Input

- **D-09:** Command syntax: `:pf npc update <name> | <freeform correction>` — same pipe-separator pattern as create.
- **D-10:** LLM extracts which frontmatter fields changed from the correction string. Identity/roleplay fields are surgically PATCHed. If stats are mentioned, the stats block is read-modify-write PUT (entire block replaced).
- **D-11:** Freeform correction is consistent with create UX — no explicit key=value syntax required.

### NPC Relate

- **D-12:** Command syntax: `:pf npc relate <npc-name> <relation> <target-npc-name>` — three positional args after `relate`.
- **D-13:** Valid relation types (closed enum, validated at input): `knows | trusts | hostile-to | allied-with | fears | owes-debt`. Invalid type returns an error embed listing valid options.
- **D-14:** Stored in `relationships:` frontmatter list as structured entries: `- {target: "Baron Aldric", relation: "trusts"}`.

### Obsidian Note Schema

- **D-15:** Split schema — identity/roleplay fields in YAML frontmatter; PF2e mechanical stats in a fenced `yaml` block in the note body.
- **D-16:** Frontmatter fields (identity layer — surgically PATCHable):
  ```yaml
  name: Varek
  level: 5
  ancestry: Gnome
  class: Rogue
  traits: [sneaky, paranoid]
  personality: Nervous, evasive, loyal to old crew
  backstory: Fled the Thornwood Thieves Guild after...
  mood: neutral
  relationships: []
  imported_from: null
  ```
- **D-17:** Stats fenced block (mechanical layer — full-block PUT on update):
  ```markdown
  ## Stats
  ```yaml
  ac: 21
  hp: 65
  fortitude: +9
  reflex: +13
  will: +10
  speed: 25
  skills:
    stealth: +14
    deception: +12
  ```
  ```
- **D-18:** File slug: `slugify(name)` only — e.g., `varek.md`, `baron-aldric.md`. Stable regardless of level changes.
- **D-19:** Collision check: `GET /vault/mnemosyne/pf2e/npcs/{slug}.md` before every create. If 200, return 409 with the existing note path rather than silently overwriting.
- **D-20:** Initial mood: `neutral` at creation. Mood updates via `:pf npc update` freeform correction.

### NPC Show Embed

- **D-21:** `:pf npc show <name>` returns a Discord embed with:
  - Title: `<Name>` (level `<N>` `<Ancestry>` `<Class>`)
  - Description: personality + first 200 chars of backstory
  - Embed fields: AC, HP, Perception (if in stats block), Fort/Ref/Will saves, current relationships list
  - Footer: mood + Obsidian note path
- **D-22:** If the stats block is absent (NPC created name-only with no stats), stats fields are omitted from the embed.

### Foundry Bulk Import

- **D-23:** `:pf npc import` expects a JSON file attachment in the Discord message.
- **D-24:** Fidelity: identity fields only — extracts name, level, ancestry, class, traits from each actor entry. Stats block is left empty (to be filled via update or Phase 30 schema work). This is intentional: Phase 30 derives the canonical Foundry PF2e JSON schema.
- **D-25:** Parser defensively ignores unknown JSON keys — future schema changes do not break the importer.
- **D-26:** Returns a summary embed: "Imported N NPC(s): [name1, name2, ...]" with any skipped-due-to-collision names listed.

### Pathfinder Module — Obsidian Integration

- **D-27:** Pathfinder module calls the Obsidian REST API directly with its own httpx client — does NOT route through sentinel-core. This keeps sentinel-core's API surface stable.
- **D-28:** Pathfinder module needs two new env vars: `OBSIDIAN_BASE_URL` (e.g., `http://host.docker.internal:27123`) and `OBSIDIAN_API_KEY`. Add both to `modules/pathfinder/app/main.py` pydantic-settings config and to `.env.example`.
- **D-29:** Obsidian PATCH uses `Content-Type: application/json` with `Target-Type: frontmatter` header, per obsidian-local-rest-api plugin spec.

### Claude's Discretion

- LLM model used for NPC field extraction/generation (use the project's configured LITELLM_MODEL)
- Exact LLM prompt templates for create extraction and update diff parsing
- Internal pathfinder router file structure (`app/routes/npc.py` or equivalent)
- Pydantic models for NPC creation/update request/response shapes
- Stats block section heading (e.g., `## Stats` vs `## Mechanics`)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — NPC-01 through NPC-05 requirements (full field list, acceptance criteria)
- `.planning/ROADMAP.md` §Phase 29 — success criteria (SC-1 through SC-5)

### Architecture
- `.planning/PROJECT.md` §Constraints — "Modules must implement POST /healthz and call POST /modules/register at startup"
- `.planning/phases/28-pf2e-module-skeleton-cors/28-CONTEXT.md` — D-11 through D-18: module registry name, base_url, Docker profile, registration retry pattern
- `.planning/phases/27-architecture-pivot/27-CONTEXT.md` — Path B module contract

### Files Being Modified
- `interfaces/discord/bot.py` — add `_pf_dispatch()` helper + route `:pf` subcommand prefix through it
- `modules/pathfinder/app/main.py` — add NPC router (new `app/routes/npc.py`), OBSIDIAN env vars
- `modules/pathfinder/compose.yml` — add OBSIDIAN_BASE_URL, OBSIDIAN_API_KEY to env block
- `.env.example` — add OBSIDIAN_BASE_URL, OBSIDIAN_API_KEY with documented defaults

### Existing Patterns to Follow
- `sentinel-core/app/clients/obsidian.py` — Obsidian REST API call patterns (PUT, GET, search); PATCH pattern is new but follows same `_safe_request` wrapper style
- `sentinel-core/app/routes/modules.py` — proxy_module() pattern that bot.py's SentinelCoreClient calls
- `shared/sentinel_client.py` — SentinelCoreClient: how bot.py calls Core's module proxy endpoints

### Obsidian REST API — PATCH Frontmatter
- Endpoint: `PATCH /vault/{path}`
- Headers required: `Content-Type: application/json`, `Target-Type: frontmatter`
- Body: JSON object with only the fields to update (e.g., `{"mood": "hostile"}`)
- Source: CLAUDE.md §Obsidian Local REST API table — "Surgical edit (update frontmatter)"

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `modules/pathfinder/app/main.py`: lifespan + registration pattern already implemented (D-15 through D-18 from Phase 28) — NPC router attaches to this existing `app` instance
- `sentinel-core/app/clients/obsidian.py`: `_safe_request()` wrapper and `write_session_summary()` PUT pattern — PATCH implementation in pathfinder module follows the same httpx async pattern
- `shared/sentinel_client.py`: `SentinelCoreClient._post()` — how `bot.py` calls `POST /modules/pathfinder/npc/create`; `_pf_dispatch()` uses this same client

### Established Patterns
- FastAPI router: `app/routes/npc.py` with `router = APIRouter(prefix="/npc")` attached in `main.py` via `app.include_router(npc_router)`
- pydantic-settings: `OBSIDIAN_BASE_URL` added to a `Settings(BaseSettings)` class in pathfinder module, same pattern as sentinel-core `config.py`
- Obsidian GET-before-write: collision check uses same pattern as `get_user_context()` (404 → None, 200 → content)
- Discord embed: `discord.Embed` with `.add_field(name=..., value=..., inline=True)` — same pattern already used in some bot responses

### Integration Points
- `handle_sentask_subcommand()` in `bot.py`: new `elif subcmd == "pf":` branch routes to `_pf_dispatch(args, user_id)`
- `_pf_dispatch()` parses `args` as `<noun> <verb> <rest>` and maps to `SentinelCoreClient` calls on `/modules/pathfinder/npc/{verb}`
- pathfinder module registers `routes: [{"path": "healthz", ...}, {"path": "npc/create", ...}, ...]` at startup — update REGISTRATION_PAYLOAD in `main.py`

</code_context>

<specifics>
## Specific Ideas

- Pipe separator (`|`) distinguishes name from description in create/update: `:pf npc create Varek | young gnome rogue, nervous, fled from thieves guild`
- Relationship storage format in frontmatter: `relationships: [{target: "Baron Aldric", relation: "trusts"}]`
- Mood initialized to `neutral` at NPC creation; updated via freeform update correction
- Foundry importer should log the raw JSON field names it couldn't map (for Phase 30 schema derivation reference)
- Stats block heading: `## Stats` (matches the preview the user selected)
- `imported_from: foundry` frontmatter flag on bulk-imported NPCs — lets Phase 30 find and enrich them

</specifics>

<deferred>
## Deferred Ideas

- Full Foundry stat block extraction from bulk import JSON — Phase 30 derives canonical schema first, then Phase 30 can enrich Phase 29 imports
- NPC combat tracker integration — explicitly deferred to future milestone (REQUIREMENTS.md Future Requirements)
- Mood state transitions driven by dialogue history — Phase 31 owns mood logic; Phase 29 only initializes mood at `neutral`
- `/pf` as a true Discord app_commands slash command group — could be added in a future polish phase if the prefix UX proves limiting

</deferred>

---

*Phase: 29-npc-crud-obsidian-persistence*
*Context gathered: 2026-04-22*
