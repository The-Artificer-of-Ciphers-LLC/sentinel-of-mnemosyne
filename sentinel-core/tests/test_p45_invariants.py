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

from app.services.note_classifier import TOPIC_VAULT_PATH


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
