from unittest.mock import AsyncMock

import discord_router_bridge


async def test_route_message_delegates_to_command_router():
    router = type("R", (), {"route_message": AsyncMock(return_value="ok")})()
    out = await discord_router_bridge.route_message(
        user_id="u1",
        message="hello",
        attachments=None,
        channel=None,
        command_router=router,
        handle_subcommand=AsyncMock(),
        call_core=AsyncMock(),
        subcommand_help="H",
    )
    assert out == "ok"


async def test_handle_subcommand_delegates_with_kwargs():
    router = type("R", (), {"handle_subcommand": AsyncMock(return_value="ok")})()
    out = await discord_router_bridge.handle_subcommand(
        subcmd="help",
        args="",
        user_id="u1",
        attachments=None,
        channel=None,
        command_router=router,
        kwargs={"x": 1},
    )
    assert out == "ok"
