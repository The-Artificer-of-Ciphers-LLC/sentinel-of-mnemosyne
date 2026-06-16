from __future__ import annotations

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
    assert is_in_topic_dir("journal/2026-06-16/a.md", "journal/2026-06-17")
    assert propose_topic_move("accomplishments/a.md", "accomplishment") is None


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
        "dst": "accomplishments/a.md",
        "reason": "topic=accomplishment (confidence=0.95)",
    }


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
