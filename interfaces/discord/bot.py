"""
Sentinel Discord Bot — Phase 3 Interface.

Command: /sen <message>
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
  :ralph      — batch process inbox queue
  :pipeline   — full 6 Rs pipeline
  :reweave    — backward pass to update older notes
  :check      — validate schema compliance
  :rethink    — review observations and tensions
  :refactor   — suggest vault restructuring
  :tasks      — show task queue
  :stats      — vault metrics
  :graph      — graph analysis
  :learn      — research a topic
  :remember   — capture a methodology observation
  :revisit    — revisit and update a note
  :connect    — find connections for a note
  :review     — verify note quality
  :seed       — drop raw content into inbox/
  :plugin:*   — plugin commands (help, health, architect, setup, tutorial, upgrade, reseed, add-domain, recommend)

Thread replies:
  Any non-bot message in a Sentinel thread triggers another Core call,
  using the same user_id so Obsidian context carries across the conversation.

User identity: str(interaction.user.id) — Discord snowflake as string.
Thread per invocation: each /sentask creates a fresh thread (never reuses).
"""
import asyncio
import logging
import os

import discord
import httpx
from discord import app_commands
from shared.sentinel_client import SentinelCoreClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _read_secret(name: str, env_fallback: str = "") -> str:
    """Read a Docker secret from /run/secrets/<name>.
    Falls back to env_fallback value (for local dev without Docker secrets)."""
    path = f"/run/secrets/{name}"
    try:
        with open(path) as f:
            return f.read().strip()
    except FileNotFoundError:
        return env_fallback


# Public API for this module (consumed by tests and future integrations)
__all__ = [
    "handle_sentask_subcommand",
    "_SUBCOMMAND_PROMPTS",
    "_PLUGIN_PROMPTS",
    "_persist_thread_id",
]

DISCORD_BOT_TOKEN: str = _read_secret("discord_bot_token", os.environ.get("DISCORD_BOT_TOKEN", ""))
SENTINEL_API_KEY: str = _read_secret("sentinel_api_key", os.environ.get("SENTINEL_API_KEY", ""))
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

# Module-level SentinelCoreClient — shared across all interactions
_sentinel_client = SentinelCoreClient(
    base_url=SENTINEL_CORE_URL,
    api_key=SENTINEL_API_KEY,
    timeout=200.0,
)

# Subcommand help text (D-08 — grouped by category)
SUBCOMMAND_HELP = """\
**Sentinel 2nd Brain Commands** — prefix with `:` inside a /sen thread:

**Standard Commands**
`:help` — show this command list
`:capture <text>` — extract insights from source material; route to inbox/
`:seed <text>` — drop raw content into inbox/ with zero friction
`:ralph` — batch process inbox/ queue (Reduce + Reflect)
`:pipeline` — run full 6 Rs pipeline (Record → Reduce → Reflect → Reweave → Verify → Rethink)
`:connect <note title>` — find connections for a note; add wikilink to hub MOC
`:reweave` — backward pass: update older notes with recent vault additions
`:review <note title>` — verify note quality (claim title, schema, wikilinks)
`:check` — validate schema compliance across all notes/
`:rethink` — review observations and tensions; triage each
`:refactor` — suggest vault restructuring improvements
`:tasks` — show ops/queue/ task queue
`:stats` — vault metrics (note count, orphans, link density)
`:graph [query]` — graph analysis (orphans, triangles, density, backlinks)
`:next` — surface what needs attention based on vault state
`:learn <topic>` — research a topic and grow the knowledge graph
`:remember <observation>` — capture a methodology learning to ops/observations/
`:revisit <note title>` — revisit and update an old note

**Plugin Commands** (prefix `:plugin:`)
`:plugin:help` — contextual guidance on commands and when to use each
`:plugin:health` — full vault diagnostics
`:plugin:ask <question>` — query the methodology knowledge base
`:plugin:architect` — research-backed vault evolution advice
`:plugin:setup` — create initial vault structure
`:plugin:tutorial` — interactive walkthrough of the 2nd brain system
`:plugin:upgrade` — check for methodology improvements
`:plugin:reseed` — principled vault restructuring
`:plugin:add-domain <domain>` — extend vault with a new domain area
`:plugin:recommend` — architecture advice for current vault state

Regular messages (no `:` prefix) go straight to the AI.
"""

# Map subcommand names to the prompt sent to Core (standard no-arg commands)
_SUBCOMMAND_PROMPTS: dict[str, str] = {
    # Existing commands
    "next": "What should I work on next based on my current goals?",
    "health": "Run a health check on my vault and report orphan notes, stale goals, neglected gear.",
    "goals": "Show me my current active goals.",
    "reminders": "What are my current time-bound reminders?",
    # New standard commands (D-03)
    "ralph": "Process my inbox queue — work through items in inbox/ and move completed ones to notes/ following the 2nd brain pipeline.",
    "pipeline": "Run the full 6 Rs pipeline on my inbox queue: Record → Reduce → Reflect → Reweave → Verify → Rethink.",
    "reweave": "Run a reweave pass on my vault — identify notes that should be updated given recent additions. Update older notes with new context and connections.",
    "check": "Validate _schema compliance across all notes/ files. Report FAIL items (missing description, missing topics, YAML errors) and WARN items (stale status, isolated notes).",
    "rethink": "Review accumulated observations and tensions in ops/observations/ and ops/tensions/. Triage each: PROMOTE, IMPLEMENT, METHODOLOGY, ARCHIVE, or KEEP PENDING.",
    "refactor": "Review vault organization and suggest restructuring improvements.",
    "tasks": "Show the ops/queue/ task queue. List pending items by status.",
    "stats": "Report vault metrics: note count in notes/, orphan count, link density, hub sizes, inbox depth.",
}

# Map plugin subcommand names to the prompt sent to Core (plugin: prefix commands)
_PLUGIN_PROMPTS: dict[str, str] = {
    "help": "List all available Sentinel 2nd brain commands grouped by category with one-line descriptions.",
    "health": "Run full vault diagnostics: orphan notes, dangling wiki links, hub coherence, stale content. Return a structured health report.",
    "architect": "Review the current vault structure and provide research-backed advice for evolution.",
    "setup": "Create the initial vault structure for the 2nd brain system: self/, notes/, ops/, inbox/, templates/ directories with stub files.",
    "tutorial": "Walk me through the 2nd brain system interactively — explain each command and when to use it.",
    "upgrade": "Check for methodology improvements based on recent usage patterns and observations.",
    "reseed": "Perform a principled vault restructuring based on accumulated observations.",
    "recommend": "Analyze the current vault state and provide architecture advice.",
}


async def _call_core(user_id: str, message: str) -> str:
    """
    Route message through the shared SentinelCoreClient.
    Creates a per-call httpx.AsyncClient as the client owns no persistent connection state.
    """
    async with httpx.AsyncClient() as http_client:
        return await _sentinel_client.send_message(user_id, message, http_client)


# Relation types valid for :pf npc relate (D-13 — closed enum)
_VALID_RELATIONS = frozenset({"knows", "trusts", "hostile-to", "allied-with", "fears", "owes-debt"})


async def _pf_dispatch(args: str, user_id: str, attachments: list | None = None) -> str:
    """Route ':pf <noun> <verb> <rest>' to pathfinder module endpoints.

    Called from handle_sentask_subcommand when subcmd == 'pf' (D-04).
    Uses post_to_module() on SentinelCoreClient — NOT _call_core() (D-03).
    """
    parts = args.strip().split(" ", 2)
    if len(parts) < 2:
        return "Usage: `:pf npc <create|update|show|relate|import> ...`"
    noun, verb = parts[0].lower(), parts[1].lower()
    rest = parts[2] if len(parts) > 2 else ""

    if noun != "npc":
        return f"Unknown pf category `{noun}`. Currently supported: `npc`."

    try:
        async with httpx.AsyncClient() as http_client:
            if verb == "create":
                # Split name | description on first pipe (D-05, Pitfall 5: maxsplit=1)
                name, _, description = rest.partition("|")
                if not name.strip():
                    return "Usage: `:pf npc create <name> | <description>`"
                payload = {
                    "name": name.strip(),
                    "description": description.strip(),
                    "user_id": user_id,
                }
                result = await _sentinel_client.post_to_module(
                    "modules/pathfinder/npc/create", payload, http_client
                )
                return (
                    f"NPC **{result.get('name', name.strip())}** created.\n"
                    f"Path: `{result.get('path', '?')}`\n"
                    f"Ancestry: {result.get('ancestry', '?')} | Class: {result.get('class', '?')} | Level: {result.get('level', '?')}"
                )

            elif verb == "update":
                name, _, correction = rest.partition("|")
                if not name.strip() or not correction.strip():
                    return "Usage: `:pf npc update <name> | <correction>`"
                payload = {
                    "name": name.strip(),
                    "correction": correction.strip(),
                    "user_id": user_id,
                }
                result = await _sentinel_client.post_to_module(
                    "modules/pathfinder/npc/update", payload, http_client
                )
                return f"NPC **{name.strip()}** updated. Fields changed: {', '.join(result.get('changed_fields', []))}"

            elif verb == "show":
                npc_name = rest.strip()
                if not npc_name:
                    return "Usage: `:pf npc show <name>`"
                result = await _sentinel_client.post_to_module(
                    "modules/pathfinder/npc/show", {"name": npc_name}, http_client
                )
                # Build a simple text embed (Discord embed objects not possible in text response)
                lines = [
                    f"**{result.get('name', npc_name)}** "
                    f"(Level {result.get('level', '?')} {result.get('ancestry', '?')} {result.get('class', '?')})",
                    f"*{result.get('personality', '')}*",
                    result.get('backstory', '')[:200],
                ]
                stats = result.get("stats") or {}
                if stats:
                    lines.append(
                        f"AC {stats.get('ac', '—')} | HP {stats.get('hp', '—')} | "
                        f"Fort {stats.get('fortitude', '—')} Ref {stats.get('reflex', '—')} Will {stats.get('will', '—')}"
                    )
                rels = result.get("relationships") or []
                if rels:
                    rel_text = ", ".join(f"{r.get('target')} ({r.get('relation')})" for r in rels)
                    lines.append(f"Relationships: {rel_text}")
                lines.append(f"*Mood: {result.get('mood', 'neutral')} | {result.get('path', '')}*")
                return "\n".join(lines)

            elif verb == "relate":
                # Format: :pf npc relate <name> | <relation> | <target>
                # Pipe separator allows multi-word NPC names and targets (CR-01 fix)
                relate_parts = [p.strip() for p in rest.split("|")]
                if len(relate_parts) < 3 or not all(relate_parts[:3]):
                    return (
                        "Usage: `:pf npc relate <npc-name> | <relation> | <target-npc-name>`\n"
                        f"Valid relations: {', '.join(sorted(_VALID_RELATIONS))}"
                    )
                npc_name, relation, target = relate_parts[0], relate_parts[1], relate_parts[2]
                # Bot-layer validation (D-13) — fail fast, don't call module
                if relation not in _VALID_RELATIONS:
                    return (
                        f"`{relation}` is not a valid relation type.\n"
                        f"Valid options: {', '.join(sorted(_VALID_RELATIONS))}"
                    )
                result = await _sentinel_client.post_to_module(
                    "modules/pathfinder/npc/relate",
                    {"name": npc_name, "relation": relation, "target": target},
                    http_client,
                )
                return f"Relationship added: **{npc_name}** {relation} **{target}**."

            elif verb == "import":
                # Attachment-based import (D-23, Pattern 6)
                # Attachments come from on_message thread reply — not slash command
                if not attachments:
                    return (
                        "Usage: `:pf npc import` — attach a Foundry actor list JSON file "
                        "as a reply in this thread."
                    )
                attachment = attachments[0]
                fetch_resp = await http_client.get(str(attachment.url), timeout=10.0)
                fetch_resp.raise_for_status()
                actors_json = fetch_resp.text
                result = await _sentinel_client.post_to_module(
                    "modules/pathfinder/npc/import",
                    {"actors_json": actors_json, "user_id": user_id},
                    http_client,
                )
                imported = result.get("imported_count", 0)
                skipped = result.get("skipped", [])
                lines = [f"Imported **{imported}** NPC(s)."]
                if skipped:
                    lines.append(f"Skipped (already exist): {', '.join(skipped)}")
                return "\n".join(lines)

            else:
                return (
                    f"Unknown npc command `{verb}`. "
                    "Available: `create`, `update`, `show`, `relate`, `import`."
                )

    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        try:
            detail = exc.response.json().get("detail", exc.response.text)
        except Exception:
            detail = exc.response.text
        if status == 409:
            return f"NPC already exists: {detail}"
        if status == 404:
            return "NPC not found."
        logger.error("Module returned HTTP %d: %s", status, detail)
        return f"Pathfinder module error (HTTP {status}): {detail}"
    except httpx.ConnectError:
        logger.error("Cannot reach sentinel-core for pf dispatch")
        return "Cannot reach the Sentinel. Is sentinel-core running?"
    except httpx.TimeoutException:
        logger.error("pf dispatch timed out")
        return "The pathfinder module took too long to respond. Try again."
    except Exception as exc:
        logger.exception("Unexpected error in _pf_dispatch: %s", exc)
        return "An unexpected error occurred in pathfinder dispatch."


_HELP_KEYWORDS = frozenset({"commands", "help", "what can you do", "what do you do", "how do i use"})


async def _route_message(user_id: str, message: str, attachments: list | None = None) -> str:
    """
    Unified message router used by both /sentask and on_message thread replies.

    Routing order:
    1. Colon-prefixed subcommands (`:help`, `:capture`, etc.)
    2. Natural-language help intent (short message containing help/commands keywords)
    3. Everything else → AI via _call_core
    """
    if message.startswith(":"):
        parts = message[1:].split(" ", 1)
        subcmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        return await handle_sentask_subcommand(subcmd, args, user_id, attachments=attachments)

    # Intercept natural-language help queries locally — never send to AI.
    # Prevents Obsidian session context from producing leaked/irrelevant responses
    # when the user is just asking what the bot can do.
    msg_lower = message.lower()
    if len(message) < 120 and any(kw in msg_lower for kw in _HELP_KEYWORDS):
        return SUBCOMMAND_HELP

    return await _call_core(user_id, message)


async def handle_sentask_subcommand(subcmd: str, args: str, user_id: str, attachments: list | None = None) -> str:
    """
    Route `:subcommand` prefixed messages to the correct handler.
    Returns a response string in all cases — never raises.
    """
    if subcmd == "pf":
        return await _pf_dispatch(args, user_id, attachments=attachments)

    if subcmd == "help":
        return SUBCOMMAND_HELP

    # plugin: prefix routing (D-12) — check BEFORE dict lookup
    if subcmd.startswith("plugin:"):
        plugin_name = subcmd[7:]  # strip "plugin:" prefix
        if plugin_name == "ask":
            if not args.strip():
                return "Usage: `:plugin:ask <question>` — query the methodology knowledge base."
            return await _call_core(user_id, f"Answer this question about my 2nd brain methodology: {args.strip()}")
        if plugin_name == "add-domain":
            if not args.strip():
                return "Usage: `:plugin:add-domain <domain>` — extend vault with a new domain area."
            return await _call_core(user_id, f"Extend my vault with a new domain area: {args.strip()}")
        fixed_prompt = _PLUGIN_PROMPTS.get(plugin_name)
        if fixed_prompt:
            return await _call_core(user_id, fixed_prompt)
        return f"Unknown plugin command `:{subcmd}`. Try `:plugin:help`."

    # Arg-taking standard commands
    if subcmd == "capture":
        if not args.strip():
            return "Usage: `:capture <text>` — provide something to capture."
        return await _call_core(user_id, f"Capture this insight to my inbox/ for processing: {args.strip()}")

    if subcmd == "seed":
        if not args.strip():
            return "Usage: `:seed <text>` — drop raw content into inbox/."
        return await _call_core(user_id, f"Add this raw content to my inbox/ without processing: {args.strip()}")

    if subcmd == "connect":
        if not args.strip():
            return "Usage: `:connect <note title>` — find connections for a note."
        return await _call_core(
            user_id,
            f"Find connections for the note '{args.strip()}' and add a wikilink to the appropriate hub MOC.",
        )

    if subcmd == "review":
        if not args.strip():
            return "Usage: `:review <note title>` — verify note quality."
        return await _call_core(
            user_id,
            f"Review note quality for '{args.strip()}': check claim title, YAML frontmatter (description, type, topics, status), and wikilinks. Be precise and literal. Do not elaborate beyond the requested format.",
        )

    if subcmd == "graph":
        query = args.strip() or "all"
        prompt = f"Run graph analysis on my vault{': ' + query if query != 'all' else ''}. Report orphans, triangles, link density, and backlinks."
        return await _call_core(user_id, prompt)

    if subcmd == "learn":
        if not args.strip():
            return "Usage: `:learn <topic>` — research a topic."
        return await _call_core(user_id, f"Research the topic '{args.strip()}' and grow my knowledge graph with new permanent notes.")

    if subcmd == "remember":
        if not args.strip():
            return "Usage: `:remember <observation>` — capture a methodology learning."
        return await _call_core(user_id, f"Capture this operational observation to ops/observations/: {args.strip()}")

    if subcmd == "revisit":
        if not args.strip():
            return "Usage: `:revisit <note title>` — revisit and update a note."
        return await _call_core(user_id, f"Revisit and update the note '{args.strip()}' with current understanding.")

    # No-arg standard commands (dict lookup)
    fixed_prompt = _SUBCOMMAND_PROMPTS.get(subcmd)
    if fixed_prompt:
        return await _call_core(user_id, fixed_prompt)

    return f"Unknown command `:{subcmd}`. Try `:help` for available commands."


async def _persist_thread_id(thread_id: int) -> None:
    """Append thread ID to ops/discord-threads.md using PATCH (append). Best-effort."""
    obsidian_url = os.environ.get("OBSIDIAN_API_URL", "http://host.docker.internal:27123")
    obsidian_key = _read_secret("obsidian_api_key", os.environ.get("OBSIDIAN_API_KEY", ""))
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.patch(
                f"{obsidian_url}/vault/ops/discord-threads.md",
                headers={
                    "Authorization": f"Bearer {obsidian_key}",
                    "Content-Type": "text/markdown",
                    "Obsidian-API-Content-Insertion-Position": "end",
                },
                content=f"{thread_id}\n".encode("utf-8"),
            )
    except Exception as exc:
        logger.warning(f"Failed to persist thread ID {thread_id}: {exc}")


class SentinelBot(discord.Client):
    """Discord client with app_commands tree for slash command support."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True  # required to read thread reply content
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        """Called once per process startup — safe point to sync command tree and load thread IDs."""
        synced_commands = await self.tree.sync()
        synced_count = len(synced_commands) if synced_commands else 0
        logger.info(
            f"Slash commands synced to Discord API: {synced_count} command(s) registered "
            f"(global sync — up to 1hr propagation to all servers)."
        )
        if synced_count == 0:
            logger.warning(
                "tree.sync() returned 0 commands — /sen may not be visible in Discord. "
                "Verify bot has applications.commands scope and the @bot.tree.command "
                "decorator runs before bot = SentinelBot()."
            )
        # Load persisted thread IDs from vault (D-04)
        obsidian_url = os.environ.get("OBSIDIAN_API_URL", "http://host.docker.internal:27123")
        obsidian_key = _read_secret("obsidian_api_key", os.environ.get("OBSIDIAN_API_KEY", ""))
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{obsidian_url}/vault/ops/discord-threads.md",
                    headers={"Authorization": f"Bearer {obsidian_key}"},
                )
                if resp.status_code == 200:
                    for line in resp.text.splitlines():
                        line = line.strip()
                        if line.isdigit():
                            SENTINEL_THREAD_IDS.add(int(line))
                    logger.info(f"Loaded {len(SENTINEL_THREAD_IDS)} persisted thread IDs")
        except Exception as exc:
            logger.warning(f"Could not load thread IDs from vault: {exc}")

    async def on_ready(self) -> None:
        user = self.user
        logger.info(f"Sentinel bot ready: {user} (id={user.id if user else 'unknown'})")

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

        # Only respond in threads we created — check in-memory set first, then fall
        # back to owner_id for restart-survivable behaviour (D-04 restart fix).
        thread = message.channel
        is_sentinel_thread = (
            thread.id in SENTINEL_THREAD_IDS
            or thread.owner_id == self.user.id
        )
        if not is_sentinel_thread:
            return

        # Re-persist thread ID if it was recovered via owner_id fallback so future
        # restarts populate SENTINEL_THREAD_IDS from the Obsidian cache.
        if thread.id not in SENTINEL_THREAD_IDS:
            SENTINEL_THREAD_IDS.add(thread.id)
            asyncio.ensure_future(_persist_thread_id(thread.id))

        user_id = str(message.author.id)
        logger.info(f"Thread reply from {user_id} in thread {message.channel.id}: {message.content[:60]}")

        async with message.channel.typing():
            ai_response = await _route_message(user_id, message.content, attachments=list(message.attachments))

        await message.channel.send(ai_response)


bot = SentinelBot()


@bot.tree.command(name="sen", description="Ask the Sentinel a question or give it a task")
@app_commands.describe(message="Your message to the Sentinel (prefix with : for subcommands)")
async def sen(interaction: discord.Interaction, message: str) -> None:
    """
    /sen <message> — Primary Sentinel interaction command.

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
        await _persist_thread_id(thread.id)
        logger.info(f"Created thread {thread.id} '{thread_name}' for user {interaction.user.id}")
    except discord.Forbidden as exc:
        logger.error(f"Missing permission to create thread (403): {exc}")
    except discord.HTTPException as exc:
        logger.error(f"Failed to create thread (HTTP {exc.status}, code {exc.code}): {exc}")

    # 3. Route message — subcommand, help-intent, or AI
    user_id = str(interaction.user.id)
    ai_response = await _route_message(user_id, message)

    # 4. Send AI response — into thread if created, fallback to channel
    if thread:
        await thread.send(ai_response)
        await interaction.followup.send(f"Response ready in {thread.mention}", ephemeral=True)
    else:
        await interaction.followup.send(ai_response)


def main() -> None:
    bot.run(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
