---
phase: 29-npc-crud-obsidian-persistence
plan: "05"
subsystem: pathfinder-module
tags: [npc, obsidian, foundry, import, relate, pathfinder, pf2e]
dependency_graph:
  requires:
    - 29-04  # npc.py router + helpers already established
    - 29-02  # ObsidianClient.patch_frontmatter_field in obsidian.py
  provides:
    - /npc/relate endpoint (NPC-04)
    - /npc/import endpoint (NPC-05)
    - parse_foundry_actor() helper
  affects:
    - modules/pathfinder/app/routes/npc.py
tech_stack:
  added: []
  patterns:
    - GET-then-PATCH for single-field Obsidian frontmatter update
    - Defensive Foundry JSON parsing (unknown keys logged, not fatal)
    - Per-actor collision check in bulk import loop
key_files:
  created: []
  modified:
    - modules/pathfinder/app/routes/npc.py
decisions:
  - "Use module-level `obsidian` variable (not request.app.state) — matches existing handler pattern and test patch target"
  - "import json added as stdlib import; ruff PostToolUse hook stripped it on first edit attempt (json.loads usage inside function body)"
  - "Duplicate relationships appended without dedup — plan spec: no deduplication in Phase 29"
metrics:
  duration: "~5 minutes"
  completed: "2026-04-22"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 1
---

# Phase 29 Plan 05: /npc/relate and /npc/import Endpoints Summary

One-liner: POST /npc/relate (GET-then-PATCH relationship append) and POST /npc/import (defensive Foundry actor JSON bulk create) added to npc.py router, completing all 5 NPC endpoints and making all 9 test_npc.py tests green.

## What Was Built

### Task 1: /npc/relate (NPC-04)

`relate_npc` handler appended to `modules/pathfinder/app/routes/npc.py`:

- Validates `relation` against `VALID_RELATIONS` frozenset before any I/O (returns 422 with valid options list on invalid type)
- GET current note — returns 404 if NPC does not exist
- Parses frontmatter via `_parse_frontmatter()`, reads existing `relationships` list
- Appends `{"target": req.target, "relation": req.relation}` entry (D-14 format)
- PATCH single field via `obsidian.patch_frontmatter_field(path, "relationships", updated_list)` (D-29 replace semantics)
- Returns 200 with slug, path, relation, target, full updated relationships list

### Task 2: /npc/import + parse_foundry_actor (NPC-05)

`parse_foundry_actor()` helper:

- Extracts identity fields from Foundry PF2e actor dict (`system.details.*` path)
- Returns `None` if actor has no name (silently skipped)
- Defensively handles both dict and scalar values for level/ancestry/class/traits
- Logs unrecognized top-level keys for Phase 30 schema derivation reference
- Sets `imported_from: "foundry"` on all returned dicts

`import_npcs` handler:

- Size guard: 413 if `len(req.actors_json) > 10_000_000` before `json.loads()` (T-29-04 DoS mitigation)
- Parses JSON array; 400 on malformed JSON or non-array
- Per-actor loop: skip non-dict entries, skip None from `parse_foundry_actor`, collision check via `get_note`, `put_note` to create identity-only note
- Collision actors added to `skipped` list, created actors to `imported` list
- Returns 200 with `imported_count`, `imported`, `skipped`

## Test Results

All 14 pathfinder tests pass:

| Test | Status |
|------|--------|
| test_healthz_returns_ok | PASS |
| test_npc_create_success | XPASS |
| test_npc_create_collision | XPASS |
| test_npc_update_identity_fields | XPASS |
| test_npc_show_returns_fields | XPASS |
| test_npc_show_not_found | XPASS |
| test_npc_relate_valid | XPASS |
| test_npc_relate_invalid_type | XPASS |
| test_npc_import_basic | XPASS |
| test_npc_import_collision_skipped | XPASS |
| test_registration_succeeds_on_first_attempt | PASS |
| test_registration_retries_on_failure | PASS |
| test_registration_exits_after_all_failures | PASS |
| test_registration_payload_correct | PASS |

Zero XFAIL remaining in test_npc.py. All 9 NPC tests now XPASS.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 | 5f1a7c0 | feat(29-05): implement /npc/relate endpoint (NPC-04) |
| Task 2 | a3bf354 | feat(29-05): implement /npc/import endpoint + parse_foundry_actor (NPC-05) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Used module-level `obsidian` instead of `request.app.state.obsidian_client`**
- **Found during:** Task 1 implementation
- **Issue:** Plan's code snippet used `request.app.state.obsidian_client` and `Request` parameter injection, but all existing handlers (create, update, show) use the module-level `obsidian = None` variable patched by tests via `patch("app.routes.npc.obsidian", ...)`. Using `request.app.state` would bypass the test mock and cause all tests to fail.
- **Fix:** Used module-level `obsidian` variable (no `Request` parameter) for both new handlers, matching the established pattern.
- **Files modified:** modules/pathfinder/app/routes/npc.py
- **Commit:** 5f1a7c0, a3bf354

**2. [Rule 1 - Bug] `import json` stripped by ruff PostToolUse hook on first edit**
- **Found during:** Task 2 verification
- **Issue:** The PostToolUse hook runs `ruff check --fix` after every Edit. When `import json` was added in a separate Edit before the function body using it existed, ruff F401 flagged it as unused and stripped it. Subsequent Edits added `json.loads` to the body, but the import was already gone.
- **Fix:** Re-added `import json` after the function body with `json.loads` and `json.JSONDecodeError` was already committed, so ruff correctly saw it as used.
- **Files modified:** modules/pathfinder/app/routes/npc.py
- **Commit:** a3bf354

## Known Stubs

None. All 5 NPC endpoints are fully implemented with live Obsidian I/O (mocked in tests). No placeholder text or hardcoded empty returns.

## Threat Flags

No new threat surface beyond what the plan's threat model covers:
- T-29-04: 10MB size guard implemented before `json.loads()` call
- T-29-01: `slugify()` path-sanitization applied to actor names (same as create)
- T-29-02: `VALID_RELATIONS` frozenset check before any Obsidian I/O
- T-29-03: Endpoints are behind sentinel-core proxy X-Sentinel-Key (accepted, per-plan)

## Self-Check: PASSED

- [x] `modules/pathfinder/app/routes/npc.py` exists and contains `relate_npc`, `import_npcs`, `parse_foundry_actor`
- [x] Commit 5f1a7c0 exists: `git log --oneline | grep 5f1a7c0`
- [x] Commit a3bf354 exists: `git log --oneline | grep a3bf354`
- [x] 14/14 tests pass with zero XFAIL
- [x] `grep -c 'patch_frontmatter_field'` returns 1 in npc.py
- [x] `grep -c 'imported_from.*foundry'` returns 2 in npc.py
