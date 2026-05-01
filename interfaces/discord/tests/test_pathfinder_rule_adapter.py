"""Direct tests for pathfinder_rule_adapter seam."""

from unittest.mock import AsyncMock

import pathfinder_rule_adapter


async def test_handle_rule_query_usage_when_empty():
    out = await pathfinder_rule_adapter.handle_rule(
        verb="query",
        rest="",
        parts=["rule"],
        user_id="u1",
        channel=None,
        sentinel_client=AsyncMock(),
        http_client=object(),
        build_ruling_embed=lambda _r: object(),
    )
    assert "Usage" in out


async def test_handle_rule_history_caps_n():
    client = AsyncMock()
    client.post_to_module = AsyncMock(return_value={"rulings": []})
    out = await pathfinder_rule_adapter.handle_rule(
        verb="history",
        rest="500",
        parts=["rule", "history", "500"],
        user_id="u1",
        channel=None,
        sentinel_client=client,
        http_client=object(),
        build_ruling_embed=lambda _r: object(),
    )
    assert out == "_No rulings yet._"
    payload = client.post_to_module.call_args[0][1]
    assert payload["n"] == 50
