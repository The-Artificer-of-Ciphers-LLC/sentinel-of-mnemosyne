"""Compose root for Sentinel Core.

Constructs the application graph from a flat ``AppGraph`` dataclass. Lifespan
delegates wiring here so the construction logic is independently testable.

This module is introduced incrementally:

- Task 1: defines ``AppGraph``.
- Task 2: adds ``build_provider_router``.
- Task 5 (this commit): adds ``build_application``.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from app.state import RouteContext
from app.vault import VaultUnreachableError

from app.clients.embeddings import DEFAULT_LMSTUDIO_BASE_URL, Embeddings
from app.clients.litellm_provider import LiteLLMProvider
from app.model import (
    DECLARED_DEFAULT_CONTEXT_WINDOW,
    ActiveModel,
    LMStudioModelSource,
    ModelProfile,
    static_model_source,
)
from app.services.injection_filter import InjectionFilter
from app.services.message_processing import MessageProcessor
from app.services.recall import Recall, RecallConfig, RetentionPolicy, SemanticRecall
from app.services.model_registry import build_model_registry
from app.services.model_selector import (
    ensure_litellm_prefix,
    probe_embedding_model_loaded,
)
from app.services.note_classifier import classify_note
from app.services.output_scanner import OutputScanner
from app.services.provider_router import ProviderRouter
from app.services.self_profile import profile_status
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
    from app.services.recall import Recall
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
    recall: "Recall"
    module_registry: dict[str, Any]
    embeddings: "Embeddings"
    note_classifier_fn: Callable[[str], Awaitable[Any]]
    # The Active model seam (ADR-0007). Carried through to RouteContext so the
    # request path can ask "which model is loaded" instead of reading a scalar
    # pinned at startup. Defaulted so test fakes constructed before this field
    # existed keep working.
    active_model: "ActiveModel | None" = None
    # See ProviderRouterBundle.primary_model — the seam the chat path may resolve
    # through, which is ``active_model`` only when LM Studio is the primary.
    primary_model: "ActiveModel | None" = None


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
    # The seam the three scalars above are on their way to being replaced by
    # (ADR-0007 step 4). Present from step 2 so the request path can reach it.
    active_model: "ActiveModel | None" = None
    # The subset of ``active_model`` that describes the PRIMARY provider: the same
    # object when AI_PROVIDER is lmstudio, and None otherwise. ``active_model`` is
    # LM Studio's seam whatever AI_PROVIDER says (SC-3), so the chat path must not
    # resolve through it for a different backend — it would budget against, and
    # name, models from the wrong catalogue.
    primary_model: "ActiveModel | None" = None


async def build_active_model(
    settings: "Settings", http_client: "httpx.AsyncClient"
) -> ActiveModel:
    """Compose the Active model seam over LM Studio (ADR-0007).

    This is LM STUDIO's seam specifically, not the active provider's, for the
    same reason ``discover_lmstudio_model`` was independent of
    ``settings.ai_provider``: the LM Studio entry in ``provider_map`` is
    unconditionally paired with ``settings.lmstudio_base_url`` and must always
    name a model LM Studio actually serves, so LM Studio works as either the
    primary OR the fallback provider (SC-3 bidirectional fallback, D-07).

    ``StaticModelSource`` carries ``settings.model_name`` as the answer for when
    there is no live backend at all — which, per ADR decision 4 as amended, is
    that setting's ONLY remaining role. It is consulted only when the live
    source RAISES; a reachable backend reporting nothing reaches the refusal
    rung instead.

    ``MODEL_AUTO_DISCOVER=false`` keeps its documented meaning: the live source
    is left out entirely and resolution answers from configuration alone.
    """
    sources: list[Any] = []
    if settings.model_auto_discover:
        sources.append(LMStudioModelSource(http_client, settings.lmstudio_base_url))
    else:
        logger.info(
            "MODEL_AUTO_DISCOVER=false — the Active model seam will answer from "
            "configuration (MODEL_NAME=%s) without querying the backend",
            settings.model_name,
        )
    sources.append(await static_model_source(settings, provider="lmstudio"))
    return ActiveModel(sources, settings)


async def _resolve_lmstudio_profile(
    active_model: ActiveModel, settings: "Settings"
) -> ModelProfile:
    """Resolve LM Studio's chat profile, never raising.

    ``build_provider_router`` has always been non-fatal — startup must not fail
    because a backend is unreachable — so a resolution failure degrades to the
    configured name with a loud WARNING. This is composition's startup posture,
    not a resolution rung: the ladder itself still refuses to invent a model,
    and the request path (Plan 02) re-resolves through the same seam and
    surfaces the refusal properly rather than answering with a phantom.
    """
    try:
        return await active_model.for_task("chat")
    except Exception as exc:
        logger.warning(
            "Active model resolution failed at startup (%s: %s) — the LM Studio "
            "provider will be built with MODEL_NAME=%s, which the backend has NOT "
            "confirmed it serves",
            type(exc).__name__,
            exc,
            settings.model_name,
        )
        return ModelProfile(
            model_id=settings.model_name,
            litellm_model=ensure_litellm_prefix(settings.model_name),
            api_base=settings.lmstudio_base_url,
            context_window=DECLARED_DEFAULT_CONTEXT_WINDOW,
            task_kind="chat",
        )


async def build_provider_router(
    settings: "Settings", http_client: "httpx.AsyncClient"
) -> ProviderRouterBundle:
    """Construct the ProviderRouter and the metadata pinned alongside it.

    Performs:
      * Model registry build (live fetch + seed fallback).
      * ONE metadata refresh through the Active model seam, which answers the
        model id, the context window and the stop sequences together.
      * Provider map construction (4 backends route through LiteLLMProvider).
      * Primary + fallback selection per ``settings.ai_provider`` and
        ``settings.ai_fallback_provider``.

    ADR-0007 step 2: this function used to make three independent HTTP fetches
    of its own for those three facts — a ``/v1/models`` discovery call, a
    registry context-window lookup backed by ``/api/v0/models/{id}``, and a
    second ``/api/v0/models/{id}`` fetch for the stop-sequence profile. They are
    now one ``ActiveModel.for_task("chat")``.

    Non-fatal where the pre-refactor code was non-fatal (model resolution,
    profile fetch, fallback instantiation). The function never raises.
    """
    # ONE metadata refresh. Everything below reads the resolved profile —
    # including the registry, which is handed the answer rather than repeating
    # the discovery call and the per-model context fetch itself.
    active_model = await build_active_model(settings, http_client)
    lmstudio_profile = await _resolve_lmstudio_profile(active_model, settings)
    lmstudio_model_name = lmstudio_profile.model_id
    lmstudio_model_str = lmstudio_profile.litellm_model

    # Build model registry (seed + cloud fetch) — non-fatal if providers unavailable
    model_registry = await build_model_registry(
        settings,
        http_client,
        lmstudio_model=lmstudio_model_name,
        lmstudio_context_window=lmstudio_profile.context_window,
    )

    # Table-driven active_model lookup (Pitfall 1 fix) — replaces the ternary
    # chain that silently fell through to llamacpp_model for any unlisted
    # ai_provider. ProviderRouterBundle and these tables are on ADR-0007's
    # deletion list, but that is step 4; deleting them here would drag the
    # RouteContext rewiring into this step and break "green on its own".
    active_model_table = {
        "lmstudio": lmstudio_model_name,
        "claude": settings.claude_model,
        "ollama": settings.ollama_model,
        "llamacpp": settings.llamacpp_model,
    }
    active_model_name = active_model_table.get(settings.ai_provider, settings.ai_provider)

    lmstudio_stop_sequences: list[str]
    if settings.ai_provider == "lmstudio":
        # Both facts come off the one resolved profile.
        context_window = lmstudio_profile.context_window
        lmstudio_stop_sequences = list(lmstudio_profile.stop_sequences)
        logger.info(
            "Context window: %d tokens (model: %s, resolved from %s); stop sequences: %s",
            context_window,
            lmstudio_model_name,
            lmstudio_profile.context_window_source,
            lmstudio_stop_sequences,
        )
    else:
        # Non-LM-Studio providers are not discoverable, so the registry still
        # answers for their context window and the family table (no I/O —
        # api_base=None) answers for their stop sequences.
        model_info = model_registry.get(active_model_name)
        context_window = model_info.context_window if model_info else 4096
        if not model_info:
            logger.warning(
                f"Active model '{active_model_name}' not found in registry — "
                "using 4096 token default"
            )
        else:
            logger.info(
                f"Context window: {context_window} tokens (model: {active_model_name})"
            )
        stop_seq_model_table = {
            "lmstudio": lmstudio_model_name,
            "ollama": settings.ollama_model,
            "llamacpp": settings.llamacpp_model,
        }
        active_profile_model = stop_seq_model_table.get(
            settings.ai_provider, lmstudio_model_name
        )
        try:
            profile = await get_profile(active_profile_model, api_base=None)
            lmstudio_stop_sequences = profile.stop_sequences or []
            logger.info(
                "Model stop sequences: %s (family: %s)",
                profile.stop_sequences,
                profile.family,
            )
        except Exception as exc:
            logger.warning(
                "Model profile lookup failed for %r — no stop sequences will be sent: %s",
                active_profile_model,
                exc,
            )
            lmstudio_stop_sequences = []

    # All backends route through LiteLLMProvider (RD-02 — eliminate stub providers).
    # lmstudio is an openai_compatible entry (D-01/D-02/D-03).
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

    # Select fallback provider — generalized to any configured provider name
    # (D-05), not just claude; "none" means no fallback.
    fallback = None
    if settings.ai_fallback_provider != "none":
        fallback = provider_map.get(settings.ai_fallback_provider)
        if fallback is None:
            logger.warning(
                "AI_FALLBACK_PROVIDER=%r but provider could not be instantiated — "
                "no fallback available",
                settings.ai_fallback_provider,
            )

    # ADR-0007 step 3. `active_model` is LM STUDIO's seam unconditionally (SC-3:
    # provider_map["lmstudio"] must name a model LM Studio serves whatever
    # AI_PROVIDER says). It is therefore handed to the router ONLY when LM Studio
    # is also the primary — giving an ollama primary a seam that answers with LM
    # Studio's catalogue would make the not-served retry re-resolve into a model
    # that backend has never heard of, which is a worse failure than the 404 it
    # is trying to recover from.
    primary_model = active_model if settings.ai_provider == "lmstudio" else None

    # The fallback's OWN seam (ADR decision 8 / Flagged call 12). Config-derived
    # and I/O-free: `StaticModelSource` is the whole source list, so resolving it
    # costs nothing and cannot hand Anthropic LM Studio's base URL.
    fallback_model = None
    if fallback is not None:
        fallback_model = ActiveModel(
            [
                await static_model_source(
                    settings, provider=settings.ai_fallback_provider
                )
            ],
            settings,
        )

    router = ProviderRouter(
        primary,
        fallback_provider=fallback,
        active_model=primary_model,
        fallback_model=fallback_model,
    )
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
        active_model=active_model,
        primary_model=primary_model,
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
    recall: "Recall | None" = None,
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
        active_model = provider_bundle.active_model
        primary_model = provider_bundle.primary_model
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
            active_model = provider_bundle.active_model
            primary_model = provider_bundle.primary_model
        else:
            model_registry = {}
            context_window = 4096
            lmstudio_stop_sequences = []
            ai_provider_name = settings.ai_provider
            active_model = None
            primary_model = None

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

    # Embeddings MUST be constructed before the recall guard so embeddings.embed
    # is available to inject into SemanticRecall (D-12 / wiring constraint).
    if embeddings is None:
        embeddings = Embeddings(
            http_client,
            settings.embedding_base_url or DEFAULT_LMSTUDIO_BASE_URL,
            settings.embedding_model,
            api_key=settings.embedding_api_key or "lm-studio",
        )

    if recall is None:
        # Construct SemanticRecall with the no-prefix active_model (D-12).
        # active_model is settings.embedding_model (no "openai/" prefix) so the
        # exact-string comparison in SemanticRecall matches the embedding_model
        # written by vault_sweeper.py.  Do NOT use embeddings._model — it has
        # the "openai/" prefix and would make every model-match fail.
        _config = RecallConfig()
        _policy = RetentionPolicy(
            hot_limit=settings.retention_hot_limit,
            hot_window_days=settings.retention_hot_window_days,
        )
        _semantic = SemanticRecall(
            vault,
            embed_fn=embeddings.embed,
            active_model=settings.embedding_model,
            config=_config,
        )
        recall = Recall(vault=vault, config=_config, semantic_strategy=_semantic, policy=_policy)

    if message_processor is None:
        message_processor = MessageProcessor(
            vault=vault,
            ai_provider=ai_provider,
            injection_filter=injection_filter,
            output_scanner=output_scanner,
            recall=recall,
            active_model=primary_model,
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
            settings.embedding_base_url,
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
        recall=recall,
        module_registry=module_registry,
        embeddings=embeddings,
        note_classifier_fn=note_classifier_fn,
        active_model=active_model,
        primary_model=primary_model,
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
        recall=graph.recall,
        ai_provider=graph.ai_provider,
        # getattr, not attribute access: several test fakes are SimpleNamespace
        # graphs built before this field existed, and startup must not break on
        # one of them.
        active_model=getattr(graph, "active_model", None),
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

    # D-06: non-blocking startup INDEX REBUILD so a cold start (no prior
    # embedding-index.json) becomes semantically searchable without operator
    # action.  Fires rebuild_embedding_index() — an INDEX-ONLY routine that
    # walks the vault, (re)embeds bodies, and writes ops/sweeps/embedding-index.json
    # WITHOUT ever classifying, relocating, or trashing a note.
    #
    # *** UAT INCIDENT POST-MORTEM ***
    # The original implementation called the FULL destructive run_sweep() here.
    # On first boot, models were not yet loaded, so classifications were degraded,
    # and the sweeper RELOCATED sentinel/persona.md → learning/persona/, crash-looping
    # every subsequent boot at composition.py:424 (persona missing).
    # This is fixed by using rebuild_embedding_index() which can NEVER relocate or
    # trash any vault file — it uses ONLY read/write/list primitives (T-40-13).
    #
    # On-demand rebuild trigger (D-06): the EXISTING admin-gated
    # POST /vault/sweep/start route (note.py) runs run_sweep() via start_sweep()
    # and therefore re-emits the embedding index with a mandatory fail-closed probe.
    # No new unauthenticated surface is introduced (T-40-09).
    from app.services.vault_sweeper import rebuild_embedding_index as _rebuild_embedding_index

    # Phase 45 (NOTE-03 / D-04): non-blocking startup rebuild of the links
    # sidecar (ops/graph/links-index.json), alongside the embedding-index
    # startup rebuild. rebuild_links_index() is INDEX-ONLY — it uses only
    # list_under/read_note/write_note and never relocates or trashes a note —
    # so a cold start becomes graph-queryable (:graph/:stats/:check) without
    # operator action. A failure here is logged and non-fatal, exactly like
    # the embedding-index rebuild.
    from app.services.links_sidecar_index import rebuild_links_index as _rebuild_links_index

    # Both rebuilds acquire the SAME vault sweep lock (ObsidianVault.
    # acquire_sweep_lock), which is serialized by a module-level asyncio.Lock
    # (becb590). Running them as two independent concurrent tasks meant the
    # loser was correctly denied the lock and raised SweepInProgressError —
    # a real functional loss (links-index silently skipped on every cold
    # start), not just a benign race. Fix: run both rebuilds SEQUENTIALLY
    # inside a single background task so each acquires-and-releases the lock
    # in turn and BOTH complete. Each keeps its own try/except so one
    # failing still leaves the other attempted and logged non-fatally.
    async def _startup_rebuild_sequential() -> None:
        try:
            _report = await _rebuild_embedding_index(
                graph.vault,
                graph.embeddings.embed,
                model_loaded=graph.embedding_model_loaded,
            )
            # Reflect the REPORT'S actual status — a "partial" rebuild (the
            # embedder raised mid-run) is a real semantic-recall degradation
            # and must be loud, not folded into the same INFO line a full
            # success gets. Never fatal to startup either way (D-06).
            if _report.status == "partial":
                logger.error(
                    "Startup embedding-index rebuild PARTIAL (%s) — semantic "
                    "recall will be degraded until the next successful rebuild",
                    "; ".join(_report.errors) or "no error detail",
                )
            elif _report.status == "skipped":
                logger.warning(
                    "Startup embedding-index rebuild skipped — embedding "
                    "model not loaded; semantic recall will be degraded "
                    "until the next successful rebuild"
                )
            else:
                logger.info("Startup embedding-index rebuild complete")
        except Exception as exc:
            logger.warning(
                "Startup embedding-index rebuild failed (non-fatal): %r", exc
            )

        try:
            await _rebuild_links_index(graph.vault)
            logger.info("Startup links-index rebuild complete")
        except Exception as exc:
            logger.warning(
                "Startup links-index rebuild failed (non-fatal): %r", exc
            )

    # WR-02: keep a strong reference to the task so it can't be GC-collected
    # before completion. Store on app.state and register a done-callback that
    # discards the reference once the task finishes. Both
    # startup_rebuild_task and startup_links_rebuild_task are retained (no
    # other code in the tree reads these attributes independently — grepped
    # sentinel-core/ — so both intentionally point at the SAME task now that
    # the two rebuilds share one sequential background task).
    _rebuild_task = asyncio.create_task(_startup_rebuild_sequential())
    app.state.startup_rebuild_task = _rebuild_task
    app.state.startup_links_rebuild_task = _rebuild_task

    def _clear_startup_rebuild_task(_task: asyncio.Task) -> None:
        app.state.startup_rebuild_task = None
        app.state.startup_links_rebuild_task = None

    _rebuild_task.add_done_callback(_clear_startup_rebuild_task)

    # Onboarding (GH #38): non-blocking startup self-profile completeness
    # check. Fires _startup_profile_check() in its own background task —
    # same posture as the index rebuilds above: never awaited inline (so it
    # cannot block boot), and internally wrapped so a vault failure can never
    # escape into startup. It does not need the vault sweep lock (read-only,
    # no write/relocate/trash), so it is scheduled independently rather than
    # folded into _startup_rebuild_sequential.
    _profile_check_task = asyncio.create_task(_startup_profile_check(graph.vault))
    app.state.startup_profile_check_task = _profile_check_task

    def _clear_startup_profile_check_task(_task: asyncio.Task) -> None:
        app.state.startup_profile_check_task = None

    _profile_check_task.add_done_callback(_clear_startup_profile_check_task)

    return StartupResult(graph=graph, warnings=warnings)


async def _startup_profile_check(vault: "Vault") -> None:
    """Log the self-profile completeness state at startup.

    WARNING when incomplete (names the unfilled paths), INFO when complete.
    Never raises: a ``profile_status`` failure (vault error) is caught and
    logged non-fatally — identical posture to the embedding-index /
    links-index startup rebuilds, which must never block or fail boot.
    """
    try:
        status = await profile_status(vault)
    except Exception as exc:
        logger.warning("Startup self-profile check failed (non-fatal): %r", exc)
        return

    total = len(status.paths)
    if status.complete:
        logger.info("Self-profile complete (%d/%d files filled)", total, total)
    else:
        n_unfilled = len(status.unfilled)
        logger.warning(
            "Self-profile incomplete: %d of %d files are unfilled stubs (%s) — "
            "the Sentinel has no personal context; run onboarding.",
            n_unfilled,
            total,
            ", ".join(status.unfilled),
        )
