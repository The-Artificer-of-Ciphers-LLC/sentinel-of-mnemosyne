"""Tests for ``app.services.moc_maintenance`` (Phase 45, Plan 05).

Covers embedding-first hub lookup reusing the recall cosine floor + shared
cosine + ``eligible_entries`` (D-03/D-03a, Task 1), the idempotent
trailing-``_schema``-preserving hub attach (D-03d + RESEARCH Pitfall 1,
Task 2), and create-or-update orchestration + constrained concept-slug
naming with an untrusted-input posture (D-03c/d, Task 3).
"""
from __future__ import annotations

import re

import numpy as np
import pytest

from app.services import moc_maintenance
from app.services.recall import RecallConfig
from sentinel_shared.embedding_codec import encode_embedding
from tests.fakes.vault import FakeVault

MEMBER_WIKILINK_RE = re.compile(r"\[\[[^\]]*member[ -]two[^\]]*\]\]", re.IGNORECASE)


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


# --- Task 2: attach_to_hub ---


@pytest.mark.asyncio
async def test_attach_to_hub_preserves_trailing_schema_block_position():
    hub_path = "notes/hub-concept.md"
    hub_body = (
        "# Hub Concept\n\n"
        "## Member Notes\n\n"
        "- [[Member One]]\n\n"
        "```_schema\n"
        "type: hub\n"
        "```\n"
    )
    vault = FakeVault(notes={hub_path: hub_body})

    await moc_maintenance.attach_to_hub(vault, hub_path, "member-two")

    result_body = vault.notes[hub_path]
    assert result_body.rstrip().endswith("```")
    assert len(MEMBER_WIKILINK_RE.findall(result_body)) == 1
    # Member One must survive the merge unchanged.
    assert "[[Member One]]" in result_body


@pytest.mark.asyncio
async def test_attach_to_hub_reattaching_same_member_is_noop():
    hub_path = "notes/hub-concept.md"
    hub_body = (
        "# Hub Concept\n\n"
        "## Member Notes\n\n"
        "- [[Member One]]\n\n"
        "```_schema\n"
        "type: hub\n"
        "```\n"
    )
    vault = FakeVault(notes={hub_path: hub_body})

    await moc_maintenance.attach_to_hub(vault, hub_path, "member-two")
    once = vault.notes[hub_path]
    await moc_maintenance.attach_to_hub(vault, hub_path, "member-two")
    twice = vault.notes[hub_path]

    assert once == twice
    assert len(MEMBER_WIKILINK_RE.findall(twice)) == 1


@pytest.mark.asyncio
async def test_attach_to_hub_adds_marker_section_when_absent():
    """A hub note with no member-section marker yet still gets one added."""
    hub_path = "notes/hub-concept.md"
    hub_body = "# Hub Concept\n\n```_schema\ntype: hub\n```\n"
    vault = FakeVault(notes={hub_path: hub_body})

    await moc_maintenance.attach_to_hub(vault, hub_path, "member-two")

    result_body = vault.notes[hub_path]
    assert moc_maintenance.HUB_MEMBER_MARKER in result_body
    assert result_body.rstrip().endswith("```")
    assert len(MEMBER_WIKILINK_RE.findall(result_body)) == 1


@pytest.mark.asyncio
async def test_attach_to_hub_never_calls_patch_append():
    """attach_to_hub must never call vault.patch_append (RESEARCH Pitfall 1)."""
    hub_path = "notes/hub-concept.md"
    hub_body = (
        "# Hub Concept\n\n"
        "## Member Notes\n\n"
        "- [[Member One]]\n\n"
        "```_schema\n"
        "type: hub\n"
        "```\n"
    )
    vault = FakeVault(notes={hub_path: hub_body})

    async def _boom(path: str, body: str) -> None:
        raise AssertionError("attach_to_hub must never call patch_append")

    vault.patch_append = _boom  # type: ignore[assignment]

    await moc_maintenance.attach_to_hub(vault, hub_path, "member-two")
    assert vault.notes[hub_path].rstrip().endswith("```")


def test_moc_maintenance_source_never_calls_patch_append():
    """Static guard: no code path in this module invokes ``vault.patch_append``.

    Scans the AST for any attribute access named ``patch_append`` (an
    actual call site), not the module's own prose docstrings that
    *mention* the primitive by name as the anti-pattern to avoid.
    """
    import ast
    import inspect

    source = inspect.getsource(moc_maintenance)
    tree = ast.parse(source)
    attr_accesses = [
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "patch_append"
    ]
    assert not attr_accesses, "moc_maintenance.py must never call .patch_append(...)"


@pytest.mark.asyncio
async def test_attach_to_hub_handles_no_trailing_block():
    """A hub note with no trailing _schema block yet still merges cleanly."""
    hub_path = "notes/hub-concept.md"
    hub_body = "# Hub Concept\n\n## Member Notes\n\n- [[Member One]]\n"
    vault = FakeVault(notes={hub_path: hub_body})

    await moc_maintenance.attach_to_hub(vault, hub_path, "member-two")

    result_body = vault.notes[hub_path]
    assert "[[Member One]]" in result_body
    assert len(MEMBER_WIKILINK_RE.findall(result_body)) == 1
