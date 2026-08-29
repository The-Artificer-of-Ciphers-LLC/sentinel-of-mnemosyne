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

    Handles the journal nested-date case: ``ops/journal/2026-04-27/foo.md`` is
    considered in-dir for any ``ops/journal/...`` topic_dir, not just exact
    same-day match. The sweeper does not relocate journal entries between
    days, only flags a wrong-topic placement.

    Taxonomy-aware family-root derivation (Pitfall 2 fix): under the PARA
    taxonomy, ``journal``, ``accomplishment``, and ``observation`` all nest
    under the shared ``ops/`` parent, so truncating to the first path segment
    (the old single-segment heuristic) would collapse all three into one
    indistinguishable ``ops/`` family. Only the nested-date journal family
    uses a truncated (day-agnostic) root; every other topic dir must match
    on its FULL path, not just its first segment.
    """
    if not topic_dir:
        return False
    if topic_dir.startswith("ops/journal/") or topic_dir == "ops/journal":
        family_root = "ops/journal/"  # nested-date family, any day matches
    else:
        family_root = topic_dir.rstrip("/") + "/"  # exact-match family
    return path.startswith(family_root)


def propose_topic_move(
    src_path: str, topic: str, *, today: str | None = None
) -> str | None:
    """Return the destination path a topic move would use."""
    from app.services.note_classifier import STAGING_DIRS, topic_dir_for

    topic_dir = topic_dir_for(topic, today=today)
    if not topic_dir:
        return None
    # Staging dirs are intake queues, never move an existing note into one
    # (see STAGING_DIRS).
    if topic_dir.rstrip("/") in STAGING_DIRS:
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


def is_move_protected(plan: SweepMovePlan) -> bool:
    """True when a LIVE sweep would REFUSE ``plan`` via the protected-namespace guard.

    Dry-run/live parity fix: ``ObsidianVault.move_to_trash`` refuses whenever
    the SOURCE path is protected, and ``ObsidianVault.relocate`` refuses
    whenever EITHER the source OR the destination is protected (the
    destination check exists to stop namespace poisoning — moving arbitrary
    content INTO ``sentinel/``, ``self/``, ``security/``, or ``templates/``).
    Checking both ``plan.src`` and ``plan.dst`` here means a dry-run report
    reflects exactly what the live path would do for every move kind: for
    ``kind="trash"`` the dst is always under ``_trash/`` (never protected),
    so this reduces to the src-only check ``move_to_trash`` performs; for
    ``kind="topic"`` this mirrors ``relocate``'s dual guard.

    Reuses ``app.vault.is_protected_path`` (segment-boundary matching, e.g.
    it will not false-positive on ``notessentinel/x.md`` matching
    ``sentinel/``) rather than reimplementing that matching logic here.
    Imported locally — mirrors the existing local import of
    ``topic_dir_for`` in ``propose_topic_move`` above — so this
    side-effect-free planning module doesn't acquire a module-load-order
    dependency on ``app.vault``.
    """
    from app.vault import is_protected_path

    return is_protected_path(plan.src) or is_protected_path(plan.dst)
