# Phase 36: Foundry NPC Pull Import — Research

**Researched:** 2026-04-26
**Domain:** Foundry VTT v14 JS API (ApplicationV2, hooks, Actor API) + FastAPI GET endpoints + ObsidianClient listing
**Confidence:** HIGH on Python backend; HIGH on ApplicationV2 architecture; MEDIUM on exact v14 hook signature details

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Button injected via `renderActorDirectory` hook; opens ApplicationV2 or equivalent dialog — NOT DialogV2.input text field.
- **D-02:** Listing endpoint returns `[{name, slug, level, ancestry}]`; dialog shows `"Varek (Level 5, Human)"`.
- **D-03:** Offline error → `"No NPCs found. Is Sentinel running?"` + Retry button; dialog stays open.
- **D-04:** Two-step flow: select NPC → preview panel (from listing data, no extra fetch) → Import button → `Actor.create()`.
- **D-05:** Duplicate check via `game.actors.getName()`; `Dialog.confirm()` "Overwrite?" → Yes: `existing.update({name, system})`; No: `Actor.create()` new.

### Claude's Discretion

- New `routes/npcs.py` with `prefix="/npcs"` — two routes: `GET /{slug}/foundry-actor` and `GET /`.
- Add both routes to `REGISTRATION_PAYLOAD` in `main.py`.
- Obsidian listing mechanism: `obsidian.list_directory()` vs search — researcher picks.
- Overwrite field set on `existing.update()`: replace `system.*` and `name`; do NOT overwrite `_id`, `items`, `effects`, `folder`, `ownership`, `prototypeToken`.
- JS dialog implementation: `ApplicationV2` vs `DialogV2` — researcher picks.
- `module.json` version bump `1.0.0` → `1.1.0`.

### Deferred Ideas (OUT OF SCOPE)

- Right-click "Sync from Sentinel" via `getActorDirectoryEntryContext` hook.
- `<select>` → `<datalist>` typeahead upgrade.
- NPC picker search/filter input.
- Bulk multi-select import.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FVT-04 | The Foundry JS module can pull NPC actor JSON directly from Sentinel (pull-based import, no file attachment) | Two new GET endpoints (`/npcs/` and `/npcs/{slug}/foundry-actor`) + ApplicationV2 import dialog in `sentinel-connector.js` |
</phase_requirements>

---

## Summary

Phase 36 adds two new FastAPI GET endpoints to the pathfinder module and extends `sentinel-connector.js` with an actor-import UI. The Python backend work is straightforward — a thin `routes/npcs.py` that reuses `_build_foundry_actor`, `_parse_frontmatter`, `slugify`, and `obsidian.list_directory()` which already exists in the codebase.

The JS side is more nuanced. DialogV2 is confirmed NOT viable for this dialog because it does not support re-rendering — the Retry button requires re-fetching and repopulating the `<select>`, which means state must be held across render cycles. ApplicationV2 extended with a plain `_renderHTML()` method (no bundler, no Handlebars, ESModule globals) is the correct approach. The class is accessed at runtime via `foundry.applications.api.ApplicationV2` — no imports needed.

There is one critical infrastructure landmine: `allow_methods` in `main.py` CORS middleware is currently `["POST", "OPTIONS"]`. The two new endpoints are GET requests, which means the Foundry browser client will be blocked by CORS on GET preflight. Adding `"GET"` to `allow_methods` is mandatory and must be a task in the plan.

**Primary recommendation:** Extend `ApplicationV2` directly (no Handlebars) using `_renderHTML()` returning a template-literal HTML string; wire `_onRender()` for `<select>` change and button listeners; use `this.render()` for Retry re-render. One class, one file, no build step.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| NPC listing (`GET /npcs/`) | API / Backend (pf2e module) | — | Reads Obsidian vault; returns structured JSON |
| NPC actor JSON (`GET /npcs/{slug}/foundry-actor`) | API / Backend (pf2e module) | — | Builds PF2e actor dict from note; no Foundry state |
| Import UI dialog | Browser / Foundry Client | — | Runs inside Foundry browser; all JS |
| Duplicate detection | Browser / Foundry Client | — | `game.actors.getName()` is a Foundry client API |
| Actor creation / update | Browser / Foundry Client | — | `Actor.create()` and `actor.update()` are Foundry document APIs |
| CORS for GET | API / Backend (pf2e module) | — | Current `allow_methods` blocks GET; must add |

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | >=0.135.x | GET endpoint router | Project standard; `APIRouter(prefix="/npcs")` pattern already used |
| httpx AsyncClient | >=0.28.1 | Obsidian client (existing) | Already wired in lifespan singleton |
| Foundry ApplicationV2 | v14 (runtime) | Stateful import dialog | Built into Foundry; no install; supports re-render |
| Foundry Actor API | v14 (runtime) | Actor creation/update | `Actor.create()`, `actor.update()`, `game.actors.getName()` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| yaml (Python stdlib) | — | Frontmatter parsing | Already used in `_parse_frontmatter` |
| `obsidian.list_directory()` | existing | NPC vault enumeration | Confirmed in codebase — use this |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| ApplicationV2 | DialogV2 | DialogV2 lacks re-render support — Retry button requires repopulating `<select>`, which needs state across render cycles. Not viable. |
| ApplicationV2 | Legacy `Application` (v1) | v1 works but is deprecated in v14; ApplicationV2 is the supported path |
| `obsidian.list_directory()` | `POST /search/simple/?query=tag:npc` | Directory listing is simpler, has no search-index dependency, already in the codebase |

---

## Architecture Patterns

### System Architecture Diagram

```
Foundry browser (DM clicks "Import from Sentinel")
  │
  ├─ renderActorDirectory hook → injects button into .directory-header .action-buttons
  │
  ├─ SentinelNpcImporter.render() [ApplicationV2 subclass]
  │     │
  │     ├─ _prepareContext() → fetches GET /modules/pathfinder/npcs/
  │     │     │
  │     │     └─ pf2e module: /npcs/ → obsidian.list_directory(mnemosyne/pf2e/npcs/)
  │     │           → _parse_frontmatter per .md file → [{name, slug, level, ancestry}]
  │     │
  │     ├─ _renderHTML() → template-literal HTML with <select>, preview panel, buttons
  │     │
  │     └─ _onRender() → addEventListener: select change → update preview; Import → fetchActor
  │           │
  │           ├─ GET /modules/pathfinder/npcs/{slug}/foundry-actor
  │           │     └─ pf2e module: obsidian.get_note → _parse_frontmatter + _parse_stats_block
  │           │           → _build_foundry_actor(fields, stats) → JSON response
  │           │
  │           └─ game.actors.getName(name) → duplicate? → Dialog.confirm() → Actor.create() / actor.update()
  │
  └─ ui.notifications.info / .error
```

### Recommended Project Structure

```
modules/pathfinder/
├── app/
│   └── routes/
│       └── npcs.py          # NEW — GET /npcs/ and GET /npcs/{slug}/foundry-actor
├── foundry-client/
│   ├── sentinel-connector.js  # MODIFIED — add renderActorDirectory hook + SentinelNpcImporter class
│   ├── module.json            # MODIFIED — version 1.0.0 → 1.1.0
│   └── package.sh             # RE-RUN to produce updated sentinel-connector.zip
```

### Pattern 1: ApplicationV2 Subclass (No Bundler, No Handlebars)

**What:** Extend `foundry.applications.api.ApplicationV2` directly using `_renderHTML()` returning a plain HTML string. No Handlebars, no bundler — compatible with the existing ESModule-only approach.

**When to use:** Any stateful Foundry UI that requires re-rendering (e.g., populating a `<select>` after a fetch, enabling/disabling buttons based on selection state).

**Example:**
```javascript
// Source: Foundry VTT API v14 — https://foundryvtt.com/api/classes/foundry.applications.api.ApplicationV2.html
// + community pattern from https://docs.rayners.dev/seasons-and-stars/applicationv2-development/

const { ApplicationV2 } = foundry.applications.api;

class SentinelNpcImporter extends ApplicationV2 {
  static DEFAULT_OPTIONS = {
    id: 'sentinel-npc-importer',
    tag: 'div',
    window: { title: 'Import NPC from Sentinel', resizable: false },
    position: { width: 400, height: 'auto' },
  };

  // Internal state — persists across render() calls (not cleared by re-render)
  #npcs = [];
  #selectedSlug = null;
  #loading = false;
  #error = null;

  async _prepareContext(options) {
    // Fetch listing only on first render or after Retry
    if (options.fetchNpcs !== false) {
      this.#npcs = [];
      this.#error = null;
      const sentinelUrl = game.settings.get(MODULE_ID, 'sentinelBaseUrl');
      const sentinelKey = game.settings.get(MODULE_ID, 'apiKey');
      try {
        const resp = await fetch(`${sentinelUrl}/modules/pathfinder/npcs/`, {
          headers: { 'X-Sentinel-Key': sentinelKey },
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        this.#npcs = await resp.json();
      } catch (err) {
        this.#error = 'No NPCs found. Is Sentinel running?';
      }
    }
    return { npcs: this.#npcs, selectedSlug: this.#selectedSlug, error: this.#error };
  }

  async _renderHTML(context, options) {
    const { npcs, selectedSlug, error } = context;

    if (error) {
      return `
        <div class="sentinel-npc-importer">
          <p class="error">${error}</p>
          <button type="button" data-action="retry">Retry</button>
        </div>`;
    }

    const options_html = npcs.map(n =>
      `<option value="${n.slug}" ${n.slug === selectedSlug ? 'selected' : ''}>
        ${n.name} (Level ${n.level}, ${n.ancestry})
      </option>`
    ).join('');

    const selected = selectedSlug ? npcs.find(n => n.slug === selectedSlug) : null;
    const previewHtml = selected
      ? `<p class="preview">${selected.name} | Level ${selected.level} ${selected.ancestry}</p>`
      : '<p class="preview muted">Select an NPC above to preview.</p>';

    return `
      <div class="sentinel-npc-importer">
        <select name="npc-select">${options_html}</select>
        ${previewHtml}
        <div class="form-footer">
          <button type="button" data-action="importNpc" ${selectedSlug ? '' : 'disabled'}>Import</button>
          <button type="button" data-action="close">Cancel</button>
        </div>
      </div>`;
  }

  // Non-click listeners go in _onRender (static actions handle click events)
  _onRender(context, options) {
    const select = this.element.querySelector('select[name="npc-select"]');
    if (select) {
      // Auto-select first item if nothing selected yet
      if (!this.#selectedSlug && context.npcs.length) {
        this.#selectedSlug = context.npcs[0].slug;
        this.render();  // re-render to activate Import button
        return;
      }
      select.addEventListener('change', (ev) => {
        this.#selectedSlug = ev.target.value;
        this.render();  // partial re-render to update preview and button state
      });
    }
  }

  // Static actions — bound to data-action attributes by DEFAULT_OPTIONS.actions
  static DEFAULT_OPTIONS = {
    ...SentinelNpcImporter.DEFAULT_OPTIONS,
    actions: {
      retry: SentinelNpcImporter.#onRetry,
      importNpc: SentinelNpcImporter.#onImport,
      close: SentinelNpcImporter.#onClose,
    },
  };

  static async #onRetry(event, target) {
    await this.render({ fetchNpcs: true });
  }

  static async #onClose(event, target) {
    this.close();
  }

  static async #onImport(event, target) {
    if (!this.#selectedSlug) return;
    const sentinelUrl = game.settings.get(MODULE_ID, 'sentinelBaseUrl');
    const sentinelKey = game.settings.get(MODULE_ID, 'apiKey');
    try {
      const resp = await fetch(
        `${sentinelUrl}/modules/pathfinder/npcs/${this.#selectedSlug}/foundry-actor`,
        { headers: { 'X-Sentinel-Key': sentinelKey } },
      );
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const actorData = await resp.json();

      const existing = game.actors.getName(actorData.name);
      if (existing) {
        const overwrite = await Dialog.confirm({
          title: 'Overwrite Actor?',
          content: `<p>${actorData.name} already exists in Foundry. Overwrite with Sentinel data?</p>`,
        });
        if (overwrite) {
          await existing.update({ name: actorData.name, system: actorData.system });
          ui.notifications.info(`${actorData.name} updated from Sentinel.`);
        } else {
          await Actor.create(actorData, { renderSheet: false });
          ui.notifications.info(`${actorData.name} imported from Sentinel (new copy).`);
        }
      } else {
        await Actor.create(actorData, { renderSheet: false });
        ui.notifications.info(`${actorData.name} imported from Sentinel.`);
      }
      this.close();
    } catch (err) {
      ui.notifications.error('Import failed. Check Sentinel connection.');
      console.error('[sentinel-connector] Import error:', err);
    }
  }
}
```

**Key nuances:**
- `DEFAULT_OPTIONS` is a single static property; the `actions:` block must be in the SAME `DEFAULT_OPTIONS` literal — you cannot spread from yourself mid-definition. Combine into one object literal (see Anti-Patterns below).
- `_onRender()` is not `await`-ed by the render pipeline; it is called post-render, fire-and-forget.
- `this.render()` inside `_onRender()` without `{ fetchNpcs: true }` skips the listing fetch — passes `options.fetchNpcs` as falsy, and `_prepareContext` preserves `this.#npcs`.
- Static action handlers receive `this` bound to the class instance via Foundry's action binding.

### Pattern 2: `renderActorDirectory` Hook for Button Injection

**What:** `Hooks.on('renderActorDirectory', (app, html) => {...})` fires whenever the actors sidebar renders. `html` is either a jQuery object (v12 pattern) or the DOM element in v14. Use the `element` on the second parameter and DOM manipulation to inject the button.

**When to use:** Persistent button in the actor directory header that survives sidebar refreshes.

**Example:**
```javascript
// Source: VERIFIED against community module pattern
// https://bringingfire.com/blog/intro-to-foundry-module-development

// In Hooks.once('ready', ...) so the importer class is defined before the hook fires:
Hooks.on('renderActorDirectory', (app, html) => {
  // html may be jQuery or DOM element depending on Foundry version;
  // .find() works on jQuery; use querySelector on DOM element.
  const actionButtons = html.find
    ? html.find('.directory-header .action-buttons')  // jQuery (v12 compat)
    : html.querySelector('.directory-header .action-buttons');  // DOM element

  // Idempotency guard — re-renders fire this hook again
  if (html.find
    ? html.find('#sentinel-import-btn').length
    : html.querySelector('#sentinel-import-btn')) return;

  const button = document.createElement('button');
  button.id = 'sentinel-import-btn';
  button.type = 'button';
  button.textContent = 'Import from Sentinel';
  button.addEventListener('click', () => {
    new SentinelNpcImporter().render(true);
  });

  if (html.find) {
    $(actionButtons).append(button);  // jQuery
  } else {
    actionButtons.append(button);     // DOM
  }
});
```

**v14 note:** In Foundry v14, the `renderActorDirectory` hook fires with the new ApplicationV2-based sidebar. The `html` parameter type may change. The dual-path pattern above (jQuery .find check) is the safe compat approach given `module.json` declares `minimum: "12"`. [ASSUMED — v14 exact parameter type not confirmed via official docs; jQuery check is safe fallback]

### Pattern 3: FastAPI GET Route (`routes/npcs.py`)

**What:** A new single-concern router file following the existing `routes/foundry.py`, `routes/harvest.py` pattern.

**Example:**
```python
# Source: VERIFIED — mirrors existing routes/npc.py structure

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from app.routes.npc import (
    _NPC_PATH_PREFIX,
    _build_foundry_actor,
    _parse_frontmatter,
    _parse_stats_block,
    slugify,
)

router = APIRouter(prefix="/npcs")
obsidian = None  # set by main.py lifespan

@router.get("/")
async def list_npcs() -> JSONResponse:
    """Return [{name, slug, level, ancestry}] for all NPCs in the vault."""
    paths = await obsidian.list_directory(_NPC_PATH_PREFIX)
    npcs = []
    for path in paths:
        if not path.endswith(".md"):
            continue
        note_text = await obsidian.get_note(path)
        if note_text is None:
            continue
        fields = _parse_frontmatter(note_text)
        name = fields.get("name")
        if not name:
            continue
        npcs.append({
            "name": name,
            "slug": slugify(name),
            "level": fields.get("level", 1),
            "ancestry": fields.get("ancestry", ""),
        })
    return JSONResponse(npcs)


@router.get("/{slug}/foundry-actor")
async def get_foundry_actor(slug: str) -> JSONResponse:
    """Return PF2e actor JSON for the NPC identified by slug."""
    # Path traversal guard — slugify only allows [a-z0-9-]
    safe_slug = slugify(slug)
    if safe_slug != slug:
        raise HTTPException(status_code=400, detail={"error": "invalid slug"})
    path = f"{_NPC_PATH_PREFIX}/{safe_slug}.md"
    note_text = await obsidian.get_note(path)
    if note_text is None:
        raise HTTPException(status_code=404, detail={"error": "NPC not found", "slug": slug})
    fields = _parse_frontmatter(note_text)
    stats = _parse_stats_block(note_text)
    actor = _build_foundry_actor(fields, stats)
    return JSONResponse(actor)
```

### Pattern 4: `main.py` Wiring (REGISTRATION_PAYLOAD + lifespan)

```python
# routes/npcs.py import block (add alongside existing imports):
import app.routes.npcs as _npcs_module
from app.routes.npcs import router as npcs_router

# In lifespan, after _npc_module.obsidian = obsidian_client:
_npcs_module.obsidian = obsidian_client

# In REGISTRATION_PAYLOAD["routes"] (add 2 entries — Pitfall 7):
{"path": "npcs/", "description": "List all Sentinel NPCs (FVT-04)"},
{"path": "npcs/{slug}/foundry-actor", "description": "Return PF2e actor JSON for NPC (FVT-04)"},

# After existing include_router calls:
app.include_router(npcs_router)
```

### Anti-Patterns to Avoid

- **`DEFAULT_OPTIONS` self-spread:** Cannot write `static DEFAULT_OPTIONS = { ...SentinelNpcImporter.DEFAULT_OPTIONS, actions: {...} }` in the class body — the class is not yet defined. Write one combined `DEFAULT_OPTIONS` literal.
- **DialogV2 for this dialog:** DialogV2 has no re-render support. The Retry button requires repopulating the `<select>`, which requires a new render cycle. DialogV2 will not work.
- **`Hooks.once('ready')` for the directory hook:** Use `Hooks.on('renderActorDirectory', ...)` (persistent, not once) so the button reappears if the sidebar is re-rendered. Register inside `Hooks.once('ready')` to ensure `SentinelNpcImporter` class is defined first.
- **Missing idempotency guard on hook:** `renderActorDirectory` fires on every sidebar render. Without the `#sentinel-import-btn` existence check the button duplicates on each render.
- **GET without CORS fix:** The new GET endpoints will be blocked by the browser's CORS preflight because `allow_methods` is currently `["POST", "OPTIONS"]`. Must add `"GET"`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Foundry actor JSON shape | Custom schema builder | `_build_foundry_actor()` in `routes/npc.py:272` | Already implemented, Phase 30 validated against live Foundry |
| Frontmatter parsing | Re-implement YAML parse | `_parse_frontmatter()` in `routes/npc.py:220` | Already handles edge cases |
| Slug generation | Custom slugify | `slugify()` in `routes/npc.py:210` | Stable slug, path traversal stripped |
| NPC vault listing | Walk vault manually | `obsidian.list_directory()` in `obsidian.py:101` | Recursive, max-depth bounded, returns leaf paths only |
| Duplicate confirm dialog | Custom confirm UI | `Dialog.confirm()` (Foundry built-in) | Decision D-05 uses this explicitly |

**Key insight:** The Python backend for Phase 36 is almost entirely composition of existing code. The only net-new logic is the route handlers in `routes/npcs.py` and the `allow_methods` CORS fix.

---

## Common Pitfalls

### Pitfall 1: CORS GET Blocked — `allow_methods` Missing "GET"

**What goes wrong:** The Foundry browser client calls `fetch("http://sentinel:8000/modules/pathfinder/npcs/", ...)`. Browser sends CORS preflight OPTIONS. Starlette's CORSMiddleware responds with `Access-Control-Allow-Methods: POST, OPTIONS` — GET is absent. Browser blocks the actual GET request. Foundry shows a network error with no useful message.

**Why it happens:** `main.py` line 240 currently has `allow_methods=["POST", "OPTIONS"]`. All existing routes in the pathfinder module are POST. This is the first module with GET endpoints called from the Foundry browser.

**How to avoid:** Add `"GET"` to `allow_methods` in `main.py`. Full list should be `["GET", "POST", "OPTIONS"]`.

**Warning signs:** Foundry browser devtools shows CORS error on `OPTIONS /modules/pathfinder/npcs/`. Python logs show no GET request arriving (the preflight is rejected before the actual request).

### Pitfall 2: `renderActorDirectory` Hook Button Duplication

**What goes wrong:** The hook fires every time the actor directory re-renders (opening/closing sidebar, switching tabs). Without a guard the button accumulates, showing multiple "Import from Sentinel" buttons.

**Why it happens:** `Hooks.on()` registers a persistent listener. Every render event fires the callback.

**How to avoid:** Check for `#sentinel-import-btn` existence before appending. If it exists, return immediately.

**Warning signs:** Multiple "Import from Sentinel" buttons visible in the actor directory header.

### Pitfall 3: `DEFAULT_OPTIONS` Self-Reference in Class Body

**What goes wrong:** `static DEFAULT_OPTIONS = { ...SentinelNpcImporter.DEFAULT_OPTIONS, actions: {...} }` — `SentinelNpcImporter` is not yet defined when the static field initializer runs.

**Why it happens:** JavaScript class static field initializers run top-to-bottom during class evaluation. The class name is not in scope inside its own body.

**How to avoid:** Write a single `DEFAULT_OPTIONS` object literal with all properties including `actions`. Do not reference the class by name in the static initializer.

**Warning signs:** `ReferenceError: SentinelNpcImporter is not defined` in Foundry's browser console at module load time.

### Pitfall 4: Phase 28 Pitfall 7 — REGISTRATION_PAYLOAD Missing New Routes

**What goes wrong:** Routes `npcs/` and `npcs/{slug}/foundry-actor` are not listed in `REGISTRATION_PAYLOAD`. Sentinel Core's module registry does not know about them. Proxy routing may fail or the module health check shows partial registration.

**Why it happens:** Per Phase 28 Pitfall 7 (locked decision D-23), ALL routes must be registered at startup in `REGISTRATION_PAYLOAD`. There is no auto-discovery.

**How to avoid:** Add both routes as explicit entries in `REGISTRATION_PAYLOAD["routes"]` before merge.

**Warning signs:** `GET /modules/pathfinder/npcs/` returns 404 at the sentinel-core proxy level even though the pathfinder module responds correctly on its internal port.

### Pitfall 5: `actor.update()` Clobbers `system` Sub-keys Not Passed

**What goes wrong:** Calling `existing.update({ system: actorData.system })` with the full `system` object from the fetched actor data. This replaces the entire `system` object, potentially overwriting fields that the DM manually edited in Foundry (custom skills, resources, notes).

**Why it happens:** Foundry's `update()` uses mergeObject semantics for dot-notation keys but performs object-level replacement when passing a top-level `system:` key containing a full nested object.

**How to avoid:** D-05 specifies: overwrite only `name` and `system` from the fetched actor. This is intentional for the Overwrite path. However, be explicit: pass `{ name: actorData.name, system: actorData.system }` — not the full `actorData` dict, which also contains `_id`, `items`, `effects`, `prototypeToken`, `ownership`, `folder`. Passing `_id` in an update call is especially dangerous (may create a new document or throw).

**Warning signs:** DM reports that items or token settings disappear after overwrite.

### Pitfall 6: Slug Path Traversal in GET Route

**What goes wrong:** `GET /npcs/../../../etc/passwd/foundry-actor` — malicious slug reaches `obsidian.get_note("mnemosyne/pf2e/npcs/../../../etc/passwd.md")`.

**Why it happens:** Path parameter `{slug}` is user-controlled. Existing POST routes use Pydantic request models with `_validate_npc_name()` which rejects control characters. GET path params bypass Pydantic model validation.

**How to avoid:** Re-slugify the incoming slug via `slugify(slug)` and verify it matches before constructing the vault path. The `slugify()` function strips everything except `[a-z0-9-]`, making path traversal impossible. If `slugify(slug) != slug`, return 400.

**Warning signs:** `get_note()` receives a path with `../` in it.

### Pitfall 7: `list_directory` Returns Trailing-Slash Paths for Subdirs

**What goes wrong:** If any `.md` files exist inside subdirectories of `mnemosyne/pf2e/npcs/` (e.g., from a future reorganization), `list_directory()` returns them. The file suffix check `if not path.endswith(".md")` handles this correctly — no action needed. Just ensure the filter is present.

**Why it happens:** `list_directory()` recurses. It returns all leaf paths including subdirectory children.

**How to avoid:** Filter: `if not path.endswith(".md"): continue` in the listing handler (shown in Pattern 3 above).

### Pitfall 8: `Hooks.once('ready')` vs `Hooks.on('ready')` for Class Definition Scope

**What goes wrong:** `SentinelNpcImporter` class is defined at module top-level (not inside any hook). `renderActorDirectory` hook is registered inside `Hooks.once('ready', ...)`. If the class is defined after the hook registration that triggers it, the `new SentinelNpcImporter()` call fails with `ReferenceError`.

**How to avoid:** Define `SentinelNpcImporter` class at file top-level (after `const MODULE_ID = ...`), before any Hooks registration. The class definition is hoisted-compatible with `const`-based declarations. Register the `renderActorDirectory` hook registration inside `Hooks.once('ready', ...)` after the class is defined.

---

## Code Examples

### GET /npcs/ Response Shape

```json
[
  {"name": "Varek", "slug": "varek", "level": 5, "ancestry": "Human"},
  {"name": "Baron Aldric", "slug": "baron-aldric", "level": 8, "ancestry": "Dwarf"}
]
```

### GET /npcs/{slug}/foundry-actor Response Shape

The response is the direct output of `_build_foundry_actor(fields, stats)` — no wrapper object. Compare this to `POST /npc/export-foundry` which wraps in `{"actor": ..., "filename": ..., "slug": ...}`. The new GET endpoint returns the actor JSON directly so `Actor.create(await resp.json())` works without unwrapping.

```json
{
  "_id": "a1b2c3d4e5f60718",
  "name": "Varek",
  "type": "npc",
  "system": { "details": {"level": {"value": 5}}, ... }
}
```

### `game.actors.getName()` — confirmed v14 signature

```javascript
// Source: VERIFIED — https://foundryvtt.com/api/classes/foundry.documents.collections.Actors.html
const existing = game.actors.getName("Varek");  // returns Actor | undefined
if (existing) {
  // actor with that name exists
}
```

### `Actor.create()` with `renderSheet: false`

```javascript
// Source: ASSUMED — renderSheet option is community-standard but not explicitly in v14 API docs
await Actor.create(actorData, { renderSheet: false });
// renderSheet: false prevents the actor sheet from popping open on creation
```

### `actor.update()` — partial merge semantics

```javascript
// Source: VERIFIED — Foundry update() applies incremental data (merge, not replace)
// https://foundryvtt.com/api/classes/foundry.documents.Actor.html
// Passing system: {...} replaces the system object; do NOT pass _id, items, effects, prototypeToken
await existing.update({ name: actorData.name, system: actorData.system });
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Foundry Application (v1) | ApplicationV2 | v12+ | ApplicationV1 deprecated; use ApplicationV2 for new modules |
| DialogV2.input() text field | ApplicationV2 custom dialog | v12+ | DialogV2.input is fine for simple prompts; stateful list pickers need ApplicationV2 |
| `Hooks.on('renderActorDirectory', (app, html, data) => {...})` 3-arg | same, but `data` may be absent in v14 | v14 | Use only `app` and `html`; ignore third arg |

**Deprecated/outdated:**
- `Application` (v1) class: Works but deprecated since v12. Not suitable for new modules targeting v14.
- `Dialog` (v1) class: `Dialog.confirm()` is still available in v14 (in `foundry.appv1.api.Dialog`). Decision D-05 uses it by name — confirmed present in v14. [VERIFIED: https://foundryvtt.com/api/classes/foundry.appv1.api.Dialog.html]

---

## Runtime State Inventory

> Omitted — this is a greenfield feature addition, not a rename/refactor/migration phase.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Foundry VTT | JS module (client-side) | ✓ (user's install) | v14 verified | — |
| Python / FastAPI | `routes/npcs.py` | ✓ | existing container | — |
| Obsidian REST API | `list_directory` + `get_note` | ✓ (operational dep) | running on Mac | — |
| pytest + pytest-asyncio | unit tests | ✓ | pyproject.toml | — |

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | `modules/pathfinder/pyproject.toml` `[tool.pytest.ini_options]` `asyncio_mode = "auto"` |
| Quick run command | `cd modules/pathfinder && python -m pytest tests/test_npcs.py -x -q` |
| Full suite command | `cd modules/pathfinder && python -m pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FVT-04a | `GET /npcs/` returns `[{name, slug, level, ancestry}]` for vault with 2 NPCs | unit | `pytest tests/test_npcs.py::test_list_npcs_success -x` | ❌ Wave 0 |
| FVT-04b | `GET /npcs/` returns `[]` when vault directory is empty | unit | `pytest tests/test_npcs.py::test_list_npcs_empty -x` | ❌ Wave 0 |
| FVT-04c | `GET /npcs/` returns `[]` (not 503) when Obsidian is unreachable | unit | `pytest tests/test_npcs.py::test_list_npcs_obsidian_down -x` | ❌ Wave 0 |
| FVT-04d | `GET /npcs/{slug}/foundry-actor` returns valid PF2e actor JSON for known slug | unit | `pytest tests/test_npcs.py::test_get_foundry_actor_success -x` | ❌ Wave 0 |
| FVT-04e | `GET /npcs/{slug}/foundry-actor` returns 404 for unknown slug | unit | `pytest tests/test_npcs.py::test_get_foundry_actor_not_found -x` | ❌ Wave 0 |
| FVT-04f | `GET /npcs/{slug}/foundry-actor` returns 400 for slug with path traversal | unit | `pytest tests/test_npcs.py::test_get_foundry_actor_invalid_slug -x` | ❌ Wave 0 |
| FVT-04g | Foundry module renders "Import from Sentinel" button in actor directory header | manual | Load module in Foundry, verify button visible | n/a |
| FVT-04h | Import flow: select → preview → Import → Actor created in Foundry | manual | Live Foundry test | n/a |
| FVT-04i | Duplicate handling: existing actor → Dialog.confirm → overwrite → actor.update | manual | Live Foundry test | n/a |

### Sampling Rate

- **Per task commit:** `python -m pytest tests/test_npcs.py -x -q`
- **Per wave merge:** `python -m pytest tests/ -q`
- **Phase gate:** Full suite green + manual Foundry import smoke test before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_npcs.py` — 6 unit tests covering FVT-04a through FVT-04f
- [ ] No new `conftest.py` fixtures needed — existing pattern (mock `obsidian` module-level var, `httpx.ASGITransport`) applies directly

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — |
| V3 Session Management | no | — |
| V4 Access Control | yes | X-Sentinel-Key header on GET requests from Foundry client |
| V5 Input Validation | yes | Path traversal guard on `{slug}` parameter via `slugify()` re-validation |
| V6 Cryptography | no | — |

### Known Threat Patterns for Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal via slug (`../../etc`) | Tampering | `slugify(slug)` strips to `[a-z0-9-]`; reject if `slugify(slug) != slug` |
| Missing auth on GET endpoints | Spoofing | `X-Sentinel-Key` header required; Starlette CORS rejects cross-origin without it |
| CORS misconfiguration (GET not in allow_methods) | Tampering | Add `"GET"` to `allow_methods` in CORSMiddleware |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `renderActorDirectory` hook `html` parameter is jQuery in v14 (or the dual-path check handles it) | Pitfall 2, Pattern 2 | Button injection fails silently; DM sees no button. Mitigation: dual-path code handles both jQuery and DOM element. |
| A2 | `Actor.create(data, { renderSheet: false })` suppresses sheet auto-open in v14 | Code Examples | Actor sheet pops open on import — annoying but not blocking. Fix: remove option if it causes errors. |
| A3 | `Dialog.confirm()` (v1 Dialog class) is callable in v14 | Code Examples | Duplicate confirm dialog does not appear; need to switch to `DialogV2` equivalent. Low risk: v13 API docs confirm v1 Dialog still present. |
| A4 | `this.render()` inside `_onRender()` does not cause infinite recursion | Pattern 1 | If Foundry ApplicationV2 re-fires _onRender synchronously on re-render, the select change listener will loop. Mitigation: check if `#selectedSlug` already matches before calling `this.render()`. |

---

## Open Questions (RESOLVED)

1. **ApplicationV2 `_onRender` render loop risk**
   - What we know: `_onRender` is called after every render cycle; calling `this.render()` inside it is the documented pattern for reactive state.
   - What's unclear: Does Foundry v14 guard against synchronous re-render loops, or must the module guard explicitly?
   - Recommendation: Add an explicit guard: compare new `selectedSlug` to `this.#selectedSlug` before calling `this.render()`.

2. **`Dialog.confirm()` vs `DialogV2` for the overwrite confirm**
   - What we know: Decision D-05 explicitly says `Dialog.confirm()`. The v1 Dialog class is present in v14 API docs at `/api/v13/`.
   - What's unclear: Whether calling `Dialog.confirm()` produces a deprecation warning in v14 Foundry console.
   - Recommendation: Implement with `Dialog.confirm()` per D-05. If it produces console warnings in live testing, note for a deferred cleanup.

---

## Sources

### Primary (HIGH confidence)

- `modules/pathfinder/app/obsidian.py:101` — `list_directory()` method signature, return type, behavior [VERIFIED: codebase grep]
- `modules/pathfinder/app/routes/npc.py:272` — `_build_foundry_actor()` [VERIFIED: codebase read]
- `modules/pathfinder/app/main.py:240` — `allow_methods=["POST", "OPTIONS"]` — GET missing [VERIFIED: codebase read]
- `modules/pathfinder/foundry-client/module.json:8` — current version 1.0.0 [VERIFIED: codebase read]
- https://foundryvtt.com/api/classes/foundry.documents.collections.Actors.html — `getName()` signature [VERIFIED: WebFetch]
- https://foundryvtt.com/api/classes/foundry.documents.Actor.html — `Actor.create()` and `actor.update()` signatures [VERIFIED: WebFetch]
- https://foundryvtt.com/api/classes/foundry.applications.api.ApplicationV2.html — lifecycle methods, `_renderHTML`, `_onRender`, `DEFAULT_OPTIONS` [VERIFIED: WebFetch]
- https://foundryvtt.com/api/classes/foundry.applications.api.DialogV2.html — DialogV2 no-rerender confirmation [VERIFIED: WebFetch]
- https://foundryvtt.com/api/classes/foundry.appv1.api.Dialog.html — v1 Dialog.confirm() present in v14 [VERIFIED: WebFetch]

### Secondary (MEDIUM confidence)

- https://bringingfire.com/blog/intro-to-foundry-module-development — `renderActorDirectory` hook signature `(app, html)` + jQuery append pattern [VERIFIED via WebFetch]
- https://docs.rayners.dev/seasons-and-stars/applicationv2-development/ — ApplicationV2 static actions, `_onRender`, `HandlebarsApplicationMixin` patterns [VERIFIED via WebFetch]

### Tertiary (LOW confidence)

- `Actor.create({...}, { renderSheet: false })` option — community standard behavior, not explicitly in v14 API docs [ASSUMED]
- v14 `renderActorDirectory` hook html parameter type (jQuery vs DOM) — [ASSUMED based on dual-path pattern]

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — codebase fully read, existing patterns confirmed
- Python backend: HIGH — `list_directory`, `_build_foundry_actor`, `slugify`, `_parse_frontmatter` all confirmed in codebase
- CORS landmine: HIGH — `allow_methods` read directly from source
- ApplicationV2 architecture: HIGH — confirmed via official API docs and dev guide
- `renderActorDirectory` hook exact v14 param type: MEDIUM — jQuery dual-path is the safe implementation
- `Actor.create renderSheet` option: LOW/ASSUMED — community standard

**Research date:** 2026-04-26
**Valid until:** 2026-06-01 (Foundry v14 stable; ApplicationV2 API is stable)
