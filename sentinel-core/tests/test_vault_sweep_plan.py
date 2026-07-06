from __future__ import annotations

from app.services.note_classifier import topic_dir_for
from app.services.vault_sweep_plan import (
    is_in_topic_dir,
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
