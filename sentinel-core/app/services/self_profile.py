"""Self-profile completeness checks (onboarding, GH issue #38 core half).

The hot tier (``RecallConfig.self_paths``) is read into EVERY message, but the
only thing that ever writes the four canonical ``self/`` files is
``recall._ensure_self_stub`` / ``recall.build_self_stub`` — a lazy stub-create
on first read-miss. Nothing ever prompted an operator to replace that stub
with real content, so production sat for months with untouched placeholders
that the Sentinel then paraphrased back as if they were the user's real
profile.

This module answers one question: "has the operator actually filled in their
profile, or is it still the seeded stub?" — via ``profile_status`` — and
exposes ``is_unfilled`` as the pure primitive that answers it per-path.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.services.recall import _CANONICAL_SELF_STUB_PATHS, build_self_stub

if TYPE_CHECKING:
    from app.vault import Vault

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Canonical profile paths
# ---------------------------------------------------------------------------

# "Profile completeness" is scoped to EXACTLY the 4 canonical stub-created
# files (self/identity.md, self/methodology.md, self/goals.md,
# self/relationships.md) — imported verbatim from recall._CANONICAL_SELF_STUB_PATHS,
# never duplicated. These are the only paths that have a known stub body to
# diff against (build_self_stub); that stub-diff is the ONLY reliable signal
# this module has for "created but never touched" (see is_unfilled below).
#
# RecallConfig.self_paths is a LARGER hot-tier allowlist — it also includes
# ops/reminders.md and self/learning-areas.md. Those two are deliberately
# excluded from "completeness": recall.py already documents that they are
# read via the plain read-only read_self_context path and are NEVER
# stub-created (D-04 scope), so there is no stub body to compare against and
# no reliable way to tell "operator never wrote this" from "operator wrote
# an empty reminders list on purpose". Treating them as required would make
# "complete" unreachable for a user who legitimately has no reminders yet.
CANONICAL_PROFILE_PATHS: tuple[str, ...] = _CANONICAL_SELF_STUB_PATHS


def is_unfilled(path: str, body: str) -> bool:
    """True when ``body`` is missing/empty/whitespace, or byte-equal (after
    strip) to the seeded stub for ``path``.

    Comparing against ``build_self_stub(path)`` is the ONLY reliable way to
    detect "file was lazily created but never touched" — there is no other
    signal (mtime, a sentinel marker, etc.) available through the Vault REST
    seam. Any user edit — even appending one line after the stub text —
    changes the stripped body and correctly flips this to False; we would
    rather under-detect "unfilled" (false negative on a near-empty edit) than
    ever treat a real edit as still-a-stub.
    """
    if not body or not body.strip():
        return True
    return body.strip() == build_self_stub(path).strip()


def _path_state(path: str, body: str) -> str:
    """Return "missing" | "stub" | "filled" for one profile path's body."""
    if not body or not body.strip():
        return "missing"
    if body.strip() == build_self_stub(path).strip():
        return "stub"
    return "filled"


@dataclass(frozen=True)
class ProfileStatus:
    """Typed result of ``profile_status``.

    ``paths`` maps each canonical profile path to its state: "filled",
    "stub", "missing", or "unknown" (vault read error for that one path —
    fail-soft, never raised).
    """

    paths: dict[str, str] = field(default_factory=dict)
    complete: bool = False
    unfilled: list[str] = field(default_factory=list)


async def profile_status(vault: "Vault") -> ProfileStatus:
    """Read each canonical profile path and classify its fill state.

    Fail-soft per path: a vault read error for one path is caught, logged,
    and recorded as "unknown" (counted as unfilled, since an unreadable file
    cannot be confirmed complete) — it never raises and never aborts the
    remaining paths.
    """
    paths: dict[str, str] = {}
    unfilled: list[str] = []

    for path in CANONICAL_PROFILE_PATHS:
        try:
            body = await vault.read_note(path)
        except Exception as exc:
            logger.warning("profile_status: read failed for %r: %r", path, exc)
            paths[path] = "unknown"
            unfilled.append(path)
            continue

        if not isinstance(body, str):
            body = ""

        state = _path_state(path, body)
        paths[path] = state
        if state != "filled":
            unfilled.append(path)

    return ProfileStatus(paths=paths, complete=not unfilled, unfilled=unfilled)


__all__ = [
    "CANONICAL_PROFILE_PATHS",
    "ProfileStatus",
    "is_unfilled",
    "profile_status",
]
