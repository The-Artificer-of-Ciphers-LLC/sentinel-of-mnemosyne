"""Direct tests for Session commands (deepened seam).

Tests the new adapter classes directly — these replace the old module-level
handle_session tests that were removed during deepening.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pathfinder_session_adapter
from pathfinder_types import PathfinderRequest


async def test_handle_session_builds_payload_flags():
    cmd = pathfinder_session_adapter.SessionStartCommand()
    client = AsyncMock()
    client.post_to_module = AsyncMock(return_value={"type": "log"})
    request = PathfinderRequest(
        noun="session", verb="start", rest="--force met NPC", user_id="u1",
        channel=None, sentinel_client=client,
    )
    response = await cmd.handle(request)
    assert response.kind == "embed"
    payload = client.post_to_module.call_args[0][1]
    assert payload["flags"]["force"] is True
    assert payload["args"] == "met NPC"


async def test_handle_session_show_uses_placeholder_edit():
    placeholder = SimpleNamespace(edit=AsyncMock())
    channel = SimpleNamespace(send=AsyncMock(return_value=placeholder))
    cmd = pathfinder_session_adapter.SessionShowCommand()
    client = AsyncMock()
    client.post_to_module = AsyncMock(return_value={"type": "show"})
    request = PathfinderRequest(
        noun="session", verb="show", rest="", user_id="u1",
        channel=channel, sentinel_client=client,
    )
    response = await cmd.handle(request)
    assert response.kind == "suppressed"
    placeholder.edit.assert_awaited_once()
