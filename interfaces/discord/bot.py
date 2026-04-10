"""
Sentinel Discord Bot — Phase 3 Interface.

Command: /sentask <message>
  1. Defer within 3s (IFACE-03 — shows "Bot is thinking...")
  2. Create public thread named from first 50 chars of message (IFACE-04)
  3. Parse subcommand prefix (:cmd) or call Core POST /message with X-Sentinel-Key (IFACE-06)
  4. Send AI response into thread
  5. Acknowledge interaction with thread mention (ephemeral)

Subcommands (prefix message with :):
  :help       — list available subcommands
  :capture    — capture text to Obsidian inbox
  :next       — what to work on next based on goals
  :health     — vault health check
  :goals      — show current active goals
  :reminders  — show current time-bound reminders

Thread replies:
  Any non-bot message in a Sentinel thread triggers another Core call,
  using the same user_id so Obsidian context carries across the conversation.

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

# Track thread IDs created by this bot instance so on_message knows which to respond to.
# Uses the parent channel ID set for allowlist checks on thread replies.
SENTINEL_THREAD_IDS: set[int] = set()

# Subcommand help text
SUBCOMMAND_HELP = """\
**Sentinel subcommands** — prefix your message with `:` to invoke:

`:help` — show this list
`:capture <text>` — capture a thought to your Obsidian inbox
`:next` — what to work on next based on current goals
`:health` — vault health check (orphan notes, stale goals, neglected gear)
`:goals` — show current active goals
`:reminders` — show current time-bound reminders

Regular messages (no `:` prefix) go straight to the AI.
"""

# Map subcommand names to the prompt sent to Core
_SUBCOMMAND_PROMPTS: dict[str, str] = {
    "next": "What should I work on next based on my current goals?",
    "health": "Run a health check on my vault and report orphan notes, stale goals, neglected gear.",
    "goals": "Show me my current active goals.",
    "reminders": "What are my current time-bound reminders?",
}


async def call_core(user_id: str, message: str) -> str:
    """
    POST to Sentinel Core /message. Returns the AI response string.
    All error cases return a user-facing string rather than raising.
    Reads Obsidian context for user_id automatically via Core's memory layer.
    """
    try:
        async with httpx.AsyncClient(timeout=200.0) as client:
            resp = await client.post(
                f"{SENTINEL_CORE_URL}/message",
                json={"content": message, "user_id": user_id},
                headers={"X-Sentinel-Key": SENTINEL_API_KEY},
            )
            resp.raise_for_status()
            return resp.json()["content"]
    except httpx.TimeoutException:
        logger.warning(f"Core timeout for user {user_id}")
        return "The Sentinel took too long to respond. Please try again."
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 422:
            return "Your message is too long for the current context window."
        elif exc.response.status_code == 401:
            logger.error("Core returned 401 — SENTINEL_API_KEY mismatch")
            return "Authentication error — check SENTINEL_API_KEY configuration."
        else:
            logger.error(f"Core HTTP error {exc.response.status_code} for user {user_id}")
            return f"The Sentinel encountered an error (HTTP {exc.response.status_code})."
    except httpx.RequestError as exc:
        logger.error(f"Core unreachable: {exc}")
        return "The Sentinel Core is unreachable. Please check the service."


async def handle_sentask_subcommand(subcmd: str, args: str, user_id: str) -> str:
    """
    Route `:subcommand` prefixed messages to the correct handler.
    Returns a response string in all cases — never raises.
    """
    if subcmd == "help":
        return SUBCOMMAND_HELP

    if subcmd == "capture":
        if not args.strip():
            return "Usage: `:capture <text>` — provide something to capture."
        prompt = f"Capture this to my inbox: {args.strip()}"
        return await call_core(user_id, prompt)

    fixed_prompt = _SUBCOMMAND_PROMPTS.get(subcmd)
    if fixed_prompt:
        return await call_core(user_id, fixed_prompt)

    return f"Unknown command `:{subcmd}`. Try `:help` for available commands."


class SentinelBot(discord.Client):
    """Discord client with app_commands tree for slash command support."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True  # required to read thread reply content
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        """Called once per process startup — safe point to sync command tree."""
        await self.tree.sync()
        logger.info("Slash commands synced globally (up to 1hr propagation).")

    async def on_ready(self) -> None:
        logger.info(f"Sentinel bot ready: {self.user} (id={self.user.id})")

    async def on_message(self, message: discord.Message) -> None:
        """
        Respond to replies inside Sentinel-created threads.
        Ignores: bot messages, non-thread channels, threads not created by this bot.
        """
        # Never respond to ourselves
        if message.author.bot:
            return

        # Only act on messages inside public threads
        if not isinstance(message.channel, discord.Thread):
            return

        # Only respond in threads we created
        if message.channel.id not in SENTINEL_THREAD_IDS:
            return

        user_id = str(message.author.id)
        logger.info(f"Thread reply from {user_id} in thread {message.channel.id}: {message.content[:60]}")

        async with message.channel.typing():
            ai_response = await call_core(user_id, message.content)

        await message.channel.send(ai_response)


bot = SentinelBot()


@bot.tree.command(name="sentask", description="Ask the Sentinel a question or give it a task")
@app_commands.describe(message="Your message to the Sentinel (prefix with : for subcommands)")
async def sentask(interaction: discord.Interaction, message: str) -> None:
    """
    /sentask <message> — Primary Sentinel interaction command.

    Creates a new thread per invocation. Multi-turn: replies inside the thread
    continue the conversation context — Obsidian memory is read on every exchange.

    Subcommands: prefix message with : (e.g. :help, :capture <text>, :next, :health, :goals, :reminders)
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
    thread_name = message[:50] if message else "Sentinel response"
    thread = None
    try:
        thread = await interaction.channel.create_thread(
            name=thread_name,
            type=discord.ChannelType.public_thread,
            auto_archive_duration=60,
        )
        SENTINEL_THREAD_IDS.add(thread.id)
        logger.info(f"Created thread {thread.id} '{thread_name}' for user {interaction.user.id}")
    except discord.Forbidden as exc:
        logger.error(f"Missing permission to create thread (403): {exc}")
    except discord.HTTPException as exc:
        logger.error(f"Failed to create thread (HTTP {exc.status}, code {exc.code}): {exc}")

    # 3. Parse subcommand prefix or call Core directly
    user_id = str(interaction.user.id)
    if message.startswith(":"):
        parts = message[1:].split(" ", 1)
        subcmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        ai_response = await handle_sentask_subcommand(subcmd, args, user_id)
    else:
        ai_response = await call_core(user_id, message)

    # 4. Send AI response — into thread if created, fallback to channel
    if thread:
        await thread.send(ai_response)
        await interaction.followup.send(
            f"Response ready in {thread.mention}", ephemeral=True
        )
    else:
        await interaction.followup.send(ai_response)


def main() -> None:
    bot.run(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
