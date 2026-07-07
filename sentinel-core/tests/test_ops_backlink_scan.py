"""RED unit tests for ``app.services.ops_backlink_scan`` (Phase 47, Plan 01
Wave 0, RESEARCH.md Pattern 3).

Mirrors ``tests/test_links_sidecar_index.py``'s fake-vault-with-canned-
``find()``-results fixture style. Fails RED today with a
``ModuleNotFoundError`` -- ``app.services.ops_backlink_scan`` does not exist
yet; a downstream plan lands the module and turns this GREEN.

``graph_analysis``/``links_sidecar_index`` are both deliberately
``notes/``-scoped by design (RESEARCH.md Pattern 3: ``build_links_index``
only ever walks ``NOTES_ROOT``) and must NOT be widened to cover ``ops/`` --
this is a NEW, standalone, vault-wide scan function instead. This test file
does not import or touch either module.
"""
from __future__ import annotations

import pytest


class _FakeVault:
    """Fake vault whose ``find()`` returns canned hits per query string."""

    def __init__(self, hits: dict[str, list[dict]] | None = None) -> None:
        self._hits: dict[str, list[dict]] = dict(hits or {})
        self.queries: list[str] = []

    async def find(self, query: str) -> list[dict]:
        self.queries.append(query)
        return list(self._hits.get(query, []))


@pytest.mark.asyncio
async def test_scan_counts_title_refs():
    """``scan_for_title_refs(vault, title)`` returns the int hit count for
    a ``"[[Old Title]]"`` search against ``vault.find()``."""
    from app.services.ops_backlink_scan import scan_for_title_refs

    vault = _FakeVault(
        hits={
            "[[Old Title]]": [
                {"filename": "notes/some-note.md", "score": 1.0},
                {"filename": "ops/journal/2026-01-01/entry.md", "score": 1.0},
            ]
        }
    )

    count = await scan_for_title_refs(vault, "Old Title")

    assert count == 2
    assert vault.queries == ["[[Old Title]]"]


@pytest.mark.asyncio
async def test_scan_is_not_notes_scoped():
    """The scan surfaces a reference located under ``ops/journal/...`` --
    proving it is vault-wide and NOT ``notes/``-scoped (unlike
    ``graph_analysis``/``links_sidecar_index``)."""
    from app.services.ops_backlink_scan import scan_for_title_refs

    vault = _FakeVault(
        hits={
            "[[Old Title]]": [
                {"filename": "ops/journal/2026-02-02/entry.md", "score": 1.0},
            ]
        }
    )

    count = await scan_for_title_refs(vault, "Old Title")

    assert count == 1
    hit_paths = [h["filename"] for h in vault._hits["[[Old Title]]"]]
    assert any(p.startswith("ops/") for p in hit_paths), (
        "scan must surface ops/-located hits -- it is vault-wide, not notes/-scoped"
    )


@pytest.mark.asyncio
async def test_scan_diff_detects_new_dangling():
    """A pre-move count vs. a smaller post-move count is what the caller
    uses to detect a broken ops-bound backlink (RESEARCH.md Pattern 3's
    verify-then-trust backstop, since ``:graph`` is structurally blind to
    ``ops/``)."""
    from app.services.ops_backlink_scan import scan_for_title_refs

    vault = _FakeVault(
        hits={
            "[[Old Title]]": [
                {"filename": "notes/some-note.md", "score": 1.0},
                {"filename": "ops/journal/2026-01-01/entry.md", "score": 1.0},
            ]
        }
    )

    pre_count = await scan_for_title_refs(vault, "Old Title")

    # Simulate a rewrite that broke one backlink (caller re-scans post-move).
    vault._hits["[[Old Title]]"] = [
        {"filename": "notes/some-note.md", "score": 1.0},
    ]

    post_count = await scan_for_title_refs(vault, "Old Title")

    assert post_count < pre_count, (
        "caller detects a new dangling backlink via a smaller post-move count"
    )
