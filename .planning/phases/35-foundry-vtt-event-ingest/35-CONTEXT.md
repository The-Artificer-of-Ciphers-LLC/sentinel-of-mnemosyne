# Phase 35: Foundry VTT Event Ingest — Context

**Gathered:** 2026-04-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver a Foundry VTT JavaScript module (`modules/pathfinder/foundry-client/`) that hooks into PF2e-typed dice rolls and trigger-prefixed chat messages, POSTs structured events to `POST /modules/pathfinder/foundry/event` on the pf2e module, and the backend produces LLM-narrated Discord notifications in the DM's pf2e channel.

**What this phase delivers:**
1. `modules/pathfinder/foundry-client/` — new JS artifact: `module.json`, `sentinel-connector.js`, bundled as a zip
2. FastAPI `StaticFiles` mount at `/foundry/` in the pf2e module serving `module.json` + zip
3. New `POST /foundry/event` route on the pf2e module (`app/routes/foundry.py`)
4. `REGISTRATION_PAYLOAD` extended with the `foundry/event` route
5. Lightweight internal HTTP endpoint added to `bot.py` so pathfinder can push Discord notifications
6. LLM narrative call per roll event producing Discord embed with flavor text

**What this phase explicitly does NOT do:**
- Phase 36 NPC pull-import button in Foundry UI — that reuses this module but is a separate phase
- Campaign-level roll history or analytics — Phase 35 is per-event notifications, not aggregation
- Foundry-side display widgets — all output goes to Discord, not back to Foundry

</domain>

<decisions>
## Implementation Decisions

### Foundry JS module — event scope
- **D-01 (hook: PF2e-typed rolls):** Register `Hooks.on('preCreateChatMessage', ...)` and inspect `message.flags?.pf2e?.context`. Forward events only when `flags.pf2e.context` exists with a recognized roll type (attack-roll, saving-throw, skill-check). The hook fires before the message is stored, which is where pf2e modules (e.g., pf2e-modifiers-matter) intercept roll data. This filters out initiative, damage rolls, flat checks, and GM-only rolls at the JS layer, keeping POST volume low.
- **D-02 (chat message forwarding — trigger prefix):** Non-roll chat messages are forwarded only if the message text starts with the configured trigger prefix. The prefix is stored as a Foundry world setting alongside `X-Sentinel-Key` (GM-only, set in the module's settings panel). Default prefix: empty (no chat forwarding unless DM configures one). Researcher picks the Foundry `game.settings.register` API shape and setting key names.
- **D-03 (X-Sentinel-Key storage):** `X-Sentinel-Key` stored as a `scope: "world"` Foundry world setting (GM-only, not visible to players). Sent as the `X-Sentinel-Key` header on every POST. Researcher confirms `game.settings.register` with `config: true` for GM visibility.
- **D-04 (Foundry version compatibility):** `module.json` declares `compatibility.minimum: "12"` and `compatibility.verified: "14"` (the installed version per ROADMAP SC-5). Researcher confirms the correct v14 manifest schema fields.

### Foundry JS module — event payload schema
- **D-05 (roll payload — PF2e pre-computed):** The JS module sends the PF2e system's pre-computed result. Per-roll POST body:
  ```json
  {
    "event_type": "roll",
    "roll_type": "attack-roll",
    "actor_name": "Seraphina",
    "target_name": "Goblin Warchief",
    "outcome": "criticalSuccess",
    "roll_total": 28,
    "dc": 14,
    "dc_hidden": false,
    "item_name": "Longsword +1",
    "timestamp": "2026-04-25T19:42:00Z"
  }
  ```
  `outcome` maps directly from `flags.pf2e.context.outcome` (`criticalSuccess / success / failure / criticalFailure`). `dc` is `flags.pf2e.context.dc.value`; `dc_hidden: true` when the DC value is null (GM secret DC). `actor_name` from `message.actor?.name`. `target_name` from `message.target?.name` (null for saves/skills with no specific target).
- **D-06 (chat message payload):** Non-roll forwarded chat:
  ```json
  {
    "event_type": "chat",
    "actor_name": "DM",
    "content": "party finds a secret door",
    "timestamp": "2026-04-25T19:45:00Z"
  }
  ```
  Content is the message text with the trigger prefix stripped.
- **D-07 (Sentinel URL stored in world settings):** The Foundry module stores `SENTINEL_BASE_URL` (e.g., `http://192.168.1.10:8000`) in world settings so the DM can configure the LAN IP without editing files. POST target: `{SENTINEL_BASE_URL}/modules/pathfinder/foundry/event`.

### Backend — pf2e module route
- **D-08 (new route: `POST /foundry/event`):** New file `modules/pathfinder/app/routes/foundry.py` with a FastAPI router. Receives the event, classifies `event_type`, dispatches to `app/foundry.py` helpers. Follows the single-file-per-noun pattern of `app/routes/harvest.py`, `app/routes/session.py`.
- **D-09 (REGISTRATION_PAYLOAD):** Add `{"path": "foundry/event", "description": "Receive Foundry VTT game events (FVT-01..03)"}` to `REGISTRATION_PAYLOAD` in `modules/pathfinder/app/main.py`. This is the 15th route entry.
- **D-10 (StaticFiles mount for JS distribution):** Mount `modules/pathfinder/foundry-client/dist/` at `/foundry/static/` using FastAPI's `StaticFiles`. `module.json` served at `GET /foundry/module.json`. The zip served at `GET /foundry/sentinel-connector.zip`. These URLs are what the DM pastes into Foundry's module manager as the manifest URL.

### Backend — LLM narration
- **D-11 (LLM narrative per roll):** Each roll event triggers an LLM call via the existing LiteLLM helpers in `modules/pathfinder/app/llm.py`. System prompt: "You are a Pathfinder 2e DM narrator. Given a dice roll result, write ONE dramatic sentence (max 20 words) describing the outcome in third-person past-tense narrative. No headings. No bullet points. Use the actor and target names." Input includes: actor name, target name, item name, outcome, roll total, DC. LLM output is the `narrative` field sent to Discord.
- **D-12 (`FOUNDRY_NARRATION_MODEL` env var):** Pathfinder reads `FOUNDRY_NARRATION_MODEL` if set; falls back to `LITELLM_MODEL`. Mirrors `SESSION_RECAP_MODEL` and `RULES_EMBEDDING_MODEL` separation pattern. Add to `modules/pathfinder/app/config.py` Settings + `modules/pathfinder/compose.yml` env block + `.env.example`.
- **D-13 (LLM failure fallback):** If LLM times out or errors, fall back to a plain-text summary: `{outcome_emoji} {outcome_label} | {actor_name} → {target_name or roll_type} | {roll_total} vs DC {dc}`. Discord embed is still sent; narrative field contains the plain fallback. No error bubbled to Foundry.

### Discord delivery
- **D-14 (bot.py internal HTTP endpoint):** `bot.py` grows a lightweight aiohttp server (or a FastAPI sub-app on a non-public port, e.g., `8001`) that listens for `POST /internal/notify` requests from pathfinder. Auth: `X-Sentinel-Key` header checked against the same shared secret. Researcher picks the exact implementation (aiohttp vs FastAPI sub-app) and confirms the asyncio event loop integration with discord.py.
- **D-15 (target channel — same as other pf2e commands):** Foundry event notifications post to the same Discord channel as harvest, session, NPC commands. No new `FOUNDRY_DISCORD_CHANNEL_ID` env var. The existing `DISCORD_ALLOWED_CHANNELS` allowlist governs channel permissions. Researcher confirms the channel-send mechanism in bot.py (direct `channel.send()` vs via the existing pf2e embed dispatch path).
- **D-16 (Discord embed shape for rolls):**
  ```
  🎲 Critical Hit! | Seraphina vs Goblin Warchief
  "Seraphina's blade found the gap in the warchief's armor, driving deep."
  Roll: 28 | AC: 14 | Longsword +1
  ```
  Title: `{outcome_emoji} {outcome_label} | {actor_name} vs {target_name}`. Body: LLM narrative (or fallback). Footer: `Roll: {total} | DC/AC: {dc} | {item_name}`. For hidden-DC rolls: footer shows `DC: [hidden]`. Researcher picks the exact `discord.Embed` field layout.

### Foundry JS module — distribution
- **D-17 (no Node.js build required in MVP):** `sentinel-connector.js` is written as a Foundry v14 ESModule (`import`/`export`, no bundler required). Foundry v14 natively supports ESModules. The zip contains `module.json` + `sentinel-connector.js` only. No webpack/vite build step in MVP — keeps the module installable without a build tool. Researcher confirms ESModule support in Foundry v14.
- **D-18 (zip packaging):** A short `package.sh` script at `modules/pathfinder/foundry-client/` creates `sentinel-connector.zip` from the current directory contents. Script runs as part of the developer workflow (not in Docker). Researcher confirms the exact zip structure Foundry expects (root files vs subdirectory in zip).

### Claude's Discretion
- Exact Foundry `game.settings.register` API shape for `SENTINEL_BASE_URL`, `SENTINEL_KEY`, and trigger prefix (researcher confirms v14 API)
- Whether bot.py internal endpoint uses aiohttp or a FastAPI sub-app — researcher picks based on asyncio discord.py compatibility
- Internal port for bot.py HTTP listener (e.g., 8001) and compose.yml network exposure (internal network only)
- Exact Foundry v14 `module.json` manifest fields and `esmodules` array format
- LLM prompt refinement for the 20-word narrative sentence
- How pathfinder discovers the bot.py internal URL (env var `DISCORD_BOT_INTERNAL_URL` pointing to `http://discord-bot:8001`)
- Outcome emoji mapping: 🎯 criticalSuccess, ✅ success, ❌ failure, 💀 criticalFailure (researcher can adjust)
- Whether `preCreateChatMessage` returns `false` to suppress the message or just reads it passively (it should NOT suppress; only read)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap / requirements
- `.planning/ROADMAP.md` §Phase 35 — goal, success criteria 1-5, dependency on Phase 28
- `.planning/REQUIREMENTS.md` §Foundry VTT Connector — FVT-01, FVT-02, FVT-03 authoritative wording
- `.planning/PROJECT.md` — tech stack constraints, "Obsidian IS the database", Docker Compose include pattern

### Architecture
- `.planning/phases/28-pf2e-module-skeleton-cors/28-CONTEXT.md` — D-11..D-18: module registry name "pathfinder", base_url `http://pf2e-module:8000`, REGISTRATION_PAYLOAD schema, CORS allow_origins (Foundry browser fetch already works)
- `.planning/phases/27-architecture-pivot/27-CONTEXT.md` (if exists) — Path B module contract (modules call Obsidian directly; sentinel-core is a proxy)

### Existing patterns (files to read before planning)
- `modules/pathfinder/app/main.py` — REGISTRATION_PAYLOAD shape; `StaticFiles` mount example if any; lifespan singleton pattern
- `modules/pathfinder/app/routes/session.py` — single-route-many-verbs FastAPI pattern for new `app/routes/foundry.py`
- `modules/pathfinder/app/llm.py` — existing LiteLLM helpers; reuse for D-11 narrative call
- `modules/pathfinder/app/config.py` — Settings extension pattern for `FOUNDRY_NARRATION_MODEL`
- `interfaces/discord/bot.py` — `_pf_dispatch`, embed patterns, `DISCORD_ALLOWED_CHANNELS` — adding internal HTTP listener in D-14
- `modules/pathfinder/compose.yml` — env block pattern; internal network config
- `.env.example` — env var documentation pattern

### Phase 34 / LLM patterns
- `.planning/phases/34-session-notes/34-CONTEXT.md` — D-37 (model env var separation), D-28 (LLM prompt voice), D-38 (structured logging pattern); slow-query placeholder→edit Discord pattern

### Discord library
- `discord.py` 2.7.x `discord.Embed` API — field layout for D-16 embed shape
- `discord.py` 2.7.x and aiohttp compatibility for bot.py internal HTTP listener (D-14)

### Foundry VTT v14 JS API (researcher must verify)
- Foundry v14 `Hooks.on('preCreateChatMessage', ...)` hook signature and `ChatMessage` object shape
- `ChatMessagePF2e.flags.pf2e.context` structure: `outcome`, `dc.value`, `type` fields
- `game.settings.register` v14 API for world-scope GM settings
- `module.json` v14 manifest format: `esmodules` array, `compatibility.minimum/verified`, `languages`, `url`
- Foundry v14 ESModule support confirmation (no bundler required)
- Zip structure Foundry expects for installable module packages

### Memory constraints (active)
- Memory §`project_dockerfile_deps.md` — any new Python dep requires dual-shipping in `pyproject.toml` AND `modules/pathfinder/Dockerfile`
- Memory §`project_obsidian_patch_constraint.md` — GET-then-PUT required for new frontmatter fields (not relevant for this phase, but keep in mind for any Obsidian writes)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `modules/pathfinder/app/llm.py` — LiteLLM call helpers; reuse for D-11 narrative LLM call (same `litellm_api_base` + `litellm_model` config)
- `modules/pathfinder/app/config.py` — `Settings` class; extend with `foundry_narration_model: str | None = None`
- `modules/pathfinder/app/main.py:63` — `REGISTRATION_PAYLOAD` list; add `foundry/event` entry (15th route)
- `modules/pathfinder/app/main.py:110-160` — lifespan pattern for module-level singleton wiring; extend if a pathfinder→bot HTTP client needs initialization
- `modules/pathfinder/app/routes/session.py` — FastAPI router structure and pydantic request/response models template for `app/routes/foundry.py`
- `interfaces/discord/bot.py` — embed builder pattern (`discord.Embed` with fields/footer); `_pf_dispatch` channel send mechanism; async bot lifecycle to hook aiohttp into

### Established Patterns
- Single-route-many-verbs dispatch: `modules/pathfinder/app/routes/rule.py` and `session.py` — `foundry.py` handles `event_type` field instead of a verb
- Module-level singleton + lifespan: `modules/pathfinder/app/main.py` — if a persistent httpx client to bot.py is needed, wire it in lifespan
- LLM model env var separation: `SESSION_RECAP_MODEL`, `RULES_EMBEDDING_MODEL` → `FOUNDRY_NARRATION_MODEL` follows same pattern
- Pydantic-settings: all config in `modules/pathfinder/app/config.py` via `pydantic-settings`; add new env vars there and nowhere else
- Dual-shipping deps: `modules/pathfinder/pyproject.toml` + `modules/pathfinder/Dockerfile` must both be updated for any new Python dep

### Integration Points
- `modules/pathfinder/app/main.py` — REGISTRATION_PAYLOAD addition (D-09) + `StaticFiles` mount (D-10) + lifespan additions
- `modules/pathfinder/app/routes/foundry.py` (NEW) — FastAPI router for `POST /foundry/event`
- `modules/pathfinder/app/foundry.py` (NEW) — pure helpers: event parsing, LLM narrative call, bot notification dispatch
- `modules/pathfinder/foundry-client/` (NEW) — JS module: `module.json`, `sentinel-connector.js`, `package.sh`
- `interfaces/discord/bot.py` — internal HTTP listener (D-14) for notifications from pathfinder
- `modules/pathfinder/compose.yml` — new env vars (`FOUNDRY_NARRATION_MODEL`, `DISCORD_BOT_INTERNAL_URL`); internal Docker network expose for bot.py listener
- `.env.example` — document new env vars

</code_context>

<specifics>
## Specific Ideas

- Foundry module installs from a zip via a manifest URL pointing to the pf2e FastAPI container: `http://{MAC_MINI_IP}:8000/modules/pathfinder/foundry/module.json`. DM pastes this into Foundry's Add-on Modules > Install Module field.
- Module settings panel (GM-only) has three fields: Sentinel Base URL, Sentinel API Key, Chat Trigger Prefix (optional).
- Roll narration is a MAX 20-word single sentence — short enough to read at a glance during combat. "Seraphina's blade found the gap in the warchief's armor, driving deep."
- Outcome emoji mapping (adjustable): 🎯 criticalSuccess, ✅ success, ❌ failure, 💀 criticalFailure.
- Hidden-DC handling: footer shows `DC: [hidden]`, narrative still generated without the DC value.
- The JS module does NOT suppress the Foundry chat message — `preCreateChatMessage` is read-only; the roll still appears in Foundry's chat as normal.
- LLM failure graceful fallback: `✅ Success | Seraphina → Goblin Warchief | Roll: 18 vs AC 14` — plain text, no LLM required.

</specifics>

<deferred>
## Deferred Ideas

- **Phase 36: NPC pull-import button** — The Foundry JS module from Phase 35 is extended in Phase 36 to add an "Import from Sentinel" button in the Foundry actor directory. Phase 35 module should be structured to allow this extension without a full rewrite.
- **Roll history / session context** — Aggregating all roll events into a combat log or session analytics dashboard. Phase 35 is per-event notification only.
- **Foundry → Sentinel combat tracker** — Live HP tracking, turn order, condition management synced to Obsidian. Out of scope for v0.5; belongs in a future combat module.
- **All-rolls event scope** — Relaxing D-01's PF2e-typed filter to capture all dice rolls (initiative, damage, flat checks). Easy upgrade: remove the `flags.pf2e.context` guard in the JS module. Deferred until DM feedback indicates missing roll types.
- **Player-visible Discord notifications** — Phase 35 routes all output to the DM's channel. A future phase could add a player-facing channel (`FOUNDRY_PLAYER_CHANNEL_ID`) for combat results.
- **Foundry → Obsidian combat log** — Writing roll events to a running session note in real-time (separate from D-16 Discord notification). Would make the session auto-recap richer. Deferred as a Phase 34 enhancement.

</deferred>

---

*Phase: 35-foundry-vtt-event-ingest*
*Context gathered: 2026-04-25*
