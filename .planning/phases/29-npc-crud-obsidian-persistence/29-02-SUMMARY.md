---
phase: 29-npc-crud-obsidian-persistence
plan: "02"
subsystem: pathfinder-module
tags: [obsidian-client, litellm, pydantic-settings, npc, config]
dependency_graph:
  requires:
    - "29-01"
  provides:
    - modules/pathfinder/app/config.py
    - modules/pathfinder/app/obsidian.py
    - modules/pathfinder/app/llm.py
  affects:
    - modules/pathfinder/pyproject.toml
    - modules/pathfinder/compose.yml
    - .env.example
tech_stack:
  added:
    - litellm>=1.83.0
    - pydantic-settings>=2.13.0
    - pyyaml>=6.0.0
  patterns:
    - pydantic-settings BaseSettings with env_file + extra=ignore
    - httpx.AsyncClient injected at ObsidianClient construction (not created internally)
    - _safe_request wrapper for graceful GET degradation
    - litellm.acompletion with api_base kwarg injection
    - _strip_code_fences for LLM JSON response cleaning
key_files:
  created:
    - modules/pathfinder/app/config.py
    - modules/pathfinder/app/obsidian.py
    - modules/pathfinder/app/llm.py
  modified:
    - modules/pathfinder/pyproject.toml
    - modules/pathfinder/compose.yml
    - .env.example
decisions:
  - "ObsidianClient uses PATCH with Target-Type: frontmatter + Target: <field> headers for single-field updates; multi-field updates use GET-then-PUT per D-29 research finding"
  - "litellm.acompletion called directly (no wrapper class) matching sentinel-core/app/clients/litellm_provider.py pattern"
  - "_strip_code_fences handles both ```json and plain ``` fences as LLMs frequently wrap JSON in either form"
metrics:
  duration: "~103 seconds"
  completed: "2026-04-22"
  tasks_completed: 2
  files_created: 3
  files_modified: 3
---

# Phase 29 Plan 02: Pathfinder Foundation Layer Summary

**One-liner:** pydantic-settings config, ObsidianClient (get/put/patch), and LiteLLM NPC extraction functions for the pathfinder module.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add dependencies + create config.py | 3fa0b0e | pyproject.toml, app/config.py |
| 2 | Create obsidian.py + llm.py service clients | 1efbaba | app/obsidian.py, app/llm.py, compose.yml, .env.example |

## What Was Built

**config.py** — `Settings(BaseSettings)` class with all env vars needed by the pathfinder module: `sentinel_core_url`, `sentinel_api_key` (required, no default), `obsidian_base_url`, `obsidian_api_key`, `litellm_model`, `litellm_api_base`. Reads from `.env` file and environment; `extra="ignore"` prevents unknown var failures.

**obsidian.py** — `ObsidianClient` mirroring `sentinel-core/app/clients/obsidian.py`. Constructor takes injected `httpx.AsyncClient`. Three methods: `get_note` (GET with 404→None via `_safe_request`), `put_note` (full note create/replace, raises on error), `patch_frontmatter_field` (single-field PATCH with `Target-Type: frontmatter` + `Target: <field>` + `Operation: replace` headers per D-29).

**llm.py** — `extract_npc_fields` and `update_npc_fields` async functions calling `litellm.acompletion` directly. Both use `_strip_code_fences` to handle LLM JSON wrapped in markdown fences. `extract_npc_fields` sends a structured PF2e Remaster prompt constraining output to all NPC frontmatter fields with random-fill for unspecified ancestry/class/traits (D-06, D-07). `update_npc_fields` prompts for only changed fields (D-10).

**pyproject.toml** — Added `litellm>=1.83.0`, `pydantic-settings>=2.13.0`, `pyyaml>=6.0.0` to project dependencies.

**compose.yml** — Added `OBSIDIAN_BASE_URL`, `OBSIDIAN_API_KEY`, `LITELLM_MODEL`, `LITELLM_API_BASE` to the `pf2e-module` environment block.

**.env.example** — Added Pathfinder Module Obsidian direct access block with `OBSIDIAN_BASE_URL`, `OBSIDIAN_API_KEY`, `LITELLM_MODEL`, `LITELLM_API_BASE` after the existing `OBSIDIAN_API_URL` line (D-27: pathfinder calls Obsidian directly, sentinel-core uses `OBSIDIAN_API_URL`).

## Verification Results

- All 5 existing pathfinder tests pass (test_healthz, test_registration x4)
- `from app.config import settings` imports cleanly with `SENTINEL_API_KEY=test` in env
- `settings.obsidian_base_url` == `"http://host.docker.internal:27123"`
- `from app.obsidian import ObsidianClient` imports cleanly
- `from app import llm` imports cleanly
- grep confirms litellm, pydantic-settings, pyyaml each appear once in pyproject.toml

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — no stub implementations. `extract_npc_fields` and `update_npc_fields` are fully implemented functions (they require a live LiteLLM endpoint to produce output, which is an operational dependency, not a stub).

## Threat Surface Scan

No new network endpoints introduced in this plan. Files implement client-side callers only (ObsidianClient calls :27123, llm.py calls LiteLLM endpoint). Both trust boundaries (pathfinder→Obsidian, pathfinder→LiteLLM) are pre-declared in the plan's threat model (T-29-01, T-29-02, T-29-04). No unregistered surface found.

## Self-Check: PASSED

- `modules/pathfinder/app/config.py` — FOUND
- `modules/pathfinder/app/obsidian.py` — FOUND
- `modules/pathfinder/app/llm.py` — FOUND
- Commit 3fa0b0e — FOUND
- Commit 1efbaba — FOUND
