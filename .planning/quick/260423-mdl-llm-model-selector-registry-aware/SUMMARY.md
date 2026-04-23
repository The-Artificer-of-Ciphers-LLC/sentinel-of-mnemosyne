---
task: llm-model-selector-registry-aware
slug: mdl
date: 2026-04-23
status: complete
scope: pathfinder-only (sentinel-core integration deferred)
---

# Quick Task Summary — Registry-Aware LLM Model Selector

## What was built

A capability-aware model selector that queries LM Studio's OpenAI-compatible `GET /v1/models` at runtime, consults `litellm.get_model_info` for each loaded model's capability metadata (`max_tokens`, `supports_function_calling`), and picks the best match for one of three task kinds: `chat`, `structured`, `fast`. The three NPC LLM call sites in the pathfinder module now resolve their model per-call instead of sharing the single `LITELLM_MODEL` env var.

## Files

### New

| File | Purpose | LOC |
|------|---------|-----|
| `modules/pathfinder/app/model_selector.py` | Pure logic: `get_loaded_models(api_base)` with process-level cache + `select_model(task_kind, loaded, preferences, default)` with per-task scoring rubric | 143 |
| `modules/pathfinder/app/resolve_model.py` | Thin wrapper wiring pathfinder's settings into the selector | 30 |
| `modules/pathfinder/tests/test_model_selector.py` | 13 tests covering discovery (4), scoring per task kind (3), preference override (2), fallback chain (3), error (1) | 209 |

### Modified

| File | Change |
|------|--------|
| `modules/pathfinder/app/config.py` | Added optional `litellm_model_chat`/`_structured`/`_fast: str \| None = None` |
| `modules/pathfinder/app/routes/npc.py` | 3 call sites replace `settings.litellm_model` with `await resolve_model("structured"\|"fast")`; new `from app.resolve_model import resolve_model` import |
| `.env.example` | Documents the three new optional env vars with commented examples |

## Scoring rubric

| Task kind | Score formula (higher wins) | Ineligible if |
|-----------|------------------------------|---------------|
| `chat` | `max_tokens + (10_000 if supports_function_calling else 0)` | — |
| `structured` | `10_000 - abs(max_tokens - 8_000)` | `not supports_function_calling` |
| `fast` | `100_000 - max_tokens` | `max_tokens < 4_000` |

Models not present in `litellm.model_cost` (common for local GGUFs like Qwen2.5-3B-Instruct-GGUF) score 0 and fall through to the preference → default → first-loaded chain.

## Resolution order (in `select_model`)

1. `preferences[task_kind]` if set AND in `loaded` — honors user intent
2. Highest-scoring loaded model per task rubric
3. `default` if set AND in `loaded`
4. First entry in `loaded` if non-empty
5. `default` if set (even if not discovered — LiteLLM may accept name anyway)
6. Raise `ModelSelectorError`

## Verification

```
$ cd modules/pathfinder && uv run pytest tests/ -q
....................................                                     [100%]
36 passed in 1.25s
```

Pathfinder: 36 tests pass (previously 23 — added 13 from test_model_selector.py). The existing NPC CRUD and OUT-01..04 tests still pass because the selector falls back to `settings.litellm_model` when LM Studio is unreachable (test environment), producing the same model string the previous code used directly.

```
$ uv run --with ... python -m pytest sentinel-core/tests/test_litellm_provider.py -q
.........                                                                [100%]
9 passed in 16.14s
```

Sentinel-core LiteLLMProvider regression check: still green (not modified by this task).

## Call-site mapping

| Call site | Task kind | Rationale |
|-----------|-----------|-----------|
| `routes/npc.py:create_npc` → `extract_npc_fields` | `structured` | JSON extraction — needs function-calling-capable model for reliable schema |
| `routes/npc.py:update_npc` → `update_npc_fields` | `structured` | Same JSON-extraction profile |
| `routes/npc.py:token_prompt` → `generate_mj_description` | `fast` | `max_tokens=40`, small model with >4K context is ideal |

## Deviations from PLAN.md

1. **Scoped to pathfinder only — sentinel-core not touched.** Discovered mid-implementation: the repo's Docker build context for `modules/pathfinder/` doesn't include `shared/` (unlike `interfaces/discord/` which uses `context: ../..`). Putting `model_selector` in `shared/` would require a Dockerfile + compose.yml rework on pathfinder's build pipeline — out of scope for a quick task. Moved the selector into `modules/pathfinder/app/` instead. Sentinel-core also has its own `model_registry` infrastructure (`sentinel-core/app/services/model_registry.py`) that already handles single-model capability lookup; full integration there is a larger refactor.

2. **`chat` preference env var included but currently unused.** Pathfinder's three call sites map to `structured` or `fast`. Added `LITELLM_MODEL_CHAT` to config anyway for consistency with the selector's three-kind vocabulary — no code cost, eases future integration.

## Threat model status

| Threat | Mitigation | Evidence |
|--------|------------|----------|
| LM Studio unreachable during discovery | `get_loaded_models` catches `Exception` and returns `[]`; logged as warning | `test_get_loaded_models_returns_empty_on_network_error` passes |
| Malicious model names from `/v1/models` response | Names used only as string keys to `litellm.get_model_info` and as the `model=` kwarg — no shell interpolation | Code inspection |
| Cache staleness across LM Studio model swaps | Documented `force_refresh=True` parameter on `get_loaded_models`; process restart also clears cache | `test_get_loaded_models_force_refresh_bypasses_cache` passes |
| Selected model's context too small for current prompt | Out of scope — existing token-guard in `sentinel-core/routes/message.py` handles this upstream | n/a |

## Known follow-ups (NOT this task)

- **Sentinel-core integration**: requires either moving `model_selector` to `shared/` + reshaping pathfinder's Docker build context, OR duplicating into sentinel-core's `app/services/`. Either way, sentinel-core's existing `model_registry` ought to be the integration point since it already handles model metadata.
- **HF Hub API fallback** for local GGUF models not in `litellm.model_cost`: parse the model name, query `https://huggingface.co/api/models/{repo}`, read `pipeline_tag` + `tags`. Significant scope — promote to a planned phase if wanted.
- **Config-level preferences instead of env vars**: move to `.planning/config.json` or similar so non-env config can drive selection. Low priority.
- **Per-request task-kind override**: caller could pass `task_kind_override` to `extract_npc_fields` etc. Not needed today; none of the 3 call sites want to override their task kind.

## Self-check: PASSED

- `modules/pathfinder/app/model_selector.py` exists, exports `get_loaded_models`, `select_model`, `ModelSelectorError`, `TaskKind`
- `modules/pathfinder/app/resolve_model.py` exists, exports `resolve_model(task_kind)`
- `config.py` has 3 new optional fields
- `npc.py` uses `await resolve_model("structured")` × 2, `await resolve_model("fast")` × 1
- `.env.example` documents the new vars
- 36/36 pathfinder tests pass; 9/9 sentinel-core LiteLLMProvider tests still pass
