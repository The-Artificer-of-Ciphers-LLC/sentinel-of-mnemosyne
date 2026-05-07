"""Per-player vault store — slug-prefix isolation gate (PVL-07).

Every read/write goes through `_resolve_player_path` which validates the slug
shape, rejects path-traversal segments, and asserts the resulting path lives
under `mnemosyne/pf2e/players/{slug}/`. This is the single I/O seam — callers
never construct vault paths themselves.

Append helpers use GET-then-PUT (not PATCH heading) per
project_obsidian_patch_constraint memory: PATCH replace-on-missing fails 400
in the wild, so we round-trip the full body.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_PLAYER_NAMESPACE_PREFIX = "mnemosyne/pf2e/players"

# Slug regex: either the canonical hash form (p-{12 hex}) or an operator-mapped
# alias slug (alphanumerics + dash/underscore, 1-40 chars). Must NOT contain
# path separators, dots, or be empty.
_SLUG_RE = re.compile(r"^(?:p-[a-f0-9]{12}|[a-zA-Z0-9_-]{1,40})$")


def _resolve_player_path(slug: str, relative: str) -> str:
    """Validate (slug, relative) and return the vault path under the slug prefix.

    Raises ValueError if:
      - slug is not a string, is empty, contains '/', '..', or starts with '.'
        or otherwise fails the slug regex.
      - relative contains '..' segments, leading '/', or starts with '.'.
      - the resolved path doesn't start with mnemosyne/pf2e/players/{slug}/.
    """
    if not isinstance(slug, str) or not slug:
        raise ValueError(f"player slug must be a non-empty string, got {slug!r}")
    if slug.startswith(".") or "/" in slug or ".." in slug:
        raise ValueError(f"player slug contains forbidden chars: {slug!r}")
    if not _SLUG_RE.match(slug):
        raise ValueError(f"player slug failed shape validation: {slug!r}")

    if not isinstance(relative, str) or not relative:
        raise ValueError(f"relative path must be a non-empty string, got {relative!r}")
    if relative.startswith("/") or relative.startswith("."):
        raise ValueError(f"relative path must not start with '/' or '.': {relative!r}")
    parts = relative.split("/")
    if any(part in ("", "..", ".") for part in parts):
        raise ValueError(f"relative path contains forbidden segment: {relative!r}")

    expected_prefix = f"{_PLAYER_NAMESPACE_PREFIX}/{slug}/"
    full = f"{expected_prefix}{relative}"
    if not full.startswith(expected_prefix):
        # Defensive — string concat can't escape, but assert the invariant.
        raise ValueError(f"resolved path escapes slug prefix: {full!r}")
    return full


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


async def read_profile(slug: str, *, obsidian: Any) -> str | None:
    """Read mnemosyne/pf2e/players/{slug}/profile.md."""
    path = _resolve_player_path(slug, "profile.md")
    return await obsidian.get_note(path)


async def write_profile(slug: str, profile: dict, *, obsidian: Any) -> None:
    """Write the player profile as YAML frontmatter at players/{slug}/profile.md."""
    from app.vault_markdown import build_frontmatter_markdown  # noqa: PLC0415

    path = _resolve_player_path(slug, "profile.md")
    body = build_frontmatter_markdown(profile, body="")
    await obsidian.put_note(path, body)


# ---------------------------------------------------------------------------
# Append helpers (inbox / questions / todo) — GET-then-PUT
# ---------------------------------------------------------------------------


async def _append_via_get_then_put(
    slug: str,
    relative: str,
    entry: str,
    default_scaffold: str,
    *,
    obsidian: Any,
) -> None:
    path = _resolve_player_path(slug, relative)
    existing = await obsidian.get_note(path)
    if existing is None:
        existing = default_scaffold
    if not existing.endswith("\n"):
        existing += "\n"
    merged = existing + entry
    if not merged.endswith("\n"):
        merged += "\n"
    await obsidian.put_note(path, merged)


async def append_to_inbox(slug: str, entry: str, *, obsidian: Any) -> None:
    """Append a line to players/{slug}/inbox.md (GET-then-PUT)."""
    await _append_via_get_then_put(
        slug, "inbox.md", entry, "# Inbox\n", obsidian=obsidian
    )


async def append_to_questions(slug: str, entry: str, *, obsidian: Any) -> None:
    """Append a line to players/{slug}/questions.md (GET-then-PUT)."""
    await _append_via_get_then_put(
        slug, "questions.md", entry, "# Questions\n", obsidian=obsidian
    )


async def append_to_todo(slug: str, entry: str, *, obsidian: Any) -> None:
    """Append a line to players/{slug}/todo.md (GET-then-PUT)."""
    await _append_via_get_then_put(
        slug, "todo.md", entry, "# Todo\n", obsidian=obsidian
    )


# ---------------------------------------------------------------------------
# Per-player NPC knowledge
# ---------------------------------------------------------------------------


async def read_npc_knowledge(
    slug: str, npc_slug: str, *, obsidian: Any
) -> str | None:
    """Read this player's private notes about an NPC at players/{slug}/npcs/{npc}.md.

    Distinct from the global Phase 29 NPC note at mnemosyne/pf2e/npcs/{npc}.md.
    """
    relative = f"npcs/{npc_slug}.md"
    path = _resolve_player_path(slug, relative)
    return await obsidian.get_note(path)


async def write_npc_knowledge(
    slug: str, npc_slug: str, content: str, *, obsidian: Any
) -> None:
    """Write this player's private NPC knowledge note."""
    relative = f"npcs/{npc_slug}.md"
    path = _resolve_player_path(slug, relative)
    await obsidian.put_note(path, content)


# ---------------------------------------------------------------------------
# Canonization (PVL-04) — yellow→green/red rule outcomes with provenance
# ---------------------------------------------------------------------------


async def append_canonization(slug: str, entry: dict, *, obsidian: Any) -> str:
    """Append a canonization line to players/{slug}/canonization.md (GET-then-PUT).

    `entry` shape: {outcome, question_id, rule_text, timestamp_iso}. The
    rendered bullet embeds all three load-bearing fields so the test's
    substring asserts on outcome + question_id hit the body verbatim.

    Returns the resolved vault path so the route layer can include it in the
    JSON response without reconstructing the prefix.
    """
    from datetime import datetime, timezone  # noqa: PLC0415

    path = _resolve_player_path(slug, "canonization.md")
    timestamp_iso = entry.get("timestamp_iso") or datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    )
    outcome = entry["outcome"]
    question_id = entry["question_id"]
    rule_text = entry["rule_text"]
    line = (
        f"- [{outcome}] {timestamp_iso} — question:{question_id} — {rule_text}"
    )

    existing = await obsidian.get_note(path)
    if existing is None:
        existing = "# Canonization\n"
    if not existing.endswith("\n"):
        existing += "\n"
    merged = existing + line
    if not merged.endswith("\n"):
        merged += "\n"
    await obsidian.put_note(path, merged)
    return path


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


async def list_player_files(slug: str, *, obsidian: Any) -> list[str]:
    """List all vault files under players/{slug}/ (recursive)."""
    # Validate slug shape via _resolve_player_path with a sentinel relative.
    _resolve_player_path(slug, "_probe")
    prefix = f"{_PLAYER_NAMESPACE_PREFIX}/{slug}/"
    return await obsidian.list_directory(prefix)
