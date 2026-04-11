"""Tests for Discord bot thread ID persistence (2B-03) — Phase 10 stubs.
All tests in this file are RED until Plan 10-02 implements thread persistence
in interfaces/discord/bot.py (setup_hook loading + _persist_thread_id).
"""
import sys
import os
import types
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Stub out discord before importing bot.py (no discord.py in test env)
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

# Set required env vars before importing bot.py
os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token-for-pytest")
os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")

# Add interfaces/discord to path
_repo_root = os.path.join(os.path.dirname(__file__), "..", "..", "interfaces", "discord")
sys.path.insert(0, _repo_root)
import bot  # noqa: E402


# ---------------------------------------------------------------------------
# Tests — all RED until Plan 10-02 adds persistence logic to bot.py
# ---------------------------------------------------------------------------


async def test_thread_ids_loaded_on_startup():
    """After setup_hook runs, SENTINEL_THREAD_IDS contains IDs from ops/discord-threads.md.

    RED: setup_hook currently only syncs the command tree; it does not load
    thread IDs from Obsidian.  Will be GREEN after Plan 10-02.
    """
    import httpx

    threads_content = "12345\n67890\n"

    def handler(request: httpx.Request) -> httpx.Response:
        if "ops/discord-threads.md" in request.url.path:
            return httpx.Response(200, text=threads_content)
        return httpx.Response(404)

    bot.SENTINEL_THREAD_IDS.clear()

    with patch("bot.httpx") as mock_httpx:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=httpx.Response(200, text=threads_content))
        mock_httpx.AsyncClient.return_value = mock_client

        sentinel_bot = bot.bot
        # setup_hook does not yet load thread IDs — this call will NOT populate
        # SENTINEL_THREAD_IDS, causing the assertion below to fail (expected RED).
        with patch.object(sentinel_bot.tree, "sync", new=AsyncMock()):
            await sentinel_bot.setup_hook()

    assert 12345 in bot.SENTINEL_THREAD_IDS, (
        "setup_hook did not load thread 12345 from ops/discord-threads.md "
        "(RED — expected until Plan 10-02)"
    )
    assert 67890 in bot.SENTINEL_THREAD_IDS, (
        "setup_hook did not load thread 67890 from ops/discord-threads.md "
        "(RED — expected until Plan 10-02)"
    )


async def test_thread_ids_startup_graceful_on_404():
    """setup_hook does not crash when ops/discord-threads.md returns 404.

    RED: the 404-handling code does not yet exist in setup_hook.  Will be
    GREEN after Plan 10-02 adds graceful handling (SENTINEL_THREAD_IDS stays
    empty, no exception raised).
    """
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    bot.SENTINEL_THREAD_IDS.clear()

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
        "SENTINEL_THREAD_IDS should be empty after 404 response "
        "(RED — expected until Plan 10-02)"
    )


async def test_thread_id_persisted_on_creation():
    """_persist_thread_id(99999) sends 99999 in a PUT body to ops/discord-threads.md.

    RED: _persist_thread_id does not yet exist in bot.py.  Will be GREEN after
    Plan 10-02 adds the function.
    """
    import httpx

    put_bodies: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and "ops/discord-threads.md" in request.url.path:
            return httpx.Response(200, text="# Discord Thread IDs\n")
        if request.method == "PUT" and "ops/discord-threads.md" in request.url.path:
            put_bodies.append(request.content.decode())
            return httpx.Response(200)
        return httpx.Response(404)

    # _persist_thread_id does not yet exist — AttributeError is the expected RED failure
    persist_fn = getattr(bot, "_persist_thread_id", None)
    assert persist_fn is not None, (
        "_persist_thread_id not found in bot module "
        "(RED — expected until Plan 10-02 adds the function)"
    )

    with patch("bot.httpx") as mock_httpx:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=httpx.Response(200, text="# Discord Thread IDs\n"))

        captured_put = AsyncMock(return_value=httpx.Response(200))
        mock_client.put = captured_put
        mock_httpx.AsyncClient.return_value = mock_client

        await persist_fn(99999)

    assert any("99999" in body for body in put_bodies), (
        "99999 was not found in any PUT body sent to ops/discord-threads.md"
    )
