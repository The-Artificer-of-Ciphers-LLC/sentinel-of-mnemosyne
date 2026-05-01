"""Pathfinder session noun adapter for Discord :pf commands."""

from __future__ import annotations


async def handle_session(
    *,
    verb: str,
    rest: str,
    user_id: str,
    channel,
    sentinel_client,
    http_client,
    recap_view_cls,
    build_session_embed,
) -> "str | dict":
    force = "--force" in rest
    recap_flag = "--recap" in rest
    retry_recap = "--retry-recap" in rest

    event_text = rest
    for flag_token in ("--force", "--recap", "--retry-recap"):
        event_text = event_text.replace(flag_token, "").strip()

    payload = {
        "verb": verb,
        "args": event_text,
        "flags": {
            "force": force,
            "recap": recap_flag,
            "retry_recap": retry_recap,
        },
        "user_id": user_id,
    }

    needs_placeholder = verb in {"show", "end"}
    placeholder = None
    if needs_placeholder and channel is not None and hasattr(channel, "send"):
        try:
            placeholder = await channel.send("_Generating session narrative..._")
        except Exception:
            placeholder = None

    try:
        result = await sentinel_client.post_to_module(
            "modules/pathfinder/session", payload, http_client
        )
    except Exception as exc:
        if placeholder is not None and hasattr(placeholder, "edit"):
            try:
                await placeholder.edit(content=f"Session operation failed — {exc}", embed=None)
                return {"type": "suppressed", "content": "", "embed": None}
            except Exception:
                pass
        raise

    if verb == "start" and result.get("recap_text") and not recap_flag:
        recap_view = recap_view_cls(recap_text=result["recap_text"])
        embed = build_session_embed(result)
        if channel is not None and hasattr(channel, "send"):
            try:
                msg = await channel.send(embed=embed, view=recap_view)
                recap_view.message = msg
                return {"type": "suppressed", "content": "", "embed": embed}
            except Exception:
                pass
        return {"type": "embed", "content": "", "embed": embed}

    embed = build_session_embed(result)
    if placeholder is not None and hasattr(placeholder, "edit"):
        try:
            await placeholder.edit(content="", embed=embed)
            return {"type": "suppressed", "content": "", "embed": embed}
        except Exception:
            pass
    return {"type": "embed", "content": "", "embed": embed}
