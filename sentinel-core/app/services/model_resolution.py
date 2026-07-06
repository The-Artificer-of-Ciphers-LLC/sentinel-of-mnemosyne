"""Shared LM Studio model-resolution + profile-lookup helper.

Promoted from ``note_classifier._resolve_model_for_classification`` (Phase 46
Plan 02, RESEARCH Assumption A2) so there is exactly ONE implementation of
this logic in the codebase. ``note_classifier`` and every
``app/services/six_rs/*`` structured-completion stage (Reduce, Reflect,
Reweave, Rethink, and Verify's optional claim-title assist — D-05) resolve
their LM Studio model + profile through this single helper, eliminating the
5-way drift risk RESEARCH flags in Assumption A2 (the same failure class as
the carrier-allowlist drift Pitfall 2 warns about).

This is a pure move — no resolution semantics were changed. Every graceful
``except``-warn fallback from the original classifier resolver is preserved
verbatim.
"""
from __future__ import annotations

import logging

from app.config import settings
from app.services.model_selector import (
    ensure_litellm_prefix,
    get_loaded_models as _default_get_loaded_models,
    select_model as _default_select_model,
    strip_litellm_prefix,
)
from sentinel_shared.model_profiles import get_profile as _default_get_profile

logger = logging.getLogger(__name__)


async def resolve_structured_model(
    *,
    task_kind: str = "structured",
    get_loaded_models=_default_get_loaded_models,
    select_model=_default_select_model,
    get_profile=_default_get_profile,
) -> tuple[str, object | None, str | None]:
    """Resolve ``(prefixed_model_id, profile, api_base)`` for a structured-output
    (JSON-mode ``response_format``) completion call.

    Single source of truth for LM Studio model-resolution + profile-lookup —
    used by ``note_classifier.classify_note`` and every ``six_rs/*`` stage's
    structured completion. Falls back gracefully when LM Studio is
    unreachable — returns a best-effort model string from settings; the
    caller's LLM call may still fail, in which case the caller should coerce
    to a safe default (mirrors ``note_classifier``'s coerce-to-``unsure``
    discipline).

    ``get_loaded_models`` / ``select_model`` / ``get_profile`` are accepted
    as keyword overrides (defaulting to the real ``model_selector`` /
    ``model_profiles`` implementations) so callers — including tests that
    patch these at their own module's import site — can substitute fakes
    without this function needing its own separate patch surface.
    """
    api_base = settings.lmstudio_base_url or "http://host.docker.internal:52415"
    api_base_v1 = (
        f"{api_base.rstrip('/')}/v1"
        if not api_base.rstrip("/").endswith("/v1")
        else api_base
    )
    try:
        loaded = await get_loaded_models(api_base_v1)
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("resolve_structured_model: get_loaded_models failed: %s", exc)
        loaded = []

    # Honor MODEL_PREFERRED for the structured task kind too — operators set
    # this when they want one specific model for everything (avoids LM Studio
    # TTL-unloading multiple models, pinning to known-working ones).
    preferences: dict[str, str] = {}
    preferred = settings.model_preferred or settings.model_name
    if preferred:
        preferences[task_kind] = preferred

    try:
        model_id = select_model(
            task_kind,
            loaded,
            preferences=preferences,
            default=settings.model_name or None,
        )
    except Exception as exc:
        # select_model only raises when there's no configured default AND the loaded/catalog
        # set is ambiguous (0 or 2+ unscored/unmatched entries). Falling back to `loaded[0]`
        # here would reintroduce the unsound "guess a catalog entry" behavior select_model
        # just refused to do (exo-model-notfound-502) — prefer the configured model_name
        # (even if unconfirmed) over an arbitrary catalog pick.
        logger.warning(
            "resolve_structured_model: select_model failed (%s); falling back to configured MODEL_NAME",
            exc,
        )
        model_id = settings.model_name or "openai/local-model"

    # Ensure litellm provider prefix — HF-style namespaces (qwen/qwen2.5-coder-14b)
    # are NOT litellm provider tags, so '/' alone is not a sufficient guard.
    prefixed_model_id = ensure_litellm_prefix(model_id)

    # get_profile hits LM Studio's /api/v0/models/{id} which needs the BARE id,
    # not the litellm-prefixed form. Strip the openai/ prefix back off.
    bare_model_id = strip_litellm_prefix(prefixed_model_id)

    try:
        profile = await get_profile(bare_model_id, api_base=api_base)
    except Exception as exc:
        logger.warning("resolve_structured_model: get_profile failed (%s); using None", exc)
        profile = None

    return prefixed_model_id, profile, api_base
