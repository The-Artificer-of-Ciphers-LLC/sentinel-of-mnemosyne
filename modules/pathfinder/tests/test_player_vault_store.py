"""Wave 0 RED tests for app.player_vault_store (Phase 37-01).

Locks the contract for PVL-07 — per-player slug-prefix isolation. Every
Obsidian path written by the store must live under
`mnemosyne/pf2e/players/{player_slug}/...` and the store must reject any
attempt (via traversal segments or malformed slugs) to escape that prefix.

Function-scope imports (Phase 33-01 pattern) so pytest collection succeeds
before Wave 1 lands the implementation. Tests fail with ImportError until
then — that is the RED state.

Per the Behavioral-Test-Only Rule, every test calls the function under test
with an AsyncMock obsidian client and asserts on the call_args of the
observable I/O — no source-grep, no tautologies.
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

import pytest


# ---------------------------------------------------------------------------
# PVL-07 — read/write paths land under the slug prefix
# ---------------------------------------------------------------------------


async def test_read_profile_calls_correct_path():
    """read_profile('p-abc', obsidian=...) reads players/p-abc/profile.md."""
    from app.player_vault_store import read_profile

    obsidian = AsyncMock()
    obsidian.get_note = AsyncMock(return_value="---\nonboarded: true\n---\n")

    await read_profile("p-abc", obsidian=obsidian)

    obsidian.get_note.assert_awaited_once_with("mnemosyne/pf2e/players/p-abc/profile.md")


async def test_write_profile_calls_put_note_with_slug_path():
    """write_profile('p-abc', {...}, obsidian=...) PUTs to players/p-abc/profile.md."""
    from app.player_vault_store import write_profile

    obsidian = AsyncMock()
    obsidian.put_note = AsyncMock(return_value=None)

    await write_profile(
        "p-abc",
        {"character_name": "Aria", "preferred_name": "Ari", "onboarded": True},
        obsidian=obsidian,
    )

    assert obsidian.put_note.await_count == 1
    call_args = obsidian.put_note.await_args
    path_arg = call_args.args[0] if call_args.args else call_args.kwargs.get("path")
    assert path_arg == "mnemosyne/pf2e/players/p-abc/profile.md"


async def test_append_to_inbox_uses_get_then_put():
    """append_to_inbox reads existing inbox.md, appends, and PUTs the merged content."""
    from app.player_vault_store import append_to_inbox

    obsidian = AsyncMock()
    obsidian.get_note = AsyncMock(return_value="# Inbox\n- old\n")
    obsidian.put_note = AsyncMock(return_value=None)

    await append_to_inbox("p-abc", "- new entry", obsidian=obsidian)

    # get_note must be called for the inbox path
    obsidian.get_note.assert_awaited()
    inbox_path = "mnemosyne/pf2e/players/p-abc/inbox.md"
    assert any(
        (call.args and call.args[0] == inbox_path)
        or call.kwargs.get("path") == inbox_path
        for call in obsidian.get_note.await_args_list
    )

    # put_note must be called with content that contains BOTH old and new lines
    assert obsidian.put_note.await_count == 1
    put_call = obsidian.put_note.await_args
    put_path = put_call.args[0] if put_call.args else put_call.kwargs.get("path")
    put_body = put_call.args[1] if len(put_call.args) > 1 else put_call.kwargs.get("content")
    assert put_path == inbox_path
    assert "- old" in put_body
    assert "- new entry" in put_body
    # New entry should follow the old entry (append semantics, not prepend)
    assert put_body.index("- old") < put_body.index("- new entry")


def test_store_rejects_path_outside_slug_prefix():
    """The path resolver helper rejects traversal and malformed slugs (PVL-07 guard)."""
    from app.player_vault_store import _resolve_player_path

    # Traversal in the relative path: must not escape the slug prefix.
    with pytest.raises(ValueError):
        _resolve_player_path("p-abc", "../p-xyz/profile.md")

    # Malformed slugs.
    with pytest.raises(ValueError):
        _resolve_player_path("..", "profile.md")
    with pytest.raises(ValueError):
        _resolve_player_path("p/abc", "profile.md")
    with pytest.raises(ValueError):
        _resolve_player_path(".hidden", "profile.md")


async def test_read_npc_knowledge_uses_per_player_path():
    """read_npc_knowledge reads players/{slug}/npcs/{npc}.md, NOT the global npcs/ path."""
    from app.player_vault_store import read_npc_knowledge

    obsidian = AsyncMock()
    obsidian.get_note = AsyncMock(return_value="# Goblin notes\n")

    await read_npc_knowledge("p-abc", "goblin", obsidian=obsidian)

    expected = "mnemosyne/pf2e/players/p-abc/npcs/goblin.md"
    obsidian.get_note.assert_awaited_once_with(expected)
    # Hard regression check: never the global Phase 29 NPC path for the per-player API.
    for call in obsidian.get_note.await_args_list:
        path = call.args[0] if call.args else call.kwargs.get("path", "")
        assert path != "mnemosyne/pf2e/npcs/goblin.md"


async def test_per_player_isolation_assertion():
    """Every Obsidian path arg for slug 'p-abc' contains '/players/p-abc/' (PVL-07)."""
    from app.player_vault_store import (
        append_to_inbox,
        read_npc_knowledge,
        read_profile,
        write_profile,
    )

    slug = "p-abc"
    obsidian = AsyncMock()
    obsidian.get_note = AsyncMock(return_value="")
    obsidian.put_note = AsyncMock(return_value=None)

    await read_profile(slug, obsidian=obsidian)
    await write_profile(slug, {"onboarded": True}, obsidian=obsidian)
    await append_to_inbox(slug, "- entry", obsidian=obsidian)
    await read_npc_knowledge(slug, "goblin", obsidian=obsidian)

    expected_prefix = f"/players/{slug}/"
    all_calls = (
        list(obsidian.get_note.await_args_list)
        + list(obsidian.put_note.await_args_list)
    )
    assert all_calls, "expected at least one Obsidian I/O call"
    for call in all_calls:
        path = call.args[0] if call.args else call.kwargs.get("path", "")
        assert expected_prefix in path, (
            f"PVL-07 isolation violation: path {path!r} missing {expected_prefix!r}"
        )
