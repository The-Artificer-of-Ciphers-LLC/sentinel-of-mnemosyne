"""Litellm prefix helpers and the two LM Studio readiness probes.

**This module no longer selects models.** ADR-0007 step 4 removed
``select_model``, its ``_score`` rubric, ``get_loaded_models``,
``_fetch_live_capabilities`` and the three ``discover_*`` functions; every one
of them was absorbed by ``app/model.py``, which answers "which model is loaded
and what can it do" once. Leaving them here would have preserved exactly the
two-shapes-one-concept split the ADR set out to remove.

What survives, and why each thing survives:

- ``strip_litellm_prefix`` / ``ensure_litellm_prefix`` — string normalisation
  between litellm's provider-tagged ids and LM Studio's bare ids. Pure
  functions with no notion of which model is loaded, so they are not a second
  implementation of anything.
- ``probe_classifier_model_ready`` — the gate on a DESTRUCTIVE vault sweep.
  ADR-0007 rewired it onto the seam; it is not a resolver, it is a fail-closed
  verdict on the profile the seam resolves.
- ``probe_embedding_model_loaded`` — untouched per ADR decision 5. The
  embedding model is OBSERVED, never re-pointed: re-pointing it would
  invalidate every entry in ``ops/sweeps/embedding-index.json`` and, under
  ADR-0004's fail-soft posture, turn a loud model swap into quiet memory loss.

Deliberate absence: there is no module-level model cache here any more. The
process-lifetime ``_model_cache`` dict had no TTL, which is the exact staleness
``ActiveModel``'s 60-second refresh window exists to fix.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from app.model import ActiveModel

logger = logging.getLogger(__name__)

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
    than inferred by ``_score`` from litellm's static cloud registry, which had
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
    reads live state rather than a TTL-cached verdict.

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

    # /v1 → /api/v0 — same strip pattern as the seam's own api-root derivation.
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
