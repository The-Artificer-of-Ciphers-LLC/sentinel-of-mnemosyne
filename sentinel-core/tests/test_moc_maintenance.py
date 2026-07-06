"""Tests for ``app.services.moc_maintenance`` (Phase 45, Plan 05).

Covers embedding-first hub lookup reusing the recall cosine floor + shared
cosine + ``eligible_entries`` (D-03/D-03a, Task 1), the idempotent
trailing-``_schema``-preserving hub attach (D-03d + RESEARCH Pitfall 1,
Task 2), and create-or-update orchestration + constrained concept-slug
naming with an untrusted-input posture (D-03c/d, Task 3).
"""
from __future__ import annotations

import numpy as np

from app.services import moc_maintenance
from app.services.recall import RecallConfig
from sentinel_shared.embedding_codec import encode_embedding


def _entry(vector: list[float], *, model: str = "test-model") -> dict:
    return {
        "embedding_b64": encode_embedding(vector),
        "embedding_model": model,
        "content_hash": "deadbeef",
        "embedding_dim": len(vector),
    }


# --- Task 1: find_hub_candidate / should_materialize_hub ---


def test_hub_cosine_floor_reuses_recall_semantic_cosine_floor():
    """D-03: the hub floor is imported, never a duplicated literal."""
    assert moc_maintenance.HUB_COSINE_FLOOR == RecallConfig.semantic_cosine_floor


def test_find_hub_candidate_returns_best_clearing_hub():
    query = [1.0, 0.0]
    index = {
        "notes/hub-a.md": _entry([1.0, 0.0]),  # cosine 1.0
        "notes/hub-b.md": _entry([0.0, 1.0]),  # cosine 0.0 — below floor
        "notes/member-x.md": _entry([1.0, 0.0]),  # not a hub path — excluded
    }
    result = moc_maintenance.find_hub_candidate(
        note_vector=np.asarray(query, dtype=np.float32),
        hub_paths={"notes/hub-a.md", "notes/hub-b.md"},
        index=index,
        active_model="test-model",
    )
    assert result == "notes/hub-a.md"


def test_find_hub_candidate_returns_none_when_no_hub_clears_floor():
    """No hub clears the floor -> hub-pending (D-03b: reported as orphan)."""
    query = [1.0, 0.0]
    index = {
        "notes/hub-a.md": _entry([0.0, 1.0]),  # orthogonal — cosine 0.0
    }
    result = moc_maintenance.find_hub_candidate(
        note_vector=np.asarray(query, dtype=np.float32),
        hub_paths={"notes/hub-a.md"},
        index=index,
        active_model="test-model",
    )
    assert result is None


def test_find_hub_candidate_respects_dimension_mismatch_guard():
    """Reuses eligible_entries verbatim — a stored-dim mismatch is hard-skipped."""
    query = [1.0, 0.0, 0.0]
    mismatched = _entry([1.0, 0.0])  # 2-dim entry, 3-dim query
    index = {"notes/hub-a.md": mismatched}
    result = moc_maintenance.find_hub_candidate(
        note_vector=np.asarray(query, dtype=np.float32),
        hub_paths={"notes/hub-a.md"},
        index=index,
        active_model="test-model",
    )
    assert result is None


def test_should_materialize_hub_false_for_first_true_for_second_member():
    assert moc_maintenance.should_materialize_hub(1) is False
    assert moc_maintenance.should_materialize_hub(2) is True
