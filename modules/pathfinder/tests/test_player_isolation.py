"""End-to-end PVL-07 isolation regression tests (Phase 37 closeout, plan 37-14).

These tests exercise the full route → orchestrator/store → vault path with the
``app.routes.player.obsidian`` singleton patched to a recording AsyncMock.
The single load-bearing assertion: every list_directory / get_note / put_note
path argument issued during a /player/recall call belongs to the requesting
player's namespace and never leaks into another player's slug-prefixed tree.

Behavioral-Test-Only Rule: assertions are on observable I/O — actual obsidian
method args. No source-grep, no `assert True`, no mock.assert_called as the
sole assertion.
"""
from __future__ import annotations

import os

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("SENTINEL_CORE_URL", "http://sentinel-core:8000")
os.environ.setdefault("OBSIDIAN_BASE_URL", "http://localhost:27123")
os.environ.setdefault("OBSIDIAN_API_KEY", "")
os.environ.setdefault("LITELLM_MODEL", "openai/local-model")
os.environ.setdefault("LITELLM_API_BASE", "http://localhost:1234/v1")

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


_HEADERS = {"X-Sentinel-Key": "test-key-for-pytest"}


def _resolved_slug(user_id: str) -> str:
    from app.player_identity_resolver import slug_from_discord_user_id

    return slug_from_discord_user_id(user_id)


def _onboarded_profile(slug: str) -> str:
    return (
        "---\n"
        "onboarded: true\n"
        "character_name: Aria\n"
        "preferred_name: Ari\n"
        f"slug: {slug}\n"
        "style_preset: Tactician\n"
        "---\n"
    )


def _make_recording_obsidian(slug_a: str, slug_b: str) -> MagicMock:
    """An obsidian client that records every call and returns plausible content
    keyed by which slug's namespace the path falls under.
    """
    a_prefix = f"mnemosyne/pf2e/players/{slug_a}/"
    b_prefix = f"mnemosyne/pf2e/players/{slug_b}/"

    profile_text_a = _onboarded_profile(slug_a)
    profile_text_b = _onboarded_profile(slug_b)

    inbox_text_a = "# Inbox\n\nRemembered: dragon at the gate.\n"
    inbox_text_b = "# Inbox\n\nRemembered: secret heirloom.\n"

    listings: dict[str, list[str]] = {
        a_prefix: [f"{a_prefix}profile.md", f"{a_prefix}inbox.md"],
        b_prefix: [f"{b_prefix}profile.md", f"{b_prefix}inbox.md"],
    }

    async def _get_note(path: str):
        # Alias map probe — empty.
        if path == "mnemosyne/pf2e/players/_aliases.json":
            return None
        if path == f"{a_prefix}profile.md":
            return profile_text_a
        if path == f"{b_prefix}profile.md":
            return profile_text_b
        if path == f"{a_prefix}inbox.md":
            return inbox_text_a
        if path == f"{b_prefix}inbox.md":
            return inbox_text_b
        return None

    async def _list_directory(path: str, *args, **kwargs):
        # Return only paths that legitimately sit under the requested prefix.
        return list(listings.get(path, []))

    obs = MagicMock()
    obs.get_note = AsyncMock(side_effect=_get_note)
    obs.list_directory = AsyncMock(side_effect=_list_directory)
    obs.put_note = AsyncMock(return_value=None)
    obs.patch_heading = AsyncMock(return_value=None)
    return obs


@pytest.mark.asyncio
async def test_two_users_recall_no_cross_leakage():
    """PVL-07 regression: u1's /player/recall touches only u1's namespace.

    Set up two onboarded players. Submit /player/recall for u1. Assert that
    every list_directory and get_note path argument with a player-namespace
    prefix sits under u1's slug — none of them touch u2's slug-prefixed tree.
    """
    slug_a = _resolved_slug("u1")
    slug_b = _resolved_slug("u2")
    assert slug_a != slug_b, "fixture invariant: two users must hash to two slugs"

    obs = _make_recording_obsidian(slug_a, slug_b)
    a_prefix = f"mnemosyne/pf2e/players/{slug_a}/"
    b_prefix = f"mnemosyne/pf2e/players/{slug_b}/"

    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.player.obsidian", obs):
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/player/recall",
                json={"user_id": "u1", "query": "dragon"},
                headers=_HEADERS,
            )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["slug"] == slug_a
    # Recall must surface u1's content — u1 had "dragon at the gate"
    assert any("dragon" in r["snippet"].lower() for r in body["results"]), body

    # Strong invariant: no list_directory / get_note path argument for a
    # player-namespace path may sit under u2's slug.
    list_paths = [c.args[0] for c in obs.list_directory.await_args_list if c.args]
    get_paths = [c.args[0] for c in obs.get_note.await_args_list if c.args]

    namespace_paths = [
        p for p in list_paths + get_paths if isinstance(p, str)
        and p.startswith("mnemosyne/pf2e/players/")
        and not p.endswith("_aliases.json")
    ]
    assert namespace_paths, (
        "expected at least one player-namespace path during recall; "
        f"saw list={list_paths!r} get={get_paths!r}"
    )
    for p in namespace_paths:
        assert p.startswith(a_prefix), (
            f"PVL-07 leak: path {p!r} is outside requesting player's namespace "
            f"{a_prefix!r}"
        )
        assert not p.startswith(b_prefix), (
            f"PVL-07 leak: path {p!r} reaches into other player's namespace "
            f"{b_prefix!r}"
        )


@pytest.mark.asyncio
async def test_npc_writes_isolated_per_player():
    """Two players writing /player/npc for the same NPC name produce two
    distinct paths — one under each player's namespace; never the global
    mnemosyne/pf2e/npcs/{npc_slug}.md path.
    """
    slug_a = _resolved_slug("u1")
    slug_b = _resolved_slug("u2")
    obs = _make_recording_obsidian(slug_a, slug_b)

    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.player.obsidian", obs):
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r1 = await client.post(
                "/player/npc",
                json={"user_id": "u1", "npc_name": "Varek", "note": "ally"},
                headers=_HEADERS,
            )
            r2 = await client.post(
                "/player/npc",
                json={"user_id": "u2", "npc_name": "Varek", "note": "enemy"},
                headers=_HEADERS,
            )
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    assert r1.json()["slug"] == slug_a
    assert r2.json()["slug"] == slug_b

    npc_writes = [
        c.args[0] for c in obs.put_note.await_args_list
        if c.args and "/npcs/" in c.args[0] and c.args[0].endswith("/varek.md")
    ]
    assert len(npc_writes) == 2, (
        f"expected two NPC-knowledge writes (one per player); saw {npc_writes!r}"
    )
    a_path = f"mnemosyne/pf2e/players/{slug_a}/npcs/varek.md"
    b_path = f"mnemosyne/pf2e/players/{slug_b}/npcs/varek.md"
    assert a_path in npc_writes
    assert b_path in npc_writes
    # Critical: the global Phase-29 NPC path must NEVER be touched by /player/npc.
    for w in npc_writes:
        assert not w.startswith("mnemosyne/pf2e/npcs/"), (
            f"PVL-07 violation: /player/npc wrote to global path {w!r}"
        )

    # Cross-namespace check: each write's path-prefix matches its requester.
    a_writes = [p for p in npc_writes if p == a_path]
    b_writes = [p for p in npc_writes if p == b_path]
    assert len(a_writes) == 1
    assert len(b_writes) == 1
