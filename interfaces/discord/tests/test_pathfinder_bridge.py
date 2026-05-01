from unittest.mock import AsyncMock

import pathfinder_bridge


async def test_dispatch_pf_returns_parse_error_directly():
    out = await pathfinder_bridge.dispatch_pf(
        args="bad",
        user_id="u1",
        attachments=None,
        channel=None,
        bot_user=None,
        parse_pf_args=lambda _a: (None, "ERR"),
        dispatch=AsyncMock(),
        sent_client=object(),
        is_admin=lambda _u: False,
        valid_relations=frozenset(),
        adapters={},
        builders={},
    )
    assert out == "ERR"
