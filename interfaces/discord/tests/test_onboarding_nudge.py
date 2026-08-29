"""Tests for SentinelBot._maybe_post_onboarding_nudge (startup profile-incomplete
invitation). Mirrors test_thread_persistence.py conventions: patch bot.httpx /
core_gateway for HTTP, assert on the resulting channel.send / non-crash behaviour.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import bot
import core_gateway


@pytest.fixture(autouse=True)
def reset_nudge_flag():
    """The nudge-posted flag is module-global (guards at-most-once-per-boot);
    reset it around each test so tests don't leak state into each other."""
    bot._ONBOARDING_NUDGE_POSTED = False
    yield
    bot._ONBOARDING_NUDGE_POSTED = False


@pytest.fixture(autouse=True)
def restore_get_channel():
    """discord.Client stub has no get_channel — tests assign it directly onto
    the bot singleton (monkeypatch.setattr requires the attr to pre-exist).
    Restore afterwards so it doesn't leak into unrelated test modules."""
    had_attr = "get_channel" in bot.bot.__dict__
    original = bot.bot.__dict__.get("get_channel")
    yield
    if had_attr:
        bot.bot.__dict__["get_channel"] = original
    else:
        bot.bot.__dict__.pop("get_channel", None)


async def test_nudge_posts_once_when_incomplete(monkeypatch):
    monkeypatch.setattr(
        core_gateway,
        "call_core_profile_status",
        AsyncMock(
            return_value={
                "complete": False,
                "paths": {},
                "unfilled": ["self/identity.md", "self/goals.md"],
            }
        ),
    )
    monkeypatch.setattr(bot, "NOTIFY_CHANNEL_ID", 555)

    fake_channel = MagicMock()
    fake_channel.send = AsyncMock()
    bot.bot.get_channel = MagicMock(return_value=fake_channel)

    await bot.bot._maybe_post_onboarding_nudge()

    assert fake_channel.send.await_count == 1
    posted = fake_channel.send.call_args.args[0]
    assert "2" in posted  # names how many files are unfilled
    assert ":onboard" in posted

    # Second call in the same boot must NOT post again.
    await bot.bot._maybe_post_onboarding_nudge()
    assert fake_channel.send.await_count == 1


async def test_nudge_does_not_post_when_complete(monkeypatch):
    monkeypatch.setattr(
        core_gateway,
        "call_core_profile_status",
        AsyncMock(return_value={"complete": True, "paths": {}, "unfilled": []}),
    )
    monkeypatch.setattr(bot, "NOTIFY_CHANNEL_ID", 555)
    fake_channel = MagicMock()
    fake_channel.send = AsyncMock()
    bot.bot.get_channel = MagicMock(return_value=fake_channel)

    await bot.bot._maybe_post_onboarding_nudge()

    assert fake_channel.send.await_count == 0


async def test_nudge_core_unreachable_no_crash_no_post(monkeypatch):
    monkeypatch.setattr(
        core_gateway, "call_core_profile_status", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(bot, "NOTIFY_CHANNEL_ID", 555)
    fake_channel = MagicMock()
    fake_channel.send = AsyncMock()
    bot.bot.get_channel = MagicMock(return_value=fake_channel)

    # Must not raise.
    await bot.bot._maybe_post_onboarding_nudge()

    assert fake_channel.send.await_count == 0


async def test_nudge_no_channel_configured_logs_and_skips(monkeypatch):
    monkeypatch.setattr(
        core_gateway,
        "call_core_profile_status",
        AsyncMock(return_value={"complete": False, "paths": {}, "unfilled": ["self/identity.md"]}),
    )
    monkeypatch.setattr(bot, "NOTIFY_CHANNEL_ID", None)
    monkeypatch.setattr(bot, "ALLOWED_CHANNEL_IDS", set())

    # Must not raise even though no channel is resolvable.
    await bot.bot._maybe_post_onboarding_nudge()
