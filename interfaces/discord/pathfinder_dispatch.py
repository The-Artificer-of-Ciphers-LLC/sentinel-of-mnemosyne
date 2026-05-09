"""Pathfinder noun/verb dispatcher for Discord :pf commands.

Deepened: dispatch looks up commands from the COMMANDS registry (noun → verb →
PathfinderCommand) instead of routing through an if-chain.  Each command
receives one PathfinderRequest and returns one PathfinderResponse.

The bridge (pathfinder_bridge.py) converts the response into a str | dict
for Discord rendering and handles all HTTP errors.

Registry is populated by importing the adapter modules — each adapter class
registers itself via COMMANDS[noun][verb] = ClassName().

See pathfinder_types.py for the full registry contract.
"""
from __future__ import annotations

import logging

from pathfinder_types import (
    PathfinderCommand,
    PathfinderRequest,
    PathfinderResponse,
)

logger = logging.getLogger(__name__)

# Registry: noun → verb → PathfinderCommand.
COMMANDS: dict[str, dict[str, PathfinderCommand]] = {}


def register(noun: str, verb: str, command: PathfinderCommand) -> None:
    """Register a command in the dispatch registry."""
    if noun not in COMMANDS:
        COMMANDS[noun] = {}
    COMMANDS[noun][verb] = command


def register_star(noun: str, command: PathfinderCommand) -> None:
    """Register a wildcard (``*``) handler for a noun."""
    if noun not in COMMANDS:
        COMMANDS[noun] = {}
    COMMANDS[noun]["*"] = command


async def dispatch(
    *,
    noun: str,
    verb: str,
    rest: str,
    parts: list[str],
    user_id: str,
    channel,
    attachments,
    bot_user,
    sentinel_client,
    http_client,
    is_admin,
    valid_relations: frozenset[str],
    builders: dict,  # builder function name → callable (injected by bridge)
    extract_thread_history=None,  # injected by bridge for npc say
    author_display_name: str | None = None,  # Phase 38: message.author.display_name
) -> PathfinderResponse:
    """Look up the command from the registry and handle it.

    Returns a PathfinderResponse (text, embed, or file).  The bridge converts
    this into a str | dict for Discord rendering.

    If the noun/verb combination is not registered, returns a text error
    response: ``"Unknown pf category \`{noun}\`."``.

    Args:
        noun: The pathfinder noun (harvest, rule, session, npc, ingest, cartosia).
        verb: The sub-verb (create, show, query, etc.).  For nouns without
              sub-verbs (harvest), verb is ignored and the wildcard handler is used.
        rest: Raw remaining text after noun/verb parsing.
        user_id: Discord user ID.
        channel: Discord channel (may be None).  Commands that need it check
                 ``isinstance(channel, discord.Thread)`` internally.
        attachments: Discord message attachments (may be None).
        bot_user: Discord bot user object (may be None, used by npc say for thread history).
        sentinel_client: The sentinel-core HTTP client.  Every command calls
                         ``sentinel_client.post_to_module(path, payload, http_client)``.
        http_client: An active httpx.AsyncClient (created by the bridge).
        is_admin: Callable returning whether user_id is an admin.  Passed to
                  PathfinderRequest.is_admin for ingest/cartosia commands.
        valid_relations: Frozenset of valid NPC relation types.  Passed to
                        PathfinderRequest.valid_relations for npc relate command.
        builders: Dict mapping builder function names to callables (injected by bridge).
                 Used by commands that return embed responses: the bridge calls
                 ``builders[response.embed_builder](response.embed_data)`` to produce
                 the final Discord embed.  Passed to PathfinderRequest.builders.
        extract_thread_history: Function for npc say to extract thread history.
                               Passed to PathfinderRequest.extract_thread_history.

    Returns:
        A PathfinderResponse (kind="text" | "embed" | "file").  The bridge
        converts this into a str | dict for Discord rendering.
    """
    # Look up the command from the registry.
    noun_commands = COMMANDS.get(noun)
    if noun_commands is None:
        return PathfinderResponse(kind="text", content=f"Unknown pf category `{noun}`.")

    # Try exact verb match first, then wildcard.
    command: PathfinderCommand | None = noun_commands.get(verb) or noun_commands.get("*")
    if command is None:
        return PathfinderResponse(
            kind="text", content=f"Unknown `{noun}` sub-command `{verb}`."
        )

    # Build the unified request object (bridge-supplied metadata included).
    request = PathfinderRequest(
        noun=noun,
        verb=verb,
        rest=rest,
        parts=parts,
        user_id=user_id,
        channel=channel,
        attachments=attachments,
        bot_user=bot_user,
        sentinel_client=sentinel_client,
        http_client=http_client,
        is_admin=is_admin,
        valid_relations=valid_relations,
        extract_thread_history=extract_thread_history,
        builders=builders,
        author_display_name=author_display_name,
    )

    return await command.handle(request)


# Import all adapter modules to populate the registry.
# Each adapter module registers its commands via register() / register_star().
from pathfinder_harvest_adapter import HarvestCommand  # noqa: E402, F401
from pathfinder_ingest_adapter import CartosiaCommand, IngestCommand  # noqa: E402, F401
from pathfinder_foundry_adapter import FoundryImportMessagesCommand  # noqa: E402, F401
from pathfinder_npc_basic_adapter import (  # noqa: E402, F401
    NpcCreateCommand,
    NpcRelateCommand,
    NpcShowCommand,
    NpcUpdateCommand,
)
from pathfinder_npc_rich_adapter import (  # noqa: E402, F401
    NpcExportCommand,
    NpcImportCommand,
    NpcPdfCommand,
    NpcSayCommand,
    NpcStatCommand,
    NpcTokenCommand,
    NpcTokenImageCommand,
)
from pathfinder_rule_adapter import (  # noqa: E402, F401
    RuleHistoryCommand,
    RuleListCommand,
    RuleQueryCommand,
    RuleShowCommand,
)
from pathfinder_session_adapter import (  # noqa: E402, F401
    SessionEndCommand,
    SessionStartCommand,
    SessionShowCommand,
)
from pathfinder_player_adapter import (  # noqa: E402, F401
    PlayerAskCommand,
    PlayerCanonizeCommand,
    PlayerNoteCommand,
    PlayerNpcCommand,
    PlayerRecallCommand,
    PlayerStartCommand,
    PlayerStyleCommand,
    PlayerTodoCommand,
)

# Populate the registry from imported command classes.
# Harvest: wildcard handler (no sub-verbs).
register_star("harvest", HarvestCommand())

# Rule: each sub-verb is a separate command.
COMMANDS.setdefault("rule", {})["query"] = RuleQueryCommand()
COMMANDS["rule"]["list"] = RuleListCommand()
COMMANDS["rule"]["show"] = RuleShowCommand()
COMMANDS["rule"]["history"] = RuleHistoryCommand()

# Session: each sub-verb is a separate command.
COMMANDS.setdefault("session", {})["start"] = SessionStartCommand()
COMMANDS["session"]["show"] = SessionShowCommand()
COMMANDS["session"]["end"] = SessionEndCommand()

# NPC basic: sub-verbs that npc_rich doesn't handle.
COMMANDS.setdefault("npc", {})["create"] = NpcCreateCommand()
COMMANDS["npc"]["update"] = NpcUpdateCommand()
COMMANDS["npc"]["show"] = NpcShowCommand()
COMMANDS["npc"]["relate"] = NpcRelateCommand()

# NPC rich: sub-verbs that npc_basic doesn't handle.
COMMANDS["npc"]["import"] = NpcImportCommand()
COMMANDS["npc"]["export"] = NpcExportCommand()
COMMANDS["npc"]["token"] = NpcTokenCommand()
COMMANDS["npc"]["token-image"] = NpcTokenImageCommand()
COMMANDS["npc"]["stat"] = NpcStatCommand()
COMMANDS["npc"]["pdf"] = NpcPdfCommand()
COMMANDS["npc"]["say"] = NpcSayCommand()

# Ingest: two nouns, each with its own command.
COMMANDS.setdefault("ingest", {})["*"] = IngestCommand()
COMMANDS["cartosia"] = {"*": CartosiaCommand()}

# Foundry import commands.
COMMANDS.setdefault("foundry", {})["import-messages"] = FoundryImportMessagesCommand()

# Player: per-player memory verbs (Phase 37 — pf2e-per-player-memory).
COMMANDS.setdefault("player", {})["start"] = PlayerStartCommand()
COMMANDS["player"]["note"] = PlayerNoteCommand()
COMMANDS["player"]["ask"] = PlayerAskCommand()
COMMANDS["player"]["npc"] = PlayerNpcCommand()
COMMANDS["player"]["recall"] = PlayerRecallCommand()
COMMANDS["player"]["todo"] = PlayerTodoCommand()
COMMANDS["player"]["style"] = PlayerStyleCommand()
COMMANDS["player"]["canonize"] = PlayerCanonizeCommand()
