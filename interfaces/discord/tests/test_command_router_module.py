"""Direct tests for command_router module seam."""

from unittest.mock import AsyncMock

import pytest

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
        call_core_pipeline_start=AsyncMock(),
        call_core_pipeline_status=AsyncMock(),
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
        call_core_pipeline_start=AsyncMock(),
        call_core_pipeline_status=AsyncMock(),
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


# --- pipeline verbs: :ralph / :pipeline / :reweave / :rethink / :refactor (Phase 46-07) ---


async def _call_pipeline_subcommand(
    subcmd: str,
    args: str = "",
    *,
    is_admin=None,
    call_core_pipeline_start=None,
    call_core_pipeline_status=None,
):
    return await command_router.handle_subcommand(
        subcmd=subcmd,
        args=args,
        user_id="u1",
        attachments=None,
        channel=None,
        pf_dispatch=AsyncMock(),
        call_core=AsyncMock(return_value="core-fallback"),
        call_core_note=AsyncMock(),
        call_core_inbox_list=AsyncMock(),
        call_core_inbox_classify=AsyncMock(),
        call_core_inbox_discard=AsyncMock(),
        call_core_sweep_start=AsyncMock(),
        call_core_sweep_status=AsyncMock(),
        call_core_graph=AsyncMock(),
        call_core_stats=AsyncMock(),
        call_core_check=AsyncMock(),
        call_core_pipeline_start=call_core_pipeline_start or AsyncMock(return_value="PIPELINE-STARTED"),
        call_core_pipeline_status=call_core_pipeline_status or AsyncMock(return_value="PIPELINE-STATUS"),
        is_admin=is_admin or (lambda _u: True),
        note_closed_vocab=frozenset(),
        plugin_prompts={},
        subcommand_prompts={},
        subcommand_help="HELP",
    )


@pytest.mark.parametrize(
    "subcmd,expected_mode",
    [
        ("ralph", "ralph"),
        ("pipeline", "pipeline"),
        ("reweave", "reweave"),
        ("rethink", "rethink"),
        ("refactor", "rethink"),  # D-09 synonym
    ],
)
async def test_pipeline_verb_starts_with_correct_mode(subcmd, expected_mode):
    call_core_pipeline_start = AsyncMock(return_value="PIPELINE-STARTED")
    res = await _call_pipeline_subcommand(subcmd, call_core_pipeline_start=call_core_pipeline_start)
    call_core_pipeline_start.assert_awaited_once_with("u1", mode=expected_mode)
    assert res == "PIPELINE-STARTED"


@pytest.mark.parametrize("subcmd", ["ralph", "pipeline", "reweave", "rethink", "refactor"])
async def test_pipeline_verb_status_invokes_status_gateway(subcmd):
    call_core_pipeline_status = AsyncMock(return_value="PIPELINE-STATUS")
    call_core_pipeline_start = AsyncMock()
    res = await _call_pipeline_subcommand(
        subcmd,
        "status",
        call_core_pipeline_start=call_core_pipeline_start,
        call_core_pipeline_status=call_core_pipeline_status,
    )
    call_core_pipeline_status.assert_awaited_once_with("u1")
    call_core_pipeline_start.assert_not_called()
    assert res == "PIPELINE-STATUS"


async def test_pipeline_verb_non_admin_refused():
    call_core_pipeline_start = AsyncMock()
    res = await _call_pipeline_subcommand(
        "pipeline",
        is_admin=lambda _u: False,
        call_core_pipeline_start=call_core_pipeline_start,
    )
    assert "admin only" in res.lower()
    call_core_pipeline_start.assert_not_called()


async def test_pipeline_verb_concurrency_message_passed_through():
    call_core_pipeline_start = AsyncMock(return_value="A vault operation is already in progress.")
    res = await _call_pipeline_subcommand("pipeline", call_core_pipeline_start=call_core_pipeline_start)
    assert "already in progress" in res.lower()


# --- :migrate (Phase 47-05, T-47-01/T-47-02) ---


async def _call_migrate_subcommand(
    args: str = "",
    *,
    is_admin=None,
    call_core_migrate_start=None,
    call_core_migrate_status=None,
):
    return await command_router.handle_subcommand(
        subcmd="migrate",
        args=args,
        user_id="u1",
        attachments=None,
        channel=None,
        pf_dispatch=AsyncMock(),
        call_core=AsyncMock(return_value="core-fallback"),
        call_core_note=AsyncMock(),
        call_core_inbox_list=AsyncMock(),
        call_core_inbox_classify=AsyncMock(),
        call_core_inbox_discard=AsyncMock(),
        call_core_sweep_start=AsyncMock(),
        call_core_sweep_status=AsyncMock(),
        call_core_graph=AsyncMock(),
        call_core_stats=AsyncMock(),
        call_core_check=AsyncMock(),
        call_core_pipeline_start=AsyncMock(),
        call_core_pipeline_status=AsyncMock(),
        call_core_migrate_start=call_core_migrate_start or AsyncMock(return_value="MIGRATE-STARTED"),
        call_core_migrate_status=call_core_migrate_status or AsyncMock(return_value="MIGRATE-STATUS"),
        is_admin=is_admin or (lambda _u: True),
        note_closed_vocab=frozenset(),
        plugin_prompts={},
        subcommand_prompts={},
        subcommand_help="HELP",
    )


async def test_migrate_non_admin_refused():
    call_core_migrate_start = AsyncMock()
    res = await _call_migrate_subcommand(is_admin=lambda _u: False, call_core_migrate_start=call_core_migrate_start)
    assert "admin only" in res.lower()
    call_core_migrate_start.assert_not_called()


async def test_migrate_bare_defaults_to_dry_run():
    call_core_migrate_start = AsyncMock(return_value="MIGRATE-STARTED")
    res = await _call_migrate_subcommand(call_core_migrate_start=call_core_migrate_start)
    call_core_migrate_start.assert_awaited_once_with("u1", dry_run=True)
    assert res == "MIGRATE-STARTED"


async def test_migrate_explicit_dry_run_verb():
    call_core_migrate_start = AsyncMock(return_value="MIGRATE-STARTED")
    res = await _call_migrate_subcommand("dry-run", call_core_migrate_start=call_core_migrate_start)
    call_core_migrate_start.assert_awaited_once_with("u1", dry_run=True)
    assert res == "MIGRATE-STARTED"


async def test_migrate_live_verb_requires_explicit_confirmation():
    call_core_migrate_start = AsyncMock(return_value="MIGRATE-STARTED")
    res = await _call_migrate_subcommand("live", call_core_migrate_start=call_core_migrate_start)
    call_core_migrate_start.assert_awaited_once_with("u1", dry_run=False)
    assert res == "MIGRATE-STARTED"


async def test_migrate_status_verb_invokes_status_gateway():
    call_core_migrate_status = AsyncMock(return_value="MIGRATE-STATUS")
    call_core_migrate_start = AsyncMock()
    res = await _call_migrate_subcommand(
        "status",
        call_core_migrate_start=call_core_migrate_start,
        call_core_migrate_status=call_core_migrate_status,
    )
    call_core_migrate_status.assert_awaited_once_with("u1")
    call_core_migrate_start.assert_not_called()
    assert res == "MIGRATE-STATUS"
