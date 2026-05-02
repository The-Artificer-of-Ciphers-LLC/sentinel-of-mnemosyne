from unittest.mock import AsyncMock

import httpx

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
        map_http_status=lambda s, d: f"{s}:{d}",
        log_error=lambda _m: None,
    )
    assert out == "ERR"


async def test_dispatch_pf_maps_http_status_error():
    response = httpx.Response(404, request=httpx.Request("POST", "http://x"), json={"detail": "missing"})

    async def _raise(*_, **__):
        raise httpx.HTTPStatusError("bad", request=response.request, response=response)

    out = await pathfinder_bridge.dispatch_pf(
        args="npc show x",
        user_id="u1",
        attachments=None,
        channel=None,
        bot_user=None,
        parse_pf_args=lambda _a: (("npc", "show", "x", ["npc", "show", "x"]), None),
        dispatch=_raise,
        sent_client=object(),
        is_admin=lambda _u: False,
        valid_relations=frozenset(),
        adapters={},
        builders={},
        map_http_status=lambda s, d: f"mapped:{s}:{d}",
        log_error=lambda _m: None,
    )
    assert out == "mapped:404:missing"
