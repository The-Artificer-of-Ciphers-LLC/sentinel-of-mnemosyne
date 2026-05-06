"""Pathfinder session noun adapter for Discord :pf commands.

Deepened into PathfinderCommand classes: one handle() method per sub-verb,
one request object, one response type.  HTTP plumbing stays in the bridge.

Sub-verbs: start (with --force/--recap/--retry-recap flags), show, end.
"""
from __future__ import annotations

from pathfinder_types import (
    PathfinderCommand,
    PathfinderRequest,
    PathfinderResponse,
)


class SessionStartCommand(PathfinderCommand):
    """Handle ``:pf session start [--force|--recap|--retry-recap]``."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        rest = request.rest
        force = "--force" in rest
        recap_flag = "--recap" in rest
        retry_recap = "--retry-recap" in rest

        event_text = rest
        for flag_token in ("--force", "--recap", "--retry-recap"):
            event_text = event_text.replace(flag_token, "").strip()

        payload = {
            "verb": "start",
            "args": event_text,
            "flags": {
                "force": force,
                "recap": recap_flag,
                "retry_recap": retry_recap,
            },
            "user_id": request.user_id,
        }

        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/session", payload, request.http_client
        )

        # Start with recap text → send view + embed (suppressed)
        if result.get("recap_text") and not recap_flag:
            return PathfinderResponse(
                kind="embed",
                embed_data=result,
                embed_builder="build_session_embed",
                builders=request.builders,
            )

        return PathfinderResponse(
            kind="embed",
            embed_data=result,
            embed_builder="build_session_embed",
            builders=request.builders,
        )


class SessionShowCommand(PathfinderCommand):
    """Handle ``:pf session show``."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/session", {"verb": "show"}, request.http_client
        )
        return PathfinderResponse(
            kind="embed",
            embed_data=result,
            embed_builder="build_session_embed",
            builders=request.builders,
        )


class SessionEndCommand(PathfinderCommand):
    """Handle ``:pf session end [--force]``."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        rest = request.rest
        force = "--force" in rest
        event_text = rest.replace("--force", "").strip()

        payload = {
            "verb": "end",
            "args": event_text,
            "flags": {"force": force},
            "user_id": request.user_id,
        }

        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/session", payload, request.http_client
        )
        return PathfinderResponse(
            kind="embed",
            embed_data=result,
            embed_builder="build_session_embed",
            builders=request.builders,
        )
