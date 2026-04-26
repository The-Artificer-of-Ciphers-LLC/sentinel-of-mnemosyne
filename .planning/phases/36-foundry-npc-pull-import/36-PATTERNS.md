# Phase 36: Foundry NPC Pull Import — Pattern Map

**Mapped:** 2026-04-26
**Files analyzed:** 6 (2 new, 4 modified)
**Analogs found:** 6 / 6

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `modules/pathfinder/app/routes/npcs.py` | route | request-response (GET, read-only) | `modules/pathfinder/app/routes/npc.py` (export_foundry + show_npc) | exact |
| `modules/pathfinder/app/main.py` | config/wiring | — | itself (existing lifespan + REGISTRATION_PAYLOAD) | self-analog |
| `modules/pathfinder/foundry-client/sentinel-connector.js` | browser module | event-driven + request-response | itself (existing hook + fetch pattern) | self-analog |
| `modules/pathfinder/foundry-client/module.json` | config | — | itself | self-analog |
| `modules/pathfinder/foundry-client/package.sh` | utility/script | — | itself | self-analog |
| `modules/pathfinder/tests/test_npcs.py` | test | request-response | `modules/pathfinder/tests/test_foundry.py` + `test_npc.py` | exact |

---

## Pattern Assignments

### `modules/pathfinder/app/routes/npcs.py` (route, request-response GET)

**Primary analog:** `modules/pathfinder/app/routes/npc.py`
**Secondary analog:** `modules/pathfinder/app/routes/foundry.py`

**Imports pattern** (`npc.py` lines 1–53):
```python
import logging
import re

import yaml
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.config import settings  # only if settings needed; not expected for Phase 36

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/npcs")

# Module-level ObsidianClient instance — set by main.py lifespan, patchable in tests.
obsidian = None

# NPC vault path prefix — import from npc.py rather than redeclare
# (actual constant lives at npc.py:52: _NPC_PATH_PREFIX = "mnemosyne/pf2e/npcs")
```

**Import of reused helpers from npc.py** (RESEARCH.md Pattern 3):
```python
from app.routes.npc import (
    _NPC_PATH_PREFIX,
    _build_foundry_actor,
    _parse_frontmatter,
    _parse_stats_block,
    slugify,
)
```

**Core GET listing pattern** — analogous to `npc.py` `show_npc` (lines 449–471) but uses `list_directory`:
```python
@router.get("/")
async def list_npcs() -> JSONResponse:
    """Return [{name, slug, level, ancestry}] for all NPCs in the vault (FVT-04)."""
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
```

**Core GET single-resource pattern** — direct analog of `export_foundry` (`npc.py` lines 668–688), but returns actor JSON unwrapped:
```python
@router.get("/{slug}/foundry-actor")
async def get_foundry_actor(slug: str) -> JSONResponse:
    """Return PF2e actor JSON for NPC identified by slug (FVT-04)."""
    # Path traversal guard — slugify strips to [a-z0-9-] (Pitfall 6)
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

**Error handling pattern** (`npc.py` lines 354–358, 411–413 — 404 on get_note=None):
```python
note_text = await obsidian.get_note(path)
if note_text is None:
    raise HTTPException(status_code=404, detail={"error": "NPC not found", "slug": slug})
```

**Key difference from existing npc.py POST routes:** No Pydantic request model needed — path parameter only. No LLM call. `list_npcs` silently skips unreadable files (degrade-gracefully, mirrors `list_directory` behavior at `obsidian.py:119`).

---

### `modules/pathfinder/app/main.py` (config/wiring — MODIFY)

**Analog:** itself (`main.py` lines 51–60, 135–196, 69–90)

**Import block pattern** (lines 51–60 — copy verbatim style, add one entry per new router):
```python
import app.routes.npcs as _npcs_module          # ADD
from app.routes.npcs import router as npcs_router  # ADD
```

**Lifespan singleton wiring pattern** (lines 135–196 — copy the pattern at lines 135, 139, 149, 178):
```python
# After _foundry_module.discord_bot_url = ... (line 195), add:
_npcs_module.obsidian = obsidian_client
```
Teardown — add matching None assignment after the yield block, following lines 198–206:
```python
_npcs_module.obsidian = None
```

**REGISTRATION_PAYLOAD routes list pattern** (lines 72–89 — append 2 entries, Pitfall 7):
```python
{"path": "npcs/", "description": "List all Sentinel NPCs (FVT-04)"},
{"path": "npcs/{slug}/foundry-actor", "description": "Return PF2e actor JSON for NPC (FVT-04)"},
```

**include_router pattern** (lines 258–265 — append after existing routers):
```python
app.include_router(npcs_router)
```

**CORS fix** (line 240 — REQUIRED: add "GET" or both new endpoints are CORS-blocked from Foundry browser):
```python
# BEFORE (line 240):
allow_methods=["POST", "OPTIONS"],
# AFTER:
allow_methods=["GET", "POST", "OPTIONS"],
```

---

### `modules/pathfinder/foundry-client/sentinel-connector.js` (browser module — MODIFY)

**Analog:** itself (lines 43–151)

**Class definition placement** — define `SentinelNpcImporter` at file top-level after `const MODULE_ID`, before any `Hooks` registration (RESEARCH.md Pitfall 8). RESEARCH.md Pattern 1 provides the full class template.

**ApplicationV2 subclass pattern** (RESEARCH.md Pattern 1 — condensed version):
```javascript
const { ApplicationV2 } = foundry.applications.api;

class SentinelNpcImporter extends ApplicationV2 {
  static DEFAULT_OPTIONS = {
    id: 'sentinel-npc-importer',
    tag: 'div',
    window: { title: 'Import NPC from Sentinel', resizable: false },
    position: { width: 400, height: 'auto' },
    actions: {
      retry:     function(ev, t) { return this._onRetry(ev, t); },
      importNpc: function(ev, t) { return this._onImport(ev, t); },
      close:     function(ev, t) { this.close(); },
    },
  };

  #npcs = [];
  #selectedSlug = null;
  #error = null;

  async _prepareContext(options) { /* fetch listing or preserve #npcs */ }
  async _renderHTML(context, options) { /* template-literal HTML string */ }
  _onRender(context, options) { /* addEventListener on <select> */ }
  async _onRetry(ev, t) { await this.render({ fetchNpcs: true }); }
  async _onImport(ev, t) { /* fetch actor + Actor.create / actor.update */ }
}
```

**Critical:** `DEFAULT_OPTIONS.actions` must be in the SAME object literal as the rest of DEFAULT_OPTIONS — no self-spread from `SentinelNpcImporter.DEFAULT_OPTIONS` (Pitfall 3). The action handler functions use `this` bound to the instance by Foundry's action binding.

**Hook injection pattern** (`sentinel-connector.js` lines 84–151 — add inside existing `Hooks.once('ready', ...)` block):
```javascript
Hooks.once('ready', () => {
  // ... existing preCreateChatMessage hook registration ...

  // Phase 36: actor directory import button
  Hooks.on('renderActorDirectory', (app, html) => {
    // Idempotency guard — hook fires on every sidebar render (Pitfall 2)
    const existing = html.find
      ? html.find('#sentinel-import-btn')
      : html.querySelector('#sentinel-import-btn');
    if (html.find ? existing.length : existing) return;

    const actionButtons = html.find
      ? html.find('.directory-header .action-buttons')
      : html.querySelector('.directory-header .action-buttons');

    const button = document.createElement('button');
    button.id = 'sentinel-import-btn';
    button.type = 'button';
    button.textContent = 'Import from Sentinel';
    button.addEventListener('click', () => new SentinelNpcImporter().render(true));

    if (html.find) {
      $(actionButtons).append(button);
    } else {
      actionButtons?.append(button);
    }
  });
});
```

**`await fetch()` pattern for import** — unlike `postEvent()` which is fire-and-forget (line 179 `async function postEvent`), the import handler MUST `await fetch()` before calling `Actor.create()`:
```javascript
// In _onImport():
const sentinelUrl = game.settings.get(MODULE_ID, 'sentinelBaseUrl');
const sentinelKey = game.settings.get(MODULE_ID, 'apiKey');
const resp = await fetch(
  `${sentinelUrl}/modules/pathfinder/npcs/${this.#selectedSlug}/foundry-actor`,
  { headers: { 'X-Sentinel-Key': sentinelKey } },
);
if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
const actorData = await resp.json();
```

**Duplicate check + notification pattern** (D-05, RESEARCH.md Code Examples):
```javascript
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
```

**Error notification pattern** (mirrors existing `sentinel-connector.js` console.warn style, line 203):
```javascript
} catch (err) {
  ui.notifications.error('Import failed. Check Sentinel connection.');
  console.error('[sentinel-connector] Import error:', err);
}
```

---

### `modules/pathfinder/foundry-client/module.json` (config — MODIFY)

**Analog:** itself (line 4)

Single field change — version bump:
```json
"version": "1.1.0"
```

No other fields change.

---

### `modules/pathfinder/foundry-client/package.sh` (utility — RE-RUN)

**Analog:** itself (all lines)

No modifications to `package.sh` itself. Re-run after JS and module.json changes:
```bash
cd modules/pathfinder/foundry-client && ./package.sh
```
Output: `sentinel-connector.zip` with updated `sentinel-connector/module.json` (v1.1.0) and `sentinel-connector/sentinel-connector.js`.

---

### `modules/pathfinder/tests/test_npcs.py` (test — NEW)

**Primary analog:** `modules/pathfinder/tests/test_foundry.py` (structure, env setup, ASGITransport pattern)
**Secondary analog:** `modules/pathfinder/tests/test_npc.py` (obsidian mock pattern, `patch("app.routes.npc.obsidian", mock_obs)`)

**Env setup + import pattern** (`test_npc.py` lines 1–13, `test_foundry.py` lines 1–21):
```python
"""Tests for GET /npcs/ and GET /npcs/{slug}/foundry-actor (FVT-04a..FVT-04f)."""
import os
os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("SENTINEL_CORE_URL", "http://sentinel-core:8000")
os.environ.setdefault("OBSIDIAN_BASE_URL", "http://localhost:27123")
os.environ.setdefault("OBSIDIAN_API_KEY", "")
os.environ.setdefault("LITELLM_MODEL", "openai/local-model")
os.environ.setdefault("LITELLM_API_BASE", "http://localhost:1234/v1")

from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch
```

**Obsidian mock pattern** (`test_npc.py` lines 23–38 — patch the module-level `obsidian` variable):
```python
mock_obs = MagicMock()
mock_obs.list_directory = AsyncMock(return_value=["mnemosyne/pf2e/npcs/varek.md"])
mock_obs.get_note = AsyncMock(return_value="---\nname: Varek\nlevel: 5\nancestry: Human\n---\n")

with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
     patch("app.routes.npcs.obsidian", mock_obs):
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/npcs/")
```

**GET vs POST distinction** — existing tests all use `client.post(...)`. The new tests use `client.get(...)`:
```python
resp = await client.get("/npcs/")
resp = await client.get("/npcs/varek/foundry-actor")
```

**Test structure for 6 required tests** (FVT-04a..FVT-04f):

```python
# FVT-04a: list_npcs returns [{name, slug, level, ancestry}] for vault with 2 NPCs
async def test_list_npcs_success():
    mock_obs = MagicMock()
    mock_obs.list_directory = AsyncMock(return_value=[
        "mnemosyne/pf2e/npcs/varek.md",
        "mnemosyne/pf2e/npcs/baron-aldric.md",
    ])
    mock_obs.get_note = AsyncMock(side_effect=[
        "---\nname: Varek\nlevel: 5\nancestry: Human\n---\n",
        "---\nname: Baron Aldric\nlevel: 8\nancestry: Dwarf\n---\n",
    ])
    # ... assert resp.status_code == 200, len(data) == 2, data[0]["slug"] == "varek"

# FVT-04b: empty vault → []
async def test_list_npcs_empty():
    mock_obs.list_directory = AsyncMock(return_value=[])
    # ... assert resp.json() == []

# FVT-04c: obsidian unreachable → [] not 503
async def test_list_npcs_obsidian_down():
    mock_obs.list_directory = AsyncMock(return_value=[])  # list_directory degrades to [] on error
    # ... assert resp.status_code == 200, resp.json() == []

# FVT-04d: known slug → valid PF2e actor JSON
async def test_get_foundry_actor_success():
    mock_obs.get_note = AsyncMock(return_value="---\nname: Varek\nlevel: 5\nancestry: Human\n---\n")
    # ... assert resp.status_code == 200, "name" in data, "system" in data, data["type"] == "npc"

# FVT-04e: unknown slug → 404
async def test_get_foundry_actor_not_found():
    mock_obs.get_note = AsyncMock(return_value=None)
    # GET /npcs/nobody/foundry-actor → assert resp.status_code == 404

# FVT-04f: path traversal slug → 400
async def test_get_foundry_actor_invalid_slug():
    # GET /npcs/..%2F..%2Fetc%2Fpasswd/foundry-actor → 400
    # (URL-encoded, or use slug="../../etc/passwd" if httpx decodes; also test "varek/etc")
    # assert resp.status_code == 400
```

**REGISTRATION_PAYLOAD test** (mirrors `test_foundry.py` lines 163–168):
```python
async def test_registration_payload():
    from app.main import REGISTRATION_PAYLOAD
    paths = [r["path"] for r in REGISTRATION_PAYLOAD["routes"]]
    assert "npcs/" in paths
    assert "npcs/{slug}/foundry-actor" in paths
```

---

## Shared Patterns

### Module-level obsidian singleton
**Source:** `modules/pathfinder/app/routes/npc.py` lines 48–49; `modules/pathfinder/app/main.py` lines 135, 198
**Apply to:** `routes/npcs.py` (set at lifespan) and `tests/test_npcs.py` (patched per test)
```python
# routes/npcs.py
obsidian = None  # set by main.py lifespan, patchable in tests

# main.py lifespan (add alongside line 135):
_npcs_module.obsidian = obsidian_client

# main.py teardown (add alongside line 198):
_npcs_module.obsidian = None
```

### 404 error handling
**Source:** `modules/pathfinder/app/routes/npc.py` lines 411–413
**Apply to:** `GET /npcs/{slug}/foundry-actor` in `routes/npcs.py`
```python
if note_text is None:
    raise HTTPException(status_code=404, detail={"error": "NPC not found", "slug": slug})
```

### Degrade-gracefully on Obsidian errors
**Source:** `modules/pathfinder/app/obsidian.py` lines 119–120 (`list_directory` returns `[]` on error)
**Apply to:** `GET /npcs/` — no try/except needed; `list_directory` degrades to `[]` silently. `get_note` returns `None` on 404. Both are skip-friendly.

### X-Sentinel-Key auth (JS side)
**Source:** `modules/pathfinder/foundry-client/sentinel-connector.js` lines 180–183, 191–195
**Apply to:** all `fetch()` calls in `SentinelNpcImporter` — include header on both listing and actor fetches:
```javascript
headers: { 'X-Sentinel-Key': game.settings.get(MODULE_ID, 'apiKey') }
```

### ASGITransport test client
**Source:** `modules/pathfinder/tests/test_foundry.py` lines 46–52; `test_npc.py` lines 30–38
**Apply to:** all tests in `test_npcs.py`
```python
async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
    resp = await client.get("/npcs/")
```

### Settings read pattern (JS)
**Source:** `modules/pathfinder/foundry-client/sentinel-connector.js` lines 180–182
**Apply to:** `SentinelNpcImporter._prepareContext()` and `_onImport()`:
```javascript
const sentinelUrl = game.settings.get(MODULE_ID, 'sentinelBaseUrl');
const sentinelKey = game.settings.get(MODULE_ID, 'apiKey');
```

---

## No Analog Found

No files in this phase lack a codebase analog. All patterns have direct matches.

---

## Metadata

**Analog search scope:** `modules/pathfinder/app/routes/`, `modules/pathfinder/tests/`, `modules/pathfinder/foundry-client/`, `modules/pathfinder/app/`
**Files scanned:** 9 (npc.py, main.py, foundry.py, obsidian.py, sentinel-connector.js, module.json, package.sh, test_foundry.py, test_npc.py, conftest.py)
**Pattern extraction date:** 2026-04-26
