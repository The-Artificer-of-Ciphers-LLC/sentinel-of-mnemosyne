"""Direct tests for pathfinder_dispatch seam."""

from unittest.mock import AsyncMock

import pathfinder_dispatch


class _Adapter:
    def __init__(self, fn_name: str, return_value):
        self.fn_name = fn_name
        setattr(self, fn_name, AsyncMock(return_value=return_value))


async def test_dispatch_routes_rule_noun():
    adapters = {
        "harvest": _Adapter("handle_harvest", "h"),
        "ingest": _Adapter("handle_ingest", "i"),
        "rule": _Adapter("handle_rule", "RULE"),
        "session": _Adapter("handle_session", "s"),
        "npc_basic": _Adapter("handle_npc_basic", (False, "")),
        "npc_rich": _Adapter("handle_npc_rich", (True, "r")),
    }
    out = await pathfinder_dispatch.dispatch(
        noun="rule",
        verb="query",
        rest="x",
        parts=["rule", "query", "x"],
        user_id="u1",
        attachments=None,
        channel=None,
        bot_user=None,
        sentinel_client=object(),
        http_client=object(),
        is_admin=lambda _u: True,
        valid_relations=frozenset(),
        adapters=adapters,
        builders={
            "build_harvest_embed": lambda _r: None,
            "build_ruling_embed": lambda _r: None,
            "recap_view_cls": object,
            "build_session_embed": lambda _r: None,
            "build_stat_embed": lambda _r: None,
            "render_say_response": lambda _r: "",
            "extract_thread_history": AsyncMock(return_value=[]),
        },
    )
    assert out == "RULE"
    adapters["rule"].handle_rule.assert_awaited_once()


async def test_dispatch_falls_to_npc_rich_when_basic_unhandled():
    adapters = {
        "harvest": _Adapter("handle_harvest", "h"),
        "ingest": _Adapter("handle_ingest", "i"),
        "rule": _Adapter("handle_rule", "rule"),
        "session": _Adapter("handle_session", "s"),
        "npc_basic": _Adapter("handle_npc_basic", (False, "")),
        "npc_rich": _Adapter("handle_npc_rich", (True, "RICH")),
    }
    out = await pathfinder_dispatch.dispatch(
        noun="npc",
        verb="say",
        rest="A|B",
        parts=["npc", "say", "A|B"],
        user_id="u1",
        attachments=[],
        channel=None,
        bot_user=None,
        sentinel_client=object(),
        http_client=object(),
        is_admin=lambda _u: True,
        valid_relations=frozenset({"knows"}),
        adapters=adapters,
        builders={
            "build_harvest_embed": lambda _r: None,
            "build_ruling_embed": lambda _r: None,
            "recap_view_cls": object,
            "build_session_embed": lambda _r: None,
            "build_stat_embed": lambda _r: None,
            "render_say_response": lambda _r: "",
            "extract_thread_history": AsyncMock(return_value=[]),
        },
    )
    assert out == "RICH"
