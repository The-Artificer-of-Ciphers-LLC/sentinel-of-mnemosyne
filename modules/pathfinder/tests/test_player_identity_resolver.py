"""Wave 0 RED tests for app.player_identity_resolver (Phase 37-01).

Locks the contracts for:
  * PVL-06 — deterministic, stable player_slug derivation from Discord user ID.
  * FCM-01 — Foundry speaker resolution precedence: alias > NPC roster > PC
    character_name > unknown.

Imports of the (yet-nonexistent) resolver symbols happen inside each test body
(function-scope import pattern from Phase 33-01 STATE.md decision) so pytest
collection succeeds. Tests fail at call-time with ImportError until Wave 1
(plan 37-06) lands the implementation.

Per the Behavioral-Test-Only Rule, every test calls the function under test
and asserts on its observable return value — no source-grep, no tautologies.
"""
from __future__ import annotations

import os

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("SENTINEL_CORE_URL", "http://sentinel-core:8000")
os.environ.setdefault("OBSIDIAN_BASE_URL", "http://localhost:27123")
os.environ.setdefault("OBSIDIAN_API_KEY", "")
os.environ.setdefault("LITELLM_MODEL", "openai/local-model")
os.environ.setdefault("LITELLM_API_BASE", "http://localhost:1234/v1")

import pytest


# ---------------------------------------------------------------------------
# PVL-06 — slug derivation
# ---------------------------------------------------------------------------


def test_slug_deterministic():
    """Same Discord user id always derives the same slug, prefix `p-`, length 14."""
    from app.player_identity_resolver import slug_from_discord_user_id

    a = slug_from_discord_user_id("u-1")
    b = slug_from_discord_user_id("u-1")
    assert a == b
    assert isinstance(a, str)
    assert a.startswith("p-")
    assert len(a) == 14


def test_slug_uniqueness():
    """Different Discord user ids derive different slugs."""
    from app.player_identity_resolver import slug_from_discord_user_id

    assert slug_from_discord_user_id("u-1") != slug_from_discord_user_id("u-2")


def test_slug_rejects_non_str():
    """Non-string input raises TypeError; empty string raises ValueError."""
    from app.player_identity_resolver import slug_from_discord_user_id

    with pytest.raises(TypeError):
        slug_from_discord_user_id(12345)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        slug_from_discord_user_id("")


def test_alias_override_wins():
    """alias_map entry for a Discord user id overrides the hash-derived slug."""
    from app.player_identity_resolver import slug_from_discord_user_id

    alias_map = {"u-1": "p-custom"}
    assert slug_from_discord_user_id("u-1", alias_map=alias_map) == "p-custom"


# ---------------------------------------------------------------------------
# FCM-01 — Foundry speaker precedence (alias > npc_roster > character_name > unknown)
# ---------------------------------------------------------------------------


def test_foundry_speaker_precedence_alias_first():
    """Alias map maps Foundry actor -> Discord user id; alias wins over PC name match.

    Pitfall 7 regression: even though "Valeros" also matches an onboarded player's
    character_name, the alias entry for "Valeros" -> "u-1" must take precedence.
    """
    from app.player_identity_resolver import (
        resolve_foundry_speaker,
        slug_from_discord_user_id,
    )

    alias_map = {"Valeros": "u-1"}
    npc_roster: dict = {}
    pc_character_names = {"Valeros": "p-someone-else"}

    kind, ident = resolve_foundry_speaker(
        actor="Valeros",
        alias_map=alias_map,
        npc_roster=npc_roster,
        pc_character_names=pc_character_names,
    )
    assert kind == "player"
    assert ident == slug_from_discord_user_id("u-1")


def test_foundry_speaker_precedence_npc_roster_second():
    """NPC roster match returns ('npc', npc_slug) when no alias matches."""
    from app.player_identity_resolver import resolve_foundry_speaker

    alias_map: dict = {}
    npc_roster = {"Goblin Boss": "goblin-boss"}
    pc_character_names: dict = {}

    kind, ident = resolve_foundry_speaker(
        actor="Goblin Boss",
        alias_map=alias_map,
        npc_roster=npc_roster,
        pc_character_names=pc_character_names,
    )
    assert kind == "npc"
    assert ident == "goblin-boss"


def test_foundry_speaker_precedence_character_name_third():
    """PC character_name match returns ('player', that_slug) when alias+roster miss."""
    from app.player_identity_resolver import resolve_foundry_speaker

    alias_map: dict = {}
    npc_roster: dict = {}
    pc_character_names = {"Aria": "p-aria-slug-x"}

    kind, ident = resolve_foundry_speaker(
        actor="Aria",
        alias_map=alias_map,
        npc_roster=npc_roster,
        pc_character_names=pc_character_names,
    )
    assert kind == "player"
    assert ident == "p-aria-slug-x"


def test_foundry_speaker_unknown_falls_through():
    """Actor not in any map returns ('unknown', raw_actor_token)."""
    from app.player_identity_resolver import resolve_foundry_speaker

    kind, ident = resolve_foundry_speaker(
        actor="Random Bandit",
        alias_map={},
        npc_roster={},
        pc_character_names={},
    )
    assert kind == "unknown"
    assert ident == "Random Bandit"
