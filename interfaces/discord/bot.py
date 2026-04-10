"""
Sentinel Discord Bot — Phase 3 Interface.

Command: /sentask <message>
  1. Defer within 3s (IFACE-03 — shows "Bot is thinking...")
  2. Create public thread named from first 50 chars of message (IFACE-04)
  3. Call Core POST /message with X-Sentinel-Key (IFACE-06)
  4. Send AI response into thread
  5. Acknowledge interaction with thread mention (ephemeral)

User identity: str(interaction.user.id) — Discord snowflake as string.
Thread per invocation: each /sentask creates a fresh thread (never reuses).
"""
import logging
import os

import discord
import httpx
from discord import app_commands

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
SENTINEL_API_KEY = os.environ["SENTINEL_API_KEY"]
SENTINEL_CORE_URL = os.environ.get("SENTINEL_CORE_URL", "http://sentinel-core:8000")
DISCORD_ALLOWED_CHANNELS_RAW = os.environ.get("DISCORD_ALLOWED_CHANNELS", "")

# Parse optional channel allowlist (empty string = all channels allowed)
ALLOWED_CHANNEL_IDS: set[int] = set()
if DISCORD_ALLOWED_CHANNELS_RAW.strip():
    ALLOWED_CHANNEL_IDS = {
        int(cid.strip())
        for cid in DISCORD_ALLOWED_CHANNELS_RAW.split(",")
        if cid.strip().isdigit()
    }


class SentinelBot(discord.Client):
    """Discord client with app_commands tree for slash command support."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        """Called once per process startup — safe point to sync command tree."""
        await self.tree.sync()
        logger.info("Slash commands synced globally (up to 1hr propagation).")

    async def on_ready(self) -> None:
        logger.info(f"Sentinel bot ready: {self.user} (id={self.user.id})")


bot = SentinelBot()


@bot.tree.command(name="sentask", description="Ask the Sentinel a question or give it a task")
@app_commands.describe(message="Your message to the Sentinel")
async def sentask(interaction: discord.Interaction, message: str) -> None:
    """
    /sentask <message> — Primary Sentinel interaction command.

    Creates a new thread per invocation. Multi-turn: replies inside the thread
    continue the conversation context (same thread_id → same Obsidian session path
    in future phases).
    """
    # Guard: channel allowlist (if configured)
    if ALLOWED_CHANNEL_IDS and interaction.channel_id not in ALLOWED_CHANNEL_IDS:
        allowed_mentions = " or ".join(f"<#{cid}>" for cid in ALLOWED_CHANNEL_IDS)
        await interaction.response.send_message(
            f"I only respond in {allowed_mentions}. Head there and try again.",
            ephemeral=True,
        )
        return

    # 1. Defer within 3 seconds — shows "Bot is thinking..." to user (IFACE-03)
    await interaction.response.defer(thinking=True)

    # 2. Create public thread from the channel (IFACE-04)
    #    CORRECT: channel.create_thread() — not followup.send().create_thread()
    #    interaction.followup.send() returns WebhookMessage which has NO create_thread()
    thread_name = message[:50] if message else "Sentinel response"
    thread = None
    try:
        thread = await interaction.channel.create_thread(
            name=thread_name,
            type=discord.ChannelType.public_thread,
            auto_archive_duration=60,
        )
    except discord.Forbidden as exc:
        logger.error(f"Missing permission to create thread (403): {exc}")
    except discord.HTTPException as exc:
        logger.error(f"Failed to create thread (HTTP {exc.status}, code {exc.code}): {exc}")

    # 3. Call Sentinel Core (IFACE-02, IFACE-06)
    user_id = str(interaction.user.id)  # Discord snowflake as string (D-01)
    ai_response: str
    try:
        async with httpx.AsyncClient(timeout=200.0) as client:
            resp = await client.post(
                f"{SENTINEL_CORE_URL}/message",
                json={"content": message, "user_id": user_id},
                headers={"X-Sentinel-Key": SENTINEL_API_KEY},
            )
            resp.raise_for_status()
            ai_response = resp.json()["content"]
    except httpx.TimeoutException:
        ai_response = "The Sentinel took too long to respond. Please try again."
        logger.warning(f"Core timeout for user {user_id}")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 422:
            ai_response = "Your message is too long for the current context window."
        elif exc.response.status_code == 401:
            ai_response = "Authentication error — check SENTINEL_API_KEY configuration."
            logger.error("Core returned 401 — SENTINEL_API_KEY mismatch")
        else:
            ai_response = f"The Sentinel encountered an error (HTTP {exc.response.status_code})."
            logger.error(f"Core HTTP error {exc.response.status_code} for user {user_id}")
    except httpx.RequestError as exc:
        ai_response = "The Sentinel Core is unreachable. Please check the service."
        logger.error(f"Core unreachable: {exc}")

    # 4. Send AI response — into thread if created, fallback to channel
    if thread:
        await thread.send(ai_response)
        await interaction.followup.send(
            f"Response ready in {thread.mention}", ephemeral=True
        )
    else:
        # Thread creation failed — respond directly in channel so the user isn't left hanging
        await interaction.followup.send(ai_response)


def main() -> None:
    bot.run(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
