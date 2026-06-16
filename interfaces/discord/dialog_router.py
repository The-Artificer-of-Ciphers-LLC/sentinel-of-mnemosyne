"""Pre-router gate for the multi-step onboarding dialog.

Inserted into ``discord_router_bridge.route_message`` BEFORE ``command_router``
so that plain-text replies inside a draft-bearing thread are consumed as
onboarding answers, not routed to the AI / command pipeline. On hit, returns a
renderable dialog response string or suppression dict. On miss, returns
``None`` and the bridge falls through to ``command_router`` unchanged.

Hit conditions (Phase 38, D-02 in 38-CONTEXT.md — ALL must hold):
  1. ``message`` is non-empty after strip and does not start with ``":"`` (raw
     prefix check ignoring leading whitespace, mirroring command_router.py).
  2. ``channel`` is an instance of ``discord.Thread``.
  3. ``pathfinder_player_draft_store`` reports a draft for ``(thread.id,
     user_id)``. The router checks existence only; parsing belongs to
     ``pathfinder_player_dialog.consume_as_answer`` which re-loads the draft
     authoritatively in the hit path.

D-01 (pre-router precedence) and D-02 (hit conditions) from 38-CONTEXT.md.
D-03 (command_router untouched) and D-04 (on_message untouched) are honored
by keeping this module a pure pre-gate — the bridge layer alone wires it in.
"""
from __future__ import annotations

import discord

from pathfinder_player_draft_store import draft_exists


async def maybe_consume_as_answer(
    *,
    user_id: str,
    message: str,
    channel,
    sentinel_client,
    http_client,
) -> str | dict | None:
    """Return a renderable response if this message is an onboarding answer.

    Cheapest checks first to keep the blast radius zero in regular text channels:
    empty/colon-prefix → channel-type → draft existence (HTTP).
    """
    # Hit condition 1a: empty / whitespace-only is never a dialog answer.
    if not message or not message.strip():
        return None
    # Hit condition 1b: ``:`` prefix means the user is invoking a command.
    # Ignore leading whitespace to match command_router.py raw-prefix semantics.
    if message.lstrip().startswith(":"):
        return None
    # Hit condition 2: only Threads carry onboarding state. Early-out before any
    # network call so regular text channels stay free of HTTP traffic.
    if not isinstance(channel, discord.Thread):
        return None
    # Hit condition 3: draft must exist for ``(thread.id, user_id)``.
    if not await draft_exists(channel.id, str(user_id), http_client=http_client):
        return None

    # Lazy import — keeps dialog_router decoupled from dialog-state internals at
    # import time (avoids a cycle through bot.py during conftest collection).
    import pathfinder_player_dialog as ppd

    # All conditions met — consume the message as the next dialog answer.
    outcome = await ppd.consume_as_answer_outcome(
        thread=channel,
        user_id=str(user_id),
        message_text=message,
        sentinel_client=sentinel_client,
        http_client=http_client,
    )
    return outcome.to_router_response()
