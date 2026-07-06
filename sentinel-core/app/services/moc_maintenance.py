"""Lazy MOC/hub machinery (NOTE-02, SC-2).

Finds the nearest existing hub for a note by reusing the vault sweeper's
embedding sidecar + the shared cosine helper + the already-shipped recall
``semantic_cosine_floor`` (D-03) -- no new embedding call, no new threshold.
A hub materializes only on the 2nd topically-similar member clearing the
floor (min-cluster-size 2, D-03a); a lone clearing note is held hub-pending
(``find_hub_candidate`` returns ``None``, reported as an orphan by
``graph_analysis``, D-03b).

``attach_to_hub`` is the idempotent, trailing-``_schema``-block-preserving
read-modify-write (D-03d + RESEARCH Pitfall 1): it NEVER calls
``vault.patch_append`` on a hub note, because a blind append would push the
new wikilink *after* the trailing ``_schema`` block, breaking the
"terminal content" invariant ``note_schema.py``'s regex-from-end parser
depends on. Always: read full body -> ``note_schema.split_schema_block`` ->
mutate the pre-block body -> re-append the (unchanged) trailing block ->
single ``write_note``.

Phase 45 ships and unit-tests this machinery only -- no pipeline caller
wires it into a write path yet (Phase 46 wires the Reflect-stage caller,
D-02).
"""
from __future__ import annotations

import re
from typing import Any

from app.services.embedding_sidecar_index import EligibleEmbeddingEntry, eligible_entries
from app.services.graph_analysis import NOTES_ROOT
from app.services.note_schema import split_schema_block
from app.services.recall import RecallConfig
from sentinel_shared.similarity import cosine_similarity

MIN_CLUSTER_SIZE = 2
"""D-03a: a hub materializes only on the 2nd topically-similar member that
clears the cosine floor. A lone clearing member stays hub-pending."""

HUB_COSINE_FLOOR: float = RecallConfig.semantic_cosine_floor
"""D-03: reuse the already-shipped recall cosine floor (0.50) verbatim as
the hub-membership floor -- never redeclare a new threshold here."""

HUB_MEMBER_MARKER = "## Member Notes"
"""Stable section heading under which member wikilinks are inserted/found.
Both freshly-created hub notes (``create_or_update_hub``) and pre-existing
hub notes attached to via ``attach_to_hub`` share this exact marker string."""

_MEMBER_TITLE_WORD_RE = re.compile(r"[-_]+")


def _slug_to_display(slug: str) -> str:
    """Convert a kebab/snake-case slug into a Title Case display string.

    ``"member-two"`` -> ``"Member Two"``. Pure formatting helper -- the
    exact display-text transform is this module's implementation detail
    (Wave-0 fixture matches loosely on the member reference, not on exact
    casing).
    """
    words = [w for w in _MEMBER_TITLE_WORD_RE.split(slug or "") if w]
    return " ".join(w.capitalize() for w in words) if words else (slug or "")


def hub_path_for_slug(concept_slug: str) -> str:
    """Return the deterministic ``notes/{concept-slug}.md`` hub path (D-03d).

    Idempotent creation under the transaction-less REST vault is achieved by
    ALWAYS re-deriving this same path from ``concept_slug`` -- identity is
    the path itself, not a lock. Reuses ``graph_analysis.NOTES_ROOT`` as the
    single source of truth for the flat notes/ prefix (Pitfall 3 SPOT).
    """
    return f"{NOTES_ROOT}/{concept_slug}.md"


# ---------------------------------------------------------------------------
# Task 1: embedding-first hub lookup + min-cluster-size decision (D-03/D-03a)
# ---------------------------------------------------------------------------


def find_hub_candidate(
    *,
    note_vector: Any,
    hub_paths: set[str],
    index: dict[str, dict[str, Any]],
    active_model: str,
) -> str | None:
    """Return the best-matching hub path clearing the cosine floor, or None.

    Reuses ``embedding_sidecar_index.eligible_entries`` verbatim (preserving
    its dimension-mismatch guard and model-string match) and
    ``sentinel_shared.similarity.cosine_similarity`` verbatim -- no second
    cosine implementation, no fresh embedding call (D-03, Pattern 3).
    Candidates are restricted to ``hub_paths`` (already ``notes/``-scoped by
    the caller). Returns ``None`` when no hub clears
    :data:`HUB_COSINE_FLOOR` -- the note stays hub-pending (D-03b: reported
    as an orphan by ``graph_analysis``, not a separate pending state).
    """
    entries: list[EligibleEmbeddingEntry]
    entries, _matched_model_count = eligible_entries(
        index,
        active_model=active_model,
        exclude_prefixes=(),
        query_dim=len(note_vector),
    )

    best_path: str | None = None
    best_sim = HUB_COSINE_FLOOR
    for entry in entries:
        if entry.path not in hub_paths:
            continue
        sim = float(cosine_similarity(note_vector, entry.vector))
        if sim >= best_sim:
            best_path, best_sim = entry.path, sim

    return best_path


def should_materialize_hub(clearing_count: int) -> bool:
    """D-03a: a hub materializes on the 2nd clearing member, not the 1st.

    ``clearing_count`` is the count of members (for one nascent topic) that
    have cleared :data:`HUB_COSINE_FLOOR` against each other so far,
    including the current note.
    """
    return clearing_count >= MIN_CLUSTER_SIZE


# ---------------------------------------------------------------------------
# Task 2: idempotent, trailing-_schema-preserving hub attach (D-03d + Pitfall 1)
# ---------------------------------------------------------------------------


def _insert_member_wikilink(pre_block_body: str, wikilink: str) -> str:
    """Insert ``wikilink`` under :data:`HUB_MEMBER_MARKER` if not already present.

    Idempotent: returns ``pre_block_body`` unchanged when ``wikilink`` is
    already present anywhere in it (append-never-duplicate, D-03d). Adds
    the marker section itself when absent.
    """
    if wikilink in pre_block_body:
        return pre_block_body

    stripped = pre_block_body.rstrip("\n")
    if HUB_MEMBER_MARKER not in stripped:
        stripped = f"{stripped}\n\n{HUB_MEMBER_MARKER}" if stripped else HUB_MEMBER_MARKER

    return f"{stripped}\n- {wikilink}\n"


async def attach_to_hub(vault: Any, hub_path: str, member_slug: str) -> None:
    """Idempotently attach ``member_slug`` to the hub note at ``hub_path``.

    Reads the full hub body, splits off any trailing ``_schema`` block
    (``note_schema.split_schema_block``), inserts the member wikilink under
    :data:`HUB_MEMBER_MARKER` only if not already present, re-appends the
    trailing block unchanged so it stays the LAST thing in the file, and
    performs a single ``write_note`` of the merged body. NEVER calls
    ``vault.patch_append`` -- see the module docstring / RESEARCH Pitfall 1.
    """
    body = await vault.read_note(hub_path)
    pre_block_body, trailing_block = split_schema_block(body)

    wikilink = f"[[{_slug_to_display(member_slug)}]]"
    updated_pre_block = _insert_member_wikilink(pre_block_body, wikilink)

    merged = updated_pre_block if updated_pre_block.endswith("\n") else f"{updated_pre_block}\n"
    if trailing_block:
        if not merged.endswith("\n\n"):
            merged = f"{merged.rstrip(chr(10))}\n\n"
        # Trailing single newline after the re-appended block keeps a
        # freshly-created hub (create_or_update_hub) and a re-attached one
        # byte-identical when nothing changed (idempotent convergence, D-03d).
        merged = merged + trailing_block + "\n"

    await vault.write_note(hub_path, merged)
