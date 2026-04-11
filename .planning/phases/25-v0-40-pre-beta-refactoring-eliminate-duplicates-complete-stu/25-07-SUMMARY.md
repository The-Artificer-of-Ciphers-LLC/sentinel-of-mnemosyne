---
phase: 25-v0-40-pre-beta-refactoring-eliminate-duplicates-complete-stu
plan: "07"
subsystem: docs-models
tags: [doc-sync, models, architecture, contra]
dependency_graph:
  requires: [25-05-PLAN.md, 25-06-PLAN.md]
  provides: [CONTRA-01-resolved, CONTRA-02-resolved, CONTRA-03-resolved, CONTRA-04-resolved, D-03-resolved]
  affects: [docs/ARCHITECTURE-Core.md, docs/obsidian-lifebook-design.md, sentinel-core/app/models.py]
tech_stack:
  added: []
  patterns: [pydantic-v2-optional-fields, doc-code-sync]
key_files:
  created: []
  modified:
    - sentinel-core/app/models.py
    - docs/ARCHITECTURE-Core.md
    - docs/obsidian-lifebook-design.md
decisions:
  - MessageEnvelope gains source and channel_id as optional fields — backward-compatible (D-03)
  - ARCHITECTURE-Core.md vault structure updated to match code (ops/sessions/, not core/sessions/)
  - obsidian-lifebook-design.md reminders folded into get_self_context table (5 files, not 3)
metrics:
  duration: "~8 min"
  completed: "2026-04-11"
  tasks_completed: 2
  files_modified: 3
---

# Phase 25 Plan 07: Doc Sync (CONTRA-01 through CONTRA-04 + D-03) Summary

Doc sync plan: resolves all four architecture contradictions by making docs match code and expands MessageEnvelope with two optional routing fields.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 25-07-01 | Expand MessageEnvelope (D-03) + ARCHITECTURE-Core.md (CONTRA-01/02/04) | bf2ffe6 | sentinel-core/app/models.py, docs/ARCHITECTURE-Core.md |
| 25-07-02 | Update obsidian-lifebook-design.md (CONTRA-03) + run Phase 25 acceptance checks | ad74577 | docs/obsidian-lifebook-design.md |

## What Was Built

**D-03 — MessageEnvelope expansion (`sentinel-core/app/models.py`):**
Added `source: str | None = None` and `channel_id: str | None = None` as optional fields after `user_id`. All 129 sentinel-core tests remained GREEN — the fields are optional with `None` defaults, so no existing callers break.

**CONTRA-01 — Envelope section in ARCHITECTURE-Core.md:**
Replaced 8-field JSON example with a 4-field example matching the actual model. Added explicit note about which fields are required vs optional, and that id/timestamp/attachments/metadata are reserved for future expansion and not currently accepted.

**CONTRA-02 — Pi harness port in ARCHITECTURE-Core.md:**
Changed all 4 occurrences of port `8765` to `3000` (the actual Fastify bridge port used by pi-harness).

**CONTRA-04 — Session path in ARCHITECTURE-Core.md:**
Changed all 4 occurrences of `core/sessions/` to `ops/sessions/` to match the path used in `routes/message.py`. Also corrected the vault folder structure diagram in §6.2.

**CONTRA-03 — Self context file list in obsidian-lifebook-design.md:**
Updated `get_self_context` section from "3 files" to "5 files". Added `self/methodology.md` and `ops/reminders.md` to the table, the inline context injection model, and the Vault Path Conventions table.

## Phase 25 Acceptance Criteria Results

| Check | Command | Result |
|-------|---------|--------|
| AC-1: Zero call_core duplicates | `grep -rn "def call_core" interfaces/` | PASS — 0 results |
| AC-1: Zero NotImplementedError | `grep -rn "NotImplementedError" sentinel-core/app/` | PASS — 0 results |
| AC-3: sentinel-core tests GREEN | `.venv/bin/python -m pytest tests/ -q` | PASS — 129 passed |
| AC-3: pi-harness vitest GREEN | `npx vitest run` | PASS — 2 passed |
| AC-4: No 8765 in ARCHITECTURE-Core.md | `grep "8765" docs/ARCHITECTURE-Core.md` | PASS — 0 results |
| AC-4: No core/sessions in ARCHITECTURE-Core.md | `grep "core/sessions" docs/ARCHITECTURE-Core.md` | PASS — 0 results |
| AC-4: No "3 files" in obsidian-lifebook-design.md | `grep "3 files" docs/obsidian-lifebook-design.md` | PASS — 0 results |
| AC-5: Route registry (4 routes) | `grep -rn "@router\.\|@app\."` | PASS — POST /message, GET /health, GET /status, GET /context/{user_id} |
| AC-7: SentinelCoreClient shared | `grep -rn "SentinelCoreClient" interfaces/` | PASS — 2 matches (discord, imessage) |
| AC-8: SEC-04 checkbox | `grep "\[x\].*SEC-04" REQUIREMENTS.md` | PASS — 1 match |
| AC-8: Jailbreak baseline | `python -m pytest security/pentest/jailbreak_baseline.py -q` | PASS — 41 passed |
| AC-8: JAILBREAK-BASELINE.md exists | `ls security/JAILBREAK-BASELINE.md` | PASS — file exists |

All Phase 25 acceptance criteria PASS.

## Deviations from Plan

**1. [Rule 1 - Bug] Additional core/sessions occurrences in ARCHITECTURE-Core.md**
- **Found during:** Task 1
- **Issue:** The plan specified one `core/sessions` occurrence but there were 4: in §5 POST /message flow, §6.2 vault structure diagram, §9 Phase 2 implementation guide, and §12 curl example.
- **Fix:** Updated all 4 occurrences to `ops/sessions/`. Also corrected the vault folder structure diagram to move `sessions/` from under `core/` to the correct `ops/` branch.
- **Files modified:** docs/ARCHITECTURE-Core.md
- **Commit:** bf2ffe6

**2. [Rule 1 - Bug] Context Injection Model section also showed only 3 files**
- **Found during:** Task 2
- **Issue:** The `obsidian-lifebook-design.md` Context Injection Model section referenced `<self/identity.md + self/goals.md + self/relationships.md>` (3 files only) in addition to the get_self_context table.
- **Fix:** Updated the inline block to show all 5 sources. Also updated the Vault Path Conventions table at bottom of file.
- **Files modified:** docs/obsidian-lifebook-design.md
- **Commit:** ad74577

## Known Stubs

None — all changes are documentation and model field additions. No stub values, placeholder text, or wired-but-empty data sources introduced.

## Threat Flags

None — no new network endpoints, auth paths, or trust boundaries introduced. The `source` and `channel_id` fields added to MessageEnvelope are metadata strings with no execution path (T-25-07-01 accepted residual risk per threat model).

## Self-Check: PASSED

- [x] `sentinel-core/app/models.py` — modified, source/channel_id fields present
- [x] `docs/ARCHITECTURE-Core.md` — modified, 0 occurrences of 8765 and core/sessions
- [x] `docs/obsidian-lifebook-design.md` — modified, 5-file get_self_context documented
- [x] Commit bf2ffe6 exists (Task 1)
- [x] Commit ad74577 exists (Task 2)
- [x] 129 sentinel-core tests GREEN
- [x] 41 jailbreak baseline tests GREEN
- [x] pi-harness vitest 2 PASS
