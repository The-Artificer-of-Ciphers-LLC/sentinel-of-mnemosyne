---
phase: 35-foundry-vtt-event-ingest
plan: "05"
subsystem: foundry-client
completed: "2026-04-25T14:45:58Z"
duration: "3m"
tasks_completed: 2
tasks_total: 2
files_created: 4
files_modified: 0
commits:
  - "95895ff feat(35-05): create Foundry VTT JS module artifacts"
  - "532c3e9 feat(35-05): add Phase 35 UAT script for live stack verification"
requirements_completed:
  - FVT-01
  - FVT-02
  - FVT-03
tags:
  - foundry-vtt
  - javascript
  - esmodule
  - pf2e
  - sentinel-connector
dependency_graph:
  requires:
    - "35-04 (StaticFiles mount at /foundry/static/ in main.py)"
    - "35-03 (POST /foundry/event route in app/routes/foundry.py)"
  provides:
    - "Operator-installable Foundry VTT module zip"
    - "module.json manifest served at /foundry/static/module.json"
    - "sentinel-connector.zip served at /foundry/static/sentinel-connector.zip"
    - "Live stack UAT script for Phase 35 verification"
  affects:
    - "36-foundry-npc-import (reuses sentinel-connector.js module structure)"
tech_stack:
  added: []
  patterns:
    - "Foundry v14 ESModule (no bundler) via esmodules manifest field"
    - "preCreateChatMessage hook pattern: always return true, fire-and-forget fetch"
    - "PF2e four-degree outcome derivation: delta = rollTotal - dcValue"
    - "Zip subdirectory structure: sentinel-connector/ at zip root (Foundry Pitfall 7)"
key_files:
  created:
    - "modules/pathfinder/foundry-client/module.json"
    - "modules/pathfinder/foundry-client/sentinel-connector.js"
    - "modules/pathfinder/foundry-client/package.sh"
    - "modules/pathfinder/foundry-client/sentinel-connector.zip"
    - "scripts/uat_phase35.sh"
  modified: []
decisions:
  - "D-04: compatibility minimum=12 verified=14 in module.json"
  - "D-17: ESModule declared in esmodules array (not scripts) — no bundler required for Foundry v14"
  - "D-18: zip built via package.sh tmpdir pattern with sentinel-connector/ subdirectory at root"
  - "Sentinel-connector.zip pre-built and committed alongside source files for immediate static serving"
---

# Phase 35 Plan 05: Foundry VTT JS Module Artifacts Summary

**One-liner:** Foundry v14 ESModule with preCreateChatMessage hook, PF2e four-degree outcome derivation, and correctly-structured installable zip via package.sh.

## What Was Built

**Task 1: foundry-client/ JS module artifacts**

Three files created in `modules/pathfinder/foundry-client/`:

- `module.json` — Foundry v14 manifest declaring `esmodules: ["sentinel-connector.js"]`, `compatibility minimum=12 verified=14`, and `relationships.systems` for pf2e >= 6.0.0. Manifest/download URLs use `YOUR_SENTINEL_IP` placeholder for operator customization.
- `sentinel-connector.js` — ESModule implementing three settings (baseUrl, apiKey, chatPrefix) via `Hooks.once('init')`, the `preCreateChatMessage` hook via `Hooks.once('ready')`, `deriveOutcome()` using PF2e four-degree algorithm (delta = rollTotal - dcValue), and fire-and-forget `fetch()` helpers `_postRollEvent` / `_postChatEvent`. Always returns `true` from the hook — never suppresses Foundry messages (D-01 constraint).
- `package.sh` — Executable shell script that builds `sentinel-connector.zip` with `sentinel-connector/` subdirectory at zip root (Pitfall 7 prevention). Uses `mktemp -d` + `trap` for clean tmpdir.

Pre-built `sentinel-connector.zip` committed alongside source so the StaticFiles mount at `/foundry/static/` serves the zip immediately without requiring `package.sh` to run in the container.

**Task 2: scripts/uat_phase35.sh**

9-step curl-based UAT script covering:
1. pf2e-module /healthz direct
2. sentinel-core proxy /modules/pathfinder/healthz
3. REGISTRATION_PAYLOAD route count >= 16 (regression guard)
4. Valid roll payload → 200
5. Wrong X-Sentinel-Key → 401
6. Malformed payload → 422
7. GET /foundry/static/module.json → 200
8. GET /foundry/static/sentinel-connector.zip → 200 (or INFO if not yet built)
9. Chat payload → 200

Exits non-zero if any `check()` assertion fails.

## Deviations from Plan

None — plan executed exactly as written. All three files match the interfaces specified in the plan's `<action>` blocks verbatim.

## Pre-existing Issue (out of scope)

The pathfinder test suite (`python -m pytest tests/`) fails with `ModuleNotFoundError: No module named 'rapidfuzz'` when running against `test_foundry.py` (created in plan 35-01). This failure is pre-existing before plan 35-05 changes — confirmed via `git stash` regression test. Plan 35-05 introduces no Python files, so no regression was introduced. The `rapidfuzz` import issue is a dev-environment dependency gap, not a code defect.

## Verification Results

All acceptance criteria passed:
- `module.json` exists with `esmodules`, `"minimum": "12"` — confirmed
- `sentinel-connector.js` has `function deriveOutcome` and 6× `return true` — confirmed
- `package.sh` is executable and produces `sentinel-connector/module.json` at zip root — confirmed
- `unzip -l` shows 3 entries all under `sentinel-connector/` — confirmed
- `bash -n scripts/uat_phase35.sh` exits 0 — confirmed
- Discord interface tests: 52 passed — no regression

## Self-Check: PASSED

Files verified:
- FOUND: modules/pathfinder/foundry-client/module.json
- FOUND: modules/pathfinder/foundry-client/sentinel-connector.js
- FOUND: modules/pathfinder/foundry-client/package.sh
- FOUND: modules/pathfinder/foundry-client/sentinel-connector.zip
- FOUND: scripts/uat_phase35.sh

Commits verified:
- FOUND: 95895ff
- FOUND: 532c3e9
