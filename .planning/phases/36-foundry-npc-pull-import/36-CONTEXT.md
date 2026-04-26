# Phase 36: Foundry NPC Pull Import — Context

**Gathered:** 2026-04-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Extend the existing Phase 35 `sentinel-connector.js` Foundry module with a one-click NPC import UI, and add two new backend GET endpoints to the pf2e module so the Foundry client can list and fetch actor JSON without file attachments or copy-paste.

**What this phase delivers:**
1. `GET /npcs/{slug}/foundry-actor` — new endpoint returning PF2e actor JSON directly (JSON response, not file bytes)
2. `GET /npcs/` — new listing endpoint returning all Sentinel NPCs as `[{name, slug, level, ancestry}]`
3. "Import from Sentinel" button injected into the Foundry actor directory header
4. Two-step dialog: `<select>` NPC list → preview → Import button → actor created in world
5. Duplicate-handling confirm dialog: "Varek already exists. Overwrite?"
6. `module.json` version bump (1.0.0 → 1.1.0), re-zipped distribution

**What this phase explicitly does NOT do:**
- Roll/chat event forwarding — that's Phase 35 (complete)
- Any Discord command changes — NPC import is purely Foundry-native
- Campaign-level analytics or NPC sync-back (Foundry → Obsidian)

</domain>

<decisions>
## Implementation Decisions

### Import button — UX flow

- **D-01 (list picker, not text-input):** The "Import from Sentinel" button is injected into the actor directory header via the `renderActorDirectory` hook. Clicking it opens a custom dialog (Foundry v14 ApplicationV2 or equivalent) — NOT a plain `DialogV2.input()` text field. User explicitly chose the richer list picker over the simpler text-input approach.
- **D-02 (listing data: name + level + ancestry):** The dialog's `<select>` shows entries like `"Varek (Level 5, Human)"`. Each option has `value={slug}` and `text="{name} (Level {level}, {ancestry})"`. The listing endpoint returns `[{name, slug, level, ancestry}]` per NPC — requires frontmatter read for each NPC file.
- **D-03 (offline handling — empty picker + retry):** When `GET /npcs/` fetch fails (Sentinel unreachable, Obsidian down), the dialog does NOT close. Instead it shows: `"No NPCs found. Is Sentinel running?"` plus a **Retry** button that re-fires the listing fetch. No hard failure; the dialog stays open and recoverable.
- **D-04 (two-step flow: select → preview → import):** After the DM selects an NPC from the `<select>`:
  1. A preview panel below the dropdown renders: `{name} | Level {level} {ancestry}` — sourced from the listing data already fetched; no extra API call.
  2. An "Import" button becomes active.
  3. Clicking Import → `GET /npcs/{slug}/foundry-actor` → `Actor.create(actorJson)`.

### Duplicate handling

- **D-05 (confirm dialog on duplicate name):** Before `Actor.create()`, check `game.actors.getName(actorName)`. If an actor with the same name exists:
  - Show `Dialog.confirm()`: `"[name] already exists in Foundry. Overwrite with Sentinel data?"` — `Yes` / `No`.
  - **Yes (overwrite):** Call `existing.update({name: ..., system: ...})` with the fetched actor JSON fields. Keep the existing actor's `_id` and any Foundry-managed fields (`items`, `effects`, token state).
  - **No (create new):** Proceed with `Actor.create(actorJson)` — new `_id`, new actor alongside the existing one.
  - If no duplicate found: skip dialog and go straight to `Actor.create()`.

### Claude's Discretion

- **Route naming:** The ROADMAP SC-1 specifies `GET /modules/pathfinder/npcs/{slug}/foundry-actor` with `npcs/` plural. The existing NPC router uses `prefix="/npc"` (singular). Implement as a new `routes/npcs.py` with `prefix="/npcs"` router — keeps the singular router unchanged, registers cleanly in `main.py`. Two routes: `GET /{slug}/foundry-actor` and `GET /` (listing).
- **REGISTRATION_PAYLOAD:** Add both new routes to `REGISTRATION_PAYLOAD` in `main.py` at startup per Phase 28 Pitfall 7: `"npcs/{slug}/foundry-actor"` and `"npcs/"`.
- **Obsidian listing mechanism:** For `GET /npcs/`, researcher should choose between `obsidian.list_directory("mnemosyne/pf2e/npcs/")` vs `POST /search/simple/?query=` with tag filter. The directory listing approach is simpler — reads frontmatter for each `.md` file found; no search index dependency.
- **Overwrite field set:** On `existing.update()`, replace `system.*` and `name` from the fetched actor JSON. Do NOT overwrite `_id`, `items`, `effects`, `folder`, `ownership`, `prototypeToken` — these are Foundry-managed and may have been edited post-import.
- **JS dialog implementation:** Researcher picks the appropriate Foundry v14 API for the two-step dialog — `ApplicationV2` (full render loop) vs `DialogV2` with custom HTML content. The dialog needs a `<select>`, a preview panel div, a Retry button, and an Import button — likely needs `ApplicationV2` rather than `DialogV2` given the stateful rendering.
- **Module version:** Bump `module.json` from `1.0.0` to `1.1.0`. Update `package.sh` and re-run to produce the updated `sentinel-connector.zip`.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap / requirements
- `.planning/ROADMAP.md` §Phase 36 — goal, success criteria (SC-1..4), dependencies (Phase 30, Phase 35)
- `.planning/REQUIREMENTS.md` §Foundry VTT Connector — FVT-04 authoritative wording
- `.planning/PROJECT.md` — tech stack constraints, Docker Compose include pattern

### Architecture — phases this phase builds on
- `.planning/phases/35-foundry-vtt-event-ingest/35-CONTEXT.md` — D-03..D-04 (world settings shape), D-07 (sentinelBaseUrl config), D-10 (StaticFiles mount for JS distribution at `/foundry/`), D-17 (ESModule, no bundler), D-18 (package.sh + zip structure)
- `.planning/phases/30-npc-outputs/30-CONTEXT.md` — D-04..D-06 (Foundry actor JSON schema, field defaults, uuid strategy), D-07 (SC validation by live Foundry import), D-23 (REGISTRATION_PAYLOAD pattern)
- `.planning/phases/28-pf2e-module-skeleton-cors/28-CONTEXT.md` — D-11..D-18: module registry name "pathfinder", REGISTRATION_PAYLOAD schema, Pitfall 7 (all routes at startup), CORS config

### Existing files to read before planning
- `modules/pathfinder/app/routes/npc.py` — `_build_foundry_actor()` (reuse exactly; Phase 36 GET endpoint is a thin wrapper), `_parse_frontmatter()`, `_parse_stats_block()`, `slugify()`, `obsidian` module-level singleton
- `modules/pathfinder/app/main.py` — REGISTRATION_PAYLOAD list; `include_router` pattern; lifespan singleton wiring
- `modules/pathfinder/app/config.py` — Settings class (no new env vars expected for Phase 36)
- `modules/pathfinder/foundry-client/sentinel-connector.js` — existing hook registrations, settings names, `postEvent()` pattern; Phase 36 adds import UI alongside event hooks
- `modules/pathfinder/foundry-client/module.json` — version field (bump 1.0.0 → 1.1.0)
- `modules/pathfinder/foundry-client/package.sh` — distribution script (re-run after JS changes)
- `modules/pathfinder/compose.yml` — no new env vars expected; verify REGISTRATION_PAYLOAD count after new routes added

### Foundry v14 JS API (researcher must verify)
- Foundry v14 `renderActorDirectory` hook — signature for header button injection
- Foundry v14 `ApplicationV2` or `DialogV2` API — which supports stateful `<select>` + preview panel + Retry button without a full module rewrite
- `game.actors.getName(name)` — confirm v14 availability and exact method signature
- `Actor.create(data, {renderSheet: false})` — confirm options arg for silent import
- `actor.update({name, system})` — confirm partial-update field semantics for overwrite path

### Memory constraints (active)
- Memory §`project_dockerfile_deps.md` — new Python dep requires dual-ship in `pyproject.toml` AND `modules/pathfinder/Dockerfile`; no new Python deps expected for Phase 36's GET endpoints (reuses existing obsidian client)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `modules/pathfinder/app/routes/npc.py:272` — `_build_foundry_actor(fields, stats)` — fully implemented PF2e actor dict builder; Phase 36's `GET /npcs/{slug}/foundry-actor` calls this directly
- `modules/pathfinder/app/routes/npc.py:211` — `slugify(name)` — stable slug generation; listing endpoint uses this for the slug field
- `modules/pathfinder/app/routes/npc.py:260` — `_parse_frontmatter(note_text)` — extracts `name`, `level`, `ancestry`, `traits` etc. from note YAML; used by listing endpoint to return `{name, slug, level, ancestry}`
- `modules/pathfinder/app/routes/npc.py:668` — `export_foundry()` — existing `POST /npc/export-foundry`; the new GET endpoint is a direct analog returning actor JSON via response body (not wrapped in `{"actor": ..., "filename": ...}`)
- `modules/pathfinder/foundry-client/sentinel-connector.js:43` — `Hooks.once('init', ...)` — settings registration block; "Import from Sentinel" button hooks into `Hooks.once('ready', ...)` alongside existing event hooks

### Established Patterns
- Single-concern router file: `routes/foundry.py` (Phase 35), `routes/session.py`, `routes/harvest.py` — new `routes/npcs.py` follows the same single-file-per-resource pattern
- Module-level singleton: `obsidian` variable set in `main.py` lifespan and assigned to `_npc_module.obsidian`; new `npcs.py` module will follow the same pattern (`import app.routes.npcs as _npcs_module; _npcs_module.obsidian = obsidian_client`)
- Pydantic request models: all routes use `BaseModel` request models; the `GET /npcs/{slug}/foundry-actor` route uses a path parameter (no request body), unlike existing POST routes
- JS fire-and-forget `fetch()` in `postEvent()` — the import dialog uses `await fetch()` (not fire-and-forget) since the actor JSON must arrive before `Actor.create()`

### Integration Points
- `modules/pathfinder/app/routes/npcs.py` (NEW) — two GET handlers; `obsidian` singleton wired from lifespan
- `modules/pathfinder/app/main.py` — `include_router(npcs_router)` + two REGISTRATION_PAYLOAD entries + lifespan `_npcs_module.obsidian` assignment
- `modules/pathfinder/foundry-client/sentinel-connector.js` — add `renderActorDirectory` hook and import dialog logic (no changes to existing `preCreateChatMessage` hook or `postEvent()`)
- `modules/pathfinder/foundry-client/module.json` — version bump 1.0.0 → 1.1.0
- `modules/pathfinder/foundry-client/package.sh` — re-run to update `sentinel-connector.zip`

</code_context>

<specifics>
## Specific Ideas

- Dialog `<select>` entry format: `"Varek (Level 5, Human)"` — concise enough to scan quickly; parenthetical keeps name visually dominant
- Preview panel (below select, no extra fetch): `"Varek | Level 5 Human"` — simple one-liner; no stat block details before import
- Import confirmation button label: "Import" (not "OK" or "Confirm") — verb makes intent clear
- Offline retry message: `"No NPCs found. Is Sentinel running?"` with a "Retry" button in the dialog body
- Overwrite confirm wording: `"[name] already exists in Foundry. Overwrite with Sentinel data?"` → "Yes" / "No"
- On successful import: `ui.notifications.info('[name] imported from Sentinel.')` (Foundry's standard notification)
- On error (fetch fails during import): `ui.notifications.error('Import failed. Check Sentinel connection.')` — same error surface as the rest of the module

</specifics>

<deferred>
## Deferred Ideas

- **Right-click "Sync from Sentinel"** — Phase 35 research identified a `getActorDirectoryEntryContext` hook pattern for refreshing an existing actor via right-click. Useful for "refresh already-imported NPC" semantic without opening the picker. Could land as a v1.2 extension of the module.
- **List picker → typeahead upgrade** — Swapping the `<select>` for a `<datalist>` input (typeahead/autocomplete) when the vault grows beyond ~20 NPCs. No backend change needed; pure JS swap.
- **NPC picker search/filter** — Client-side filter input above the `<select>` so the DM can type a partial name to narrow the list. Again, no backend change; JS only.
- **Bulk import** — Import multiple NPCs in one operation (multi-select `<select>` with per-item duplicate handling). Significant UX scope; separate phase.

</deferred>

---

*Phase: 36-foundry-npc-pull-import*
*Context gathered: 2026-04-26*
