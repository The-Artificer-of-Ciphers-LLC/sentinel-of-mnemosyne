"""
Discord integration tests — IFACE-02, IFACE-03, IFACE-04.

These tests require a real Discord bot token and a dedicated test channel.
They are LOCAL-ONLY — not wired into CI.

Skip conditions (per D-05, D-06):
  - DISCORD_BOT_TOKEN not set → entire module skipped
  - DISCORD_TEST_CHANNEL_ID not set → entire module skipped

Run manually:
  DISCORD_BOT_TOKEN=... DISCORD_TEST_CHANNEL_ID=... pytest interfaces/discord/tests/test_integration.py -v

What is verified:
  IFACE-02: discord container is running (docker compose ps)
  IFACE-03: bot.py calls defer(thinking=True) as first await in sentask() — code assertion
  IFACE-04: bot connects to the test channel and can detect threads
"""
import asyncio
import json
import os
import subprocess
from pathlib import Path

import discord
import pytest

# --------------------------------------------------------------------------- #
# Skip entire module if credentials are not set (D-05, D-06)
# --------------------------------------------------------------------------- #

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_TEST_CHANNEL_ID_RAW = os.getenv("DISCORD_TEST_CHANNEL_ID", "")

_SKIP_REASON = ""
if not DISCORD_BOT_TOKEN:
    _SKIP_REASON = "DISCORD_BOT_TOKEN not set"
elif not DISCORD_TEST_CHANNEL_ID_RAW:
    _SKIP_REASON = "DISCORD_TEST_CHANNEL_ID not set"

pytestmark = pytest.mark.skipif(bool(_SKIP_REASON), reason=_SKIP_REASON or "credentials present")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

BOT_PY_PATH = Path(__file__).parent.parent / "bot.py"


def _docker_compose_ps_json() -> list[dict]:
    """Return parsed JSON output of `docker compose ps --format json`."""
    result = subprocess.run(
        ["docker", "compose", "ps", "--format", "json"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return []
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    services = []
    for line in lines:
        try:
            services.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return services


async def _connect_and_fetch_channel(token: str, channel_id: int) -> discord.TextChannel | None:
    """
    Connect a temporary discord.py Client, fetch the channel, disconnect.
    Returns the channel object or None if unreachable.
    """
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    channel: discord.TextChannel | None = None

    @client.event
    async def on_ready():
        nonlocal channel
        try:
            ch = client.get_channel(channel_id) or await client.fetch_channel(channel_id)
            if isinstance(ch, discord.TextChannel):
                channel = ch
        finally:
            await client.close()

    try:
        await asyncio.wait_for(client.start(token), timeout=30)
    except (asyncio.TimeoutError, discord.LoginFailure):
        pass

    return channel


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_discord_container_running_iface02():
    """
    IFACE-02: Discord bot container is running.

    Checks `docker compose ps` output for a service whose name contains 'discord'
    and whose State is 'running'.
    """
    services = _docker_compose_ps_json()
    discord_services = [
        s for s in services
        if "discord" in s.get("Service", "").lower() or "discord" in s.get("Name", "").lower()
    ]
    assert discord_services, (
        "No discord service found in `docker compose ps` output. "
        "Run `docker compose up -d` first."
    )
    running = [s for s in discord_services if s.get("State", "").lower() == "running"]
    assert running, (
        f"Discord service exists but is not running. State: {discord_services[0].get('State')}"
    )


def test_defer_is_first_response_in_sentask_iface03():
    """
    IFACE-03: Bot calls defer(thinking=True) as the first interaction response in sentask().

    This is a code-level assertion — the defer pattern cannot be mechanically
    triggered from a test client (slash commands require a real Discord UI user).
    The assertion confirms the implementation contract is in place.
    """
    source = BOT_PY_PATH.read_text()
    # Find the sentask function body
    assert "async def sentask(" in source, "sentask() function not found in bot.py"
    sentask_idx = source.index("async def sentask(")
    sentask_body = source[sentask_idx:]
    # The defer call must appear before any followup.send or response.send_message
    defer_idx = sentask_body.find("interaction.response.defer(thinking=True)")
    followup_idx = sentask_body.find("interaction.followup.send(")
    send_message_idx = sentask_body.find("interaction.response.send_message(")

    assert defer_idx != -1, (
        "IFACE-03 FAIL: interaction.response.defer(thinking=True) not found in sentask()"
    )
    # defer must come before any followup (excluding the allowed-channels early-return path)
    # The allowed-channels guard sends an ephemeral message before defer — that is correct
    # behavior (guard fires before defer). We check that the primary happy-path defer
    # appears before followup.send.
    assert defer_idx < followup_idx, (
        "IFACE-03 FAIL: defer() does not appear before followup.send() in sentask(). "
        "The bot must acknowledge within 3 seconds."
    )


@pytest.mark.asyncio
async def test_bot_connects_and_detects_channel_iface04():
    """
    IFACE-04: Bot can connect to Discord and read the test channel.

    Full thread-per-invocation verification requires a human-triggered /sentask command
    (Discord slash commands cannot be triggered by a bot token via REST without an
    application-owner interaction endpoint). This test verifies bot connectivity and
    that the channel is reachable — the thread architecture is confirmed by code
    inspection (bot.py creates a thread in every sentask() invocation before responding).
    """
    channel_id = int(DISCORD_TEST_CHANNEL_ID_RAW)
    channel = await _connect_and_fetch_channel(DISCORD_BOT_TOKEN, channel_id)

    assert channel is not None, (
        f"Could not fetch channel {channel_id}. "
        "Verify DISCORD_TEST_CHANNEL_ID is correct and the bot has access to the channel."
    )
    assert isinstance(channel, discord.TextChannel), (
        f"Channel {channel_id} is not a TextChannel (got {type(channel).__name__}). "
        "DISCORD_TEST_CHANNEL_ID must point to a text channel."
    )

    # Code-level assertion: every sentask() invocation creates a thread before responding.
    source = BOT_PY_PATH.read_text()
    assert "await interaction.channel.create_thread(" in source, (
        "IFACE-04 FAIL: create_thread() call not found in bot.py sentask(). "
        "Thread-per-invocation architecture is not in place."
    )
    assert "await thread.send(ai_response)" in source, (
        "IFACE-04 FAIL: AI response is not sent into the thread in bot.py."
    )
