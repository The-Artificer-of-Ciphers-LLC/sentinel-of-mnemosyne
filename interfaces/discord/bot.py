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
import base64
import logging
import os
import re

import discord
import httpx
from aiohttp import web
from discord import app_commands
from shared.sentinel_client import SentinelCoreClient

import command_router
import core_gateway
import pathfinder_cli
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
    """
    Route message through the shared SentinelCoreClient.
    Creates a per-call httpx.AsyncClient as the client owns no persistent connection state.
    """
    async with httpx.AsyncClient() as http_client:
        return await _sentinel_client.send_message(user_id, message, http_client)


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
    """Build a Discord Embed from /npc/stat module response (OUT-03, D-13 through D-17).

    data: {"fields": {...frontmatter...}, "stats": {...stats block or {}...}, "slug": ..., "path": ...}
    Layout: AC+HP inline, Fort+Ref+Will inline, Speed non-inline, Skills non-inline, Perception inline.
    Absent stats block: mechanical fields omitted (D-16).
    """
    fields = data.get("fields", {})
    stats = data.get("stats") or {}
    embed = discord.Embed(
        title=(
            f"{fields.get('name', '?')} "
            f"(Level {fields.get('level', '?')} "
            f"{fields.get('ancestry', '')} {fields.get('class', '')})"
        ),
        description=fields.get("personality", ""),
        color=discord.Color.dark_gold(),
    )
    if stats:
        embed.add_field(name="AC", value=str(stats.get("ac", "—")), inline=True)
        embed.add_field(name="HP", value=str(stats.get("hp", "—")), inline=True)
        embed.add_field(name="​", value="​", inline=True)
        embed.add_field(name="Fort", value=str(stats.get("fortitude", "—")), inline=True)
        embed.add_field(name="Ref", value=str(stats.get("reflex", "—")), inline=True)
        embed.add_field(name="Will", value=str(stats.get("will", "—")), inline=True)
        embed.add_field(name="Speed", value=f"{stats.get('speed', '—')} ft.", inline=False)
        skills = stats.get("skills") or {}
        if skills:
            if isinstance(skills, dict):
                skill_text = ", ".join(
                    f"{k.capitalize()} +{v}" for k, v in skills.items()
                )
            else:
                skill_text = str(skills)
            embed.add_field(
                name="Skills",
                value=skill_text[:900] + ("..." if len(skill_text) > 900 else ""),
                inline=False,
            )
        if stats.get("perception") is not None:
            embed.add_field(name="Perception", value=f"+{stats['perception']}", inline=True)
    embed.set_footer(text=f"Mood: {fields.get('mood', 'neutral')}")
    return embed


def build_foundry_roll_embed(data: dict) -> "discord.Embed":
    """Build embed for a Foundry roll event notification (D-16, FVT-03).

    Title: "{emoji} {outcome_label} | {actor} vs {target}" (or actor + roll_type if no target)
    Description: LLM narrative (or empty)
    Footer: "Roll: {total} | DC/AC: {dc}" or "DC: [hidden]" + optional item_name
    """
    # WR-04: keep in sync with app/foundry.py OUTCOME_EMOJIS/OUTCOME_LABELS (separate containers).
    OUTCOME_EMOJIS = {
        "criticalSuccess": "🎯",
        "success": "✅",
        "failure": "❌",
        "criticalFailure": "💀",
    }
    OUTCOME_LABELS = {
        "criticalSuccess": "Critical Hit!",
        "success": "Success",
        "failure": "Failure",
        "criticalFailure": "Critical Failure!",
    }
    OUTCOME_COLORS = {
        "criticalSuccess": discord.Color.gold(),
        "success": discord.Color.green(),
        "failure": discord.Color.orange(),
        "criticalFailure": discord.Color.red(),
    }
    outcome = data.get("outcome", "")
    actor = data.get("actor_name", "?")
    target = data.get("target_name")
    narrative = data.get("narrative", "")
    roll_total = data.get("roll_total", "?")
    dc = data.get("dc")
    dc_hidden = data.get("dc_hidden", False)
    item_name = data.get("item_name", "")
    roll_type = data.get("roll_type", "check")

    emoji = OUTCOME_EMOJIS.get(outcome, "🎲")
    label = OUTCOME_LABELS.get(outcome, outcome.capitalize() if outcome else "Roll")
    color = OUTCOME_COLORS.get(outcome, discord.Color.blue())

    if target:
        title = f"{emoji} {label} | {actor} vs {target}"
    else:
        title = f"{emoji} {label} | {actor} ({roll_type})"

    dc_str = "DC: [hidden]" if dc_hidden else f"DC/AC: {dc}"
    footer_parts = [f"Roll: {roll_total}", dc_str]
    if item_name:
        footer_parts.append(item_name)

    embed = discord.Embed(
        title=title,
        description=narrative[:4000] if narrative else None,
        color=color,
    )
    embed.set_footer(text=" | ".join(footer_parts))
    return embed


def build_harvest_embed(data: dict) -> "discord.Embed":
    """Build a Discord Embed from /harvest module response (HRV-01..06, D-03a, D-04).

    Single-monster: title=monster name+level, description=note/warning.
    Batch: title='Harvest report — N monsters', description=generated-count warning.
    Fields: one per aggregated component type (D-04) with Medicine DC + monsters tally + craftable bullets.
    Footer: source attribution (FoundryVTT pf2e | LLM generated | Mixed sources).
    """
    monsters = data.get("monsters", []) or []
    aggregated = data.get("aggregated", []) or []
    footer_text = data.get("footer", "")

    if len(monsters) == 1:
        m = monsters[0]
        title = f"{m.get('monster', '?')} (Level {m.get('level', '?')})"
        description_parts: list[str] = []
        if m.get("note"):
            description_parts.append(f"_{m['note']}_")
        if not m.get("verified", True):
            description_parts.append("⚠ Generated — verify against sourcebook")
        description = "\n".join(description_parts)
    else:
        title = f"Harvest report — {len(monsters)} monsters"
        generated_count = sum(1 for m in monsters if not m.get("verified", True))
        description = (
            f"⚠ {generated_count}/{len(monsters)} entries include generated data — verify."
            if generated_count
            else ""
        )

    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.dark_green(),
    )

    for comp in aggregated:
        craftable_lines = [
            f"• {c.get('name', '?')} (Crafting DC {c.get('crafting_dc', '?')}, {c.get('value', '?')})"
            for c in comp.get("craftable", []) or []
        ]
        monsters_tally = ", ".join(comp.get("monsters", []) or [])
        field_value = (
            f"Medicine DC {comp.get('medicine_dc', '?')}\n"
            f"From: {monsters_tally}\n"
            + "\n".join(craftable_lines)
        )[:1024]  # Discord field value cap
        embed.add_field(name=comp.get("type", "?"), value=field_value, inline=False)

    embed.set_footer(text=footer_text)
    return embed


def build_session_embed(data: dict) -> "discord.Embed":
    """Build a Discord Embed from /session module response (SES-01..03, D-08, D-18, D-27).

    Dispatches on data["type"]:
    - "start": session started confirmation + optional recap button hint
    - "log": event appended confirmation
    - "undo": event removed confirmation
    - "show": narrative story-so-far
    - "end": session closed + recap
    - "end_skeleton": session closed but recap failed + retry hint
    """
    verb_type = data.get("type", "")

    if verb_type == "start":
        embed = discord.Embed(
            title=f"Session started — {data.get('date', '?')}",
            description=f"Note: `{data.get('path', '?')}`",
            color=discord.Color.green(),
        )
        if data.get("recap_available") and not data.get("recap_text"):
            embed.set_footer(text="Use the button below to recap last session.")

    elif verb_type == "log":
        embed = discord.Embed(
            title="Event logged",
            description=f"`{data.get('line', '?')}`",
            color=discord.Color.blue(),
        )

    elif verb_type == "undo":
        removed = data.get("removed", "?")
        remaining = data.get("remaining", "?")
        embed = discord.Embed(
            title="Event removed",
            description=f"Removed: `{removed}`\nEvents remaining: {remaining}",
            color=discord.Color.orange(),
        )

    elif verb_type == "show":
        embed = discord.Embed(
            title=f"Story so far — {data.get('date', '?')}",
            description=data.get("narrative", "_No narrative generated._"),
            color=discord.Color.blue(),
        )

    elif verb_type == "end":
        recap = data.get("recap", "")
        npcs = ", ".join(f"[[{s}]]" for s in (data.get("npcs") or []))
        locations = ", ".join(f"[[{s}]]" for s in (data.get("locations") or []))
        embed = discord.Embed(
            title=f"Session ended — {data.get('date', '?')}",
            description=(recap[:2048] if recap else "_Recap empty._"),
            color=discord.Color.dark_green(),
        )
        if npcs:
            embed.add_field(name="NPCs", value=npcs[:1024], inline=False)
        if locations:
            embed.add_field(name="Locations", value=locations[:1024], inline=False)

    elif verb_type == "end_skeleton":
        embed = discord.Embed(
            title="Session ended (recap failed)",
            description=(
                f"Note written: `{data.get('path', '?')}`\n"
                f"Error: {str(data.get('error', '?'))[:200]}\n\n"
                "_Use `:pf session end --retry-recap` to regenerate the recap._"
            ),
            color=discord.Color.red(),
        )

    else:
        # Generic fallback for unknown or error responses from route
        error_msg = data.get("error") or data.get("detail") or str(data)
        embed = discord.Embed(
            title="Session",
            description=str(error_msg)[:2048],
            color=discord.Color.red(),
        )

    return embed


def build_ruling_embed(data: dict) -> "discord.Embed":
    """Build a Discord Embed from POST /modules/pathfinder/rule/query response (D-08, D-09).

    Input shape (D-08):
      {
        "question": str, "answer": str, "why": str,
        "source": str | None, "citations": list[dict],
        "marker": "source" | "generated" | "declined",
        "topic": str | None,
        "reused": bool (optional), "reuse_note": str (optional),
      }

    Renders four logical fields:
      * title = question (truncated to 250 chars)
      * description = (reuse_note italic if reused) + banner + answer
      * Why field (always, inline=False)
      * Source field (inline=False, only when source non-null)
      * Citations field (inline=False, only when citations non-empty)
      * footer = "topic: <topic> | ORC license (Paizo) — Foundry pf2e"

    Color:
      * dark_green — marker="source"
      * dark_gold  — marker="generated"
      * red        — marker="declined"

    L-5: Colors rely on discord.Color.{dark_green, dark_gold, red} — all three
    are available in interfaces/discord/tests/conftest.py's Color stub (Wave 0
    added dark_gold + red). This function does NOT stub or shim colors itself.
    """
    marker = data.get("marker", "generated")
    question = data.get("question", "") or ""
    answer = data.get("answer", "") or ""
    why = data.get("why", "") or ""
    source_str = data.get("source")
    citations = data.get("citations", []) or []
    reused = bool(data.get("reused", False))
    reuse_note = data.get("reuse_note", "") or ""
    topic = data.get("topic") or "?"

    title = question[:250] if question else "Rules Ruling"

    description_parts: list[str] = []
    if reused and reuse_note:
        description_parts.append(f"_{reuse_note}_")
    if marker == "generated":
        description_parts.append("⚠ **[GENERATED — verify]**")
    elif marker == "declined":
        description_parts.append("🚫 PF1/pre-Remaster query declined")
    if answer:
        description_parts.append(answer)
    description = "\n\n".join(description_parts)[:4000]

    color = {
        "source": discord.Color.dark_green(),
        "generated": discord.Color.dark_gold(),
        "declined": discord.Color.red(),
    }.get(marker, discord.Color.dark_gold())

    embed = discord.Embed(title=title, description=description, color=color)
    if why:
        embed.add_field(name="Why", value=why[:1024], inline=False)
    if source_str:
        embed.add_field(name="Source", value=source_str[:1024], inline=False)
    if citations:
        cite_lines: list[str] = []
        for c in citations[:3]:  # cap at 3 for embed space
            line = f"• {c.get('book', '?')}"
            if c.get("page"):
                line += f" p. {c['page']}"
            line += f" — {c.get('section', '?')}"
            if c.get("url"):
                line += f" | {c['url']}"
            cite_lines.append(line)
        embed.add_field(name="Citations", value="\n".join(cite_lines)[:1024], inline=False)
    embed.set_footer(text=f"topic: {topic} | ORC license (Paizo) — Foundry pf2e")
    return embed


async def _pf_dispatch(
    args: str,
    user_id: str,
    attachments: list | None = None,
    channel=None,
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
    parts = args.strip().split(" ", 2)
    # 260427-czb: bare `:pf cartosia` returns its own usage string (the
    # generic usage doesn't mention this verb because it's admin-gated).
    if len(parts) >= 1 and parts[0].lower() == "cartosia" and len(parts) < 2:
        return (
            "Usage: `:pf cartosia <archive_path> [--live] [--dry-run] "
            "[--limit N] [--force] [--confirm-large]` (admin-only)"
        )
    if len(parts) < 2:
        # IN-01: derive the usage message from _PF_NOUNS so new nouns show up
        # automatically. `npc` retains its verb list because it's the only
        # multi-verb noun in the current surface.
        return pathfinder_cli.usage_message()
    noun, verb = parts[0].lower(), parts[1].lower()
    rest = parts[2] if len(parts) > 2 else ""

    if noun not in _PF_NOUNS:
        return pathfinder_cli.unknown_noun_message(noun)

    try:
        async with httpx.AsyncClient() as http_client:
            if noun == "harvest":
                # Format: `:pf harvest <Name>[,<Name>...]` — comma-separated batch (D-04, Pitfall 5).
                # `:pf harvest` with zero args is caught by the generic `len(parts) < 2`
                # early-return at the top of `_pf_dispatch` — it returns the combined
                # usage string BEFORE this branch runs. So the `if not names:` fallback
                # below is defensive (covers `:pf harvest ,` or `:pf harvest  ` where
                # parts[1] exists but names parses empty), not redundant.
                # WR-04: rejoin parts[1:] from the already-split noun/verb/rest tuple
                # rather than slicing the original string by len("harvest"). The slice
                # approach baked in a whitespace-class assumption — .strip() is the
                # source of truth for what counts as "whitespace" when the user
                # provides e.g. a non-breaking space before "harvest", and any
                # mismatch between that and the fixed-width len() slice silently
                # corrupted the name. split(" ", 2) already produced the post-noun
                # remainder cleanly, so use that.
                harvest_args = " ".join(parts[1:]).strip()
                names = [n.strip() for n in harvest_args.split(",") if n.strip()]
                if not names:
                    return "Usage: `:pf harvest <Name>[,<Name>...]`"
                result = await _sentinel_client.post_to_module(
                    "modules/pathfinder/harvest",
                    {"names": names, "user_id": user_id},
                    http_client,
                )
                return {
                    "type": "embed",
                    "content": "",
                    "embed": build_harvest_embed(result),
                }

            if noun in ("cartosia", "ingest"):
                # 260427-cui: `:pf ingest <subfolder>` is the generic verb; `:pf cartosia`
                # is preserved as a deprecation alias for one release that pins
                # subfolder='archive/cartosia' regardless of the archive_path token.
                # Admin-only: this writes ~50+ vault files.
                if not _is_admin(user_id):
                    return (
                        "Admin only. Set SENTINEL_ADMIN_USER_IDS in your env to use this command."
                    )
                tail = " ".join(parts[1:]).strip()
                tokens = [t for t in tail.split() if t]
                archive_path: str | None = None
                live = False
                force_flag = False
                confirm_large = False
                limit_val: int | None = None
                i = 0
                while i < len(tokens):
                    tok = tokens[i]
                    if tok == "--live":
                        live = True
                    elif tok == "--dry-run":
                        live = False
                    elif tok == "--force":
                        force_flag = True
                    elif tok == "--confirm-large":
                        confirm_large = True
                    elif tok == "--limit":
                        if i + 1 >= len(tokens) or not tokens[i + 1].lstrip("-").isdigit():
                            return "Usage: `--limit N` requires an integer argument."
                        limit_val = int(tokens[i + 1])
                        i += 1
                    elif tok.startswith("--"):
                        return f"Unknown flag `{tok}`."
                    else:
                        if archive_path is None:
                            archive_path = tok
                        else:
                            archive_path = f"{archive_path} {tok}"
                    i += 1
                if not archive_path:
                    if noun == "cartosia":
                        return (
                            "Usage: `:pf cartosia <archive_path> [--live] [--dry-run] "
                            "[--limit N] [--force] [--confirm-large]` (admin-only)"
                        )
                    return (
                        "Usage: `:pf ingest <subfolder> [--live] [--dry-run] "
                        "[--limit N] [--force] [--confirm-large]` (admin-only)"
                    )
                # Cartosia alias pins subfolder='archive/cartosia'; ingest uses the
                # archive_path token verbatim as both archive_root AND subfolder.
                if noun == "cartosia":
                    subfolder_val = "archive/cartosia"
                else:
                    subfolder_val = archive_path
                payload = {
                    "archive_root": archive_path,
                    "subfolder": subfolder_val,
                    "dry_run": not live,
                    "limit": limit_val,
                    "force": force_flag,
                    "confirm_large": confirm_large,
                    "user_id": user_id,
                }
                result = await _sentinel_client.post_to_module(
                    "modules/pathfinder/ingest", payload, http_client
                )
                if not isinstance(result, dict):
                    return f"PF2e archive ingest returned unexpected response: {result!r}"
                report_path = result.get("report_path", "?")
                kind_word = "live import" if live else "dry-run"
                summary = (
                    f"PF2e archive ingest {kind_word} complete.\n"
                    f"Report: `{report_path}`\n"
                    f"NPCs: {result.get('npc_count', 0)} "
                    f"(skipped existing: {result.get('skipped_existing', 0)}) | "
                    f"Locations: {result.get('location_count', 0)} | "
                    f"Homebrew: {result.get('homebrew_count', 0)} | "
                    f"Harvest: {result.get('harvest_count', 0)} | "
                    f"Lore: {result.get('lore_count', 0)} | "
                    f"Sessions: {result.get('session_count', 0)} | "
                    f"Arcs: {result.get('arc_count', 0)} | "
                    f"Factions: {result.get('faction_count', 0)} | "
                    f"Dialogue: {result.get('dialogue_count', 0)} | "
                    f"Skipped: {result.get('skip_count', 0)} | "
                    f"Errors: {len(result.get('errors', []) or [])}"
                )
                if noun == "cartosia":
                    summary = (
                        "Deprecated: use `:pf ingest archive/cartosia` instead — "
                        "forwarding...\n\n" + summary
                    )
                return summary

            if noun == "rule":
                # D-10 sub-verbs: <free text> (default) | show <topic> | history [N] | list.
                # `verb` here is the second whitespace-token after `rule`. If it
                # matches a reserved sub-verb token we route to that endpoint;
                # otherwise the entire post-noun string is the free-text query.
                reserved = {"show", "history", "list"}
                if verb in reserved:
                    sub_verb = verb
                    sub_arg = rest.strip()
                else:
                    sub_verb = "query"
                    # Entire post-noun string is the query (verb + rest re-joined).
                    full_tail = " ".join(parts[1:]).strip()
                    sub_arg = full_tail

                if sub_verb == "query" and not sub_arg:
                    return (
                        "Usage: `:pf rule <question>` | "
                        "`:pf rule show <topic>` | "
                        "`:pf rule history [N]` | "
                        "`:pf rule list`"
                    )

                if sub_verb == "list":
                    result = await _sentinel_client.post_to_module(
                        "modules/pathfinder/rule/list", {}, http_client,
                    )
                    topics = result.get("topics", []) or [] if isinstance(result, dict) else []
                    if not topics:
                        return "_No rulings cached yet._"
                    lines = [
                        f"• `{t.get('slug', '?')}` ({t.get('count', 0)} rulings, last active {str(t.get('last_activity', 'never'))[:19]})"
                        for t in topics
                    ]
                    return "**Rule topics with cached rulings:**\n" + "\n".join(lines)

                if sub_verb == "show":
                    if not sub_arg:
                        return "Usage: `:pf rule show <topic>`"
                    result = await _sentinel_client.post_to_module(
                        "modules/pathfinder/rule/show",
                        {"topic": sub_arg},
                        http_client,
                    )
                    rulings = result.get("rulings", []) or [] if isinstance(result, dict) else []
                    if not rulings:
                        return f"_No rulings under `{sub_arg}`._"
                    lines = [
                        f"• `{r.get('hash', '?')}` — {(r.get('question', '') or '')[:80]} [{r.get('marker', '?')}]"
                        for r in rulings
                    ]
                    return f"**Rulings under `{sub_arg}`** ({len(rulings)}):\n" + "\n".join(lines)

                if sub_verb == "history":
                    n = 10
                    if sub_arg:
                        try:
                            # IN-03 fix: RESEARCH §History Count caps N at 50.
                            n = max(1, min(50, int(sub_arg)))
                        except ValueError:
                            pass
                    result = await _sentinel_client.post_to_module(
                        "modules/pathfinder/rule/history",
                        {"n": n},
                        http_client,
                    )
                    rulings = result.get("rulings", []) or [] if isinstance(result, dict) else []
                    if not rulings:
                        return "_No rulings yet._"
                    lines = [
                        f"• {str(r.get('last_reused_at', ''))[:19]} — `{r.get('topic', '?')}/{(r.get('question', '') or '')[:60]}` → {r.get('marker', '?')}"
                        for r in rulings
                    ]
                    return f"**Recent rulings (N={n}):**\n" + "\n".join(lines)

                # sub_verb == "query" — D-11 slow path with placeholder+edit UX.
                # L-9: the bot's httpx.AsyncClient inherits the default 5s connect
                # timeout — a fresh embed + retrieve + LLM compose can take 5-15s
                # so the placeholder hides the latency from the DM. The sentinel-core
                # proxy's own timeout (configured upstream) is the real per-call ceiling.
                placeholder = None
                if channel is not None and hasattr(channel, "send"):
                    try:
                        placeholder = await channel.send(
                            f"🤔 _Thinking on PF2e rules: {sub_arg[:80]}..._"
                        )
                    except Exception:
                        placeholder = None
                try:
                    result = await _sentinel_client.post_to_module(
                        "modules/pathfinder/rule/query",
                        {"query": sub_arg, "user_id": user_id},
                        http_client,
                    )
                    embed = build_ruling_embed(result)
                    if placeholder is not None and hasattr(placeholder, "edit"):
                        try:
                            await placeholder.edit(content="", embed=embed)
                            # Suppressed — outer handler does NOT re-send.
                            return {"type": "suppressed", "content": "", "embed": embed}
                        except Exception:
                            pass
                    return {"type": "embed", "content": "", "embed": embed}
                except Exception as exc:
                    if placeholder is not None and hasattr(placeholder, "edit"):
                        try:
                            await placeholder.edit(
                                content=f"⚠ Rules query failed — {str(exc).splitlines()[0]}",
                                embed=None,
                            )
                            return {"type": "suppressed", "content": "", "embed": None}
                        except Exception:
                            pass
                    raise

            elif noun == "session":
                # D-04: session noun dispatch — verbs: start, log, end, show, undo
                # Flags parsed here and stripped from event text before forwarding to route.
                force = "--force" in rest
                recap_flag = "--recap" in rest
                retry_recap = "--retry-recap" in rest

                # Strip flag tokens from event text so "log" verb gets clean text
                # T-34-W4-01 mitigation: flags read from rest only; event_text sent in args
                # so route cannot be tricked by embedding --force in the event body.
                event_text = rest
                for flag_token in ("--force", "--recap", "--retry-recap"):
                    event_text = event_text.replace(flag_token, "").strip()

                payload = {
                    "verb": verb,
                    "args": event_text,
                    "flags": {
                        "force": force,
                        "recap": recap_flag,
                        "retry_recap": retry_recap,
                    },
                    "user_id": user_id,
                }

                # D-20: slow-query placeholder for show and end (LLM calls take 2-15s)
                needs_placeholder = verb in {"show", "end"}
                placeholder = None
                if needs_placeholder and channel is not None and hasattr(channel, "send"):
                    try:
                        placeholder = await channel.send("_Generating session narrative..._")
                    except Exception:
                        placeholder = None

                try:
                    result = await _sentinel_client.post_to_module(
                        "modules/pathfinder/session", payload, http_client
                    )
                except Exception as exc:
                    if placeholder is not None and hasattr(placeholder, "edit"):
                        try:
                            await placeholder.edit(
                                content=f"Session operation failed — {exc}", embed=None
                            )
                            return {"type": "suppressed", "content": "", "embed": None}
                        except Exception:
                            pass
                    raise

                # D-08/D-09: start verb — show recap button if prior session recap available
                if verb == "start" and result.get("recap_text") and not recap_flag:
                    recap_view = RecapView(recap_text=result["recap_text"])
                    embed = build_session_embed(result)
                    if channel is not None and hasattr(channel, "send"):
                        try:
                            msg = await channel.send(embed=embed, view=recap_view)
                            recap_view.message = msg  # D-11: set AFTER send so on_timeout can edit
                            return {"type": "suppressed", "content": "", "embed": embed}
                        except Exception:
                            pass
                    return {"type": "embed", "content": "", "embed": embed}

                embed = build_session_embed(result)
                if placeholder is not None and hasattr(placeholder, "edit"):
                    try:
                        await placeholder.edit(content="", embed=embed)
                        return {"type": "suppressed", "content": "", "embed": embed}
                    except Exception:
                        pass
                return {"type": "embed", "content": "", "embed": embed}

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
                    "modules/pathfinder/npc/show", {"name": npc_name, "user_id": user_id}, http_client
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

            elif verb == "export":
                npc_name = rest.strip()
                if not npc_name:
                    return "Usage: `:pf npc export <name>`"
                result = await _sentinel_client.post_to_module(
                    "modules/pathfinder/npc/export-foundry", {"name": npc_name}, http_client
                )
                import json as _json
                json_bytes = _json.dumps(result["actor"], indent=2).encode("utf-8")
                return {
                    "type": "file",
                    "content": f"Foundry actor JSON for **{npc_name}**:",
                    "file_bytes": json_bytes,
                    "filename": result["filename"],
                }

            elif verb == "token":
                npc_name = rest.strip()
                if not npc_name:
                    return "Usage: `:pf npc token <name>`"
                result = await _sentinel_client.post_to_module(
                    "modules/pathfinder/npc/token", {"name": npc_name}, http_client
                )
                return result.get("prompt", "No prompt generated.")

            elif verb == "token-image":
                # Close the Midjourney loop (PLAN.md token-image extension).
                # User replies in a thread with a PNG attached; bot fetches bytes,
                # base64-encodes, POSTs to /npc/token-image which stores under
                # mnemosyne/pf2e/tokens/<slug>.png and updates note frontmatter.
                npc_name = rest.strip()
                if not npc_name:
                    return "Usage: `:pf npc token-image <name>` — attach a PNG as a reply in this thread."
                if not attachments:
                    return (
                        f"Usage: `:pf npc token-image {npc_name}` — attach the Midjourney-"
                        "generated PNG as a reply in this thread."
                    )
                attachment = attachments[0]
                content_type = getattr(attachment, "content_type", "") or ""
                if not content_type.startswith("image/"):
                    return (
                        f"Expected an image attachment (got `{content_type or 'unknown'}`). "
                        "Midjourney exports PNG — re-attach the PNG and try again."
                    )
                fetch_resp = await http_client.get(str(attachment.url), timeout=30.0)
                fetch_resp.raise_for_status()
                image_bytes = fetch_resp.content
                image_b64 = base64.b64encode(image_bytes).decode("ascii")
                result = await _sentinel_client.post_to_module(
                    "modules/pathfinder/npc/token-image",
                    {"name": npc_name, "image_b64": image_b64},
                    http_client,
                )
                return (
                    f"Token image saved for **{npc_name}** "
                    f"({result.get('size_bytes', len(image_bytes))} bytes) → `{result.get('token_path', '?')}`.\n"
                    f"Run `:pf npc pdf {npc_name}` to see it embedded in the stat card."
                )

            elif verb == "stat":
                npc_name = rest.strip()
                if not npc_name:
                    return "Usage: `:pf npc stat <name>`"
                result = await _sentinel_client.post_to_module(
                    "modules/pathfinder/npc/stat", {"name": npc_name}, http_client
                )
                embed = build_stat_embed(result)
                return {
                    "type": "embed",
                    "content": "",
                    "embed": embed,
                }

            elif verb == "pdf":
                npc_name = rest.strip()
                if not npc_name:
                    return "Usage: `:pf npc pdf <name>`"
                result = await _sentinel_client.post_to_module(
                    "modules/pathfinder/npc/pdf", {"name": npc_name}, http_client
                )
                pdf_bytes = base64.b64decode(result["data_b64"])
                return {
                    "type": "file",
                    "content": f"PDF stat card for **{npc_name}**:",
                    "file_bytes": pdf_bytes,
                    "filename": result["filename"],
                }

            elif verb == "say":
                # DLG-01..03: in-character NPC dialogue with mood tracking.
                # Format: `:pf npc say <Name>[,<Name>...] | <party_line>` (D-01).
                # Empty party_line after pipe = scene-advance (D-02) — still valid.
                if "|" not in rest:
                    return "Usage: `:pf npc say <Name>[,<Name>...] | <party line>`"
                names_raw, _, party_line = rest.partition("|")
                names = [n.strip() for n in names_raw.split(",") if n.strip()]
                if not names:
                    return "Usage: `:pf npc say <Name>[,<Name>...] | <party line>`"

                # D-11..D-14: walk thread history when channel is a discord.Thread.
                # In unit tests the discord stub sets discord.Thread = object, so the
                # isinstance check is False for test SimpleNamespace channels; tests
                # pass channel=None and get history=[]. In production, channel is the
                # live Thread and the walker pairs user says with bot quote replies.
                history: list = []
                if channel is not None and isinstance(channel, discord.Thread):
                    try:
                        bot_user = bot.user
                        bot_user_id = bot_user.id if bot_user is not None else 0
                        history = await _extract_thread_history(
                            thread=channel,
                            current_npc_names=set(names),
                            bot_user_id=bot_user_id,
                            limit=50,
                        )
                    except Exception as exc:
                        logger.warning(
                            "Thread history walk failed (degrading to empty): %s", exc
                        )
                        history = []

                payload = {
                    "names": names,
                    "party_line": party_line.strip(),
                    "user_id": user_id,
                    "history": history,
                }
                result = await _sentinel_client.post_to_module(
                    "modules/pathfinder/npc/say", payload, http_client
                )
                return _render_say_response(result)

            else:
                return (
                    f"Unknown npc command `{verb}`. "
                    "Available: `create`, `update`, `show`, `relate`, `import`, `export`, `token`, `token-image`, `stat`, `pdf`, `say`."
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


async def _route_message(
    user_id: str,
    message: str,
    attachments: list | None = None,
    channel=None,
) -> "str | dict":
    return await command_router.route_message(
        user_id=user_id,
        message=message,
        attachments=attachments,
        channel=channel,
        handle_subcommand=handle_sentask_subcommand,
        call_core=_call_core,
        subcommand_help=SUBCOMMAND_HELP,
    )


async def handle_sentask_subcommand(
    subcmd: str,
    args: str,
    user_id: str,
    attachments: list | None = None,
    channel=None,
) -> "str | dict":
    return await command_router.handle_subcommand(
        subcmd=subcmd,
        args=args,
        user_id=user_id,
        attachments=attachments,
        channel=channel,
        pf_dispatch=_pf_dispatch,
        call_core=_call_core,
        call_core_note=_call_core_note,
        call_core_inbox_list=_call_core_inbox_list,
        call_core_inbox_classify=_call_core_inbox_classify,
        call_core_inbox_discard=_call_core_inbox_discard,
        call_core_sweep_start=_call_core_sweep_start,
        call_core_sweep_status=_call_core_sweep_status,
        is_admin=_is_admin,
        note_closed_vocab=_NOTE_CLOSED_VOCAB,
        plugin_prompts=_PLUGIN_PROMPTS,
        subcommand_prompts=_SUBCOMMAND_PROMPTS,
        subcommand_help=SUBCOMMAND_HELP,
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

        channel_id = NOTIFY_CHANNEL_ID or (min(ALLOWED_CHANNEL_IDS) if ALLOWED_CHANNEL_IDS else None)  # WR-04 fix: explicit var first, fallback to oldest allowed
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
            embed = discord.Embed(
                title=f"[Chat] {data.get('actor_name', 'DM')}",
                description=(data.get("content") or "")[:4000],
                color=discord.Color.blue(),
            )
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
