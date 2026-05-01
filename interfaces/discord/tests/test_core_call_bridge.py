from unittest.mock import AsyncMock

import core_call_bridge


async def test_call_core_message_delegates_to_client_send_message():
    client = AsyncMock()
    client.send_message = AsyncMock(return_value="ok")
    out = await core_call_bridge.call_core_message(
        sent_client=client,
        user_id="u1",
        message="hello",
    )
    assert out == "ok"
    client.send_message.assert_awaited_once()
