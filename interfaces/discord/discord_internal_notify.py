"""Internal notification handling for Foundry -> Discord bridge."""

from __future__ import annotations

import discord


def build_chat_embed(data: dict) -> "discord.Embed":
    return discord.Embed(
        title=f"[Chat] {data.get('actor_name', 'DM')}",
        description=(data.get("content") or "")[:4000],
        color=discord.Color.blue(),
    )


def resolve_notify_channel_id(notify_channel_id: int | None, allowed_channel_ids: set[int]) -> int | None:
    return notify_channel_id or (min(allowed_channel_ids) if allowed_channel_ids else None)
