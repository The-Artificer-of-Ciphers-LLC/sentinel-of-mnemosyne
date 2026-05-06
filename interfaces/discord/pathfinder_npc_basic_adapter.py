"""Pathfinder NPC basic verb adapter for Discord :pf commands.

Deepened into PathfinderCommand classes: one handle() method per sub-verb,
one request object, one response type.  HTTP plumbing stays in the bridge.

Sub-verbs: create, update, show, relate.
Returns PathfinderResponse(kind="unhandled") when verb doesn't match —
signals dispatch to try npc_rich next.
"""
from __future__ import annotations

from pathfinder_types import (
    PathfinderCommand,
    PathfinderRequest,
    PathfinderResponse,
)


class NpcCreateCommand(PathfinderCommand):
    """Handle ``:pf npc create <name> | <description>``."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        name, _, description = request.rest.partition("|")
        if not name.strip():
            return PathfinderResponse(
                kind="text", content="Usage: `:pf npc create <name> | <description>`"
            )
        payload = {
            "name": name.strip(),
            "description": description.strip(),
            "user_id": request.user_id,
        }
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/npc/create", payload, request.http_client
        )
        return PathfinderResponse(
            kind="text",
            content=(
                f"NPC **{result.get('name', name.strip())}** created.\n"
                f"Path: `{result.get('path', '?')}`\n"
                f"Ancestry: {result.get('ancestry', '?')} | Class: {result.get('class', '?')} | Level: {result.get('level', '?')}"
            ),
        )


class NpcUpdateCommand(PathfinderCommand):
    """Handle ``:pf npc update <name> | <correction>``."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        name, _, correction = request.rest.partition("|")
        if not name.strip() or not correction.strip():
            return PathfinderResponse(
                kind="text", content="Usage: `:pf npc update <name> | <correction>`"
            )
        payload = {
            "name": name.strip(),
            "correction": correction.strip(),
            "user_id": request.user_id,
        }
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/npc/update", payload, request.http_client
        )
        return PathfinderResponse(
            kind="text",
            content=f"NPC **{name.strip()}** updated. Fields changed: {', '.join(result.get('changed_fields', []))}",
        )


class NpcShowCommand(PathfinderCommand):
    """Handle ``:pf npc show <name>``."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        npc_name = request.rest.strip()
        if not npc_name:
            return PathfinderResponse(kind="text", content="Usage: `:pf npc show <name>`")
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/npc/show", {"name": npc_name, "user_id": request.user_id}, request.http_client
        )
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
        return PathfinderResponse(kind="text", content="\n".join(lines))


class NpcRelateCommand(PathfinderCommand):
    """Handle ``:pf npc relate <npc-name> | <relation> | <target-npc-name>``."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        relate_parts = [p.strip() for p in request.rest.split("|")]
        if len(relate_parts) < 3 or not all(relate_parts[:3]):
            return PathfinderResponse(
                kind="text",
                content=(
                    "Usage: `:pf npc relate <npc-name> | <relation> | <target-npc-name>`"
                ),
            )
        npc_name, relation, target = relate_parts[0], relate_parts[1], relate_parts[2]
        # valid_relations passed via request metadata (set by bridge)
        valid = request.valid_relations or frozenset()
        if relation not in valid:
            return PathfinderResponse(
                kind="text",
                content=f"`{relation}` is not a valid relation type.\nValid options: {', '.join(sorted(valid))}",
            )
        await request.sentinel_client.post_to_module(
            "modules/pathfinder/npc/relate",
            {"name": npc_name, "relation": relation, "target": target},
            request.http_client,
        )
        return PathfinderResponse(
            kind="text",
            content=f"Relationship added: **{npc_name}** {relation} **{target}**.",
        )
