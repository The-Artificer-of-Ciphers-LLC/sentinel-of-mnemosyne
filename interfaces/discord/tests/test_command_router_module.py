"""Direct tests for command_router module seam."""

from unittest.mock import AsyncMock

import command_router


async def test_route_message_help_keyword_short_circuits_to_help():
    res = await command_router.route_message(
        user_id="u1",
        message="help",
        attachments=None,
        channel=None,
        handle_subcommand=AsyncMock(),
        call_core=AsyncMock(return_value="core"),
        subcommand_help="HELP-TEXT",
    )
    assert res == "HELP-TEXT"


async def test_route_message_colon_delegates_to_subcommand_handler():
    sub = AsyncMock(return_value="SUB")
    res = await command_router.route_message(
        user_id="u1",
        message=":goals",
        attachments=None,
        channel=None,
        handle_subcommand=sub,
        call_core=AsyncMock(return_value="core"),
        subcommand_help="HELP",
    )
    sub.assert_awaited_once()
    assert res == "SUB"


async def test_handle_subcommand_note_parses_explicit_topic():
    note_call = AsyncMock(return_value="ok")
    res = await command_router.handle_subcommand(
        subcmd="note",
        args="learning finished course",
        user_id="u1",
        attachments=None,
        channel=None,
        pf_dispatch=AsyncMock(),
        call_core=AsyncMock(),
        call_core_note=note_call,
        call_core_inbox_list=AsyncMock(),
        call_core_inbox_classify=AsyncMock(),
        call_core_inbox_discard=AsyncMock(),
        call_core_sweep_start=AsyncMock(),
        call_core_sweep_status=AsyncMock(),
        is_admin=lambda _u: False,
        note_closed_vocab=frozenset({"learning", "reference"}),
        plugin_prompts={},
        subcommand_prompts={},
        subcommand_help="HELP",
    )
    note_call.assert_awaited_once_with("u1", content="finished course", topic="learning")
    assert res == "ok"
