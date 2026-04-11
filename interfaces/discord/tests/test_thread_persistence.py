"""Tests for Discord bot thread ID persistence (2B-03) — moved from sentinel-core/tests/."""
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# ---------------------------------------------------------------------------
# Stub out discord before importing bot.py (no discord.py in test env)
# ---------------------------------------------------------------------------


class _DiscordClientStub:
    """Minimal discord.Client stub — accepts any keyword args and is no-op."""

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

# Set required env vars before importing bot.py
os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token-for-pytest")
os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")

# Add interfaces/discord to path
_discord_dir = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(_discord_dir))

import bot  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_thread_ids():
    """Reset SENTINEL_THREAD_IDS before each test."""
    bot.SENTINEL_THREAD_IDS.clear()
    yield
    bot.SENTINEL_THREAD_IDS.clear()


# ---------------------------------------------------------------------------
# Thread persistence tests
# ---------------------------------------------------------------------------


async def test_persist_thread_id_writes_to_obsidian():
    """_persist_thread_id(99999) sends 99999 in a PATCH body to ops/discord-threads.md."""
    with patch("bot.httpx") as mock_httpx:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        captured_patch = AsyncMock(return_value=httpx.Response(200))
        mock_client.patch = captured_patch
        mock_httpx.AsyncClient.return_value = mock_client

        await bot._persist_thread_id(99999)

    assert captured_patch.called, (
        "_persist_thread_id did not call httpx PATCH on ops/discord-threads.md"
    )
    call_kwargs = captured_patch.call_args
    content_arg = call_kwargs.kwargs.get("content", b"")
    assert b"99999" in content_arg, (
        f"99999 was not found in PATCH body. Got content: {content_arg!r}"
    )


async def test_setup_hook_loads_threads_on_start():
    """After setup_hook runs, SENTINEL_THREAD_IDS contains IDs from ops/discord-threads.md."""
    threads_content = "12345\n67890\n"

    with patch("bot.httpx") as mock_httpx:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=httpx.Response(200, text=threads_content))
        mock_httpx.AsyncClient.return_value = mock_client

        sentinel_bot = bot.bot
        with patch.object(sentinel_bot.tree, "sync", new=AsyncMock()):
            await sentinel_bot.setup_hook()

    assert 12345 in bot.SENTINEL_THREAD_IDS, (
        "setup_hook did not load thread 12345 from ops/discord-threads.md"
    )
    assert 67890 in bot.SENTINEL_THREAD_IDS, (
        "setup_hook did not load thread 67890 from ops/discord-threads.md"
    )


async def test_setup_hook_graceful_on_404():
    """setup_hook does not crash when ops/discord-threads.md returns 404."""
    with patch("bot.httpx") as mock_httpx:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=httpx.Response(404))
        mock_httpx.AsyncClient.return_value = mock_client

        sentinel_bot = bot.bot
        with patch.object(sentinel_bot.tree, "sync", new=AsyncMock()):
            # Must not raise — graceful 404 handling required
            await sentinel_bot.setup_hook()

    assert bot.SENTINEL_THREAD_IDS == set(), (
        "SENTINEL_THREAD_IDS should be empty after 404 response"
    )
