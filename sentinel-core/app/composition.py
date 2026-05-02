"""Compose root for Sentinel Core.

Constructs the application graph from a flat ``AppGraph`` dataclass. Lifespan
delegates wiring here so the construction logic is independently testable.

This module is introduced incrementally:

- Task 1: defines ``AppGraph``.
- Task 2 (this commit): adds ``build_provider_router``.
- Task 5: adds ``build_application``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from app.clients.litellm_provider import LiteLLMProvider
from app.services.model_registry import build_model_registry
from app.services.model_selector import (
    _ORIGINAL_PREFIXES,
    discover_active_model,
    strip_litellm_prefix,
)
from app.services.provider_router import ProviderRouter
from sentinel_shared.model_profiles import get_profile

if TYPE_CHECKING:
    import httpx

    from app.clients.embeddings import Embeddings
    from app.config import Settings
    from app.services.injection_filter import InjectionFilter
    from app.services.message_processing import MessageProcessor
    from app.services.model_registry import ModelInfo
    from app.services.output_scanner import OutputScanner
    from app.vault import Vault


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AppGraph:
    """Frozen application graph constructed by ``build_application``.

    Tests construct fakes via explicit kwargs (W1) and assert on observable
    graph state. Lifespan pins each field onto ``app.state`` for back-compat
    with existing routes/tests (Q4(a)).
    """

    settings: "Settings"
    http_client: "httpx.AsyncClient"
    model_registry: "dict[str, ModelInfo]"
    context_window: int
    lmstudio_stop_sequences: list[str]
    ai_provider: "ProviderRouter"
    ai_provider_name: str
    vault: "Vault"
    embedding_model_loaded: bool
    injection_filter: "InjectionFilter"
    output_scanner: "OutputScanner"
    message_processor: "MessageProcessor"
    module_registry: dict[str, Any]
    embeddings: "Embeddings"
    note_classifier_fn: Callable[[str], Awaitable[Any]]


@dataclass(frozen=True)
class ProviderRouterBundle:
    """Result of :func:`build_provider_router`.

    The bundle exposes everything the lifespan needs to pin onto ``app.state``
    after constructing the provider router: the router itself, the model
    registry it consulted, the active model's context window, the stop
    sequences for that model, and the configured provider name.
    """

    router: ProviderRouter
    model_registry: "dict[str, ModelInfo]"
    context_window: int
    lmstudio_stop_sequences: list[str]
    ai_provider_name: str


async def build_provider_router(
    settings: "Settings", http_client: "httpx.AsyncClient"
) -> ProviderRouterBundle:
    """Construct the ProviderRouter and the metadata pinned alongside it.

    Performs:
      * Model registry build (live fetch + seed fallback).
      * Active-model discovery for the configured provider.
      * Context-window lookup against the registry.
      * Model-profile fetch for stop sequences (LM Studio only).
      * Provider map construction (4 backends route through LiteLLMProvider).
      * Primary + fallback selection per ``settings.ai_provider`` and
        ``settings.ai_fallback_provider``.

    Mirrors the pre-refactor lifespan behavior exactly. Non-fatal where the
    pre-refactor code was non-fatal (model discovery, profile fetch, fallback
    instantiation). The function never raises.
    """
    # Build model registry (live fetch + seed fallback) — non-fatal if providers unavailable
    model_registry = await build_model_registry(settings, http_client)

    # Discover active model for the configured provider (non-fatal)
    lmstudio_model_str = await discover_active_model(settings, http_client)
    # Strip ONLY the litellm provider tag — keep any HF-style namespace inside
    # the bare id (e.g. "qwen/qwen2.5-coder-14b" must round-trip verbatim).
    lmstudio_model_name = strip_litellm_prefix(
        lmstudio_model_str, prefixes=_ORIGINAL_PREFIXES
    )

    # Determine active model id for context window lookup
    active_model = (
        lmstudio_model_name
        if settings.ai_provider == "lmstudio"
        else settings.claude_model
        if settings.ai_provider == "claude"
        else settings.ollama_model
        if settings.ai_provider == "ollama"
        else settings.llamacpp_model
    )
    model_info = model_registry.get(active_model)
    context_window = model_info.context_window if model_info else 4096
    if not model_info:
        logger.warning(
            f"Active model '{active_model}' not found in registry — using 4096 token default"
        )
    else:
        logger.info(f"Context window: {context_window} tokens (model: {active_model})")

    # Fetch model profile for stop sequences — non-fatal; defaults to no stop sequences.
    # Only meaningful for lmstudio provider (local models need explicit stop tokens).
    # Cloud providers (Claude) manage termination via their own chat templates.
    lmstudio_api_base = settings.lmstudio_base_url or "http://host.docker.internal:1234"
    lmstudio_stop_sequences: list[str]
    try:
        profile = await get_profile(
            lmstudio_model_name,
            api_base=lmstudio_api_base,
        )
        lmstudio_stop_sequences = profile.stop_sequences or []
        logger.info(
            "Model stop sequences: %s (arch: %s)",
            profile.stop_sequences,
            profile.arch if hasattr(profile, "arch") else profile.family,
        )
    except Exception as exc:
        logger.warning(
            "Model profile fetch failed for %r — no stop sequences will be sent: %s",
            lmstudio_model_name,
            exc,
        )
        lmstudio_stop_sequences = []

    # All 4 backends route through LiteLLMProvider (RD-02 — eliminate stub providers)
    provider_map = {
        "lmstudio": LiteLLMProvider(
            model_string=lmstudio_model_str,  # discovered, not hardcoded
            api_base=settings.lmstudio_base_url,
            api_key="lmstudio",
        ),
        "ollama": LiteLLMProvider(
            model_string=f"ollama/{settings.ollama_model}",
            api_base=settings.ollama_base_url,
        ),
        "llamacpp": LiteLLMProvider(
            model_string=f"openai/{settings.llamacpp_model}",
            api_base=settings.llamacpp_base_url,
        ),
    }
    if settings.anthropic_api_key:
        provider_map["claude"] = LiteLLMProvider(
            model_string=settings.claude_model,
            api_key=settings.anthropic_api_key,
        )

    lmstudio_provider = provider_map["lmstudio"]
    primary = provider_map.get(settings.ai_provider, lmstudio_provider)
    if primary is None:
        logger.error(
            f"AI_PROVIDER='{settings.ai_provider}' selected but provider could not be instantiated "
            "(likely missing API key). Falling back to LM Studio."
        )
        primary = lmstudio_provider

    # Select fallback provider
    fallback = None
    if settings.ai_fallback_provider == "claude":
        fallback = provider_map.get("claude")
        if fallback is None:
            logger.warning(
                "AI_FALLBACK_PROVIDER=claude but ANTHROPIC_API_KEY not set — no fallback available"
            )

    router = ProviderRouter(primary, fallback_provider=fallback)
    logger.info(
        f"AI provider: {settings.ai_provider} "
        f"(fallback: {settings.ai_fallback_provider})"
    )

    return ProviderRouterBundle(
        router=router,
        model_registry=model_registry,
        context_window=context_window,
        lmstudio_stop_sequences=lmstudio_stop_sequences,
        ai_provider_name=settings.ai_provider,
    )
