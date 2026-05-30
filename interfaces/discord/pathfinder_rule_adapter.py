"""Pathfinder rule noun adapter for Discord :pf commands.

Deepened into PathfinderCommand classes: one handle() method per sub-verb,
one request object, one response type.  HTTP plumbing stays in the bridge.

Sub-verbs: query (default), list, show, history.
The wildcard handler (registered as rule/*) forwards free-text queries to
RuleQueryCommand when the question begins at the verb position in the parsed args.
"""
from __future__ import annotations

from pathfinder_types import (
    PathfinderCommand,
    PathfinderRequest,
    PathfinderResponse,
)

# Known explicit sub-verbs for the rule noun.
_RULE_NAMED_VERBS = frozenset({"query", "show", "list", "history"})


class RuleQueryCommand(PathfinderCommand):
    """Handle ``:pf rule <question>`` (sub-verb = query OR wildcard free-text).

    When invoked via the named ``query`` verb, the question text is in
    ``request.rest``.  When invoked via the wildcard handler (free-text query
    where the question starts at the verb position, e.g. "rule How does flanking
    work?"), the full question is reconstructed from ``request.parts[1:]``.

    Implements placeholder UX (D-11): sends "⏳ Thinking…" on the channel
    before calling the module, then edits the placeholder with the embed result.
    On error, edits the placeholder with a "failed" message.
    Returns ``kind="suppressed"`` when the channel placeholder was used, so the
    bridge does not send a second message; returns ``kind="embed"`` otherwise.
    """

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        # Reconstruct the query.  When invoked via wildcard (verb is not a named
        # sub-command), parts[1:] contains the full question tokens with original
        # casing (e.g. ["How", "does flanking work?"]).  When invoked via the
        # explicit "query" verb, use rest directly.
        if request.verb not in _RULE_NAMED_VERBS and request.parts and len(request.parts) >= 2:
            sub_arg = " ".join(request.parts[1:])
        else:
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

        # Placeholder UX (D-11): send "thinking" placeholder before the slow call.
        placeholder = None
        if request.channel is not None:
            placeholder = await request.channel.send("⏳ Thinking…")

        try:
            result = await request.sentinel_client.post_to_module(
                "modules/pathfinder/rule/query",
                {"query": sub_arg, "user_id": request.user_id},
                request.http_client,
            )
        except Exception:
            if placeholder is not None:
                await placeholder.edit(
                    content="⚠ Rule query failed. Try again.",
                    embed=None,
                )
                return PathfinderResponse(kind="suppressed")
            raise

        if placeholder is not None:
            builders = request.builders or {}
            builder = builders.get("build_ruling_embed")
            embed = builder(result) if builder else None
            await placeholder.edit(content="", embed=embed)
            return PathfinderResponse(kind="suppressed")

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
