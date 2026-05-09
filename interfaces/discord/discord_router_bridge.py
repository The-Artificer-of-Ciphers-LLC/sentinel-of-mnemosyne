"""Bridge wrapper for top-level Discord message routing/subcommands.

Pre-router gate (Phase 38, D-01): ``dialog_router.maybe_consume_as_answer``
runs first; on hit (returns ``str``), its response is returned directly,
bypassing ``command_router``. On miss (returns ``None``), the bridge calls
``command_router`` with the original kwargs unchanged so ``:`` commands and
non-thread plain text behave byte-for-byte as before.

The dialog gate is only invoked when both ``sentinel_client`` and
``http_client`` are supplied — keeping the existing test fixtures (which call
``route_message`` without them) byte-for-byte equivalent to pre-Phase-38
behaviour.
"""

from __future__ import annotations

from dialog_router import maybe_consume_as_answer


async def route_message(
    *,
    user_id: str,
    message: str,
    attachments,
    channel,
    command_router,
    handle_subcommand,
    call_core,
    subcommand_help: str,
    sentinel_client=None,
    http_client=None,
    author_display_name: str | None = None,
):
    # Pre-router gate (D-01). When the caller has wired the dialog dependencies,
    # try to consume this message as an onboarding answer first.
    if sentinel_client is not None and http_client is not None:
        consumed = await maybe_consume_as_answer(
            user_id=user_id,
            message=message,
            channel=channel,
            sentinel_client=sentinel_client,
            http_client=http_client,
        )
        if consumed is not None:
            return consumed
    # Miss → fall through to command_router with the original kwargs verbatim.
    return await command_router.route_message(
        user_id=user_id,
        message=message,
        attachments=attachments,
        channel=channel,
        handle_subcommand=handle_subcommand,
        call_core=call_core,
        subcommand_help=subcommand_help,
        author_display_name=author_display_name,
    )


async def handle_subcommand(*, subcmd: str, args: str, user_id: str, attachments, channel, command_router, kwargs: dict):
    return await command_router.handle_subcommand(
        subcmd=subcmd,
        args=args,
        user_id=user_id,
        attachments=attachments,
        channel=channel,
        **kwargs,
    )
