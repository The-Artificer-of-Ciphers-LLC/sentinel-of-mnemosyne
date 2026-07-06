"""Reflect stage — six_rs/reflect.py (Phase 46 Plan 05, PIPE-02, D-07).

Embedding-first hub lookup and attach. Phase 46 is where the already-shipped
but never-called ``moc_maintenance.attach_to_hub`` (Phase 45) gets its first
caller. Reuses ``find_hub_candidate`` verbatim (D-07 -- no fresh cosine
loop) restricted to ``notes/``-scoped hub candidates; falls back to an
LLM-named hub (``propose_hub_slug`` + ``create_or_update_hub``) only when
nothing clears ``HUB_COSINE_FLOOR``.

T-46-03 (information-disclosure guard): hub candidates are restricted to
``notes/``-prefixed paths only -- a ``self/`` (or any other
protected-namespace) path can never be selected as an attach target or
receive a wikilink from a ``notes/`` note, even if it happens to embed
closer than any real hub. This is a hard architectural exclusion applied
BEFORE scoring, not a cosine-floor accident.
"""
from __future__ import annotations

import logging
from typing import Any

from app.services.graph_analysis import NOTES_ROOT
from app.services.model_resolution import resolve_structured_model
from app.services.moc_maintenance import (
    attach_to_hub,
    create_or_update_hub,
    find_hub_candidate,
    propose_hub_slug,
)
from sentinel_shared.llm_call import acompletion_with_profile

logger = logging.getLogger(__name__)

_NOTES_PREFIX = f"{NOTES_ROOT}/"


def _slug_from_path(note_path: str) -> str:
    """Derive a member/concept slug from a vault-relative note path.

    ``"notes/member-note.md"`` -> ``"member-note"``.
    """
    stem = note_path.rsplit("/", 1)[-1]
    if stem.endswith(".md"):
        stem = stem[: -len(".md")]
    return stem


def _notes_scoped_hub_paths(index: dict[str, Any], *, exclude: str) -> set[str]:
    """Restrict hub candidates to ``notes/``-scoped index keys (T-46-03).

    Any path outside ``notes/`` (``self/...``, ``ops/...``, etc.) is
    excluded here, before any scoring happens -- a hard architectural
    exclusion, never merely losing a cosine-floor tie.
    """
    return {path for path in index if path.startswith(_NOTES_PREFIX) and path != exclude}


async def _default_completion_fn(*, messages: list[dict], response_format: dict) -> Any:
    """Resolve a real LM Studio model/profile and call ``acompletion_with_profile``.

    Used only on the ``propose_hub_slug`` LLM-naming fallback path (D-07) --
    never on the embedding-first match path, which makes zero LLM calls.
    """
    model_id, profile, api_base = await resolve_structured_model()
    return await acompletion_with_profile(
        model=model_id,
        messages=messages,
        profile=profile,
        api_base=api_base,
        api_key="lmstudio",
        response_format=response_format,
        temperature=0.0,
    )


async def find_and_attach_hub(
    vault: Any,
    *,
    note_path: str,
    note_vector: Any,
    index: dict[str, Any],
    active_model: str,
    completion_fn=None,
) -> str | None:
    """Embedding-first hub lookup + attach for one freshly-Reduced note (D-07).

    1. Calls ``moc_maintenance.find_hub_candidate`` (reused verbatim -- no
       fresh cosine loop) restricted to ``notes/``-scoped ``hub_paths``
       (T-46-03).
    2. On a match: ``attach_to_hub(vault, hub_path, member_slug)`` --
       idempotent, never a fresh hub.
    3. On no match: ``propose_hub_slug`` (LLM naming fallback, D-07) then
       ``create_or_update_hub``.

    Returns the hub path touched.
    """
    member_slug = _slug_from_path(note_path)
    hub_paths = _notes_scoped_hub_paths(index, exclude=note_path)

    hub_path = find_hub_candidate(
        note_vector=note_vector,
        hub_paths=hub_paths,
        index=index,
        active_model=active_model,
    )

    if hub_path is not None:
        # Defense-in-depth (T-46-03): hub_paths is already notes/-scoped
        # above, but never attach outside notes/ even if that invariant
        # were ever violated upstream.
        if not hub_path.startswith(_NOTES_PREFIX):
            logger.warning(
                "find_and_attach_hub: refusing non-notes/ hub_path %r (T-46-03)",
                hub_path,
            )
        else:
            await attach_to_hub(vault, hub_path, member_slug)
            return hub_path

    # Fallback: nothing cleared the floor -- LLM-named new/merged hub (D-07).
    fn = completion_fn or _default_completion_fn
    member_text = (await vault.read_note(note_path)) or member_slug
    concept_slug = await propose_hub_slug(member_texts=[member_text], completion_fn=fn)
    return await create_or_update_hub(
        vault, concept_slug=concept_slug, member_slug=member_slug, completion_fn=fn
    )
