"""Registry-aware model selection for LM Studio-backed LiteLLM calls.

Queries LM Studio's OpenAI-compatible `/v1/models` endpoint to discover loaded
models, then ranks each against a per-task-kind rubric using `litellm.get_model_info`
capability metadata (`max_tokens`, `supports_function_calling`). Returns the best
match or falls through to env-var preferences and a legacy default.

Three task kinds map to the three LLM usage patterns in the codebase:

- ``chat``       — conversational message responses (needs large context,
                   function calling optional but preferred)
- ``structured`` — reliable JSON extraction (needs function calling; moderate
                   context is fine)
- ``fast``       — short constrained generations like MJ prompts (needs small
                   model with at least 4K context)

Cache: a process-level cache stores the discovered list per api_base. Refresh
with ``force_refresh=True`` or restart the process.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Literal, Mapping, Sequence

import httpx
import litellm

logger = logging.getLogger(__name__)

TaskKind = Literal["chat", "structured", "fast"]

_model_cache: dict[str, list[str]] = {}
_cache_lock = asyncio.Lock()


class ModelSelectorError(RuntimeError):
    """Raised when no model can be resolved: empty discovery AND no default."""


async def get_loaded_models(api_base: str, *, force_refresh: bool = False) -> list[str]:
    """Query ``{api_base}/models`` and return the list of loaded model IDs.

    Results are cached per api_base. Network errors return an empty list so
    callers can fall through to the default; the error is logged.
    """
    async with _cache_lock:
        if not force_refresh and api_base in _model_cache:
            return list(_model_cache[api_base])

        url = f"{api_base.rstrip('/')}/models"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("Model discovery failed for %s: %s", url, exc)
            return []

        models: list[str] = []
        for entry in data.get("data", []):
            model_id = entry.get("id") if isinstance(entry, dict) else None
            if isinstance(model_id, str) and model_id:
                models.append(model_id)

        _model_cache[api_base] = models
        logger.info("Discovered %d loaded model(s) at %s", len(models), url)
        return list(models)


def select_model(
    task_kind: TaskKind,
    loaded: Sequence[str],
    *,
    preferences: Mapping[str, str | None] | None = None,
    default: str | None = None,
) -> str:
    """Pick the best loaded model for ``task_kind``.

    Resolution order:

    1. ``preferences[task_kind]`` if set AND that model is in ``loaded`` — honor user intent first.
    2. Highest-scoring loaded model per the task-kind rubric (see module docstring).
    3. ``default`` if set AND present in ``loaded``.
    4. First entry in ``loaded`` if non-empty — best-effort last resort.
    5. ``default`` if set (even if not loaded — LiteLLM may accept the name anyway).
    6. Raise ``ModelSelectorError``.
    """
    prefs = dict(preferences or {})
    preferred = prefs.get(task_kind)
    if preferred and preferred in loaded:
        return preferred

    if loaded:
        scored: list[tuple[int, str]] = []
        for model_id in loaded:
            score = _score(task_kind, model_id)
            if score > 0:
                scored.append((score, model_id))
        if scored:
            scored.sort(reverse=True)
            return scored[0][1]

        if default and default in loaded:
            return default
        return loaded[0]

    if default:
        return default

    raise ModelSelectorError(
        f"No loaded models at LM Studio and no default configured (task_kind={task_kind})"
    )


def _score(task_kind: str, model_id: str) -> int:
    """Score a model_id for a task_kind. Returns 0 for unknown or ineligible models."""
    try:
        info = litellm.get_model_info(model=model_id)
    except Exception:
        return 0
    max_tokens = int(info.get("max_tokens") or info.get("max_input_tokens") or 0)
    try:
        supports_fc = bool(litellm.supports_function_calling(model=model_id))
    except Exception:
        supports_fc = bool(info.get("supports_function_calling", False))

    if task_kind == "chat":
        return max_tokens + (10_000 if supports_fc else 0)
    if task_kind == "structured":
        if not supports_fc:
            return 0
        return 10_000 - abs(max_tokens - 8_000)
    if task_kind == "fast":
        if max_tokens < 4_000:
            return 0
        return 100_000 - max_tokens
    return 0


def _reset_cache_for_tests() -> None:
    """Test-only helper to clear the module-level cache between test cases."""
    _model_cache.clear()
