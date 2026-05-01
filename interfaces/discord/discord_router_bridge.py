"""Bridge wrapper for top-level Discord message routing/subcommands."""

from __future__ import annotations


async def route_message(*, user_id: str, message: str, attachments, channel, command_router, handle_subcommand, call_core, subcommand_help: str):
    return await command_router.route_message(
        user_id=user_id,
        message=message,
        attachments=attachments,
        channel=channel,
        handle_subcommand=handle_subcommand,
        call_core=call_core,
        subcommand_help=subcommand_help,
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
