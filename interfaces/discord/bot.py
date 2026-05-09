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
import re

import discord
import httpx
from aiohttp import web
from discord import app_commands
from shared.sentinel_client import SentinelCoreClient

import command_router
import core_call_bridge
import core_gateway
import discord_internal_notify
import discord_router_bridge
import embed_builders
import pathfinder_bridge
import pathfinder_cli
import pathfinder_error_mapper
import response_renderer

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

# 260427-vl1: admin-only gate for destructive ops (:vault-sweep). Fail-closed.
# Empty/unset env → no admins. "*" → open to all. Otherwise comma-separated
# Discord user IDs.
SENTINEL_ADMIN_USER_IDS_RAW = os.environ.get("SENTINEL_ADMIN_USER_IDS", "")
ADMIN_USER_IDS: "frozenset[str] | str"
if SENTINEL_ADMIN_USER_IDS_RAW.strip() == "*":
    ADMIN_USER_IDS = "*"
else:
    ADMIN_USER_IDS = frozenset(
        uid.strip() for uid in SENTINEL_ADMIN_USER_IDS_RAW.split(",") if uid.strip()
    )


def _is_admin(user_id: str) -> bool:
    """Fail-closed admin gate: empty allowlist refuses all."""
    if ADMIN_USER_IDS == "*":
        return True
    return bool(ADMIN_USER_IDS) and user_id in ADMIN_USER_IDS

# WR-04 fix: dedicated Foundry roll notification channel (avoids min()-by-snowflake heuristic)
_NOTIFY_CHANNEL_ID_RAW = os.environ.get("DISCORD_NOTIFY_CHANNEL_ID", "")
NOTIFY_CHANNEL_ID: int | None = int(_NOTIFY_CHANNEL_ID_RAW) if _NOTIFY_CHANNEL_ID_RAW.isdigit() else None

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
    return await core_call_bridge.call_core_message(
        sent_client=_sentinel_client,
        user_id=user_id,
        message=message,
    )


# --- 260427-vl1: note-import + inbox + vault-sweep helpers ---

_NOTE_CLOSED_VOCAB: frozenset[str] = frozenset(
    {"learning", "accomplishment", "journal", "reference", "observation", "noise", "unsure"}
)


def _format_classify_response(data: dict) -> str:
    return core_gateway.format_classify_response(data)


async def _call_core_note(user_id: str, content: str, topic: str | None) -> str:
    return await core_gateway.call_core_note(
        user_id=user_id,
        content=content,
        topic=topic,
        sentinel_client=_sentinel_client,
        core_url=SENTINEL_CORE_URL,
        api_key=SENTINEL_API_KEY,
    )


async def _call_core_inbox_list(user_id: str) -> str:
    return await core_gateway.call_core_inbox_list(
        user_id=user_id,
        core_url=SENTINEL_CORE_URL,
        api_key=SENTINEL_API_KEY,
    )


async def _call_core_inbox_classify(user_id: str, entry_n: int, topic: str) -> str:
    return await core_gateway.call_core_inbox_classify(
        user_id=user_id,
        entry_n=entry_n,
        topic=topic,
        note_closed_vocab=_NOTE_CLOSED_VOCAB,
        sentinel_client=_sentinel_client,
    )


async def _call_core_inbox_discard(user_id: str, entry_n: int) -> str:
    return await core_gateway.call_core_inbox_discard(
        user_id=user_id,
        entry_n=entry_n,
        sentinel_client=_sentinel_client,
    )


async def _call_core_sweep_start(
    user_id: str, force_reclassify: bool = False, dry_run: bool = False
) -> str:
    return await core_gateway.call_core_sweep_start(
        user_id=user_id,
        force_reclassify=force_reclassify,
        dry_run=dry_run,
        sentinel_client=_sentinel_client,
    )


async def _call_core_sweep_status(user_id: str) -> str:
    return await core_gateway.call_core_sweep_status(
        user_id=user_id,
        core_url=SENTINEL_CORE_URL,
        api_key=SENTINEL_API_KEY,
    )


# Relation types valid for :pf npc relate (D-13 — closed enum)
_VALID_RELATIONS = frozenset({"knows", "trusts", "hostile-to", "allied-with", "fears", "owes-debt"})

# IN-01: supported `:pf <noun>` top-level categories. Referenced from both
# the noun guard in _pf_dispatch and the usage/unknown-noun error strings
# so adding a new noun (e.g. `spell`) is a one-line change rather than a
# scavenger hunt through two mirrored literals.
_PF_NOUNS = pathfinder_cli.PF_NOUNS  # 260427-cui: ingest added; cartosia kept as deprecation alias


class RecapView(discord.ui.View):
    """Discord View with a 'Recap last session' button for session start (D-08, D-11).

    Constructed by the session 'start' verb handler when a prior ended session exists.
    The caller MUST set view.message = msg AFTER await channel.send(..., view=self) returns —
    do NOT set it before send(), or on_timeout will call None.edit() (PATTERNS.md anti-pattern).

    timeout=180.0 (D-11) — ephemeral, no bot-restart re-registration needed.
    """

    def __init__(self, recap_text: str):
        super().__init__(timeout=180.0)  # NEVER use timeout=None — would require re-registration
        self.recap_text = recap_text
        self.message = None  # set by caller after send() returns

    @discord.ui.button(label="Recap last session", style=discord.ButtonStyle.primary)
    async def recap_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="Last session recap",
            description=self.recap_text,
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        self.stop()
        if self.message:
            try:
                await self.message.edit(view=None)
            except Exception:
                pass

    async def on_timeout(self) -> None:
        if self.message:
            try:
                await self.message.edit(
                    content="Recap timed out — use `:pf session start --recap` to recap later.",
                    embed=None,
                    view=None,
                )
            except Exception:
                pass

# Phase 31 dialogue: pair `:pf npc say ...` user messages with their bot quote-block replies
# in a thread. Capture group 1 = names (must NOT contain newlines or pipes — they delimit the
# NPC list from the party line). Group 2 = everything after pipe; DOTALL lets it span newlines
# so a multi-line party_line is tolerated. Anchoring group 1 with [^\n|]+? prevents a crafted
# `:pf npc say Varek\nextra | text` from leaking newlines into the parsed NPC name list
# (WR-02 defence-in-depth; server-side _validate_npc_name already rejects control chars).
_SAY_PATTERN = re.compile(r"^:pf\s+npc\s+say\s+([^\n|]+?)\s*\|(.*)$", re.IGNORECASE | re.DOTALL)
_QUOTE_PATTERN = re.compile(r"^>\s+(.+)$", re.MULTILINE)


def _render_say_response(result: dict) -> str:
    """Format /npc/say response as stacked markdown quote blocks (D-03, D-18).

    - Each reply prefixed with `> ` (Discord quote markdown).
    - If `warning` is set (≥5 NPCs), prepend it with a blank-line separator.
    """
    replies = result.get("replies") or []
    warning = result.get("warning")
    lines: list[str] = []
    if warning:
        lines.append(warning)
        lines.append("")
    for r in replies:
        lines.append(f"> {r.get('reply', '')}")
    return "\n".join(lines) if lines else "_(no reply generated)_"


async def _extract_thread_history(
    thread,
    current_npc_names: set,
    bot_user_id: int,
    limit: int = 50,
) -> list:
    """Walk thread oldest→newest; pair `:pf npc say ...` user messages with the immediate
    bot quote-block reply. Filter to turns where any currently-named NPC appeared (D-13).

    `thread` is duck-typed: any object with an async `history(limit, oldest_first)` method.
    Filters on `bot_user_id` (not generic `.author.bot`) to avoid picking up other bots.
    """
    msgs = [m async for m in thread.history(limit=limit, oldest_first=True)]
    turns: list = []
    normalized_current = {n.lower() for n in current_npc_names}
    i = 0
    while i < len(msgs) - 1:
        m = msgs[i]
        if getattr(m.author, "bot", False) or not getattr(m, "content", None):
            i += 1
            continue
        match = _SAY_PATTERN.match(m.content.strip())
        if not match:
            i += 1
            continue
        name_list = [n.strip() for n in match.group(1).split(",") if n.strip()]
        name_list_lower = {n.lower() for n in name_list}
        party_line = match.group(2).strip()
        if not (name_list_lower & normalized_current):
            i += 1
            continue
        next_msg = msgs[i + 1]
        if getattr(next_msg.author, "id", None) != bot_user_id:
            i += 1
            continue
        quote_lines = _QUOTE_PATTERN.findall(getattr(next_msg, "content", "") or "")
        if not quote_lines:
            i += 2
            continue
        # WR-05: if the bot reply contained a different number of quote lines
        # than the user named NPCs (e.g. an embedded newline-then-`>` inside
        # an NPC reply inflated _QUOTE_PATTERN.findall), skip the turn rather
        # than mis-attributing quotes to `?` placeholder NPCs. Memory is
        # best-effort — dropping a malformed pairing is safer than half-
        # attributing it and misrouting scene-membership filtering downstream.
        if len(quote_lines) != len(name_list):
            logger.debug(
                "thread-history pair mismatch: %d names vs %d quote lines; skipping turn",
                len(name_list), len(quote_lines),
            )
            i += 2
            continue
        replies = [
            {"npc": name_list[idx], "reply": line}
            for idx, line in enumerate(quote_lines)
        ]
        turns.append({"party_line": party_line, "replies": replies})
        i += 2
    return turns


def build_stat_embed(data: dict) -> "discord.Embed":
    return embed_builders.build_stat_embed(data)


def build_foundry_roll_embed(data: dict) -> "discord.Embed":
    return embed_builders.build_foundry_roll_embed(data)


def build_harvest_embed(data: dict) -> "discord.Embed":
    return embed_builders.build_harvest_embed(data)


def build_session_embed(data: dict) -> "discord.Embed":
    return embed_builders.build_session_embed(data)


def build_ruling_embed(data: dict) -> "discord.Embed":
    return embed_builders.build_ruling_embed(data)


async def _pf_dispatch(
    args: str,
    user_id: str,
    attachments: list | None = None,
    channel=None,
    author_display_name: str | None = None,
) -> "str | dict":
    """Route ':pf <noun> <verb> <rest>' to pathfinder module endpoints.

    Called from handle_sentask_subcommand when subcmd == 'pf' (D-04).
    Uses post_to_module() on SentinelCoreClient — NOT _call_core() (D-03).

    Return type widened in Phase 30: text-only verbs (create/update/show/relate/
    import/token) return str; rich-response verbs (export/stat/pdf) return a typed
    dict {"type": "file"|"embed", ...} that the on_message and /sen handlers
    dispatch to discord.File / discord.Embed.

    `channel` (Phase 31, WR-01 fix): the Discord channel the command came from.
    When it is a `discord.Thread`, the `say` branch walks it for DLG-03 memory
    (D-11..D-14). Callers that do not pass a channel (tests, slash path without a
    thread) get empty history — the branch degrades gracefully.
    """
    async with httpx.AsyncClient() as http_client:
        return await pathfinder_bridge.dispatch_pf(
            args=args,
            user_id=user_id,
            attachments=attachments,
            channel=channel,
            bot_user=getattr(bot, "user", None),
            parse_pf_args=pathfinder_cli.parse_pf_args,
            sent_client=_sentinel_client,
            http_client=http_client,
            is_admin=_is_admin,
            valid_relations=_VALID_RELATIONS,
            builders={
                "build_harvest_embed": build_harvest_embed,
                "build_ruling_embed": build_ruling_embed,
                "recap_view_cls": RecapView,
                "build_session_embed": build_session_embed,
                "build_stat_embed": build_stat_embed,
                "render_say_response": _render_say_response,
            },
            extract_thread_history=_extract_thread_history,
            map_http_status=pathfinder_error_mapper.map_http_status,
            log_error=logger.error,
            author_display_name=author_display_name,
        )


async def _route_message(
    user_id: str,
    message: str,
    attachments: list | None = None,
    channel=None,
    author_display_name: str | None = None,
) -> "str | dict":
    # Phase 38 D-01: route through the bridge with sentinel_client + a fresh
    # httpx.AsyncClient so the dialog_router pre-gate can run. on_message body
    # remains untouched (D-04); only this call site gains additive kwargs.
    async with httpx.AsyncClient() as http_client:
        return await discord_router_bridge.route_message(
            user_id=user_id,
            message=message,
            attachments=attachments,
            channel=channel,
            command_router=command_router,
            handle_subcommand=handle_sentask_subcommand,
            call_core=_call_core,
            subcommand_help=SUBCOMMAND_HELP,
            sentinel_client=_sentinel_client,
            http_client=http_client,
            author_display_name=author_display_name,
        )


async def handle_sentask_subcommand(
    subcmd: str,
    args: str,
    user_id: str,
    attachments: list | None = None,
    channel=None,
    author_display_name: str | None = None,
) -> "str | dict":
    return await discord_router_bridge.handle_subcommand(
        subcmd=subcmd,
        args=args,
        user_id=user_id,
        attachments=attachments,
        channel=channel,
        command_router=command_router,
        kwargs={
            "pf_dispatch": _pf_dispatch,
            "author_display_name": author_display_name,
            "call_core": _call_core,
            "call_core_note": _call_core_note,
            "call_core_inbox_list": _call_core_inbox_list,
            "call_core_inbox_classify": _call_core_inbox_classify,
            "call_core_inbox_discard": _call_core_inbox_discard,
            "call_core_sweep_start": _call_core_sweep_start,
            "call_core_sweep_status": _call_core_sweep_status,
            "is_admin": _is_admin,
            "note_closed_vocab": _NOTE_CLOSED_VOCAB,
            "plugin_prompts": _PLUGIN_PROMPTS,
            "subcommand_prompts": _SUBCOMMAND_PROMPTS,
            "subcommand_help": SUBCOMMAND_HELP,
        },
    )


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
        logger.warning("Failed to persist thread ID %s: %s", thread_id, exc)


class SentinelBot(discord.Client):
    """Discord client with app_commands tree for slash command support."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True  # required to read thread reply content
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self._internal_runner: "web.AppRunner | None" = None  # D-14: aiohttp internal server

    async def setup_hook(self) -> None:
        """Called once per process startup — safe point to sync command tree and load thread IDs."""
        synced_commands = await self.tree.sync()
        synced_count = len(synced_commands) if synced_commands else 0
        logger.info(
            "Slash commands synced to Discord API: %d command(s) registered "
            "(global sync — up to 1hr propagation to all servers).",
            synced_count,
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
                    logger.info("Loaded %d persisted thread IDs", len(SENTINEL_THREAD_IDS))
                elif resp.status_code == 404:
                    logger.info("No discord-threads.md yet — starting fresh")
                else:
                    logger.warning("Unexpected status %d loading thread IDs", resp.status_code)
        except Exception as exc:
            logger.warning("Could not load thread IDs from vault: %s", exc)

        # D-14: Start internal aiohttp notification server for Foundry VTT event ingest (Phase 35)
        internal_port = int(os.environ.get("DISCORD_BOT_INTERNAL_PORT", "8001"))
        _aiohttp_app = web.Application()
        _aiohttp_app.router.add_post("/internal/notify", self._handle_internal_notify)
        self._internal_runner = web.AppRunner(_aiohttp_app)
        await self._internal_runner.setup()
        site = web.TCPSite(self._internal_runner, "0.0.0.0", internal_port)  # CR-01 fix: bind all interfaces so pf2e-module can reach via Docker bridge
        await site.start()
        logger.info("Internal notification server started on port %d", internal_port)

    async def _handle_internal_notify(self, request: "web.Request") -> "web.Response":
        """Handle POST /internal/notify from pf2e-module (D-14, FVT-02).

        Validates X-Sentinel-Key, builds embed, sends to first ALLOWED_CHANNEL_IDS channel.
        """
        key = request.headers.get("X-Sentinel-Key", "")
        if key != SENTINEL_API_KEY:
            return web.Response(status=401)
        try:
            data = await request.json()
        except Exception:
            return web.Response(status=400)

        channel_id = discord_internal_notify.resolve_notify_channel_id(NOTIFY_CHANNEL_ID, ALLOWED_CHANNEL_IDS)  # WR-04 fix: explicit var first, fallback to oldest allowed
        if channel_id is None:
            logger.warning("_handle_internal_notify: no DISCORD_ALLOWED_CHANNELS configured")
            return web.Response(status=500)

        channel = self.get_channel(channel_id)
        if channel is None:
            logger.warning(
                "_handle_internal_notify: channel %d not found or not cached", channel_id
            )
            return web.Response(status=500)

        event_type = data.get("event_type", "roll")
        if event_type == "roll":
            embed = build_foundry_roll_embed(data)
        elif event_type == "chat":
            # WR-03 fix: forward chat events to Discord (Phase 35 MVP)
            embed = discord_internal_notify.build_chat_embed(data)
        else:
            logger.info("_handle_internal_notify: unsupported event_type %r — ignoring", event_type)
            return web.Response(status=200)
        try:
            await channel.send(embed=embed)
        except Exception as exc:
            logger.error("_handle_internal_notify: channel.send failed: %s", exc)
            return web.Response(status=500)

        return web.Response(status=200)

    async def on_ready(self) -> None:
        user = self.user
        logger.info("Sentinel bot ready: %s (id=%s)", user, user.id if user else "unknown")

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
            asyncio.create_task(_persist_thread_id(thread.id))

        user_id = str(message.author.id)
        logger.info("Thread reply from %s in thread %s: %s", user_id, message.channel.id, message.content[:60])

        # typing() auto-renews the typing indicator every 10s while the event loop is responsive.
        async with message.channel.typing():
            ai_response = await _route_message(
                user_id,
                message.content,
                attachments=list(message.attachments),
                channel=message.channel,
                author_display_name=getattr(message.author, "display_name", None),
            )

        await response_renderer.send_rendered_response(message.channel.send, ai_response)

    async def close(self) -> None:
        """Clean up aiohttp internal server before closing discord client (Pitfall 5)."""
        if self._internal_runner:
            await self._internal_runner.cleanup()
        await super().close()


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

    try:
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
            logger.info("Created thread %s '%s' for user %s", thread.id, thread_name, interaction.user.id)
        except discord.Forbidden as exc:
            logger.error("Missing permission to create thread (403): %s", exc)
        except discord.HTTPException as exc:
            logger.error("Failed to create thread (HTTP %s, code %s): %s", exc.status, exc.code, exc)

        # 3. Route message — subcommand, help-intent, or AI.
        # Phase 31 (WR-01): forward the thread we just created as the channel so the
        # `:pf npc say` branch can walk its history. First turn in a fresh thread has
        # no prior messages, so history ends up empty — still correct.
        user_id = str(interaction.user.id)
        ai_response = await _route_message(
            user_id, message, channel=thread if thread is not None else interaction.channel
        )

        # 4. Send AI response — into thread if created, fallback to channel
        if thread:
            await response_renderer.send_rendered_response(thread.send, ai_response)
            await interaction.followup.send(f"Response ready in {thread.mention}", ephemeral=True)
        else:
            await response_renderer.send_rendered_response(interaction.followup.send, ai_response)

    except Exception as exc:
        logger.exception("Unhandled error in /sen after defer — sending error followup: %s", exc)
        await interaction.followup.send(
            "Something went wrong — the Sentinel encountered an error.",
            ephemeral=True,
        )


def main() -> None:
    bot.run(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
