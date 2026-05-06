"""Pathfinder rule noun adapter for Discord :pf commands.

Deepened into PathfinderCommand classes: one handle() method per sub-verb,
one request object, one response type.  HTTP plumbing stays in the bridge.

Sub-verbs: query (default), list, show, history.
"""
from __future__ import annotations

from pathfinder_types import (
    PathfinderCommand,
    PathfinderRequest,
    PathfinderResponse,
)


class RuleQueryCommand(PathfinderCommand):
    """Handle ``:pf rule <question>`` (sub-verb = query)."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        sub_arg = request.rest.strip()
        if not sub_arg:
            return PathfinderResponse(
                kind="text",
                content=(
                    "Usage: `:pf rule <question>` | "
                    "`:pf rule show <topic>` | "
                    "`:pf rule history [N]` | "
                    "`:pf rule list`"
                ),
            )
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/rule/query",
            {"query": sub_arg, "user_id": request.user_id},
            request.http_client,
        )
        return PathfinderResponse(
            kind="embed",
            embed_data=result,
            embed_builder="build_ruling_embed",
            builders=request.builders,
        )


class RuleListCommand(PathfinderCommand):
    """Handle ``:pf rule list``."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/rule/list", {}, request.http_client,
        )
        topics = result.get("topics", []) or [] if isinstance(result, dict) else []
        if not topics:
            return PathfinderResponse(kind="text", content="_No rulings cached yet._")
        lines = [
            f"• `{t.get('slug', '?')}` ({t.get('count', 0)} rulings, last active {str(t.get('last_activity', 'never'))[:19]})"
            for t in topics
        ]
        return PathfinderResponse(
            kind="text",
            content="**Rule topics with cached rulings:**\n" + "\n".join(lines),
        )


class RuleShowCommand(PathfinderCommand):
    """Handle ``:pf rule show <topic>``."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        sub_arg = request.rest.strip()
        if not sub_arg:
            return PathfinderResponse(kind="text", content="Usage: `:pf rule show <topic>`")
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/rule/show",
            {"topic": sub_arg},
            request.http_client,
        )
        rulings = result.get("rulings", []) or [] if isinstance(result, dict) else []
        if not rulings:
            return PathfinderResponse(kind="text", content=f"_No rulings under `{sub_arg}`._")
        lines = [
            f"• `{r.get('hash', '?')}` — {(r.get('question', '') or '')[:80]} [{r.get('marker', '?')}]"
            for r in rulings
        ]
        return PathfinderResponse(
            kind="text",
            content=f"**Rulings under `{sub_arg}`** ({len(rulings)}):\n" + "\n".join(lines),
        )


class RuleHistoryCommand(PathfinderCommand):
    """Handle ``:pf rule history [N]``."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        sub_arg = request.rest.strip()
        n = 10
        if sub_arg:
            try:
                n = max(1, min(50, int(sub_arg)))
            except ValueError:
                pass
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/rule/history",
            {"n": n},
        )
        rulings = result.get("rulings", []) or [] if isinstance(result, dict) else []
        if not rulings:
            return PathfinderResponse(kind="text", content="_No rulings yet._")
        lines = [
            f"• {str(r.get('last_reused_at', ''))[:19]} — `{r.get('topic', '?')}/{(r.get('question', '') or '')[:60]}` → {r.get('marker', '?')}"
            for r in rulings
        ]
        return PathfinderResponse(
            kind="text",
            content=f"**Recent rulings (N={n}):**\n" + "\n".join(lines),
        )
