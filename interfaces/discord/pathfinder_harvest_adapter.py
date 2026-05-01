"""Pathfinder harvest noun adapter for Discord :pf commands."""

from __future__ import annotations


async def handle_harvest(*, parts: list[str], user_id: str, sentinel_client, http_client, build_harvest_embed) -> dict | str:
    harvest_args = " ".join(parts[1:]).strip()
    names = [n.strip() for n in harvest_args.split(",") if n.strip()]
    if not names:
        return "Usage: `:pf harvest <Name>[,<Name>...]`"
    result = await sentinel_client.post_to_module(
        "modules/pathfinder/harvest",
        {"names": names, "user_id": user_id},
        http_client,
    )
    return {
        "type": "embed",
        "content": "",
        "embed": build_harvest_embed(result),
    }
