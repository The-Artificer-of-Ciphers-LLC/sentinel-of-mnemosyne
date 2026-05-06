"""Pathfinder NPC rich verb adapter for Discord :pf commands.

Deepened into PathfinderCommand classes: one handle() method per sub-verb,
one request object, one response type.  HTTP plumbing stays in the bridge.

Sub-verbs: import, export, token, token-image, stat, pdf, say.
"""
from __future__ import annotations

import base64
import json

import discord

from pathfinder_types import (
    PathfinderCommand,
    PathfinderRequest,
    PathfinderResponse,
)


class NpcImportCommand(PathfinderCommand):
    """Handle ``:pf npc import`` — attach a Foundry actor list JSON file."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        if not request.attachments:
            return PathfinderResponse(
                kind="text",
                content=(
                    "Usage: `:pf npc import` — attach a Foundry actor list JSON file "
                    "as a reply in this thread."
                ),
            )
        attachment = request.attachments[0]
        fetch_resp = await request.http_client.get(str(attachment.url), timeout=10.0)
        fetch_resp.raise_for_status()
        actors_json = fetch_resp.text
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/npc/import",
            {"actors_json": actors_json, "user_id": request.user_id},
            request.http_client,
        )
        imported = result.get("imported_count", 0)
        skipped = result.get("skipped", [])
        lines = [f"Imported **{imported}** NPC(s)."]
        if skipped:
            lines.append(f"Skipped (already exist): {', '.join(skipped)}")
        return PathfinderResponse(kind="text", content="\n".join(lines))


class NpcExportCommand(PathfinderCommand):
    """Handle ``:pf npc export <name>``."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        npc_name = request.rest.strip()
        if not npc_name:
            return PathfinderResponse(kind="text", content="Usage: `:pf npc export <name>`")
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/npc/export-foundry", {"name": npc_name}, request.http_client
        )
        json_bytes = json.dumps(result["actor"], indent=2).encode("utf-8")
        return PathfinderResponse(
            kind="file",
            content=f"Foundry actor JSON for **{npc_name}**:",
            file_bytes=json_bytes,
            filename=result["filename"],
        )


class NpcTokenCommand(PathfinderCommand):
    """Handle ``:pf npc token <name>``."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        npc_name = request.rest.strip()
        if not npc_name:
            return PathfinderResponse(kind="text", content="Usage: `:pf npc token <name>`")
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/npc/token", {"name": npc_name}, request.http_client
        )
        return PathfinderResponse(
            kind="text", content=result.get("prompt", "No prompt generated.")
        )


class NpcTokenImageCommand(PathfinderCommand):
    """Handle ``:pf npc token-image <name>`` — attach a PNG as reply."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        npc_name = request.rest.strip()
        if not npc_name:
            return PathfinderResponse(kind="text", content="Usage: `:pf npc token-image <name>`")
        if not request.attachments:
            return PathfinderResponse(
                kind="text",
                content=(
                    f"Usage: `:pf npc token-image {npc_name}` — attach the Midjourney-"
                    "generated PNG as a reply in this thread."
                ),
            )
        attachment = request.attachments[0]
        content_type = getattr(attachment, "content_type", "") or ""
        if not content_type.startswith("image/"):
            return PathfinderResponse(
                kind="text",
                content=f"Expected an image attachment (got `{content_type or 'unknown'}`). "
                        "Midjourney exports PNG — re-attach the PNG and try again.",
            )
        fetch_resp = await request.http_client.get(str(attachment.url), timeout=30.0)
        fetch_resp.raise_for_status()
        image_bytes = fetch_resp.content
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/npc/token-image",
            {"name": npc_name, "image_b64": image_b64},
            request.http_client,
        )
        return PathfinderResponse(
            kind="text",
            content=(
                f"Token image saved for **{npc_name}** "
                f"({result.get('size_bytes', len(image_bytes))} bytes) → `{result.get('token_path', '?')}`.\n"
                f"Run `:pf npc pdf {npc_name}` to see it embedded in the stat card."
            ),
        )


class NpcStatCommand(PathfinderCommand):
    """Handle ``:pf npc stat <name>``."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        npc_name = request.rest.strip()
        if not npc_name:
            return PathfinderResponse(kind="text", content="Usage: `:pf npc stat <name>`")
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/npc/stat", {"name": npc_name}, request.http_client
        )
        return PathfinderResponse(
            kind="embed",
            embed_data=result,
            embed_builder="build_stat_embed",
            builders=request.builders,
        )


class NpcPdfCommand(PathfinderCommand):
    """Handle ``:pf npc pdf <name>``."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        npc_name = request.rest.strip()
        if not npc_name:
            return PathfinderResponse(kind="text", content="Usage: `:pf npc pdf <name>`")
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/npc/pdf", {"name": npc_name}, request.http_client
        )
        pdf_bytes = base64.b64decode(result["data_b64"])
        return PathfinderResponse(
            kind="file",
            content=f"PDF stat card for **{npc_name}**:",
            file_bytes=pdf_bytes,
            filename=result["filename"],
        )


class NpcSayCommand(PathfinderCommand):
    """Handle ``:pf npc say <Name>[,<Name>...] | <party line>``."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        if "|" not in request.rest:
            return PathfinderResponse(
                kind="text", content="Usage: `:pf npc say <Name>[,<Name>...] | <party line>`"
            )
        names_raw, _, party_line = request.rest.partition("|")
        names = [n.strip() for n in names_raw.split(",") if n.strip()]
        if not names:
            return PathfinderResponse(
                kind="text", content="Usage: `:pf npc say <Name>[,<Name>...] | <party line>`"
            )

        history: list = []
        if request.channel is not None and isinstance(request.channel, discord.Thread):
            try:
                bot_user_id = request.bot_user.id if request.bot_user is not None else 0
                # extract_thread_history is injected via request metadata (set by bridge)
                extract_fn = request.extract_thread_history
                if extract_fn:
                    history = await extract_fn(
                        thread=request.channel,
                        current_npc_names=set(names),
                        bot_user_id=bot_user_id,
                        limit=50,
                    )
            except Exception:
                history = []

        payload = {
            "names": names,
            "party_line": party_line.strip(),
            "user_id": request.user_id,
            "history": history,
        }
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/npc/say", payload, request.http_client
        )

        # render_say_response is injected via request.builders (set by bridge)
        builders = getattr(request, "builders", None) or {}
        render_fn = builders.get("render_say_response")
        if render_fn:
            return PathfinderResponse(
                kind="text", content=render_fn(result)
            )
        return PathfinderResponse(kind="text", content=str(result))
