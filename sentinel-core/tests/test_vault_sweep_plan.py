from __future__ import annotations

from app.services.note_classifier import topic_dir_for
from app.services.vault_sweep_plan import (
    SweepMovePlan,
    is_in_topic_dir,
    is_move_protected,
    plan_duplicate_trash,
    plan_noise_trash,
    plan_topic_move,
    propose_topic_move,
)


def test_plan_noise_trash_matches_dry_run_report_shape():
    plan = plan_noise_trash("stale/hello.md", today="2026-06-16")

    assert plan.asdict() == {
        "kind": "trash",
        "src": "stale/hello.md",
        "dst": "_trash/2026-06-16/hello.md",
        "reason": "cheap-filter:noise",
    }


def test_plan_topic_move_skips_existing_topic_family():
    assert is_in_topic_dir("ops/journal/2026-06-16/a.md", "ops/journal/2026-06-17")
    assert propose_topic_move("ops/accomplishments/a.md", "accomplishment") is None


def test_plan_topic_move_describes_destination_and_reason():
    plan = plan_topic_move(
        "random/a.md",
        "accomplishment",
        confidence=0.954,
    )

    assert plan is not None
    assert plan.asdict() == {
        "kind": "topic",
        "src": "random/a.md",
        "dst": "ops/accomplishments/a.md",
        "reason": "topic=accomplishment (confidence=0.95)",
    }


def test_is_in_topic_dir_does_not_conflate_ops_subdirs():
    """Pitfall 2 regression: journal/accomplishment/observation must not collapse
    into one indistinguishable ``ops/`` family under the shared parent."""
    assert is_in_topic_dir("ops/observations/x.md", "ops/accomplishments") is False
    assert is_in_topic_dir("ops/accomplishments/x.md", "ops/accomplishments") is True
    # Nested-date journal family: any day matches the journal family root.
    assert is_in_topic_dir(
        "ops/journal/2026-07-06/x.md", topic_dir_for("journal", today="2026-06-01")
    ) is True


def test_plan_duplicate_trash_matches_dry_run_report_shape():
    plan = plan_duplicate_trash(
        "references/short.md",
        "references/long.md",
        confidence=0.87,
        today="2026-06-16",
    )

    assert plan.asdict() == {
        "kind": "trash",
        "src": "references/short.md",
        "dst": "_trash/2026-06-16/short.md",
        "reason": "duplicate of references/long.md (cosine≥0.92, conf=0.9)",
    }


# --- is_move_protected: dry-run/live parity guard (production incident 2026-08-01) ---
#
# A live sweep refuses moves touching a protected namespace
# (app.vault.PROTECTED_NAMESPACES / is_protected_path) via ProtectedPathError
# in ObsidianVault.move_to_trash (src only) and .relocate (src OR dst). These
# tests pin that is_move_protected mirrors both guards exactly using the
# real app.vault.is_protected_path (segment-boundary matching), not a
# reimplementation.


def test_is_move_protected_true_for_protected_src_trash_plan():
    """A noise-trash plan whose SOURCE is boot-critical (sentinel/) must be
    flagged protected — mirrors move_to_trash's src-only guard."""
    plan = plan_noise_trash("sentinel/persona.md", today="2026-08-01")
    assert is_move_protected(plan) is True


def test_is_move_protected_false_for_non_protected_trash_plan():
    """An ordinary noise-trash plan outside any protected namespace must NOT
    be flagged — the guard must not over-filter normal proposals."""
    plan = plan_noise_trash("inbox/_pending-classification.md", today="2026-08-01")
    assert is_move_protected(plan) is False


def test_is_move_protected_true_for_protected_src_topic_plan():
    """A topic-move plan whose SOURCE is under a protected namespace must be
    flagged — mirrors relocate()'s source guard (moving a critical file out)."""
    plan = SweepMovePlan(
        kind="topic",
        src="self/stray-note.md",
        dst="ops/observations/stray-note.md",
        reason="topic=observation (confidence=0.90)",
    )
    assert is_move_protected(plan) is True


def test_is_move_protected_true_for_protected_dst_topic_plan():
    """A topic-move plan whose DESTINATION lands inside a protected namespace
    must be flagged even when the source is ordinary — mirrors relocate()'s
    destination guard (namespace-poisoning prevention, vault.py concern 6).
    """
    plan = SweepMovePlan(
        kind="topic",
        src="random-folder/note.md",
        dst="templates/note.md",
        reason="topic=observation (confidence=0.90)",
    )
    assert is_move_protected(plan) is True


def test_is_move_protected_false_for_ordinary_topic_plan():
    """A ordinary topic-move plan with neither src nor dst protected must not
    be flagged — the guard must not over-filter normal relocations."""
    plan = plan_topic_move("random/a.md", "accomplishment", confidence=0.9)
    assert plan is not None
    assert is_move_protected(plan) is False


# --- propose_topic_move: staging-dir demotion guard (production incident 2026-08-01) ---
#
# TOPIC_VAULT_PATH maps the durable-knowledge topics "learning"/"reference"
# (and the fallback "unsure") to "inbox", which is an intake STAGING area for
# NEW unprocessed content, not a canonical filing destination. Before this
# fix, propose_topic_move misread that mapping as "where does this note
# belong" and relocated already-Reduced notes (e.g. notes/foo.md) back into
# inbox/ — which is excluded from warm-tier recall (RecallConfig.exclude_prefixes),
# permanently hiding the note. These tests pin that a note already living
# outside inbox/ is never proposed for a move INTO a staging dir.


def test_reduced_note_is_never_demoted_into_inbox():
    """The actual production bug: a note Reduce already promoted to notes/
    with topic 'reference' must NOT be dragged back into inbox/."""
    assert propose_topic_move("notes/creative-reset.md", "reference") is None


def test_reduced_learning_note_is_never_demoted_into_inbox():
    assert propose_topic_move("notes/creative-reset.md", "learning") is None


def test_unsure_topic_never_demotes_existing_note_into_inbox():
    assert propose_topic_move("notes/creative-reset.md", "unsure") is None


def test_accomplishment_topic_move_still_proposed_unchanged():
    """Non-regression: topics with a real canonical filing dir (not a
    staging dir) must keep proposing moves exactly as before."""
    assert (
        propose_topic_move("notes/x.md", "accomplishment")
        == "ops/accomplishments/x.md"
    )


def test_already_correctly_placed_accomplishment_note_still_returns_none():
    """Non-regression: a note already in its canonical dir is still a no-op."""
    assert propose_topic_move("ops/accomplishments/x.md", "accomplishment") is None


def test_is_move_protected_uses_segment_boundary_matching():
    """Near-miss paths that merely start with a protected prefix's letters
    (e.g. ``sentinelsomething/``) must NOT be flagged — proves is_move_protected
    delegates to the real app.vault.is_protected_path (segment-boundary
    matching) rather than a naive substring/reimplemented check."""
    plan = plan_noise_trash("sentinelsomething/x.md", today="2026-08-01")
    assert is_move_protected(plan) is False
