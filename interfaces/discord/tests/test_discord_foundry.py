"""Tests for build_foundry_roll_embed (FVT-03, D-14, D-16).

Wave 0 RED stubs — symbols referenced land in:
  - bot.build_foundry_roll_embed (Wave 2 / Plan 35-03)

All discord.* imports use the centralized _EmbedStub from conftest.py.
Do NOT re-stub discord here — conftest.py already handles it (L-5 prevention).
"""
import os

os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token-for-pytest")
os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")

import bot  # noqa: E402 — conftest.py stubs discord before this import


# ---------------------------------------------------------------------------
# FVT-03 — Discord embed builder for Foundry roll events (D-16)
# ---------------------------------------------------------------------------


async def test_embed_critical_success():
    """build_foundry_roll_embed: criticalSuccess → 🎯 title, actor vs target, narrative, roll/DC/item footer (D-16, FVT-03)."""
    data = {
        "outcome": "criticalSuccess",
        "actor_name": "Seraphina",
        "target_name": "Goblin Warchief",
        "narrative": "Seraphina's blade found the gap in the warchief's armor.",
        "roll_total": 28,
        "dc": 14,
        "dc_hidden": False,
        "item_name": "Longsword +1",
        "roll_type": "attack-roll",
    }
    embed = bot.build_foundry_roll_embed(data)
    assert "🎯" in embed.title
    assert "Critical Hit!" in embed.title
    assert "Seraphina" in embed.title
    assert "Goblin Warchief" in embed.title
    assert embed.description is not None and "Seraphina's blade" in embed.description
    assert "Roll: 28" in embed.footer_text
    assert "DC/AC: 14" in embed.footer_text
    assert "Longsword +1" in embed.footer_text


async def test_embed_hidden_dc():
    """build_foundry_roll_embed: dc_hidden=True → 'DC: [hidden]' in footer, no 'DC/AC' (D-16, FVT-03)."""
    data = {
        "outcome": "success",
        "actor_name": "Seraphina",
        "target_name": None,
        "narrative": "",
        "roll_total": 18,
        "dc": None,
        "dc_hidden": True,
        "item_name": None,
        "roll_type": "saving-throw",
    }
    embed = bot.build_foundry_roll_embed(data)
    assert "DC: [hidden]" in embed.footer_text
    assert "DC/AC" not in embed.footer_text
