"""Project-specific model resolution — wires pathfinder settings into the selector.

Call sites (extract_npc_fields, update_npc_fields, generate_mj_description, ...)
invoke ``await resolve_model("structured" | "fast" | "chat")`` to satisfy their
``model``/``api_base``/``profile`` parameters. Discovery and scoring live in
``app.model_selector``; this module is the thin adapter that reads
``app.config.settings`` and normalises the return value for LiteLLM's
``provider/model`` naming convention.

Phase 42 (D-09, SC-6): every pf2e chat/completion call site now routes through
sentinel-core's ``SentinelCoreClient.complete()``, which resolves provider and
model itself and does not accept a model/api_base override from pf2e — the
value this module returns is discarded at every call site (grep-verified: no
``core_client.complete(...)`` invocation anywhere in this codebase passes
``model=`` or ``api_base=``). This module is kept only because
``app/llm.py``'s migrated functions still accept (unused) ``model``/
``api_base``/``profile`` parameters unchanged from pre-42-04 (42-04's explicit
scoping decision — touching every ``app/routes/*.py`` caller was out of scope
for that plan). It intentionally no longer reads a per-task-kind operator
override or a hardcoded chat-model default from settings — both were removed
from ``app/config.py`` in Phase 42-05 (SC-6: no module hardcodes a chat
endpoint or model id). Discovery still probes ``settings.litellm_api_base``
(retained — Phase 43 embeddings scope) so a real loaded-model id is returned
whenever discovery succeeds.
"""

from dataclasses import dataclass

from app.config import settings
from sentinel_shared.model_profiles import ModelProfile, get_profile
from app.model_selector import TaskKind, get_loaded_models, select_model

# LM Studio exposes an OpenAI-compatible API, so bare names from /v1/models
# must be prefixed with "openai/" for litellm.acompletion to accept them.
# LiteLLM errors with "LLM Provider NOT provided" when model lacks a provider.
_LITELLM_PROVIDER_PREFIX = "openai/"

# Strip set used by strip_litellm_prefix(): the 3 provider tags that pathfinder
# may see prepended to a discovered model id.
_LITELLM_STRIP_PREFIXES: tuple[str, ...] = ("openai/", "ollama/", "anthropic/")

# Fallback used ONLY when model discovery returns nothing loaded (e.g. an
# unreachable backend). NEVER forwarded to a real LLM call — every pf2e chat
# call site routes through SentinelCoreClient.complete(), which has no model
# parameter at all (SC-6, D-09; Phase 42-05 removed the last hardcoded chat
# model default, `litellm_model`, from app/config.py).
_UNUSED_MODEL_PLACEHOLDER = "openai/unused-core-resolves-model"


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
    """Return a model id for ``task_kind`` in LiteLLM-compatible form.

    Discovers loaded models at ``settings.litellm_api_base`` (cached after first
    call per process). Falls back to a clearly-inert placeholder
    (``_UNUSED_MODEL_PLACEHOLDER``) when discovery is empty — see module
    docstring: this value is never forwarded to a real completion call (core
    resolves provider+model itself per D-09). No per-task-kind operator
    override or hardcoded chat-model default is read from settings anymore
    (both removed in Phase 42-05 — SC-6). Always returns a ``provider/model``
    string — prepends ``openai/`` if the selected model name has no provider
    prefix (typical for bare names from LM Studio's ``/v1/models``).
    """
    loaded = await get_loaded_models(settings.litellm_api_base, force_refresh=force_refresh)
    chosen = select_model(task_kind, loaded, default=_UNUSED_MODEL_PLACEHOLDER)
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
