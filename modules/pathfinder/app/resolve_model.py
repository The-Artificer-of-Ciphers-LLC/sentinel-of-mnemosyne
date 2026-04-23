"""Project-specific model resolution — wires pathfinder settings into the selector.

Call sites (extract_npc_fields, update_npc_fields, generate_mj_description) invoke
``await resolve_model("structured" | "fast")`` to get the best loaded model for
their task kind. Discovery and scoring live in ``app.model_selector``; this module
is the thin adapter that reads ``app.config.settings`` and normalises the return
value for LiteLLM's ``provider/model`` naming convention.
"""
from app.config import settings
from app.model_selector import TaskKind, get_loaded_models, select_model

# LM Studio exposes an OpenAI-compatible API, so bare names from /v1/models
# must be prefixed with "openai/" for litellm.acompletion to accept them.
# LiteLLM errors with "LLM Provider NOT provided" when model lacks a provider.
_LITELLM_PROVIDER_PREFIX = "openai/"


async def resolve_model(task_kind: TaskKind, *, force_refresh: bool = False) -> str:
    """Return the best model id for ``task_kind`` in LiteLLM-compatible form.

    Discovers loaded models at ``settings.litellm_api_base`` (cached after first
    call per process), honors the ``LITELLM_MODEL_{CHAT,STRUCTURED,FAST}`` env
    overrides, and falls back to ``settings.litellm_model`` if no scored match.
    Always returns a ``provider/model`` string — prepends ``openai/`` if the
    selected model name has no provider prefix (typical for bare names from
    LM Studio's ``/v1/models``).
    """
    loaded = await get_loaded_models(settings.litellm_api_base, force_refresh=force_refresh)
    preferences = {
        "chat": settings.litellm_model_chat,
        "structured": settings.litellm_model_structured,
        "fast": settings.litellm_model_fast,
    }
    chosen = select_model(
        task_kind,
        loaded,
        preferences=preferences,
        default=settings.litellm_model,
    )
    if "/" in chosen:
        return chosen
    return f"{_LITELLM_PROVIDER_PREFIX}{chosen}"
