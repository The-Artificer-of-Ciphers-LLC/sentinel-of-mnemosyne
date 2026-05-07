"""Pathfinder player verb adapter for Discord ``:pf player <verb>`` commands.

One PathfinderCommand subclass per verb. Each ``handle()`` validates input,
builds the route-specific payload, calls ``request.sentinel_client.post_to_module``,
and returns a ``PathfinderResponse`` with a friendly text summary.

Pitfall 4 guard: ``user_id`` is coerced via ``str(request.user_id)`` to honour
the contract that the module receives the same string the bridge handed us —
slug derivation downstream depends on byte-stable identity.

Sub-verbs: start, note, ask, npc, recall, todo, style, canonize.
"""
from __future__ import annotations

from pathfinder_types import (
    PathfinderCommand,
    PathfinderRequest,
    PathfinderResponse,
)


class PlayerStartCommand(PathfinderCommand):
    """Handle ``:pf player start`` — onboard a player and create their vault profile."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        user_id = str(request.user_id)
        payload = {"user_id": user_id}
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/player/onboard", payload, request.http_client
        )
        path = result.get("path", "?")
        return PathfinderResponse(
            kind="text",
            content=f"Player onboarded. Profile: `{path}`",
        )


class PlayerNoteCommand(PathfinderCommand):
    """Handle ``:pf player note <text>`` — append a free-form note to the player's inbox."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        text = request.rest.strip()
        if not text:
            return PathfinderResponse(
                kind="text", content="Usage: `:pf player note <text>`"
            )
        user_id = str(request.user_id)
        payload = {"user_id": user_id, "text": text}
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/player/note", payload, request.http_client
        )
        path = result.get("path", "?")
        return PathfinderResponse(
            kind="text",
            content=f"Note recorded for player. Inbox: `{path}`",
        )


class PlayerAskCommand(PathfinderCommand):
    """Handle ``:pf player ask <question>`` — log a question for the GM."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        question = request.rest.strip()
        if not question:
            return PathfinderResponse(
                kind="text", content="Usage: `:pf player ask <question>`"
            )
        user_id = str(request.user_id)
        payload = {"user_id": user_id, "question": question}
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/player/ask", payload, request.http_client
        )
        question_id = result.get("question_id", "?")
        return PathfinderResponse(
            kind="text",
            content=f"Question logged (id: `{question_id}`). The GM will see it.",
        )


class PlayerNpcCommand(PathfinderCommand):
    """Handle ``:pf player npc <npc_name> <note>`` — record a personal NPC note."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        rest = request.rest.strip()
        if not rest:
            return PathfinderResponse(
                kind="text", content="Usage: `:pf player npc <npc_name> <note>`"
            )
        # First whitespace-bounded token is the npc_name; remainder is the note.
        parts = rest.split(None, 1)
        if len(parts) < 2 or not parts[1].strip():
            return PathfinderResponse(
                kind="text", content="Usage: `:pf player npc <npc_name> <note>`"
            )
        npc_name, note = parts[0], parts[1].strip()
        user_id = str(request.user_id)
        payload = {"user_id": user_id, "npc_name": npc_name, "note": note}
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/player/npc", payload, request.http_client
        )
        path = result.get("path", "?")
        return PathfinderResponse(
            kind="text",
            content=f"Personal note on **{npc_name}** recorded. Path: `{path}`",
        )


class PlayerRecallCommand(PathfinderCommand):
    """Handle ``:pf player recall [query]`` — fetch personal recall snippets."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        query = request.rest.strip()
        user_id = str(request.user_id)
        payload = {"user_id": user_id, "query": query}
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/player/recall", payload, request.http_client
        )
        results = result.get("results") or []
        if not results:
            return PathfinderResponse(
                kind="text",
                content="No recall snippets found." if query else "No personal memory yet.",
            )
        lines = [f"Recall ({len(results)} hit{'s' if len(results) != 1 else ''}):"]
        for item in results[:10]:
            if isinstance(item, dict):
                snippet = item.get("text") or item.get("snippet") or str(item)
            else:
                snippet = str(item)
            lines.append(f"- {snippet}")
        return PathfinderResponse(kind="text", content="\n".join(lines))


class PlayerTodoCommand(PathfinderCommand):
    """Handle ``:pf player todo <text>`` — add an item to the player's todo list."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        text = request.rest.strip()
        if not text:
            return PathfinderResponse(
                kind="text", content="Usage: `:pf player todo <text>`"
            )
        user_id = str(request.user_id)
        payload = {"user_id": user_id, "text": text}
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/player/todo", payload, request.http_client
        )
        path = result.get("path", "?")
        return PathfinderResponse(
            kind="text",
            content=f"Todo recorded. Path: `{path}`",
        )


class PlayerStyleCommand(PathfinderCommand):
    """Handle ``:pf player style [list|set <preset>]`` — manage GM-style preferences.

    Empty rest defaults to ``list``.
    """

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        rest = request.rest.strip()
        user_id = str(request.user_id)

        if not rest or rest.lower() == "list":
            payload = {"user_id": user_id, "action": "list"}
            result = await request.sentinel_client.post_to_module(
                "modules/pathfinder/player/style", payload, request.http_client
            )
            presets = result.get("presets") or []
            if not presets:
                return PathfinderResponse(kind="text", content="No style presets available.")
            return PathfinderResponse(
                kind="text",
                content="Available style presets:\n" + "\n".join(f"- {p}" for p in presets),
            )

        # set <preset>
        parts = rest.split(None, 1)
        action = parts[0].lower()
        if action == "set":
            if len(parts) < 2 or not parts[1].strip():
                return PathfinderResponse(
                    kind="text",
                    content="Usage: `:pf player style set <preset>` or `:pf player style list`",
                )
            preset = parts[1].strip()
            payload = {"user_id": user_id, "action": "set", "preset": preset}
            result = await request.sentinel_client.post_to_module(
                "modules/pathfinder/player/style", payload, request.http_client
            )
            chosen = result.get("preset", preset)
            return PathfinderResponse(
                kind="text",
                content=f"Style preset set to **{chosen}**.",
            )

        return PathfinderResponse(
            kind="text",
            content="Usage: `:pf player style list` or `:pf player style set <preset>`",
        )


class PlayerCanonizeCommand(PathfinderCommand):
    """Handle ``:pf player canonize <outcome> <question_id> <rule_text>`` — promote a ruling."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        rest = request.rest.strip()
        if not rest:
            return PathfinderResponse(
                kind="text",
                content="Usage: `:pf player canonize <outcome> <question_id> <rule_text>`",
            )
        # Three-part split: outcome, question_id, rule_text (rule_text may have spaces).
        parts = rest.split(None, 2)
        if len(parts) < 3 or not parts[2].strip():
            return PathfinderResponse(
                kind="text",
                content="Usage: `:pf player canonize <outcome> <question_id> <rule_text>`",
            )
        outcome, question_id, rule_text = parts[0], parts[1], parts[2].strip()
        user_id = str(request.user_id)
        payload = {
            "user_id": user_id,
            "outcome": outcome,
            "question_id": question_id,
            "rule_text": rule_text,
        }
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/player/canonize", payload, request.http_client
        )
        path = result.get("path", "?")
        return PathfinderResponse(
            kind="text",
            content=f"Ruling canonized ({outcome}). Path: `{path}`",
        )
