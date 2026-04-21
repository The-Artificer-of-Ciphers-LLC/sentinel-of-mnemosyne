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
