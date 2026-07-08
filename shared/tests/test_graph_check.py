"""Tests for the vendored pure wikilink-orphan checker (sentinel_shared.graph_check).

Fixtures here use UNIQUE filename stems and bare-stem wikilink targets — the
RESEARCH.md Pattern 4 note bodies all name every note ``index.md`` and link by
full path, which does NOT resolve under the stem-match rule, so they are not
reused verbatim here (the corrected music hub-mesh with its zero-orphan proof
lives in Plan 04's test_music_vault_seed.py).
"""
from __future__ import annotations

from sentinel_shared.graph_check import (
    GraphReport,
    build_graph_report,
    extract_wikilinks,
    resolve_wikilink,
)


def test_mutually_linked_unique_stem_notes_yield_zero_orphans():
    """Two notes with unique stems linking to each other have no orphans."""
    notes = {
        "notes/a.md": "# A\n\nSee [[b]] for more.\n",
        "notes/b.md": "# B\n\nSee [[a]] for more.\n",
    }
    report = build_graph_report(notes)
    assert isinstance(report, GraphReport)
    assert report.orphans == []
    assert report.note_count == 2


def test_lone_note_pointing_at_unwritten_target_is_orphan():
    """A single note linking only to a target that doesn't exist yet is an orphan.

    resolve_wikilink only creates an edge when a note whose stem matches the
    target already exists in the map -- so a lone note has no outlinks and no
    backlinks and is reported as an orphan.
    """
    notes = {
        "notes/lonely.md": "# Lonely\n\nSee [[not-yet-written]].\n",
    }
    report = build_graph_report(notes)
    assert report.orphans == ["notes/lonely.md"]


def test_full_path_target_does_not_resolve_to_bare_stem():
    """A full-path wikilink target [[dir/x]] does NOT match a bare `x` stem.

    _slugify preserves slashes, so `dir/x` normalizes to `dir/x` which never
    equals the bare stem `x` -- downstream callers must use bare-stem link
    targets, never full paths.
    """
    notes = {
        "notes/x.md": "# X\n",
        "notes/pointer.md": "# Pointer\n\nSee [[dir/x]].\n",
    }
    report = build_graph_report(notes)
    # pointer.md's [[dir/x]] does not resolve to notes/x.md, so both are orphans.
    assert "notes/pointer.md" in report.orphans
    assert "notes/x.md" in report.orphans
    assert resolve_wikilink("dir/x", notes.keys()) is None


def test_unresolved_wikilink_contributes_no_edge():
    notes = {
        "notes/a.md": "# A\n\nSee [[nonexistent]].\n",
        "notes/b.md": "# B\n\nSee [[a]].\n",
    }
    report = build_graph_report(notes)
    # a.md has an inbound link from b.md, so it's not an orphan.
    assert "notes/a.md" not in report.orphans
    # b.md has an outbound link to a.md, so it's not an orphan either.
    assert "notes/b.md" not in report.orphans
    assert report.backlinks["notes/a.md"] == ["notes/b.md"]


def test_self_link_excluded_from_own_outlinks():
    notes = {
        "notes/a.md": "# A\n\nSee [[a]] and [[b]].\n",
        "notes/b.md": "# B\n\nSee [[a]].\n",
    }
    report = build_graph_report(notes)
    # a.md must not list itself as a backlink source of itself.
    assert "notes/a.md" not in report.backlinks["notes/a.md"]


def test_note_with_no_wikilinks_yields_empty_extract_set():
    assert extract_wikilinks("# Just prose, no links here.\n") == set()
    assert extract_wikilinks("") == set()


def test_graph_check_module_has_no_hub_paths_param():
    """build_graph_report's signature drops Core's hub_paths param (module self-checks

    do not classify hubs).
    """
    import inspect

    sig = inspect.signature(build_graph_report)
    assert list(sig.parameters.keys()) == ["notes"]
