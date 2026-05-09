"""Pre-router gate for the multi-step onboarding dialog.

Inserted into ``discord_router_bridge.route_message`` BEFORE ``command_router``
so that plain-text replies inside a draft-bearing thread are consumed as
onboarding answers, not routed to the AI / command pipeline. On miss, returns
``None`` and the bridge falls through to ``command_router`` unchanged.

Hit conditions (Phase 38, D-02 in 38-CONTEXT.md — ALL must hold):
  1. ``message`` is non-empty after strip and does not start with ``":"`` (raw
     prefix check ignoring leading whitespace, mirroring command_router.py).
  2. ``channel`` is an instance of ``discord.Thread``.
  3. A draft exists at ``mnemosyne/pf2e/players/_drafts/{thread.id}-{user_id}.md``
     — verified via a lightweight HTTP GET against the Obsidian REST API. We
     check existence only (status code), NOT frontmatter shape — the heavy
     parsing belongs to ``pathfinder_player_dialog.consume_as_answer`` which
     re-loads the draft authoritatively in the hit path.

D-01 (pre-router precedence) and D-02 (hit conditions) from 38-CONTEXT.md.
D-03 (command_router untouched) and D-04 (on_message untouched) are honored
by keeping this module a pure pre-gate — the bridge layer alone wires it in.
"""
from __future__ import annotations

import logging
import os

import discord
import httpx

logger = logging.getLogger(__name__)


def _draft_url(thread_id: int, user_id: str) -> str:
    """Build the canonical Obsidian REST URL for a draft (mirrors
    pathfinder_player_dialog.draft_path / _vault_url, kept inline here so the
    pre-check is independent of dialog-module internals)."""
    base = os.environ.get("OBSIDIAN_API_URL", "http://host.docker.internal:27123").rstrip("/")
    return f"{base}/vault/mnemosyne/pf2e/players/_drafts/{thread_id}-{user_id}.md"


def _draft_headers() -> dict:
    """Authorization header for the Obsidian REST API.

    Lazy-imports ``bot._read_secret`` to avoid a hard import cycle at module
    load time (bot.py imports this module via discord_router_bridge)."""
    try:
        from bot import _read_secret

        key = _read_secret("obsidian_api_key", os.environ.get("OBSIDIAN_API_KEY", ""))
    except Exception:
        key = os.environ.get("OBSIDIAN_API_KEY", "")
    return {"Authorization": f"Bearer {key}"}


async def maybe_consume_as_answer(
    *,
    user_id: str,
    message: str,
    channel,
    sentinel_client,
    http_client,
) -> str | None:
    """Return a response string if this message is an onboarding answer, else None.

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
    # Hit condition 3: draft must exist for ``(thread.id, user_id)``. Lightweight
    # existence check — a 200 means a draft is in flight; 404 (or any non-200)
    # means no active dialog and we fall through to command_router.
    try:
        resp = await http_client.get(
            _draft_url(channel.id, str(user_id)),
            headers=_draft_headers(),
            timeout=10.0,
        )
    except httpx.RequestError:
        # Defensive: Obsidian network blip during pre-check must not crash the
        # message handler. Treat as miss so command_router still runs.
        logger.warning(
            "dialog_router pre-check Obsidian error — falling through to command_router",
            exc_info=True,
        )
        return None
    except Exception:
        # Last-resort safety net: any unexpected error in the pre-check must not
        # block normal command routing. Logged for diagnostics.
        logger.exception("dialog_router pre-check unexpected error — falling through")
        return None

    if getattr(resp, "status_code", 0) != 200:
        return None

    # Lazy import — keeps dialog_router decoupled from dialog-state internals at
    # import time (avoids a cycle through bot.py during conftest collection).
    import pathfinder_player_dialog as ppd

    # All conditions met — consume the message as the next dialog answer.
    return await ppd.consume_as_answer(
        thread=channel,
        user_id=str(user_id),
        message_text=message,
        sentinel_client=sentinel_client,
        http_client=http_client,
    )
