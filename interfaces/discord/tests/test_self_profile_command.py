"""Tests for self_profile_command.dispatch_onboard (the ``:onboard`` subcommand).

Conventions mirror test_pathfinder_player_dialog.py / test_pathfinder_player_adapter.py:
``async def test_*`` (asyncio_mode = "auto"), AsyncMock for http_client and
sentinel_client, discord stubs from conftest.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import core_gateway
import self_profile_command as spc


def _make_fake_thread(thread_id: int = 555) -> MagicMock:
    fake = MagicMock()
    fake.id = thread_id
    fake.send = AsyncMock()
    fake.edit = AsyncMock()
    return fake


async def test_onboard_replies_already_complete_and_creates_no_thread(monkeypatch):
    monkeypatch.setattr(
        core_gateway,
        "call_core_profile_status",
        AsyncMock(return_value={"complete": True, "paths": {}, "unfilled": []}),
    )
    channel = MagicMock()
    channel.create_thread = AsyncMock()

    result = await spc.dispatch_onboard(
        args="",
        user_id="u-1",
        channel=channel,
        author_display_name="alice",
        sentinel_client=MagicMock(),
        http_client=AsyncMock(),
        core_url="http://core",
        api_key="k",
    )

    assert "already complete" in result.lower()
    assert channel.create_thread.await_count == 0


async def test_onboard_with_unfilled_creates_thread_and_asks_first_only(monkeypatch):
    monkeypatch.setattr(
        core_gateway,
        "call_core_profile_status",
        AsyncMock(
            return_value={
                "complete": False,
                "paths": {
                    "self/identity.md": "stub",
                    "self/goals.md": "stub",
                },
                "unfilled": ["self/identity.md", "self/goals.md"],
            }
        ),
    )
    import bot as bot_module

    fake_thread = _make_fake_thread(thread_id=42)
    channel = MagicMock()
    channel.create_thread = AsyncMock(return_value=fake_thread)

    http = AsyncMock()
    http.put = AsyncMock(return_value=MagicMock(status_code=200))
    monkeypatch.setattr(bot_module, "_persist_thread_id", AsyncMock())
    bot_module.SENTINEL_THREAD_IDS.discard(42)

    try:
        result = await spc.dispatch_onboard(
            args="",
            user_id="u-1",
            channel=channel,
            author_display_name="alice",
            sentinel_client=MagicMock(),
            http_client=http,
            core_url="http://core",
            api_key="k",
        )

        assert channel.create_thread.await_count == 1
        assert fake_thread.send.await_count == 1
        sent_text = fake_thread.send.call_args.args[0]
        from self_profile_dialog import QUESTIONS

        assert sent_text == QUESTIONS["self/identity.md"]
        assert "self/goals.md" not in sent_text
        assert str(fake_thread.id) in result
    finally:
        bot_module.SENTINEL_THREAD_IDS.discard(42)


async def test_onboard_core_unreachable_returns_message_no_crash(monkeypatch):
    monkeypatch.setattr(
        core_gateway, "call_core_profile_status", AsyncMock(return_value=None)
    )
    channel = MagicMock()
    channel.create_thread = AsyncMock()

    result = await spc.dispatch_onboard(
        args="",
        user_id="u-1",
        channel=channel,
        author_display_name="alice",
        sentinel_client=MagicMock(),
        http_client=AsyncMock(),
        core_url="http://core",
        api_key="k",
    )

    assert isinstance(result, str)
    assert channel.create_thread.await_count == 0


async def test_onboard_cancel_outside_thread_tells_user_to_go_to_thread():
    result = await spc.dispatch_onboard(
        args="cancel",
        user_id="u-1",
        channel=None,
        author_display_name="alice",
        sentinel_client=MagicMock(),
        http_client=AsyncMock(),
        core_url="http://core",
        api_key="k",
    )
    assert "onboarding thread" in result.lower()
