"""Tests for ``app.services.graph_analysis`` (Plan 45-03).

Pure wikilink-graph computation backing ``:graph``/``:stats`` (NOTE-03).
No vault I/O, no LLM/network calls — every test here operates on
in-memory notes maps / bodies only.
"""
from __future__ import annotations

import inspect
import re

from app.services import graph_analysis


# --- Task 1: NOTES_ROOT constant + wikilink extraction + filename-stem resolver ---


def test_notes_root_single_definition():
    """T-45-DRIFT guard: NOTES_ROOT must be defined exactly once in this
    module (Pitfall 3 SPOT) — mirrors the acceptance criteria's grep check
    as a live regression guard."""
    source = inspect.getsource(graph_analysis)
    assert len(re.findall(r"^NOTES_ROOT\s*=", source, re.MULTILINE)) == 1


def test_extract_wikilinks_plain_link():
    body = "See [[Target One]] for details."
    assert graph_analysis.extract_wikilinks(body) == {"Target One"}


def test_extract_wikilinks_strips_alias():
    body = "See [[Target One|a friendly alias]] for details."
    assert graph_analysis.extract_wikilinks(body) == {"Target One"}


def test_extract_wikilinks_strips_heading_anchor():
    body = "See [[Target One#Some Heading]] for details."
    assert graph_analysis.extract_wikilinks(body) == {"Target One"}


def test_extract_wikilinks_multiple_targets_and_no_links():
    body = "Refs: [[A]] and [[B|alias]] and [[C#Heading]]."
    assert graph_analysis.extract_wikilinks(body) == {"A", "B", "C"}
    assert graph_analysis.extract_wikilinks("no links in this body") == set()
    assert graph_analysis.extract_wikilinks("") == set()


def test_resolve_wikilink_matches_by_filename_stem():
    note_paths = [
        "notes/hub-concept.md",
        "notes/member-one.md",
        "notes/member-two.md",
    ]
    resolved = graph_analysis.resolve_wikilink("Member One", note_paths)
    assert resolved == "notes/member-one.md"


def test_resolve_wikilink_returns_none_on_miss():
    note_paths = ["notes/hub-concept.md", "notes/member-one.md"]
    assert graph_analysis.resolve_wikilink("No Such Note", note_paths) is None


def test_resolve_wikilink_no_ambiguity_on_flat_notes_invariant():
    # Two distinct stems never collide under the flat-notes/ invariant;
    # confirm the exact-stem path wins and no other path is returned.
    note_paths = ["notes/foo.md", "notes/foo-bar.md"]
    assert graph_analysis.resolve_wikilink("Foo", note_paths) == "notes/foo.md"
    assert graph_analysis.resolve_wikilink("Foo Bar", note_paths) == "notes/foo-bar.md"


# --- Task 2: GraphReport + build_graph_report (orphans/backlinks/density, D-03b) ---


def test_build_graph_report_hub_with_two_linked_members_and_one_isolated():
    notes = {
        "notes/hub-concept.md": "# Hub Concept\n\n[[Member One]]\n[[Member Two]]\n",
        "notes/member-one.md": "# Member One\n\n[[Hub Concept]]\n",
        "notes/member-two.md": "# Member Two\n\n[[Hub Concept]]\n",
        "notes/isolated.md": "# Isolated\n\nNo links here.\n",
    }
    hub_paths = {"notes/hub-concept.md"}

    report = graph_analysis.build_graph_report(notes, hub_paths)

    assert report.note_count == 4
    assert report.orphans == ["notes/isolated.md"]
    assert set(report.backlinks["notes/hub-concept.md"]) == {
        "notes/member-one.md",
        "notes/member-two.md",
    }
    assert report.backlinks["notes/member-one.md"] == ["notes/hub-concept.md"]
    assert report.backlinks["notes/member-two.md"] == ["notes/hub-concept.md"]
    assert report.backlinks["notes/isolated.md"] == []
    assert report.hub_count == 1
    # 4 resolved edges total (hub->m1, hub->m2, m1->hub, m2->hub) / 4 notes
    assert report.link_density == 1.0


def test_build_graph_report_empty_notes_map():
    report = graph_analysis.build_graph_report({}, set())
    assert report.note_count == 0
    assert report.orphans == []
    assert report.backlinks == {}
    assert report.hub_count == 0
    assert report.link_density == 0.0


def test_build_graph_report_hub_pending_singleton_reported_as_orphan():
    """D-03b: a hub-pending singleton (no hub cleared the cosine floor, so
    it has no links yet) is reported as an orphan — no separate pending
    state."""
    notes = {
        "notes/hub-concept.md": "# Hub Concept\n\n[[Member One]]\n",
        "notes/member-one.md": "# Member One\n\n[[Hub Concept]]\n",
        "notes/hub-pending-singleton.md": "# Hub Pending Singleton\n\nNo links yet.\n",
    }
    hub_paths = {"notes/hub-concept.md"}

    report = graph_analysis.build_graph_report(notes, hub_paths)

    assert "notes/hub-pending-singleton.md" in report.orphans
    assert report.backlinks["notes/hub-pending-singleton.md"] == []
