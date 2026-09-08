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
from types import SimpleNamespace
from typing import TYPE_CHECKING, Literal, Mapping, Sequence

from app.clients.litellm_provider import get_model_capabilities_from_lmstudio
from app.errors import ModelSelectorError

import httpx
import litellm

if TYPE_CHECKING:
    from app.config import Settings
    from app.model import ActiveModel

logger = logging.getLogger(__name__)

TaskKind = Literal["chat", "structured", "fast"]

_model_cache: dict[str, list[str]] = {}
_cache_lock = asyncio.Lock()

# LiteLLM provider prefixes recognised by litellm.acompletion(). A model id that
# already begins with one of these is left untouched; anything else (including
# HuggingFace-style namespaces such as ``qwen/qwen2.5-coder-14b``) MUST be
# prefixed with the active provider's tag, otherwise litellm raises
# "LLM Provider NOT provided" with a 400/BadRequest.
_LITELLM_PROVIDER_PREFIXES: tuple[str, ...] = (
    "openai/",
    "ollama/",
    "anthropic/",
    "azure/",
    "bedrock/",
    "cohere/",
    "gemini/",
    "groq/",
    "huggingface/",
    "mistral/",
    "perplexity/",
    "replicate/",
    "together_ai/",
    "vertex_ai/",
)

# Pre-refactor strip set (preserved verbatim). Historically only the original 3
# litellm provider tags were stripped by main.py and model_registry.py — they
# pass `prefixes=_ORIGINAL_PREFIXES` to keep behavior identical to pre-refactor
# code. Canonical home for this tuple is here, alongside _LITELLM_PROVIDER_PREFIXES.
_ORIGINAL_PREFIXES: tuple[str, ...] = ("openai/", "ollama/", "anthropic/")


def strip_litellm_prefix(
    model_str: str,
    *,
    prefixes: tuple[str, ...] = _LITELLM_PROVIDER_PREFIXES,
) -> str:
    """Strip a leading litellm provider tag from model_str.

    Preserves HuggingFace-style namespaces (e.g. "qwen/qwen2.5-coder-14b")
    inside the bare id — naive split("/", 1)[-1] would mangle them.

    The `prefixes` parameter lets callers preserve the exact strip set their
    pre-refactor code used (e.g. main.py and model_registry.py only stripped
    the original 3 — they pass `prefixes=_ORIGINAL_PREFIXES`).
    """
    for prefix in prefixes:
        if model_str.startswith(prefix):
            return model_str[len(prefix):]
    return model_str


def ensure_litellm_prefix(model_str: str, default_provider: str = "openai/") -> str:
    """Return model_str with a litellm provider tag, prepending default_provider if missing."""
    if model_str.startswith(_LITELLM_PROVIDER_PREFIXES):
        return model_str
    return f"{default_provider}{model_str}"



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
    live_capabilities: Mapping[str, dict] | None = None,
) -> str:
    """Pick the best loaded model for ``task_kind``.

    Resolution order:

    1. ``preferences[task_kind]`` if set AND that model is in ``loaded`` — honor user intent first.
    2. Highest-scoring loaded model per the task-kind rubric (see module docstring).
    3. ``default`` if set AND present in ``loaded``.
    4. The SOLE entry in ``loaded`` when ``len(loaded) == 1`` — unambiguous: with exactly
       one candidate there is nothing to guess between.
    5. ``default`` if set (even if not present in ``loaded`` — LiteLLM may accept the name
       anyway, and an explicitly operator-configured model is always a safer bet than
       guessing among an ambiguous multi-entry list).
    6. Raise ``ModelSelectorError``.

    NOTE (exo-model-notfound-502): rule 4 used to be an unconditional "first entry in
    ``loaded``" best-effort fallback. That is unsound for providers like exo whose
    ``/v1/models`` advertises every model it *could* serve (100+ entries) rather than
    the one it is *actually* serving — silently picking ``loaded[0]`` there returns an
    essentially random, usually-unserveable model id and the downstream call 404s.
    Now, when there is genuine ambiguity (0 or 2+ unscored/unmatched candidates), this
    function prefers the explicitly configured ``default`` over guessing, and raises
    rather than silently returning an arbitrary catalog entry when no default exists.

    live_capabilities: optional ``{model_id: {"max_tokens": int,
        "supports_function_calling": bool}}`` sourced from a live LM Studio
        capability fetch (see ``_fetch_live_capabilities``). Threaded straight
        into ``_score`` — see its docstring for why this is required for local
        (LM Studio) model ids, which litellm's static cloud registry has no
        entry for. ``None`` (the default) preserves the original
        litellm-only scoring behavior for every existing sync caller.
    """
    prefs = dict(preferences or {})
    preferred = prefs.get(task_kind)
    if preferred and preferred in loaded:
        return preferred

    if loaded:
        scored: list[tuple[int, str]] = []
        for model_id in loaded:
            if live_capabilities is not None:
                score = _score(task_kind, model_id, live_capabilities)
            else:
                # Preserve the original 2-arg call shape when no live capability
                # data was fetched — keeps every existing sync caller (and any
                # test that patches `_score` with the pre-existing 2-arg
                # signature) working unchanged.
                score = _score(task_kind, model_id)
            if score > 0:
                scored.append((score, model_id))
        if scored:
            scored.sort(reverse=True)
            return scored[0][1]

        if default and default in loaded:
            return default

        if len(loaded) == 1:
            # Exactly one candidate — no ambiguity, regardless of whether it matches
            # configured preferences/default. Safe even for exo-style providers,
            # because a single-entry list can't be confused with an unserveable sibling.
            return loaded[0]

    if default:
        return default

    raise ModelSelectorError(
        f"No scored/matched model for task_kind={task_kind} among {len(loaded)} "
        "loaded/catalog entries, and no default configured. Refusing to guess an "
        "arbitrary catalog entry (exo-model-notfound-502)."
    )


def _score(
    task_kind: str,
    model_id: str,
    live_capabilities: Mapping[str, dict] | None = None,
) -> int:
    """Score a model_id for a task_kind. Returns 0 for unknown or ineligible models.

    litellm.get_model_info()/supports_function_calling() query a STATIC CLOUD
    registry that has no entry for LM Studio-style local model ids (e.g.
    "google/gemma-4-31b") — every local model previously scored 0 for every
    task_kind, which made ``probe_classifier_model_ready`` permanently report
    "not ready" on local-only deployments and silently disabled destructive
    vault sweeps (fix-score-local-model-capabilities).

    ``live_capabilities``, when supplied, is an already-fetched
    ``{model_id: {"max_tokens": int, "supports_function_calling": bool}}``
    mapping (see ``_fetch_live_capabilities`` / ``get_model_capabilities_from_lmstudio``)
    sourced from LM Studio's own ``/api/v0/models/{id}`` endpoint, which DOES
    know about local models. When ``model_id`` is present in this mapping, it
    is used INSTEAD of the litellm lookup. Cloud models (absent from
    ``live_capabilities``) fall through to the original litellm-only path
    unchanged.
    """
    is_live = bool(live_capabilities and model_id in live_capabilities)
    if is_live:
        info = live_capabilities[model_id]  # type: ignore[index]
        max_tokens = int(info.get("max_tokens") or 0)
        supports_fc = bool(info.get("supports_function_calling", False))
    else:
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
        score = 10_000 - abs(max_tokens - 8_000)
        if is_live:
            # LM Studio's max_context_length/loaded_context_length is a
            # context-WINDOW size (often tens/hundreds of thousands of
            # tokens for modern local models — e.g. 262144). litellm's
            # `max_tokens` is an output-cap-style figure (typically low
            # thousands) that this "moderate context preferred" heuristic
            # was tuned against. Plugging a raw local context-window number
            # into the same formula unchanged can swing deeply negative
            # (e.g. 10_000 - abs(262_144 - 8_000) = -244_144), which would
            # make select_model's `score > 0` eligibility gate DISQUALIFY a
            # genuinely function-calling-capable local model outright — the
            # exact defect this fix addresses. Floor at a small positive
            # score instead: the model still ranks behind a more "moderate"
            # one among multiple live candidates, but a supports_fc=True
            # local model is never entirely excluded from candidacy purely
            # because of its context-window scale. Cloud models (is_live is
            # False) are NEVER floored here — they keep scoring exactly as
            # before via litellm (fix-score-local-model-capabilities).
            score = max(1, score)
        return score
    if task_kind == "fast":
        if max_tokens < 4_000:
            return 0
        score = 100_000 - max_tokens
        if is_live:
            # Same context-window-vs-output-cap scale mismatch as above —
            # floor so a large-context local model isn't disqualified
            # outright from "fast" eligibility, only ranked lower.
            score = max(1, score)
        return score
    return 0


async def _fetch_live_capabilities(
    http_client: httpx.AsyncClient,
    lmstudio_base_url: str,
    model_ids: Sequence[str],
) -> dict[str, dict]:
    """Fetch live capability data for each of ``model_ids`` from LM Studio.

    One HTTP call per model_id against ``/api/v0/models/{id}`` (via
    ``get_model_capabilities_from_lmstudio``), issued concurrently. A model_id
    whose fetch fails (unreachable LM Studio, model absent/404, unexpected
    schema, or the model isn't reported ``state: "loaded"``) is simply OMITTED
    from the returned mapping — ``_score`` treats a missing entry as "no live
    data available" and falls back to the litellm static-registry path (which
    itself fails closed, returning 0, for unknown local ids). Never raises.
    """
    live_capabilities: dict[str, dict] = {}
    if not model_ids:
        return live_capabilities

    fetched = await asyncio.gather(
        *(
            get_model_capabilities_from_lmstudio(http_client, lmstudio_base_url, model_id)
            for model_id in model_ids
        ),
        return_exceptions=True,
    )
    for model_id, info in zip(model_ids, fetched):
        if isinstance(info, dict):
            live_capabilities[model_id] = info
    return live_capabilities


def _reset_cache_for_tests() -> None:
    """Test-only helper to clear the module-level cache between test cases."""
    _model_cache.clear()


async def discover_active_model(
    settings: "Settings",
    http_client: httpx.AsyncClient,
) -> str:
    """
    Returns a LiteLLM-compatible model string (e.g. "openai/Qwen2.5-14B-Instruct").
    Falls back to _prefixed(settings.model_name) on any failure.
    Never raises — startup must not fail due to discovery issues.

    Resolves the ACTIVE provider's own model (i.e. whichever backend
    ``settings.ai_provider`` currently names). Callers that need a SPECIFIC
    backend's model regardless of which provider is active (e.g. building a
    fallback provider_map entry) must use a dedicated discovery function
    instead, such as ``discover_lmstudio_model`` — see its docstring for the
    bidirectional-fallback rationale (SC-3).
    """
    # Resolve base URL for the active provider — table-driven (Pitfall 2 fix).
    # An unrecognized ai_provider logs a WARNING rather than silently
    # defaulting to lmstudio_base_url (which could be a real, unrelated LM
    # Studio instance — querying it would silently discover the wrong
    # backend's loaded model).
    provider_base_urls = {
        "lmstudio": settings.lmstudio_base_url,
        "ollama": settings.ollama_base_url,
        "llamacpp": settings.llamacpp_base_url,
    }
    if settings.ai_provider in provider_base_urls:
        base_url = provider_base_urls[settings.ai_provider]
    else:
        logger.warning(
            "Unknown AI_PROVIDER=%r for model discovery base_url resolution — "
            "defaulting to lmstudio_base_url (%s); this may query the wrong backend",
            settings.ai_provider,
            settings.lmstudio_base_url,
        )
        base_url = settings.lmstudio_base_url

    return await _discover_model_for_provider(
        settings, http_client, provider=settings.ai_provider, base_url=base_url
    )


async def discover_lmstudio_model(
    settings: "Settings",
    http_client: httpx.AsyncClient,
) -> str:
    """Discover LM Studio's OWN active model — independent of settings.ai_provider.

    ``discover_active_model`` is ai_provider-aware: it queries whichever
    backend is currently active. That is correct for resolving whichever
    provider is currently ACTIVE, but it is WRONG for building the LM Studio
    entry in composition.py's ``provider_map`` — that entry is unconditionally
    paired with ``settings.lmstudio_base_url`` and must therefore always hold
    LM STUDIO's own loaded model, so LM Studio works correctly as either the
    primary OR the fallback provider (SC-3 bidirectional fallback).

    This discovery call is unconditionally independent of
    ``settings.ai_provider`` (D-07) so a fallback to LM Studio always
    requests a model LM Studio actually serves, regardless of which provider
    is primary.

    Never raises — mirrors discover_active_model's non-fatal contract.
    """
    return await _discover_model_for_provider(
        settings, http_client, provider="lmstudio", base_url=settings.lmstudio_base_url
    )


async def _discover_model_for_provider(
    settings: "Settings",
    http_client: httpx.AsyncClient,
    *,
    provider: str,
    base_url: str,
) -> str:
    """Shared discovery + selection + prefixing pipeline.

    ``provider`` decides the litellm prefix (only "ollama" gets "ollama/";
    every other provider — including lmstudio — gets "openai/", matching
    pre-refactor behavior) via the generic OpenAI-compatible GET /models
    fetch. ``base_url`` is the already-resolved endpoint to query.

    Extracted from ``discover_active_model`` so the active-provider-selection
    path (``discover_active_model``) and the LM-Studio-specific fallback-entry
    path (``discover_lmstudio_model``) share one implementation instead of two
    divergent copies. Never raises.
    """
    def _prefixed(name: str) -> str:
        # Already provider-prefixed for LiteLLM — leave untouched.
        # NOTE: a bare slash in the name (e.g. "qwen/qwen2.5-coder-14b") is a
        # HuggingFace-style namespace, NOT a litellm provider tag. Returning it
        # unchanged would cause litellm.BadRequestError("LLM Provider NOT provided").
        if name.startswith(_LITELLM_PROVIDER_PREFIXES):
            return name
        if provider == "ollama":
            return f"ollama/{name}"
        return f"openai/{name}"

    if not settings.model_auto_discover:
        return _prefixed(settings.model_name)

    url = base_url.rstrip("/")
    try:
        resp = await http_client.get(f"{url}/models", timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        loaded = [e["id"] for e in data.get("data", []) if isinstance(e.get("id"), str)]
    except Exception as exc:
        logger.warning("Model discovery failed: %s — using MODEL_NAME=%s", exc, settings.model_name)
        return _prefixed(settings.model_name)

    if not loaded:
        logger.warning("No models loaded at %s — using MODEL_NAME=%s", url, settings.model_name)
        return _prefixed(settings.model_name)

    preferences = {}
    preferred = settings.model_preferred or settings.model_name
    if preferred:
        # MODEL_PREFERRED pins the model for ALL task kinds, not just chat.
        # Operators set this when they want one specific model for everything
        # (e.g. avoiding TTL-unloads of multiple models or pinning to a known-
        # working model after a problem with auto-selection).
        preferences["chat"] = preferred
        preferences["structured"] = preferred
        preferences["fast"] = preferred

    try:
        chosen = select_model("chat", loaded, preferences=preferences, default=settings.model_name)
    except ModelSelectorError:
        # select_model only raises when `default` (settings.model_name) is falsy AND the
        # loaded/catalog set is ambiguous (0 or 2+ unscored/unmatched entries) — i.e. there
        # is no safe candidate at all. Falling back to `loaded[0]` here would reintroduce
        # exactly the unsound "guess a catalog entry" behavior select_model just refused to
        # do (exo-model-notfound-502); honor the documented contract above instead
        # ("Falls back to _prefixed(settings.model_name) on any failure").
        logger.warning(
            "select_model found no safe candidate among %d loaded/catalog entries and no "
            "default configured — falling back to MODEL_NAME=%s (may not be loaded)",
            len(loaded),
            settings.model_name,
        )
        chosen = settings.model_name

    logger.info("Auto-selected model: %s", chosen)
    return _prefixed(chosen)


async def probe_classifier_model_ready(
    http_client: httpx.AsyncClient,
    lmstudio_base_url: str,
    *,
    model_name: str,
    model_preferred: str | None = None,
    active_model: "ActiveModel | None" = None,
) -> bool:
    """Return True iff the model the structured path would use CAN do structured work.

    This gates whether a DESTRUCTIVE vault sweep may run
    (``routes/note.py`` re-evaluates it immediately before each destructive
    move, not once per run), so every failure mode here answers "not ready".

    ADR-0007 rewired it onto the Active model seam. The question it asks is now
    "does the profile ``ActiveModel`` would hand the structured path actually
    carry the ``tool_use`` capability?" — read straight off the backend rather
    than inferred by ``_score`` from litellm's static cloud registry, which has
    no entry for local model ids. That is both stronger and simpler, and it
    removes the deliberate divergence this probe used to document: the probe
    and the real resolver now ask the SAME object the SAME question, so a model
    the resolver would pick and a model this probe blesses cannot drift apart.

    What has NOT changed is that resolvable is not the same as ready. A model
    can be selectable — the sole candidate, or an explicit operator pin — while
    being incapable of structured output, and ``classify_note`` running on such
    a model emits degraded classifications. That is why the answer is the
    resolved profile's CAPABILITY, not the mere fact that a model string came
    back. A degraded classifier must never drive vault mutations.

    Fail-closed contract — every one of these returns False, and this function
    never raises:

    - Nothing loaded, or nothing the backend reports at all.
    - Models present but none carrying ``tool_use``.
    - An operator pin that wins the ladder despite lacking ``tool_use``.
    - **A resolution that RAISES.** Under ADR decision 4 as amended, a live
      backend whose candidates cannot be disambiguated raises rather than
      returning a config-named phantom. The probe absorbs that: an uncaught
      raise would surface in ``routes/note.py``'s sweep gate as a 500 instead
      of a refusal, and a 500 is not a refusal.
    - Any HTTP, JSON, or schema failure.

    ``active_model``: an already-composed seam to ask. When omitted, a fresh
    one is built over ``http_client`` — deliberately per call, so this probe
    reads live state rather than a TTL-cached verdict, exactly as it previously
    bypassed the module-level discovery cache.

    260502: placed next to ``probe_embedding_model_loaded`` so both readiness
    probes live in one module.
    """
    try:
        if active_model is None:
            # Imported here rather than at module scope: app.model imports the
            # shared model_profiles library, and this module is imported by the
            # composition root before that graph exists.
            from app.model import (  # noqa: PLC0415
                CAPABILITY_TOOL_USE,
                ActiveModel,
                LMStudioModelSource,
            )

            probe_settings = SimpleNamespace(
                model_name=model_name,
                model_preferred=model_preferred,
                # The probe is not the place to honour a per-task pin the caller
                # did not pass; it mirrors exactly the two values it is given.
                model_task_chat=None,
                model_task_structured=None,
                model_task_fast=None,
                model_context_cap=None,
                model_ttl_seconds=None,
            )
            active_model = ActiveModel(
                [LMStudioModelSource(http_client, lmstudio_base_url)],
                probe_settings,
            )
        else:
            from app.model import CAPABILITY_TOOL_USE  # noqa: PLC0415

        profile = await active_model.for_task("structured")
    except Exception as exc:
        logger.debug("Classifier readiness probe failed closed: %s", exc)
        return False

    ready = CAPABILITY_TOOL_USE in profile.capabilities
    if not ready:
        logger.debug(
            "Classifier not ready: resolved model %r does not report %r",
            profile.model_id,
            CAPABILITY_TOOL_USE,
        )
    return ready


async def probe_embedding_model_loaded(
    http_client: httpx.AsyncClient,
    lmstudio_base_url: str,
    configured_embedding_model: str,
) -> bool:
    """Return True iff the configured embedding model is loaded in LM Studio.

    Queries LM Studio's REST API v0 (``/api/v0/models``) which exposes a
    ``state`` field (``"loaded"`` / ``"not-loaded"``) and a ``type`` field
    (``"llm"`` / ``"embeddings"`` / ``"vlm"``) per entry. The OpenAI-compat
    ``/v1/models`` endpoint omits both, so it can't answer this question.

    Graceful degrade: any HTTP failure, JSON-decode failure, missing key,
    or schema mismatch returns False rather than raising. Startup probes
    must never fail the app over a model-state check (mirrors
    sentinel/persona.md probe pattern from commit 27d5ee9).

    Strips a leading ``openai/`` from ``configured_embedding_model`` so the
    caller can pass either the bare id or the litellm-prefixed string and
    still get a meaningful comparison against LM Studio's bare id field.

    260502-1zv D-02.
    """
    bare_id = configured_embedding_model
    if bare_id.startswith("openai/"):
        bare_id = bare_id[len("openai/"):]

    # /v1 → /api/v0 — same strip pattern as get_context_window_from_lmstudio.
    api_base = lmstudio_base_url.rstrip("/").removesuffix("/v1")
    url = f"{api_base}/api/v0/models"

    try:
        resp = await http_client.get(url, timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.debug("Embedding probe failed (%s): %s", url, exc)
        return False

    try:
        entries = data.get("data", []) if isinstance(data, dict) else []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if (
                entry.get("state") == "loaded"
                and entry.get("type") == "embeddings"
                and entry.get("id") == bare_id
            ):
                return True
        return False
    except Exception as exc:
        logger.debug("Embedding probe schema mismatch: %s", exc)
        return False
