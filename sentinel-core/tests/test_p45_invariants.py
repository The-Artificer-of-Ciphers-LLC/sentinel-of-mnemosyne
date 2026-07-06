"""Phase 45 cross-cutting invariants (Wave 0 scaffold).

This file holds the three cross-cutting characterizing / fixture tests
VALIDATION.md requires to exist BEFORE any Phase 45 feature module is built,
so the feature waves (Plans 03/05) have a live Nyquist feedback signal:

1. A live (unguarded) characterizing test locking the D-02 "inspect-only"
   premise — ``note_classifier.TOPIC_VAULT_PATH`` routes ``learning`` and
   ``reference`` to ``inbox/``, never a ``notes/`` root, which is what makes
   Phase 45 having no write-path enforcement correct rather than an oversight.
2. A fixture test (``pytest.importorskip("app.services.graph_analysis")``)
   pinning the wikilink -> path resolution rule (filename-stem match; research
   Open Question 2). SKIPS until Plan 45-03 lands ``graph_analysis``, then
   auto-activates as a hard GREEN gate.
3. A fixture test (``pytest.importorskip("app.services.moc_maintenance")``)
   pinning the trailing ``_schema`` block invariant (RESEARCH Pitfall 1):
   attaching a 2nd hub member must never push content after the terminal
   fenced block. SKIPS until Plan 45-05 lands ``moc_maintenance``, then
   auto-activates as a hard GREEN gate.

Guarded tests use ``importorskip`` (a genuine, visible pytest SKIP), never a
silent early-return/pass — see Phase 45 threat register T-45-01/T-45-02.
"""
from __future__ import annotations

import re

import pytest

from app.services.note_classifier import TOPIC_VAULT_PATH
from tests.fakes.vault import FakeVault


# --- Task 1: D-02 inspect-only premise (live, unguarded) ---


def test_classifier_routes_learning_and_reference_to_inbox_not_notes():
    """Locks the no-notes/-write-path premise (D-02) that inspect-only depends on.

    learning/reference both resolve to the inbox root, and no value in
    TOPIC_VAULT_PATH points at a notes directory. If a future edit ever
    routes learning/reference to notes/ (or introduces a notes/ write path
    anywhere in the map), this test fails — the guard is real.
    """
    assert TOPIC_VAULT_PATH["learning"] == "inbox"
    assert TOPIC_VAULT_PATH["reference"] == "inbox"
    for topic, path in TOPIC_VAULT_PATH.items():
        assert not path.startswith("notes"), (
            f"TOPIC_VAULT_PATH[{topic!r}] = {path!r} points at a notes/ root; "
            "Phase 45 assumes no notes/ write path exists yet (D-02)."
        )


# --- Task 2: wikilink -> path resolution fixture (research Open Question 2) ---


def test_wikilink_resolves_to_flat_notes_path_by_filename_stem():
    """Pins the flat-notes filename-stem wikilink resolution rule.

    SKIPS until Plan 45-03 lands app.services.graph_analysis. Once present,
    resolve_wikilink(target, note_paths) must resolve a bare [[Member One]]
    target to the flat notes path whose filename stem equals the target, and
    return None when no path has a matching stem. Pattern 3 (flat notes/)
    guarantees unique stems, so no ambiguity can arise.
    """
    graph_analysis = pytest.importorskip("app.services.graph_analysis")

    note_paths = [
        "notes/hub-concept.md",
        "notes/member-one.md",
        "notes/member-two.md",
    ]

    resolved = graph_analysis.resolve_wikilink("Member One", note_paths)
    assert resolved == "notes/member-one.md"

    missing = graph_analysis.resolve_wikilink("No Such Note", note_paths)
    assert missing is None


# --- Task 3: trailing _schema block preservation fixture (RESEARCH Pitfall 1) ---


@pytest.mark.asyncio
async def test_attach_to_hub_preserves_trailing_schema_block_position():
    """Pins the single highest-risk behavior in the phase.

    SKIPS until Plan 45-05 lands app.services.moc_maintenance. Once present,
    attach_to_hub(vault, hub_path, member_slug) adding a second member must
    insert the member wikilink BEFORE the trailing fenced ``_schema`` block,
    never after it (never via a blind patch_append) -- the block must stay
    the terminal content of the file, and the member wikilink must appear
    exactly once.
    """
    moc_maintenance = pytest.importorskip("app.services.moc_maintenance")

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
    assert result_body.rstrip().endswith("```"), (
        "trailing _schema block is no longer the terminal content of the "
        "hub note -- attach_to_hub must never call patch_append on a hub"
    )
    # Exact wikilink display text (slug vs. title-cased) is an attach_to_hub
    # implementation detail Plan 45-05 owns; match loosely on the member
    # reference itself so this fixture doesn't over-specify formatting while
    # still proving the wikilink was inserted exactly once (append-never-
    # duplicate, D-03d).
    member_wikilink_re = re.compile(r"\[\[[^\]]*member[ -]two[^\]]*\]\]", re.IGNORECASE)
    assert len(member_wikilink_re.findall(result_body)) == 1
