"""``:onboard`` subcommand dispatch — self-profile onboarding dialog entry point.

Mirrors ``pathfinder_player_adapter.PlayerStartCommand`` /
``PlayerCancelCommand`` (status check → start/resume dialog; cancel from the
dialog thread) but flattened into a single dispatch function since ``:onboard``
has no ``noun verb`` structure of its own.
"""

from __future__ import annotations

import logging

import core_gateway
import self_profile_dialog as spd
from self_profile_draft_store import load_draft

logger = logging.getLogger(__name__)

_ALREADY_COMPLETE = "Your profile is already complete — nothing to onboard."
_UNREACHABLE = (
    "Couldn't reach the Sentinel to check your profile status — try again shortly."
)


def _is_real_thread(channel) -> bool:
    """Robust thread-check that works with the test stub (``discord.Thread = object``).

    Mirrors pathfinder_player_adapter._is_real_thread verbatim: the conftest
    stub aliases discord.Thread to object, which would otherwise make every
    channel test as a thread.
    """
    import discord

    if discord.Thread is object:
        return False
    return isinstance(channel, discord.Thread)


async def dispatch_onboard(
    *,
    args: str,
    user_id: str,
    channel,
    author_display_name: str | None,
    sentinel_client,
    http_client,
    core_url: str,
    api_key: str,
) -> "str | dict":
    """Handle ``:onboard`` and ``:onboard cancel``.

    - ``:onboard cancel`` from inside the dialog thread aborts it.
    - Inside an existing dialog thread with no verb: resume (re-post current Q).
    - Otherwise: check GET /self/profile/status; if already complete, say so;
      if incomplete, create the onboarding thread and ask about the first
      unfilled file only.
    """
    verb = (args or "").strip().lower()

    if verb == "cancel":
        if not _is_real_thread(channel):
            return "Run `:onboard cancel` from inside the onboarding thread to cancel it."
        outcome = await spd.cancel_dialog_outcome(
            thread=channel, user_id=user_id, http_client=http_client
        )
        return outcome.to_router_response()

    if _is_real_thread(channel):
        existing = await load_draft(channel.id, user_id, http_client=http_client)
        if existing is not None:
            text = await spd.resume_dialog(
                thread=channel, user_id=user_id, http_client=http_client
            )
            return text

    status = await core_gateway.call_core_profile_status(core_url=core_url, api_key=api_key)
    if status is None:
        return _UNREACHABLE
    if status.get("complete"):
        return _ALREADY_COMPLETE
    unfilled = status.get("unfilled") or []
    if not unfilled:
        return _ALREADY_COMPLETE

    display_name = author_display_name or f"user {user_id}"
    thread = await spd.start_dialog(
        invoking_channel=channel,
        user_id=user_id,
        unfilled=unfilled,
        display_name=display_name,
        http_client=http_client,
    )
    return f"Onboarding started in <#{thread.id}>. Reply there to answer the questions."
