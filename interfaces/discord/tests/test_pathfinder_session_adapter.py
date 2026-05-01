"""Direct tests for pathfinder_session_adapter seam."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pathfinder_session_adapter


async def test_handle_session_builds_payload_flags():
    client = AsyncMock()
    client.post_to_module = AsyncMock(return_value={"type": "log"})
    out = await pathfinder_session_adapter.handle_session(
        verb="log",
        rest="--force met NPC",
        user_id="u1",
        channel=None,
        sentinel_client=client,
        http_client=object(),
        recap_view_cls=lambda recap_text: SimpleNamespace(message=None),
        build_session_embed=lambda _r: object(),
    )
    assert out["type"] == "embed"
    payload = client.post_to_module.call_args[0][1]
    assert payload["flags"]["force"] is True
    assert payload["args"] == "met NPC"


async def test_handle_session_show_uses_placeholder_edit():
    placeholder = SimpleNamespace(edit=AsyncMock())
    channel = SimpleNamespace(send=AsyncMock(return_value=placeholder))
    client = AsyncMock()
    client.post_to_module = AsyncMock(return_value={"type": "show"})

    out = await pathfinder_session_adapter.handle_session(
        verb="show",
        rest="",
        user_id="u1",
        channel=channel,
        sentinel_client=client,
        http_client=object(),
        recap_view_cls=lambda recap_text: SimpleNamespace(message=None),
        build_session_embed=lambda _r: object(),
    )
    assert out["type"] == "suppressed"
    placeholder.edit.assert_awaited_once()
