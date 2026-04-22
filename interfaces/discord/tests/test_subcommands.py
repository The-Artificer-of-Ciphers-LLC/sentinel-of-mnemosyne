"""Tests for Discord bot subcommand routing — RD-09."""
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Stub out discord before importing bot.py (no discord.py in test env)
# ---------------------------------------------------------------------------


class _DiscordClientStub:
    def __init__(self, **kwargs):
        pass


class _IntentsStub:
    message_content = False

    @classmethod
    def default(cls):
        return cls()


_app_commands_stub = types.ModuleType("discord.app_commands")
_app_commands_stub.CommandTree = MagicMock()
_app_commands_stub.describe = lambda **_: (lambda f: f)

_discord_stub = types.ModuleType("discord")
_discord_stub.Client = _DiscordClientStub
_discord_stub.Intents = _IntentsStub
_discord_stub.Message = object
_discord_stub.Thread = object
_discord_stub.ChannelType = MagicMock()
_discord_stub.Forbidden = Exception
_discord_stub.HTTPException = Exception
_discord_stub.Interaction = object
_discord_stub.app_commands = _app_commands_stub
sys.modules.setdefault("discord", _discord_stub)
sys.modules.setdefault("discord.app_commands", _app_commands_stub)

os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token-for-pytest")
os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")

_discord_dir = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(_discord_dir))
# Add repo root so `shared` package is importable
_repo_root = os.path.join(os.path.dirname(__file__), "..", "..", "..")
sys.path.insert(0, os.path.abspath(_repo_root))

import bot  # noqa: E402


# ---------------------------------------------------------------------------
# Subcommand routing tests
# ---------------------------------------------------------------------------


async def test_help_subcommand_returns_help_text():
    """handle_sentask_subcommand('help', '', user) returns the help string."""
    result = await bot.handle_sentask_subcommand("help", "", "user123")
    assert isinstance(result, str)
    assert len(result) > 0
    assert ":help" in result or "help" in result.lower()


async def test_known_subcommand_calls_core():
    """handle_sentask_subcommand('goals', '', user) calls Core with the goals prompt."""
    with patch("bot._call_core", new=AsyncMock(return_value="Your goals are: ...")) as mock_core:
        result = await bot.handle_sentask_subcommand("goals", "", "user123")

    mock_core.assert_called_once()
    call_args = mock_core.call_args
    assert call_args[0][0] == "user123"
    assert isinstance(call_args[0][1], str)
    assert len(call_args[0][1]) > 0
    assert result == "Your goals are: ..."


async def test_unknown_subcommand_returns_fallback():
    """handle_sentask_subcommand with unknown command returns non-empty fallback string."""
    result = await bot.handle_sentask_subcommand("nonexistent_command_xyz", "", "user123")
    assert isinstance(result, str)
    assert len(result) > 0


async def test_subcommand_prompts_dict_populated():
    """_SUBCOMMAND_PROMPTS dict has entries for expected commands."""
    assert "next" in bot._SUBCOMMAND_PROMPTS
    assert "health" in bot._SUBCOMMAND_PROMPTS
    assert "goals" in bot._SUBCOMMAND_PROMPTS
    assert "tasks" in bot._SUBCOMMAND_PROMPTS


async def test_plugin_subcommand_routing():
    """handle_sentask_subcommand('plugin:health', '', user) routes to plugin prompts."""
    with patch("bot._call_core", new=AsyncMock(return_value="vault health ok")) as mock_core:
        result = await bot.handle_sentask_subcommand("plugin:health", "", "user123")

    mock_core.assert_called_once()
    assert result == "vault health ok"


# ---------------------------------------------------------------------------
# Phase 26 expansion: :seed, :check, :pipeline subcommand coverage (2B-01, 2B-04)
# ---------------------------------------------------------------------------


async def test_seed_subcommand_calls_core():
    """handle_sentask_subcommand('seed', 'raw text', user) calls _call_core with inbox seed prompt."""
    with patch("bot._call_core", new=AsyncMock(return_value="Seeded.")) as mock_core:
        result = await bot.handle_sentask_subcommand("seed", "raw text for inbox", "user123")

    mock_core.assert_called_once()
    call_args = mock_core.call_args
    # First positional arg is user_id, second is the prompt string
    assert call_args[0][0] == "user123"
    prompt = call_args[0][1]
    assert "inbox" in prompt.lower(), f"Expected 'inbox' in seed prompt, got: {prompt!r}"
    assert "raw text for inbox" in prompt, f"Seed args not in prompt: {prompt!r}"
    assert result == "Seeded."


async def test_seed_subcommand_no_args_returns_usage():
    """handle_sentask_subcommand('seed', '', user) returns usage string without calling Core."""
    with patch("bot._call_core", new=AsyncMock()) as mock_core:
        result = await bot.handle_sentask_subcommand("seed", "", "user123")

    mock_core.assert_not_called()
    assert ":seed" in result, f"Expected ':seed' in usage hint, got: {result!r}"


async def test_check_subcommand_calls_core():
    """:check is a no-arg standard subcommand; it routes through _SUBCOMMAND_PROMPTS dict to _call_core."""
    assert "check" in bot._SUBCOMMAND_PROMPTS, (
        "':check' key missing from _SUBCOMMAND_PROMPTS — 2B-04 requirement not met"
    )
    with patch("bot._call_core", new=AsyncMock(return_value="Check complete.")) as mock_core:
        result = await bot.handle_sentask_subcommand("check", "", "user123")

    mock_core.assert_called_once()
    call_args = mock_core.call_args
    assert call_args[0][0] == "user123"
    assert isinstance(call_args[0][1], str) and len(call_args[0][1]) > 0
    assert result == "Check complete."


async def test_pipeline_subcommand_calls_core():
    """:pipeline is a no-arg standard subcommand; it routes through _SUBCOMMAND_PROMPTS dict to _call_core."""
    assert "pipeline" in bot._SUBCOMMAND_PROMPTS, (
        "':pipeline' key missing from _SUBCOMMAND_PROMPTS — 2B-01 requirement not met"
    )
    with patch("bot._call_core", new=AsyncMock(return_value="Pipeline running.")) as mock_core:
        result = await bot.handle_sentask_subcommand("pipeline", "", "user123")

    mock_core.assert_called_once()
    call_args = mock_core.call_args
    assert call_args[0][0] == "user123"
    assert isinstance(call_args[0][1], str) and len(call_args[0][1]) > 0
    assert result == "Pipeline running."


# ---------------------------------------------------------------------------
# Phase 29 — :pf npc dispatch tests (29-03)
# ---------------------------------------------------------------------------


async def test_pf_dispatch_exists():
    """bot module has a _pf_dispatch function."""
    assert hasattr(bot, "_pf_dispatch"), "_pf_dispatch not found in bot module"
    import inspect
    assert inspect.iscoroutinefunction(bot._pf_dispatch), "_pf_dispatch must be async"


async def test_valid_relations_constant_exists():
    """bot module has a _VALID_RELATIONS frozenset with the closed enum."""
    assert hasattr(bot, "_VALID_RELATIONS"), "_VALID_RELATIONS not found in bot module"
    assert isinstance(bot._VALID_RELATIONS, frozenset)
    for expected in {"knows", "trusts", "hostile-to", "allied-with", "fears", "owes-debt"}:
        assert expected in bot._VALID_RELATIONS, f"{expected!r} missing from _VALID_RELATIONS"


async def test_handle_sentask_subcommand_accepts_attachments_kwarg():
    """handle_sentask_subcommand signature accepts attachments keyword argument."""
    import inspect
    sig = inspect.signature(bot.handle_sentask_subcommand)
    assert "attachments" in sig.parameters, (
        "handle_sentask_subcommand must accept 'attachments' keyword argument"
    )
    param = sig.parameters["attachments"]
    assert param.default is None, "attachments default must be None"


async def test_pf_subcommand_routes_to_pf_dispatch():
    """handle_sentask_subcommand('pf', ...) routes to _pf_dispatch, not _call_core."""
    with patch("bot._pf_dispatch", new=AsyncMock(return_value="pf response")) as mock_dispatch, \
         patch("bot._call_core", new=AsyncMock(return_value="core response")) as mock_core:
        result = await bot.handle_sentask_subcommand("pf", "npc show Varek", "user123")

    mock_dispatch.assert_called_once()
    mock_core.assert_not_called()
    assert result == "pf response"


async def test_pf_dispatch_create():
    """_pf_dispatch('npc create Varek | gnome rogue', user_id) calls post_to_module create path."""
    mock_result = {
        "name": "Varek",
        "slug": "varek",
        "path": "mnemosyne/pf2e/npcs/varek.md",
        "ancestry": "Gnome",
        "class": "Rogue",
        "level": 1,
    }
    with patch.object(bot._sentinel_client, "post_to_module", new=AsyncMock(return_value=mock_result)) as mock_ptm:
        result = await bot._pf_dispatch("npc create Varek | gnome rogue", "user123")

    mock_ptm.assert_called_once()
    call_args = mock_ptm.call_args
    assert call_args[0][0] == "modules/pathfinder/npc/create"
    payload = call_args[0][1]
    assert payload["name"] == "Varek"
    assert "gnome rogue" in payload["description"]
    assert "Varek" in result


async def test_pf_dispatch_relate_invalid():
    """_pf_dispatch with invalid relation type rejects before calling module."""
    with patch.object(bot._sentinel_client, "post_to_module", new=AsyncMock()) as mock_ptm:
        result = await bot._pf_dispatch("npc relate Varek | enemies-with | baron", "user123")

    # post_to_module must NOT be called — validation happens in bot before module call
    mock_ptm.assert_not_called()
    assert "enemies-with" in result or "not a valid" in result.lower() or "valid" in result.lower()


async def test_pf_dispatch_relate_valid():
    """_pf_dispatch with pipe-separated relate args calls post_to_module relate path."""
    mock_result = {"status": "added"}
    with patch.object(bot._sentinel_client, "post_to_module", new=AsyncMock(return_value=mock_result)) as mock_ptm:
        result = await bot._pf_dispatch("npc relate Varek | trusts | baron-aldric", "user123")

    mock_ptm.assert_called_once()
    call_args = mock_ptm.call_args
    assert call_args[0][0] == "modules/pathfinder/npc/relate"
    payload = call_args[0][1]
    assert payload["name"] == "Varek"
    assert payload["relation"] == "trusts"
    assert payload["target"] == "baron-aldric"


async def test_pf_dispatch_show():
    """_pf_dispatch('npc show Varek', user_id) calls post_to_module show path."""
    mock_result = {
        "name": "Varek",
        "level": 5,
        "ancestry": "Gnome",
        "class": "Rogue",
        "personality": "Nervous",
        "backstory": "Fled the guild",
        "mood": "neutral",
        "path": "mnemosyne/pf2e/npcs/varek.md",
    }
    with patch.object(bot._sentinel_client, "post_to_module", new=AsyncMock(return_value=mock_result)) as mock_ptm:
        result = await bot._pf_dispatch("npc show Varek", "user123")

    mock_ptm.assert_called_once()
    call_args = mock_ptm.call_args
    assert call_args[0][0] == "modules/pathfinder/npc/show"
    assert call_args[0][1]["name"] == "Varek"
    assert "Varek" in result


async def test_pf_dispatch_unknown_noun():
    """_pf_dispatch with unknown noun returns error without calling module."""
    with patch.object(bot._sentinel_client, "post_to_module", new=AsyncMock()) as mock_ptm:
        result = await bot._pf_dispatch("monster create Goblin", "user123")

    mock_ptm.assert_not_called()
    assert "monster" in result or "Unknown" in result


async def test_pf_dispatch_import_no_attachment():
    """_pf_dispatch('npc import', user_id, attachments=None) returns usage string."""
    with patch.object(bot._sentinel_client, "post_to_module", new=AsyncMock()) as mock_ptm:
        result = await bot._pf_dispatch("npc import", "user123", attachments=None)

    mock_ptm.assert_not_called()
    assert "attach" in result.lower() or "import" in result.lower()
