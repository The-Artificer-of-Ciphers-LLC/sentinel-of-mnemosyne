"""Wave 0 RED tests for app.memory_projection_store (Phase 37-01).

Locks the contracts for:
  * FCM-02 — per-player chat-map four-section build (`## Voice Patterns`,
    `## Notable Moments`, `## Party Dynamics`, `## Chat Timeline`).
  * FCM-03 — two-mode NPC `## Foundry Chat History` append: PATCH heading
    when the section already exists, PUT full body with section appended
    when missing. Detection regex must be anchored to line-start so a
    mid-line literal does not trip it.

Function-scope imports (Phase 33-01 pattern) so pytest collection succeeds
before the implementation lands. Tests fail with ImportError until Wave 1.

Per the Behavioral-Test-Only Rule, every test calls the function under test
with an AsyncMock obsidian client and asserts on the observable I/O shape
(which method called, with what arguments).
"""
from __future__ import annotations

import os

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("SENTINEL_CORE_URL", "http://sentinel-core:8000")
os.environ.setdefault("OBSIDIAN_BASE_URL", "http://localhost:27123")
os.environ.setdefault("OBSIDIAN_API_KEY", "")
os.environ.setdefault("LITELLM_MODEL", "openai/local-model")
os.environ.setdefault("LITELLM_API_BASE", "http://localhost:1234/v1")

from unittest.mock import AsyncMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FOUR_HEADINGS = (
    "## Voice Patterns",
    "## Notable Moments",
    "## Party Dynamics",
    "## Chat Timeline",
)


def _put_call_body(mock_put):
    """Extract the body argument from a single put_note await."""
    assert mock_put.await_count == 1
    call = mock_put.await_args
    if len(call.args) > 1:
        return call.args[0], call.args[1]
    return call.args[0], call.kwargs.get("content")


# ---------------------------------------------------------------------------
# FCM-02 — player map four-section build
# ---------------------------------------------------------------------------


async def test_write_player_map_creates_four_sections():
    """When the player map file does not exist, the PUT body contains all four
    canonical headings even if only one section's lines were supplied."""
    from app.memory_projection_store import write_player_map_section

    obsidian = AsyncMock()
    obsidian.get_note = AsyncMock(return_value=None)
    obsidian.put_note = AsyncMock(return_value=None)

    await write_player_map_section(
        "p-abc",
        section="Chat Timeline",
        lines=["- [t] hi"],
        obsidian=obsidian,
    )

    path, body = _put_call_body(obsidian.put_note)
    assert path == "mnemosyne/pf2e/players/p-abc.md"
    for heading in FOUR_HEADINGS:
        assert heading in body, f"missing heading {heading!r} in new player map body"
    assert "- [t] hi" in body


async def test_write_player_map_preserves_existing_sections():
    """Adding a line under one section must not lose lines under the other three."""
    from app.memory_projection_store import write_player_map_section

    existing = (
        "## Voice Patterns\n"
        "- voice-1\n\n"
        "## Notable Moments\n"
        "- moment-1\n\n"
        "## Party Dynamics\n"
        "- dynamic-1\n\n"
        "## Chat Timeline\n"
        "- old-line\n"
    )
    obsidian = AsyncMock()
    obsidian.get_note = AsyncMock(return_value=existing)
    obsidian.put_note = AsyncMock(return_value=None)

    await write_player_map_section(
        "p-abc",
        section="Chat Timeline",
        lines=["- new-line"],
        obsidian=obsidian,
    )

    _, body = _put_call_body(obsidian.put_note)
    # Pre-existing lines must all survive
    for needle in ("- voice-1", "- moment-1", "- dynamic-1", "- old-line"):
        assert needle in body, f"{needle!r} was dropped from the merged body"
    # New line must be added
    assert "- new-line" in body
    # All four headings must remain
    for heading in FOUR_HEADINGS:
        assert heading in body


# ---------------------------------------------------------------------------
# FCM-03 — NPC `## Foundry Chat History` two-mode append
# ---------------------------------------------------------------------------


async def test_npc_history_append_existing_section():
    """When the section header is already present, use patch_heading and do NOT put_note."""
    from app.memory_projection_store import append_npc_history_row

    npc_text = (
        "---\nname: Goblin\n---\n\n"
        "## Description\n"
        "A small green creature.\n\n"
        "## Foundry Chat History\n"
        "- [2026-01-01T00:00:00Z] earlier-row\n"
    )
    obsidian = AsyncMock()
    obsidian.get_note = AsyncMock(return_value=npc_text)
    obsidian.patch_heading = AsyncMock(return_value=None)
    obsidian.put_note = AsyncMock(return_value=None)

    row = "- [2026-05-07T12:00:00Z] new-row"
    await append_npc_history_row(
        "goblin",
        row=row,
        obsidian=obsidian,
    )

    assert obsidian.patch_heading.await_count == 1
    call = obsidian.patch_heading.await_args
    args, kwargs = call.args, call.kwargs
    # Path must be the Phase 29 NPC path
    path_arg = args[0] if args else kwargs.get("path")
    assert path_arg == "mnemosyne/pf2e/npcs/goblin.md"
    # Heading and content must be supplied; operation must be append
    flat = list(args) + list(kwargs.values())
    assert "Foundry Chat History" in flat
    assert row in flat
    assert kwargs.get("operation") == "append" or "append" in flat
    # And put_note must NOT have been used in the existing-section branch
    assert obsidian.put_note.await_count == 0


async def test_npc_history_create_section_when_missing():
    """When the section header is missing, PUT the full body with section appended.

    patch_heading must NOT be used (the heading does not yet exist to patch).
    """
    from app.memory_projection_store import append_npc_history_row

    npc_text = (
        "---\nname: Goblin\n---\n\n"
        "## Description\n"
        "A small green creature.\n"
    )
    obsidian = AsyncMock()
    obsidian.get_note = AsyncMock(return_value=npc_text)
    obsidian.patch_heading = AsyncMock(return_value=None)
    obsidian.put_note = AsyncMock(return_value=None)

    row = "- [2026-05-07T12:00:00Z] new-row"
    await append_npc_history_row(
        "goblin",
        row=row,
        obsidian=obsidian,
    )

    assert obsidian.put_note.await_count == 1
    path, body = _put_call_body(obsidian.put_note)
    assert path == "mnemosyne/pf2e/npcs/goblin.md"
    # Pre-existing content must survive
    assert "## Description" in body
    assert "A small green creature." in body
    # The section + row must land at the end
    assert "## Foundry Chat History" in body
    assert row in body
    assert body.index("## Foundry Chat History") < body.index(row)
    # patch_heading must NOT be used in the create-section branch
    assert obsidian.patch_heading.await_count == 0


async def test_npc_history_skips_when_npc_note_missing():
    """When the NPC note does not exist (get_note returns None), the store must
    not write — neither put_note nor patch_heading — and must return a sentinel
    indicating the skip."""
    from app.memory_projection_store import append_npc_history_row

    obsidian = AsyncMock()
    obsidian.get_note = AsyncMock(return_value=None)
    obsidian.patch_heading = AsyncMock(return_value=None)
    obsidian.put_note = AsyncMock(return_value=None)

    result = await append_npc_history_row(
        "goblin",
        row="- whatever",
        obsidian=obsidian,
    )

    assert obsidian.put_note.await_count == 0
    assert obsidian.patch_heading.await_count == 0
    # Sentinel return: a string identifying the skip reason, or a dict with a
    # 'skipped' key, or any truthy value mentioning 'missing'/'skipped'.
    rendered = repr(result).lower()
    assert "missing" in rendered or "skipped" in rendered or "skip" in rendered


async def test_section_detection_regex_anchored():
    """The detection regex must be anchored at line start (`^## Foundry Chat History`).

    A note containing the literal text `not a ## Foundry Chat History line` mid-line
    must NOT be misclassified as having the section, so the create-section branch
    runs and put_note is called with the section + row appended.
    """
    from app.memory_projection_store import append_npc_history_row

    npc_text = (
        "---\nname: Goblin\n---\n\n"
        "## Description\n"
        "This is not a ## Foundry Chat History line, just a mention in prose.\n"
    )
    obsidian = AsyncMock()
    obsidian.get_note = AsyncMock(return_value=npc_text)
    obsidian.patch_heading = AsyncMock(return_value=None)
    obsidian.put_note = AsyncMock(return_value=None)

    row = "- [2026-05-07T12:00:00Z] real-row"
    await append_npc_history_row(
        "goblin",
        row=row,
        obsidian=obsidian,
    )

    # Anchored detection must classify this as MISSING -> create-section branch.
    assert obsidian.put_note.await_count == 1
    assert obsidian.patch_heading.await_count == 0
    _, body = _put_call_body(obsidian.put_note)
    # The new section heading must be appended (a real line-anchored heading).
    assert "\n## Foundry Chat History\n" in body or body.endswith(
        "## Foundry Chat History\n" + row + "\n"
    ) or ("## Foundry Chat History" in body and row in body)
    # And the prose mention must still be there.
    assert "not a ## Foundry Chat History line" in body
