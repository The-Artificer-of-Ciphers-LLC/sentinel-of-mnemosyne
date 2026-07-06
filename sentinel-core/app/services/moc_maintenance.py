"""Lazy MOC/hub machinery (NOTE-02, SC-2).

Finds the nearest existing hub for a note by reusing the vault sweeper's
embedding sidecar + the shared cosine helper + the already-shipped recall
``semantic_cosine_floor`` (D-03) -- no new embedding call, no new threshold.
A hub materializes only on the 2nd topically-similar member clearing the
floor (min-cluster-size 2, D-03a); a lone clearing note is held hub-pending
(``find_hub_candidate`` returns ``None``, reported as an orphan by
``graph_analysis``, D-03b).

Phase 45 ships and unit-tests this machinery only -- no pipeline caller
wires it into a write path yet (Phase 46 wires the Reflect-stage caller,
D-02).
"""
from __future__ import annotations

from typing import Any

from app.services.embedding_sidecar_index import EligibleEmbeddingEntry, eligible_entries
from app.services.recall import RecallConfig
from sentinel_shared.similarity import cosine_similarity

MIN_CLUSTER_SIZE = 2
"""D-03a: a hub materializes only on the 2nd topically-similar member that
clears the cosine floor. A lone clearing member stays hub-pending."""

HUB_COSINE_FLOOR: float = RecallConfig.semantic_cosine_floor
"""D-03: reuse the already-shipped recall cosine floor (0.50) verbatim as
the hub-membership floor -- never redeclare a new threshold here."""


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
