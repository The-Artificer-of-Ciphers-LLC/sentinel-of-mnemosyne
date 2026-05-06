"""Pathfinder command interface and types.

Defines the deepened seam: every pathfinder noun/verb combination implements
``PathfinderCommand``, receives one ``PathfinderRequest``, returns one
``PathfinderResponse``.

Bridge layer converts the response into a ``str | dict`` for Discord rendering
(text, embed, or file).  HTTP error handling stays in the bridge — commands
handle validation only.

This module is the seam: tests construct fakes by passing explicit command
instances to ``dispatch``; production uses the ``COMMANDS`` registry.
"""
from __future__ import annotations

import typing
from dataclasses import dataclass, field
from typing import Literal, Protocol


@dataclass(frozen=True)
class PathfinderRequest:
    """Unified request object for all pathfinder commands.

    Bridge extracts Discord-specific values (channel, attachments, bot_user)
    and passes them here.  Commands that do not need Discord features simply
    ignore the fields.

    The bridge also injects ``sentinel_client`` and ``http_client`` — every
    command calls ``sentinel_client.post_to_module(path, payload, http_client)``
    to reach sentinel-core.

    Bridge-supplied metadata (injected by the bridge, not part of the command
    interface):
      - ``is_admin``: callable returning whether user is admin (ingest/cartosia)
      - ``valid_relations``: frozenset of valid NPC relation types (npc relate)
      - ``extract_thread_history``: callable for npc say thread history
      - ``builders``: dict of builder functions (embed rendering)
    """

    noun: str
    verb: str
    rest: str
    user_id: str
    parts: list[str] | None = None  # bridge-supplied, raw parsed tokens
    channel: typing.Any = None
    attachments: list | None = None
    bot_user: typing.Any = None
    sentinel_client: typing.Any = None  # injected by bridge
    http_client: typing.Any = None  # injected by bridge (httpx.AsyncClient)
    is_admin: typing.Callable[[str], bool] | None = None  # bridge-supplied
    valid_relations: frozenset[str] | None = None  # bridge-supplied
    extract_thread_history: typing.Callable | None = None  # bridge-supplied
    builders: dict[str, typing.Any] | None = None  # bridge-supplied


@dataclass(frozen=True)
class PathfinderResponse:
    """Unified response type, discriminated by ``kind``.

    Bridge converts this into a ``str | dict`` for Discord rendering:
      - ``text``  -> plain string (error messages, plain text responses)
      - ``embed`` -> dict + builder name (raw data for embed rendering)
      - ``file``  -> bytes + filename (export, pdf)
    """

    kind: Literal["text", "embed", "file"]
    content: str = ""  # for text responses (error messages, plain text)
    embed_data: dict | None = None  # for embed responses (raw data from sentinel-core)
    embed_builder: str | None = None  # name of the builder function to call
    file_bytes: bytes | None = None  # for file responses (export, pdf)
    filename: str | None = None
    builders: dict[str, typing.Any] | None = None  # bridge-supplied builder functions


class PathfinderCommand(Protocol):
    """Interface for all pathfinder noun/verb commands.

    Every command implements one method: ``handle(request) -> response``.
    Commands handle their own validation (returning usage strings via text
    responses) and build the payload dict for sentinel-core.  The bridge
    handles all HTTP errors.

    Tests construct fakes by passing explicit command instances to dispatch;
    production uses the ``COMMANDS`` registry.
    """

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse: ...


# --- Registry of all commands (noun -> verb -> command instance). ---

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
