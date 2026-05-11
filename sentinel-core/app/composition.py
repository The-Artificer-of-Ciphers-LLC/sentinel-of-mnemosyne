"""Compose root for Sentinel Core.

Constructs the application graph from a flat ``AppGraph`` dataclass. Lifespan
delegates wiring here so the construction logic is independently testable.

This module is introduced incrementally:

- Task 1: defines ``AppGraph``.
- Task 2: adds ``build_provider_router``.
- Task 5 (this commit): adds ``build_application``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from app.state import RouteContext
from app.vault import VaultUnreachableError

from app.clients.embeddings import DEFAULT_LMSTUDIO_BASE_URL, Embeddings
from app.clients.litellm_provider import LiteLLMProvider
from app.services.injection_filter import InjectionFilter
from app.services.message_processing import MessageProcessor
from app.services.model_registry import build_model_registry
from app.services.model_selector import (
    _ORIGINAL_PREFIXES,
    discover_active_model,
    probe_embedding_model_loaded,
    strip_litellm_prefix,
)
from app.services.note_classifier import classify_note
from app.services.output_scanner import OutputScanner
from app.services.provider_router import ProviderRouter
from app.vault import ObsidianVault
from sentinel_shared.model_profiles import get_profile

if TYPE_CHECKING:
    import httpx

    from fastapi import FastAPI

    from app.clients.embeddings import Embeddings
    from app.config import Settings
    from app.services.injection_filter import InjectionFilter
    from app.services.message_processing import MessageProcessor
    from app.services.model_registry import ModelInfo
    from app.services.output_scanner import OutputScanner
    from app.vault import Vault


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StartupResult:
    """Result of startup initialization.

    warnings contains non-fatal startup degradations to surface in logs.
    """

    graph: "AppGraph"
    warnings: list[str]


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


async def build_application(
    settings: "Settings",
    http_client: "httpx.AsyncClient",
    *,
    vault: "Vault | None" = None,
    ai_provider: "ProviderRouter | None" = None,
    provider_bundle: "ProviderRouterBundle | None" = None,
    injection_filter: "InjectionFilter | None" = None,
    output_scanner: "OutputScanner | None" = None,
    embeddings: "Embeddings | None" = None,
    message_processor: "MessageProcessor | None" = None,
    module_registry: "dict[str, Any] | None" = None,
    note_classifier_fn: "Callable[[str], Awaitable[Any]] | None" = None,
    embedding_model_loaded: bool | None = None,
) -> AppGraph:
    """Build the full application graph.

    For each keyword-only dependency: if ``None`` (default), construct the
    production implementation; otherwise use the supplied fake. This is the
    test seam — call sites pass explicit kwargs (e.g.
    ``build_application(settings, http_client, vault=FakeVault())``).

    The signature intentionally avoids a ``**fakes`` bag so that typos like
    ``build_application(..., vualt=...)`` are caught at type-check / runtime
    rather than silently swallowed (W1).

    Note: the persona probe is NOT performed here. ADR-0001 startup contract
    (vault-up + 404 → RuntimeError; vault-unreachable → graceful degrade) is
    a startup-failure decision and stays in lifespan(); ``build_application``
    only constructs the graph.
    """
    # Provider router — supplied bundle wins; explicit ai_provider override is
    # honored (no metadata in that path); otherwise build from scratch.
    if provider_bundle is None and ai_provider is None:
        provider_bundle = await build_provider_router(settings, http_client)
    if ai_provider is None:
        assert provider_bundle is not None  # narrowed for type-checkers
        ai_provider = provider_bundle.router
        model_registry = provider_bundle.model_registry
        context_window = provider_bundle.context_window
        lmstudio_stop_sequences = provider_bundle.lmstudio_stop_sequences
        ai_provider_name = provider_bundle.ai_provider_name
    else:
        # Caller supplied an ai_provider directly (test fake) — derive
        # registry/context/stop_sequences from the supplied bundle if any,
        # otherwise fall back to empty/default values that match the
        # pre-refactor non-fatal posture.
        if provider_bundle is not None:
            model_registry = provider_bundle.model_registry
            context_window = provider_bundle.context_window
            lmstudio_stop_sequences = provider_bundle.lmstudio_stop_sequences
            ai_provider_name = provider_bundle.ai_provider_name
        else:
            model_registry = {}
            context_window = 4096
            lmstudio_stop_sequences = []
            ai_provider_name = settings.ai_provider

    if vault is None:
        vault = ObsidianVault(
            http_client,
            settings.obsidian_api_url,
            settings.obsidian_api_key,
        )

    if injection_filter is None:
        injection_filter = InjectionFilter()

    if output_scanner is None:
        output_scanner = OutputScanner(ai_provider=ai_provider)

    if message_processor is None:
        message_processor = MessageProcessor(
            vault=vault,
            ai_provider=ai_provider,
            injection_filter=injection_filter,
            output_scanner=output_scanner,
        )

    if embeddings is None:
        embeddings = Embeddings(
            http_client,
            settings.lmstudio_base_url or DEFAULT_LMSTUDIO_BASE_URL,
            settings.embedding_model,
            api_key=settings.lmstudio_api_key or "lm-studio",
        )

    if module_registry is None:
        module_registry = {}

    if note_classifier_fn is None:
        note_classifier_fn = classify_note

    if embedding_model_loaded is None:
        # Graceful degrade — never raises. Surfaces via /health and via WARNING
        # log so operators see the problem at boot rather than via opaque
        # BadRequestError when the vault sweeper / note classifier first runs.
        embedding_model_loaded = await probe_embedding_model_loaded(
            http_client,
            settings.lmstudio_base_url,
            settings.embedding_model,
        )
        if embedding_model_loaded:
            logger.info("Embedding model `%s` loaded ✓", settings.embedding_model)
        else:
            logger.warning(
                "Embedding model `%s` NOT loaded on LM Studio — vault sweeper / "
                "note classifier will fail until you `lms load %s`.",
                settings.embedding_model,
                settings.embedding_model,
            )

    return AppGraph(
        settings=settings,
        http_client=http_client,
        model_registry=model_registry,
        context_window=context_window,
        lmstudio_stop_sequences=lmstudio_stop_sequences,
        ai_provider=ai_provider,
        ai_provider_name=ai_provider_name,
        vault=vault,
        embedding_model_loaded=embedding_model_loaded,
        injection_filter=injection_filter,
        output_scanner=output_scanner,
        message_processor=message_processor,
        module_registry=module_registry,
        embeddings=embeddings,
        note_classifier_fn=note_classifier_fn,
    )


async def initialize_startup(
    app: "FastAPI", settings: "Settings", http_client: "httpx.AsyncClient"
) -> StartupResult:
    """Build graph, pin runtime state, and enforce startup policy."""
    graph = await build_application(settings, http_client)

    app.state.route_ctx = RouteContext(
        vault=graph.vault,
        processor=graph.message_processor,
        settings=graph.settings,
        http_client=graph.http_client,
        context_window=graph.context_window,
        lmstudio_stop_sequences=graph.lmstudio_stop_sequences,
        classify=graph.note_classifier_fn,
        embedder=graph.embeddings.embed,
        module_registry=graph.module_registry,
        ai_provider_name=graph.ai_provider_name,
    )
    app.state.settings = graph.settings
    app.state.vault = graph.vault

    warnings: list[str] = []
    try:
        persona = await graph.vault.read_persona()
    except VaultUnreachableError as exc:
        warnings.append(
            "Obsidian REST API unavailable at startup — memory features degraded. "
            "Ensure Obsidian is running with Local REST API plugin enabled "
            f"(HTTP mode port 27123). {exc}"
        )
    else:
        if persona is None:
            raise RuntimeError(
                "sentinel/persona.md missing from Vault — operator setup required (see README)"
            )
        logger.info("Persona loaded from vault (%d chars)", len(persona))

    return StartupResult(graph=graph, warnings=warnings)
