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
        call_core_graph=AsyncMock(),
        call_core_stats=AsyncMock(),
        call_core_check=AsyncMock(),
        is_admin=lambda _u: False,
        note_closed_vocab=frozenset({"learning", "reference"}),
        plugin_prompts={},
        subcommand_prompts={},
        subcommand_help="HELP",
    )
    note_call.assert_awaited_once_with("u1", content="finished course", topic="learning")
    assert res == "ok"


async def _call_handle_subcommand(subcmd: str, *, call_core=None, call_core_graph=None, call_core_stats=None, call_core_check=None):
    return await command_router.handle_subcommand(
        subcmd=subcmd,
        args="",
        user_id="u1",
        attachments=None,
        channel=None,
        pf_dispatch=AsyncMock(),
        call_core=call_core or AsyncMock(return_value="core"),
        call_core_note=AsyncMock(),
        call_core_inbox_list=AsyncMock(),
        call_core_inbox_classify=AsyncMock(),
        call_core_inbox_discard=AsyncMock(),
        call_core_sweep_start=AsyncMock(),
        call_core_sweep_status=AsyncMock(),
        call_core_graph=call_core_graph or AsyncMock(return_value="GRAPH"),
        call_core_stats=call_core_stats or AsyncMock(return_value="STATS"),
        call_core_check=call_core_check or AsyncMock(return_value="CHECK"),
        is_admin=lambda _u: False,
        note_closed_vocab=frozenset(),
        plugin_prompts={},
        subcommand_prompts={},
        subcommand_help="HELP",
    )


async def test_graph_subcommand_invokes_gateway_not_call_core():
    call_core = AsyncMock(return_value="core-fallback")
    call_core_graph = AsyncMock(return_value="GRAPH-REPORT")
    res = await _call_handle_subcommand("graph", call_core=call_core, call_core_graph=call_core_graph)
    call_core_graph.assert_awaited_once_with("u1")
    call_core.assert_not_called()
    assert res == "GRAPH-REPORT"


async def test_stats_subcommand_invokes_gateway_not_call_core():
    call_core = AsyncMock(return_value="core-fallback")
    call_core_stats = AsyncMock(return_value="STATS-REPORT")
    res = await _call_handle_subcommand("stats", call_core=call_core, call_core_stats=call_core_stats)
    call_core_stats.assert_awaited_once_with("u1")
    call_core.assert_not_called()
    assert res == "STATS-REPORT"


async def test_check_subcommand_invokes_gateway_not_call_core():
    call_core = AsyncMock(return_value="core-fallback")
    call_core_check = AsyncMock(return_value="CHECK-REPORT")
    res = await _call_handle_subcommand("check", call_core=call_core, call_core_check=call_core_check)
    call_core_check.assert_awaited_once_with("u1")
    call_core.assert_not_called()
    assert res == "CHECK-REPORT"
