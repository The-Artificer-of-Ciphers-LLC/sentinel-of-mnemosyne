---
task: llm-model-selector-registry-aware
slug: mdl
date: 2026-04-23
type: quick
scope: registry-aware model selection via LM Studio /v1/models discovery + litellm.get_model_info capability lookup
---

# Quick Task — Registry-Aware LLM Model Selector

## Objective

Replace the current single `LITELLM_MODEL` env var with a task-kind-aware model selector. The Sentinel queries LM Studio's `GET /v1/models` at runtime to discover loaded models, then picks the best match for each of three task kinds (`chat`, `structured`, `fast`) by consulting `litellm.get_model_info` for capability metadata.

## Background

**Current state:**
- Single `LITELLM_MODEL=openai/local-model` env var shared by 4 LiteLLM call sites
- `sentinel-core/app/clients/litellm_provider.py` — chat responses (conversational)
- `modules/pathfinder/app/routes/npc.py` × 3 — `extract_npc_fields` (structured JSON), `update_npc_fields` (structured JSON), `generate_mj_description` (short constrained, `max_tokens=40`)

**Problem:** Each task has genuinely different model requirements (big context vs function-calling reliability vs speed), but all four share one configured model.

**Solution chosen (from AskUserQuestion):** Registry-aware. Discover loaded models via LM Studio `/v1/models`; for each, consult `litellm.get_model_info` to extract capability signals (`max_tokens`, `supports_function_calling`); score each loaded model against a per-task rubric; return the best match. Fall back to env-var preferences, then to the legacy `LITELLM_MODEL` default, then to the first loaded model.

## Task Kinds and Scoring Rubric

| Task kind | Requirements | Score formula (higher = better) |
|-----------|--------------|----------------------------------|
| `chat` | Large context, function calling preferred | `max_tokens + (10_000 if supports_function_calling else 0)` |
| `structured` | Function calling REQUIRED (for reliable JSON), moderate context | `0 if not supports_function_calling else 10_000 - abs(max_tokens - 8000)` |
| `fast` | Small model, context >= 4K | `0 if max_tokens < 4_000 else 100_000 - max_tokens` (smaller = higher) |

Models not present in `litellm.model_cost` (common for local GGUFs) score 0 and fall through to preference/default tiers.

## Files

### New

- `shared/model_selector.py` (~80 LOC)
  - `async def get_loaded_models(api_base: str, *, force_refresh: bool = False) -> list[str]` — queries `{api_base}/models`, caches result (process-wide, refreshable)
  - `def select_model(task_kind: Literal["chat", "structured", "fast"], loaded: Sequence[str], *, preferences: Mapping[str, str | None] | None = None, default: str | None = None) -> str` — pure logic
  - `def _score(task_kind: str, model_id: str) -> int` — private scoring helper; wraps `litellm.get_model_info` + `litellm.supports_function_calling` with try/except (returns 0 on miss)
  - `class ModelSelectorError(RuntimeError)` — raised when no loaded models AND no default configured

- `shared/tests/test_model_selector.py` (~100 LOC)
  - `test_get_loaded_models_queries_and_caches` — mocks httpx, verifies cache hit on second call
  - `test_get_loaded_models_force_refresh` — verifies refresh bypasses cache
  - `test_select_chat_prefers_large_context_model` — stub `litellm.get_model_info`, verify selection
  - `test_select_structured_requires_function_calling` — model without FC support must not be selected even if only option
  - `test_select_fast_prefers_smaller` — smaller context wins
  - `test_preference_overrides_scoring` — if pref is in loaded, use it regardless of score
  - `test_falls_back_to_default_when_no_loaded_match` — all scores 0 + preference not loaded → default
  - `test_raises_when_no_loaded_and_no_default` — empty loaded + no default → ModelSelectorError
  - `test_falls_back_to_first_loaded_when_default_not_loaded` — default set but not present → first loaded

### Modified

- `sentinel-core/app/config.py` — add `litellm_model_chat: str | None = None`, `_structured`, `_fast` (optional overrides)
- `sentinel-core/app/clients/litellm_provider.py` — `complete()` calls `resolve_model("chat")` instead of using hard-coded model
- `sentinel-core/app/resolve_model.py` (new, ~15 LOC) — thin wrapper that reads `app.config.settings` and calls `shared.model_selector.select_model`
- `modules/pathfinder/app/config.py` — same three optional overrides
- `modules/pathfinder/app/resolve_model.py` (new, ~15 LOC) — same wrapper for pathfinder settings
- `modules/pathfinder/app/routes/npc.py` — 3 call sites replace `settings.litellm_model` with `await resolve_model("structured"|"fast")`
- `.env.example` — document the 3 optional env vars

### Preserved

- `settings.litellm_model` remains — treated as the catch-all default when no task-specific override is set and no scored match exists. Backward compatible: unset `LITELLM_MODEL_*` envs → behavior matches current code (always picks `LITELLM_MODEL`).

## Threat Model

| Threat | Mitigation |
|--------|------------|
| LM Studio unreachable during /v1/models query | `get_loaded_models` catches httpx errors, returns `[]`; `select_model` falls back to `default` env var |
| Malicious model names from LM Studio (cache poisoning via LAN attacker) | Discovered model names are used only as string keys into `litellm.get_model_info` and as the `model=` kwarg to litellm. No shell interpolation. litellm validates/normalizes model strings internally |
| Stale cache across LM Studio model swaps | Cache refresh is explicit (`force_refresh=True`) or process restart. Documented in docstring. OK for personal-use pattern where model changes are infrequent |
| Token-limit mismatch: selecting a model with smaller context than the current prompt | Out of scope for this task — caller-side concern. Existing token-guard at `routes/message.py` still applies to the selected model's max_tokens |

## Verification

```bash
# Unit tests
cd /Users/trekkie/projects/sentinel-of-mnemosyne
uv run --with pytest --with pytest-asyncio --with httpx --with litellm python -m pytest shared/tests/test_model_selector.py -q

# Sentinel-core tests still pass
cd sentinel-core && uv run pytest tests/ -q

# Pathfinder tests still pass
cd modules/pathfinder && uv run pytest tests/ -q

# Discord subcommand tests still pass (unchanged but should remain green)
uv run --with "discord.py>=2.7.0" --with "pytest>=8" --with "pytest-asyncio>=0.23" --with "httpx>=0.28.1" --with "pyyaml>=6" python -m pytest interfaces/discord/tests/test_subcommands.py -q
```

All four suites must pass.

## Out of Scope

- Per-request model override (caller-supplied task hint to override selection) — not needed for current call sites
- HF Hub API fallback for models not in `litellm.model_cost` — pushes scope to "full hybrid" option; defer to a proper phase
- Model capability caching on disk (cross-restart) — process-lifetime cache is sufficient
- Startup validation ("is the model I picked actually responsive?") — LiteLLM's retry + timeout policy at call time is enough
- Updates to the Discord bot UI to surface which model was picked — can be a follow-up quick task if desired
