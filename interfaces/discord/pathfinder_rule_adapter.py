"""Pathfinder rule noun adapter for Discord :pf commands."""

from __future__ import annotations


async def handle_rule(
    *,
    verb: str,
    rest: str,
    parts: list[str],
    user_id: str,
    channel,
    sentinel_client,
    http_client,
    build_ruling_embed,
) -> "str | dict":
    reserved = {"show", "history", "list"}
    if verb in reserved:
        sub_verb = verb
        sub_arg = rest.strip()
    else:
        sub_verb = "query"
        sub_arg = " ".join(parts[1:]).strip()

    if sub_verb == "query" and not sub_arg:
        return (
            "Usage: `:pf rule <question>` | "
            "`:pf rule show <topic>` | "
            "`:pf rule history [N]` | "
            "`:pf rule list`"
        )

    if sub_verb == "list":
        result = await sentinel_client.post_to_module(
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
        result = await sentinel_client.post_to_module(
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
                n = max(1, min(50, int(sub_arg)))
            except ValueError:
                pass
        result = await sentinel_client.post_to_module(
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

    placeholder = None
    if channel is not None and hasattr(channel, "send"):
        try:
            placeholder = await channel.send(
                f"🤔 _Thinking on PF2e rules: {sub_arg[:80]}..._"
            )
        except Exception:
            placeholder = None
    try:
        result = await sentinel_client.post_to_module(
            "modules/pathfinder/rule/query",
            {"query": sub_arg, "user_id": user_id},
            http_client,
        )
        embed = build_ruling_embed(result)
        if placeholder is not None and hasattr(placeholder, "edit"):
            try:
                await placeholder.edit(content="", embed=embed)
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
