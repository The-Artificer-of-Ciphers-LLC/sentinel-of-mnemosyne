---
phase: 36-foundry-npc-pull-import
plan: 02
status: complete
wave: 1
completed: 2026-04-26
tdd_gate:
  green: true
  tests_passing: 7
  tests_total: 7
---

# Plan 36-02: Python Backend — routes/npcs.py + main.py wiring

## Objective

Implemented the Python backend for Phase 36: `routes/npcs.py` with two GET handlers and all
required wiring in `main.py`. All 7 test_npcs.py tests pass GREEN.

## What Was Built

### New Files
- `modules/pathfinder/app/routes/npcs.py` — Two GET route handlers:
  - `GET /npcs/` — lists all NPCs from vault as `[{name, slug, level, ancestry}]`; returns `[]` gracefully on empty vault or Obsidian down (never 503)
  - `GET /npcs/{slug}/foundry-actor` — returns PF2e actor JSON for a single NPC; path-traversal guard via `slugify(slug) != slug → 400`; returns 404 when slug not found

### Modified Files
- `modules/pathfinder/app/main.py` — 6 targeted edits:
  1. Import block: added `import app.routes.npcs as _npcs_module` and `from app.routes.npcs import router as npcs_router`
  2. REGISTRATION_PAYLOAD: added `{"path": "npcs/"}` and `{"path": "npcs/{slug}/foundry-actor"}` entries
  3. CORSMiddleware: fixed `allow_methods` to include `"GET"` (was `["POST", "OPTIONS"]`)
  4. Lifespan startup: `_npcs_module.obsidian = obsidian_client`
  5. Lifespan teardown: `_npcs_module.obsidian = None`
  6. Router registration: `app.include_router(npcs_router)`

### Test Fix
- `modules/pathfinder/tests/test_npcs.py` — Fixed `test_get_foundry_actor_invalid_slug` (FVT-04f):
  - Original used `/npcs/../etc/passwd/foundry-actor` — httpx normalizes literal `..` away before routing → 404 instead of 400
  - Fixed to use `/npcs/INVALID_SLUG/foundry-actor` — uppercase+underscore chars fail slugify guard reliably
  - Added comment documenting why `%2F`-encoded traversal is untestable via httpx

## TDD Gate: GREEN

All 7 test_npcs.py tests pass:
- `test_list_npcs_success` (FVT-04a) ✓
- `test_list_npcs_empty` (FVT-04b) ✓
- `test_list_npcs_obsidian_down` (FVT-04c) ✓
- `test_get_foundry_actor_success` (FVT-04d) ✓
- `test_get_foundry_actor_not_found` (FVT-04e) ✓
- `test_get_foundry_actor_invalid_slug` (FVT-04f) ✓
- `test_registration_payload` ✓

## Deviations

- **Test URL for FVT-04f:** Plan specified `..%2F..%2Fetc%2Fpasswd` as the slug. This doesn't
  work via httpx because Starlette decodes `%2F` → `/` before routing, making the path not
  match the route template. Changed to `INVALID_SLUG` — same guard (`slugify(slug) != slug`)
  is exercised, same 400 is returned. The production CORS behavior is unaffected.

## Self-Check: PASSED

- routes/npcs.py: path-traversal guard present (`safe_slug = slugify(slug); if safe_slug != slug: raise HTTPException(400)`) ✓
- main.py: `allow_methods=["GET", "POST", "OPTIONS"]` ✓
- main.py: both REGISTRATION_PAYLOAD routes present ✓
- main.py: lifespan startup + teardown for _npcs_module.obsidian ✓
- main.py: `app.include_router(npcs_router)` ✓
- 7/7 tests GREEN ✓

## Key Files

- `modules/pathfinder/app/routes/npcs.py` (new — 72 lines)
- `modules/pathfinder/app/main.py` (modified — CORS fix, imports, REGISTRATION_PAYLOAD, lifespan, router)
- `modules/pathfinder/tests/test_npcs.py` (modified — FVT-04f URL fix)
