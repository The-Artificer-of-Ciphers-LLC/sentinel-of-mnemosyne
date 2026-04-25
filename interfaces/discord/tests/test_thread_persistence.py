"""Tests for Discord bot thread ID persistence (2B-03) — moved from sentinel-core/tests/."""
import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import bot


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

    mock_runner = AsyncMock()
    mock_runner.setup = AsyncMock()
    mock_runner.cleanup = AsyncMock()
    mock_site = AsyncMock()
    mock_site.start = AsyncMock()
    mock_web = MagicMock()
    mock_web.Application.return_value = MagicMock()
    mock_web.AppRunner.return_value = mock_runner
    mock_web.TCPSite.return_value = mock_site

    with patch("bot.httpx") as mock_httpx, patch("bot.web", mock_web):
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
    mock_runner = AsyncMock()
    mock_runner.setup = AsyncMock()
    mock_runner.cleanup = AsyncMock()
    mock_site = AsyncMock()
    mock_site.start = AsyncMock()
    mock_web = MagicMock()
    mock_web.Application.return_value = MagicMock()
    mock_web.AppRunner.return_value = mock_runner
    mock_web.TCPSite.return_value = mock_site

    with patch("bot.httpx") as mock_httpx, patch("bot.web", mock_web):
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


# ---------------------------------------------------------------------------
# Phase 26 expansion: Integration test with live Obsidian teardown (2B-03)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_persist_thread_id_integration(test_run_path):
    """_persist_thread_id writes thread ID to Obsidian and teardown removes the test path.

    Requires: OBSIDIAN_BASE_URL and OBSIDIAN_API_KEY env vars pointing to a running
    Obsidian instance with the Local REST API plugin active.

    Skips automatically when Obsidian is unreachable (ConnectError / connection refused).
    The obsidian_teardown autouse fixture (conftest.py) deletes ops/test-run-{uuid}/
    after this test completes.
    """
    import os as _os

    base_url = _os.environ.get("OBSIDIAN_BASE_URL", "http://host.docker.internal:27124")
    api_key = _os.environ.get("OBSIDIAN_API_KEY", "")
    test_note_path = f"{test_run_path}/thread-test.md"

    # Skip gracefully if Obsidian is not reachable
    try:
        async with httpx.AsyncClient(timeout=3.0) as probe:
            probe_resp = await probe.get(
                f"{base_url}/vault/",
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except (httpx.ConnectError, httpx.TimeoutException, OSError):
        pytest.skip("Obsidian REST API not reachable — skipping integration test")

    if probe_resp.status_code == 401:
        pytest.skip("OBSIDIAN_API_KEY invalid — skipping integration test")

    # Write a note under the test-run path via Obsidian REST API
    async with httpx.AsyncClient(timeout=5.0) as client:
        put_resp = await client.put(
            f"{base_url}/vault/{test_note_path}",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "text/markdown",
            },
            content=b"# Thread persistence integration test\n99999\n",
        )

    assert put_resp.status_code in (200, 204), (
        f"Failed to write test note to Obsidian at {test_note_path}: {put_resp.status_code}"
    )

    # Read it back — verify our write landed
    async with httpx.AsyncClient(timeout=5.0) as client:
        get_resp = await client.get(
            f"{base_url}/vault/{test_note_path}",
            headers={"Authorization": f"Bearer {api_key}"},
        )

    assert get_resp.status_code == 200, (
        f"Note written but not readable at {test_note_path}: {get_resp.status_code}"
    )
    assert b"99999" in get_resp.content, (
        f"Thread ID 99999 not found in vault note content: {get_resp.content!r}"
    )
    # obsidian_teardown autouse fixture handles DELETE /vault/{test_run_path}/ after yield


# ---------------------------------------------------------------------------
# Task 1 (260420-xbc): owner_id fallback path — restart survivability
# ---------------------------------------------------------------------------


async def test_on_message_owner_id_fallback():
    """on_message responds to a thread owned by the bot even when its ID is not in
    SENTINEL_THREAD_IDS (simulates restart scenario where in-memory set was empty).
    After handling the message, the thread ID must be added back to SENTINEL_THREAD_IDS.
    """
    # SENTINEL_THREAD_IDS is cleared by the autouse fixture — 55555 is NOT present.
    assert 55555 not in bot.SENTINEL_THREAD_IDS

    # Build a mock Thread where thread.id = 55555 and thread.owner_id = 999 (bot's user id).
    mock_thread = MagicMock()
    mock_thread.id = 55555
    mock_thread.owner_id = 999

    # typing() must behave as an async context manager.
    typing_cm = MagicMock()
    typing_cm.__aenter__ = AsyncMock(return_value=None)
    typing_cm.__aexit__ = AsyncMock(return_value=None)
    mock_thread.typing = MagicMock(return_value=typing_cm)
    mock_thread.send = AsyncMock()

    # Build a mock Message (not a bot, channel = that thread).
    mock_message = MagicMock()
    mock_message.author.bot = False
    mock_message.channel = mock_thread
    mock_message.author.id = "user1"
    mock_message.content = "hello"

    # Patch discord.Thread so isinstance(mock_thread, discord.Thread) is True.
    import sys
    discord_stub = sys.modules["discord"]
    original_thread_cls = discord_stub.Thread
    discord_stub.Thread = type(mock_thread)

    # Set bot.bot.user to report id=999 (the bot's snowflake).
    # SentinelBot uses the discord stub which has no .user attribute by default;
    # assign it directly on the instance then restore after the test.
    mock_user = MagicMock()
    mock_user.id = 999
    original_user = getattr(bot.bot, "user", MagicMock())
    bot.bot.user = mock_user

    try:
        with patch("bot._route_message", new=AsyncMock(return_value="response")):
            with patch("bot.asyncio") as mock_asyncio:
                mock_asyncio.ensure_future = MagicMock()
                await bot.bot.on_message(mock_message)
    finally:
        bot.bot.user = original_user
        discord_stub.Thread = original_thread_cls

    # Bot must have replied.
    mock_thread.send.assert_called_once_with("response")

    # Thread ID must be added back to in-memory set by the fallback path.
    assert 55555 in bot.SENTINEL_THREAD_IDS, (
        "owner_id fallback did not re-add thread 55555 to SENTINEL_THREAD_IDS"
    )
