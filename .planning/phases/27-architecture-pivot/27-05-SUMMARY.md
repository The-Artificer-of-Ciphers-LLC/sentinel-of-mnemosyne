---
phase: 27-architecture-pivot
plan: "05"
subsystem: documentation
tags: [architecture, path-b, docs, prd, roadmap]
dependency_graph:
  requires: []
  provides:
    - "ARCHITECTURE-Core.md: canonical Path B architecture document"
    - "PRD-Sentinel-of-Mnemosyne.md: PRD with Path B AI layer description"
    - "ROADMAP.md Phase 11: Path B module contract goal"
  affects:
    - "docs/ARCHITECTURE-Core.md"
    - "docs/PRD-Sentinel-of-Mnemosyne.md"
    - ".planning/ROADMAP.md"
tech_stack:
  added: []
  patterns:
    - "LiteLLM-direct chat: POST /message → LiteLLMProvider → AI provider"
    - "Module API gateway: POST /modules/register + POST /modules/{name}/{path} proxy"
key_files:
  created: []
  modified:
    - docs/ARCHITECTURE-Core.md
    - docs/PRD-Sentinel-of-Mnemosyne.md
    - .planning/ROADMAP.md
decisions:
  - "Path B is now the canonical architecture: LiteLLM-direct for chat, module API gateway for extensibility, Pi demoted to optional v0.7 tool"
  - "ADR-001 updated: documents Path B decision context and rationale as of 2026-04-20"
  - "ROADMAP.md Phase 11 goal: first Path B module (Pathfinder) is the reference implementation for the module contract"
metrics:
  duration: "~8 minutes"
  completed: "2026-04-20"
  tasks_completed: 2
  files_modified: 3
---

# Phase 27 Plan 05: Architecture Doc Rewrite (Path B) Summary

Path B canonical architecture docs shipped: ARCHITECTURE-Core.md fully rewritten to LiteLLM-direct + module API gateway; PRD §2 and §3.1 updated to remove Pi-as-brain language; ROADMAP.md Phase 11 goal replanned as the Path B reference module implementation.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Rewrite ARCHITECTURE-Core.md to Path B | 49760ef | docs/ARCHITECTURE-Core.md |
| 2 | Update PRD §2 + §3.1 and ROADMAP.md Phase 11 | cafea72 | docs/PRD-Sentinel-of-Mnemosyne.md, .planning/ROADMAP.md |

## What Was Built

### Task 1 — ARCHITECTURE-Core.md

Complete rewrite from Path A (Pi-as-primary) to Path B (LiteLLM-direct + module gateway):

- **§1 System Overview**: Replaced Path A diagram with Path B ASCII diagram showing Interface Layer → Sentinel Core (with Module Registry) → AI Provider and Module Containers in parallel. Pi Harness demoted to footnote: "optional, --pi flag, v0.7 scope."
- **ADR-001**: Replaced "Pi Harness as AI Execution Layer" with "LiteLLM-Direct for Chat; Module API Gateway for Extensibility." Decision dated 2026-04-20. Context documents that Phase 25 shipped LiteLLM-direct and Phase 27 formalizes it.
- **Message Flow section (§6 Core API)**: Chat path is `POST /message → LiteLLMProvider → AI provider`. No Pi hop.
- **Module API Contract (§4)**: New section documenting `POST /modules/register` payload and `POST /modules/{name}/{path}` proxy contract with 503/404 error cases and a Python startup registration example.
- **Repo structure**: Updated to include `routes/modules.py` and `services/module_registry.py`.
- **sentinel.sh**: Updated with `--pathfinder`, `--pi` flags; `--pi` is the only way Pi harness starts.

### Task 2 — PRD + ROADMAP.md

**PRD §2** — Replaced:
> "The Pi harness as the brain. The pi-mono coding-agent is the AI execution layer."

With:
> "LiteLLM-direct as the AI layer. The Sentinel calls LiteLLM → the configured AI provider directly. No intermediate layer. Pi harness is an optional power tool for advanced coding tasks, activated via `./sentinel.sh --pi`, scoped to v0.7."

**PRD §3.1** — Replaced the old sequential diagram (Interface → Core → Pi → Obsidian → Modules) with the Path B ASCII diagram. Updated Container Roles to describe sentinel-core as API gateway, LiteLLM as embedded AI layer, Module Containers as self-registering FastAPI apps, Pi Harness as optional v0.7 tool.

**ROADMAP.md Phase 11** — Replaced goal:
> "DM co-pilot. Create and query NPCs, capture session notes, generate in-character dialogue."

With:
> "Deliver the first module under the Path B contract. A FastAPI container that registers with sentinel-core via POST /modules/register at startup, exposes NPC management and session note endpoints, and is added to the stack via a single `docker compose --profile pathfinder` entry. This is the v0.5 reference implementation for all future modules."

ROADMAP.md immutable flag (`uchg`) restored after edit. Verified with `stat -f "%Sf"`.

## Deviations from Plan

### Note: ROADMAP.md Edit Went to Main Repo Initially

The `chflags nouchg` command targeted the main repo path (`/Users/trekkie/projects/sentinel-of-mnemosyne/.planning/ROADMAP.md`) and the Edit tool followed the same path — not the worktree copy. Detected immediately: reverted the main repo change with `git checkout`, re-locked main repo file, then edited the worktree copy directly. The worktree's `.planning/ROADMAP.md` has no immutable flag (it's a worktree copy, not the protected original). The acceptance criterion for `uchg` verification was run against the main repo's path — confirmed `uchg` present. No data loss.

No other deviations. Plan executed as specified.

## Verification Results

| Check | Result |
|-------|--------|
| `grep "Pi.*brain\|brain.*Pi" docs/ARCHITECTURE-Core.md` | 0 lines |
| `grep "Pi.*brain\|brain.*Pi" docs/PRD-Sentinel-of-Mnemosyne.md` | 0 lines |
| `grep "LiteLLM-direct" docs/ARCHITECTURE-Core.md` | 7 matches |
| `grep -F "POST /modules/register" docs/ARCHITECTURE-Core.md` | 6 matches |
| `grep -F "POST /modules/{name}/{path}" docs/ARCHITECTURE-Core.md` | 5 matches |
| `grep "INTERFACE LAYER\|MODULE CONTAINERS" docs/ARCHITECTURE-Core.md` | 2 matches |
| `grep "LiteLLM-direct" docs/PRD-Sentinel-of-Mnemosyne.md` | 1 match |
| `grep "MODULE CONTAINERS" docs/PRD-Sentinel-of-Mnemosyne.md` | 1 match |
| `grep "Pi API call" docs/PRD-Sentinel-of-Mnemosyne.md` | 0 matches |
| `grep "Path B contract" .planning/ROADMAP.md` | 1 match |
| `stat -f "%Sf" .planning/ROADMAP.md` (main repo) | `uchg` |

## Known Stubs

None. This plan is documentation-only — no runtime code was modified.

## Threat Flags

None. No new network endpoints, auth paths, or schema changes introduced. All changes are documentation.

## Self-Check: PASSED

- `docs/ARCHITECTURE-Core.md` — exists, contains Path B diagram and module contract
- `docs/PRD-Sentinel-of-Mnemosyne.md` — exists, Pi-as-brain language removed
- `.planning/ROADMAP.md` (worktree) — exists, Phase 11 goal updated
- Task 1 commit `49760ef` — confirmed in git log
- Task 2 commit `cafea72` — confirmed in git log
