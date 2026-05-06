"""Pathfinder harvest noun adapter for Discord :pf commands.

Deepened into a PathfinderCommand: one handle() method, one request object,
one response type.  HTTP plumbing stays in the bridge.
"""
from __future__ import annotations

from pathfinder_types import (
    PathfinderCommand,
    PathfinderRequest,
    PathfinderResponse,
)


class HarvestCommand(PathfinderCommand):
    """Handle ``:pf harvest <Name>[,<Name>...]``."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        # parts[1:] gives the name tokens:
        #   single: ["Boar"] or multi-word: ["Giant", "Rat"]
        #   batch: ["Boar,Wolf,Orc"] (commas within one token)
        if len(request.parts) == 1:
            raw = ""
        elif len(request.parts) == 2:
            # Single token — may contain commas for batch: "Boar,Wolf,Orc"
            raw = request.parts[1]
        else:
            # Multiple tokens — join with spaces: "Giant Rat"
            raw = " ".join(request.parts[1:])
        names = [n.strip() for n in raw.split(",") if n.strip()]
        if not names:
            return PathfinderResponse(kind="text", content="Usage: `:pf harvest <Name>[,<Name>...]`")
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/harvest",
            {"names": names, "user_id": request.user_id},
            request.http_client,
        )
        return PathfinderResponse(
            kind="embed",
            embed_data=result,
            embed_builder="build_harvest_embed",
            builders=request.builders,
        )
