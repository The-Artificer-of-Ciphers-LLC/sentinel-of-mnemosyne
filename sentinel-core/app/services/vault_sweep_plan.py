"""Side-effect-free move planning for Vault sweeps."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SweepMovePlan:
    """A planned Vault move before dry-run reporting or live execution."""

    kind: Literal["trash", "topic"]
    src: str
    dst: str
    reason: str

    def asdict(self) -> dict:
        return {
            "kind": self.kind,
            "src": self.src,
            "dst": self.dst,
            "reason": self.reason,
        }


def is_in_topic_dir(path: str, topic_dir: str) -> bool:
    """True when ``path`` is already within ``topic_dir``.

    Handles the journal nested-date case: ``journal/2026-04-27/foo.md`` is
    considered in-dir for any ``journal/...`` topic_dir, not just exact
    same-day match. The sweeper does not relocate journal entries between
    days, only flags a wrong-topic placement.
    """
    if not topic_dir:
        return False
    family_root = topic_dir.split("/", 1)[0] + "/"
    return path.startswith(family_root)


def propose_topic_move(
    src_path: str, topic: str, *, today: str | None = None
) -> str | None:
    """Return the destination path a topic move would use."""
    from app.services.note_classifier import topic_dir_for

    topic_dir = topic_dir_for(topic, today=today)
    if not topic_dir:
        return None
    if is_in_topic_dir(src_path, topic_dir):
        return None
    filename = src_path.rsplit("/", 1)[-1]
    return f"{topic_dir}/{filename}"


def plan_noise_trash(src_path: str, *, today: str) -> SweepMovePlan:
    filename = src_path.rsplit("/", 1)[-1]
    return SweepMovePlan(
        kind="trash",
        src=src_path,
        dst=f"_trash/{today}/{filename}",
        reason="cheap-filter:noise",
    )


def plan_topic_move(
    src_path: str,
    topic: str,
    *,
    confidence: float,
    today: str | None = None,
) -> SweepMovePlan | None:
    dst = propose_topic_move(src_path, topic, today=today)
    if dst is None:
        return None
    return SweepMovePlan(
        kind="topic",
        src=src_path,
        dst=dst,
        reason=f"topic={topic} (confidence={confidence:.2f})",
    )


def plan_duplicate_trash(
    src_path: str,
    keeper_path: str,
    *,
    confidence: float,
    today: str,
) -> SweepMovePlan:
    filename = src_path.rsplit("/", 1)[-1]
    return SweepMovePlan(
        kind="trash",
        src=src_path,
        dst=f"_trash/{today}/{filename}",
        reason=f"duplicate of {keeper_path} (cosine≥0.92, conf={confidence:.1f})",
    )
