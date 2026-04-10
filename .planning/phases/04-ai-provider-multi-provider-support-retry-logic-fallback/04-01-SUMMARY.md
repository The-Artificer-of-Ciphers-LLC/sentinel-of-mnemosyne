---
phase: 04-ai-provider-multi-provider-support-retry-logic-fallback
plan: "01"
subsystem: sentinel-core
tags: [ai-provider, config, litellm, anthropic, tenacity, models]
dependency_graph:
  requires: []
  provides:
    - sentinel-core/pyproject.toml — litellm, tenacity, anthropic runtime deps
    - sentinel-core/app/config.py — Settings with all provider env vars
    - sentinel-core/models-seed.json — static model registry seed
  affects:
    - sentinel-core/app/providers/ (phase 04 plans 02-04 depend on these settings)
tech_stack:
  added:
    - litellm>=1.83.0,<2.0
    - tenacity>=8.2.0,<10.0
    - anthropic>=0.93.0,<1.0
  patterns:
    - pydantic-settings for all env var configuration (no os.getenv())
    - Safe defaults (empty string for API keys = provider disabled, no startup failure)
key_files:
  created:
    - sentinel-core/models-seed.json
  modified:
    - sentinel-core/pyproject.toml
    - sentinel-core/app/config.py
decisions:
  - "litellm pinned >=1.83.0 to skip known-malicious 1.82.7-1.82.8 releases (March 2026 supply-chain incident)"
  - "anthropic_api_key defaults to empty string — Claude provider is opt-in, no startup failure without key"
  - "ai_provider defaults to lmstudio — existing behavior unchanged for deployments that do not set this env var"
  - "ollama and llamacpp fields are stubs with safe defaults — providers not yet implemented but config is wired"
metrics:
  duration: "~3 min"
  completed: 2026-04-10
  tasks_completed: 2
  files_changed: 3
---

# Phase 04 Plan 01: AI Provider Dependencies and Config Foundation Summary

Provider dependency installation and Settings extension with all provider env vars — litellm/tenacity/anthropic added to pyproject.toml with supply-chain-safe version pins, Settings extended with 8 new provider fields, and models-seed.json created with 5 model entries covering LM Studio, Claude (3 variants), and Ollama.

## What Was Built

### Task 1: Provider Dependencies (commit bf7a704)

Added three runtime dependencies to `sentinel-core/pyproject.toml`:

- `litellm>=1.83.0,<2.0` — pinned past the malicious 1.82.7 and 1.82.8 releases (March 2026 supply-chain incident)
- `tenacity>=8.2.0,<10.0` — async retry support for Plans 02-03
- `anthropic>=0.93.0,<1.0` — Messages API v2 compatibility for Claude provider

Supply-chain incident comment added inline above the new entries to document the reason for the lower bound on litellm.

### Task 2: Settings Extension + Model Registry (commit 9875324)

Extended `sentinel-core/app/config.py` Settings class with 8 new fields:

| Field | Default | Purpose |
|-------|---------|---------|
| `ai_provider` | `"lmstudio"` | Active provider selection |
| `ai_fallback_provider` | `"none"` | Fallback provider (claude or none) |
| `anthropic_api_key` | `""` | Claude API key — empty = disabled |
| `claude_model` | `"claude-haiku-4-5"` | Claude model ID |
| `ollama_base_url` | `"http://localhost:11434"` | Ollama server URL |
| `ollama_model` | `"qwen2.5:14b"` | Ollama model ID |
| `llamacpp_base_url` | `"http://localhost:8080"` | llama.cpp server URL |
| `llamacpp_model` | `"local-model"` | llama.cpp model ID |

All existing fields preserved unchanged.

Created `sentinel-core/models-seed.json` with 5 model entries:
- `qwen2.5:14b` (ollama) — 32768 context, no function calling
- `claude-haiku-4-5` (claude) — 200000 context, function calling + vision
- `claude-sonnet-4-5` (claude) — 200000 context, function calling + vision
- `claude-sonnet-4-6` (claude) — 200000 context, function calling + vision
- `local-model` (lmstudio) — 8192 context, no function calling

## Verification Results

All three plan verification checks passed:

1. `python3 -c "import json; json.load(open('sentinel-core/models-seed.json')); print('JSON valid')"` — PASS
2. `grep -c "ai_provider|ai_fallback_provider|anthropic_api_key|claude_model|ollama_base_url|llamacpp_base_url" sentinel-core/app/config.py` — output: 6
3. `grep -E "litellm>=1.83.0|tenacity>=8.2.0|anthropic>=0.93.0" sentinel-core/pyproject.toml | wc -l` — output: 3

## Deviations from Plan

None — plan executed exactly as written.

The plan's interface block showed `lmstudio_num_ctx: int = 8192` as an existing field, but the actual file did not have it. The new fields were appended after `obsidian_api_key` (the last actual field), which is the correct behavior — preserving what exists without inventing fields.

## Threat Mitigations Applied

| Threat | Mitigation |
|--------|-----------|
| T-04-01 (Information Disclosure — anthropic_api_key) | Empty string default; field not logged anywhere; Settings repr not exposed |
| T-04-03 (Supply Chain — litellm) | Lower bound >=1.83.0 skips malicious 1.82.7-1.82.8; upper bound <2.0 prevents silent breaking upgrades; comment documents rationale |

## Known Stubs

None that block plan goals. The ollama and llamacpp config fields are intentional stubs — provider implementations are out of scope for Plan 01 (they arrive in Plans 02-04). The config foundation is complete.

## Self-Check: PASSED

All files verified present. Both commits confirmed in git log.

| Check | Result |
|-------|--------|
| sentinel-core/pyproject.toml | FOUND |
| sentinel-core/app/config.py | FOUND |
| sentinel-core/models-seed.json | FOUND |
| commit bf7a704 | FOUND |
| commit 9875324 | FOUND |
