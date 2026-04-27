"""Project-specific model resolution — wires pathfinder settings into the selector.

Call sites (extract_npc_fields, update_npc_fields, generate_mj_description) invoke
``await resolve_model("structured" | "fast")`` to get the best loaded model for
their task kind. Discovery and scoring live in ``app.model_selector``; this module
is the thin adapter that reads ``app.config.settings`` and normalises the return
value for LiteLLM's ``provider/model`` naming convention.
"""

from dataclasses import dataclass

from app.config import settings
from app.model_profiles import ModelProfile, get_profile
from app.model_selector import TaskKind, get_loaded_models, select_model

# LM Studio exposes an OpenAI-compatible API, so bare names from /v1/models
# must be prefixed with "openai/" for litellm.acompletion to accept them.
# LiteLLM errors with "LLM Provider NOT provided" when model lacks a provider.
_LITELLM_PROVIDER_PREFIX = "openai/"

# Strip set used by strip_litellm_prefix(): the 3 provider tags that pathfinder
# may see prepended to a discovered model id.
_LITELLM_STRIP_PREFIXES: tuple[str, ...] = ("openai/", "ollama/", "anthropic/")


def strip_litellm_prefix(model_str: str) -> str:
    """Strip leading litellm provider tag, preserving HF-style namespaces."""
    for prefix in _LITELLM_STRIP_PREFIXES:
        if model_str.startswith(prefix):
            return model_str[len(prefix):]
    return model_str


@dataclass(frozen=True)
class ResolvedModel:
    """Bundles the litellm-prefixed model id, its ModelProfile, and the api_base
    override used for that model's calls. Returned by resolve()."""

    model: str
    profile: ModelProfile
    api_base: str | None


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
    if chosen.startswith(_LITELLM_PROVIDER_PREFIX):
        return chosen
    return f"{_LITELLM_PROVIDER_PREFIX}{chosen}"


async def resolve_model_profile(
    task_kind: TaskKind, *, force_refresh: bool = False
) -> ModelProfile:
    """Return the ModelProfile for the best model for task_kind.

    Calls resolve_model() to pick the best loaded model, strips the openai/
    provider prefix, then fetches arch from LM Studio at settings.litellm_api_base.
    Results are cached in model_profiles._profile_cache — no repeated network
    calls per process.
    """
    model_id = await resolve_model(task_kind, force_refresh=force_refresh)
    # Strip openai/ prefix before looking up profile — LM Studio /api/v0/models
    # endpoint uses the bare model name, not the provider-prefixed form.
    bare_id = strip_litellm_prefix(model_id)
    api_base = settings.litellm_api_base or "http://host.docker.internal:1234"
    return await get_profile(bare_id, api_base=api_base, force_refresh=force_refresh)


async def resolve(task_kind: TaskKind, *, force_refresh: bool = False) -> ResolvedModel:
    """Unified entry point — returns model + profile + api_base in one call.

    Internally calls resolve_model() then get_profile() (the same path
    resolve_model_profile takes), then bundles everything into a ResolvedModel
    so callers don't have to await two coroutines + remember the api_base
    convention separately.
    """
    model = await resolve_model(task_kind, force_refresh=force_refresh)
    bare = strip_litellm_prefix(model)
    api_base_for_profile = settings.litellm_api_base or "http://host.docker.internal:1234"
    profile = await get_profile(bare, api_base=api_base_for_profile, force_refresh=force_refresh)
    return ResolvedModel(
        model=model,
        profile=profile,
        api_base=settings.litellm_api_base or None,
    )
