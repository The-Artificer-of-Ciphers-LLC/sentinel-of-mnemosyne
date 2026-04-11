"""Tests for Discord bot subcommand routing (2B-01, 2B-04) — Phase 10 stubs.
All tests in this file are RED until Plan 10-04 implements the command system.
"""
import sys
import os
import types
import pytest
from unittest.mock import AsyncMock, MagicMock

# ---------------------------------------------------------------------------
# Stub out discord before importing bot.py so the module loads without
# discord.py installed in the test environment.
# ---------------------------------------------------------------------------


class _DiscordClientStub:
    """Minimal discord.Client stub — accepts any keyword args and is no-op."""

    def __init__(self, **kwargs):
        pass


class _IntendsStub:
    message_content = False

    @classmethod
    def default(cls):
        return cls()


_app_commands_stub = types.ModuleType("discord.app_commands")
_app_commands_stub.CommandTree = MagicMock()
_app_commands_stub.describe = lambda **_: (lambda f: f)

_discord_stub = types.ModuleType("discord")
_discord_stub.Client = _DiscordClientStub
_discord_stub.Intents = _IntendsStub
_discord_stub.Message = object
_discord_stub.Thread = object
_discord_stub.ChannelType = MagicMock()
_discord_stub.Forbidden = Exception
_discord_stub.HTTPException = Exception
_discord_stub.Interaction = object
_discord_stub.app_commands = _app_commands_stub
sys.modules.setdefault("discord", _discord_stub)
sys.modules.setdefault("discord.app_commands", _app_commands_stub)

# Set required env var before importing bot.py
os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token-for-pytest")
os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")

# Add repo root to path so interfaces.discord.bot is importable
_repo_root = os.path.join(os.path.dirname(__file__), "..", "..", "interfaces", "discord")
sys.path.insert(0, _repo_root)
from bot import handle_sentask_subcommand  # noqa: E402

USER_ID = "123456789"

# ---------------------------------------------------------------------------
# Fixture: mock call_core so tests do not make HTTP requests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_call_core(monkeypatch):
    """Patch call_core in bot module to return a canned AI response."""
    mock = AsyncMock(return_value="AI response")
    monkeypatch.setattr("bot.call_core", mock)
    return mock


# ---------------------------------------------------------------------------
# Tests — new commands (ralph, pipeline, reweave, etc.) are RED until 10-04
# ---------------------------------------------------------------------------

async def test_subcommand_routing_known_commands(mock_call_core):
    """Each of the 27 new commands must route (not fall through to Unknown command).

    RED until Plan 10-04 adds these commands to _SUBCOMMAND_PROMPTS and
    plugin: routing.
    """
    new_commands = [
        "ralph", "pipeline", "reweave", "check", "rethink", "refactor",
        "tasks", "stats", "graph", "next", "learn", "remember", "revisit",
        "connect", "review", "seed", "capture",
        "plugin:help", "plugin:health", "plugin:architect", "plugin:setup",
        "plugin:tutorial", "plugin:upgrade", "plugin:reseed",
        "plugin:add-domain", "plugin:recommend",
    ]
    unknown_error = "Unknown command"
    for cmd in new_commands:
        if ":" in cmd:
            prefix, rest = cmd.split(":", 1)
            result = await handle_sentask_subcommand(prefix + ":" + rest, rest, USER_ID)
        else:
            result = await handle_sentask_subcommand(cmd, "", USER_ID)
        assert unknown_error not in result, f"Command :{cmd} fell through to unknown-command handler"


async def test_plugin_prefix_routing(mock_call_core):
    """plugin:help must route (not fall through to Unknown command).

    RED until Plan 10-04 adds plugin: namespace routing.
    """
    result = await handle_sentask_subcommand("plugin:help", "", USER_ID)
    assert "Unknown command" not in result


async def test_plugin_ask_requires_args(mock_call_core):
    """plugin:ask with empty args must return a Usage string.

    RED until Plan 10-04 adds plugin:ask handler.
    """
    result = await handle_sentask_subcommand("plugin:ask", "", USER_ID)
    assert "Usage" in result


async def test_plugin_add_domain_requires_args(mock_call_core):
    """plugin:add-domain with empty args must return a Usage string.

    RED until Plan 10-04 adds plugin:add-domain handler.
    """
    result = await handle_sentask_subcommand("plugin:add-domain", "", USER_ID)
    assert "Usage" in result


async def test_check_validation_subcommand(mock_call_core):
    """:check must be routed (not fallen through to Unknown command).

    RED until Plan 10-04 adds :check to the command system.
    """
    result = await handle_sentask_subcommand("check", "", USER_ID)
    assert "Unknown command" not in result


async def test_help_returns_grouped_list(mock_call_core):
    """:help must return grouped command list mentioning 'standard' or 'plugin'.

    RED until Plan 10-04 rewrites the help text to include grouped output.
    """
    result = await handle_sentask_subcommand("help", "", USER_ID)
    assert "standard" in result.lower() or "plugin" in result.lower()


async def test_capture_requires_args(mock_call_core):
    """:capture with empty args returns a Usage string (existing behavior — GREEN)."""
    result = await handle_sentask_subcommand("capture", "", USER_ID)
    assert "Usage" in result


async def test_seed_requires_args(mock_call_core):
    """:seed with empty args must return a Usage string.

    RED until Plan 10-04 adds :seed handler.
    """
    result = await handle_sentask_subcommand("seed", "", USER_ID)
    assert "Usage" in result


async def test_unknown_command_falls_through(mock_call_core):
    """Unrecognised command returns 'Unknown command' string (existing behavior — GREEN)."""
    result = await handle_sentask_subcommand("not-a-real-command", "", USER_ID)
    assert "Unknown command" in result
