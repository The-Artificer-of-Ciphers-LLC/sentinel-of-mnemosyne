"""Project-specific model resolution — wires pathfinder settings into the selector.

Call sites (extract_npc_fields, update_npc_fields, generate_mj_description) invoke
``await resolve_model("structured" | "fast")`` to get the best loaded model for
their task kind. Discovery and scoring live in ``app.model_selector``; this module
is the thin adapter that reads ``app.config.settings``.
"""
from app.config import settings
from app.model_selector import TaskKind, get_loaded_models, select_model


async def resolve_model(task_kind: TaskKind, *, force_refresh: bool = False) -> str:
    """Return the best model id for ``task_kind``.

    Discovers loaded models at ``settings.litellm_api_base`` (cached after first
    call per process), honors the ``LITELLM_MODEL_{CHAT,STRUCTURED,FAST}`` env
    overrides, and falls back to ``settings.litellm_model`` if no scored match.
    """
    loaded = await get_loaded_models(settings.litellm_api_base, force_refresh=force_refresh)
    preferences = {
        "chat": settings.litellm_model_chat,
        "structured": settings.litellm_model_structured,
        "fast": settings.litellm_model_fast,
    }
    return select_model(
        task_kind,
        loaded,
        preferences=preferences,
        default=settings.litellm_model,
    )
