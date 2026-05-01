"""Direct tests for response_renderer seam."""

from unittest.mock import AsyncMock

import response_renderer


async def test_send_rendered_response_text():
    send_fn = AsyncMock()
    await response_renderer.send_rendered_response(send_fn, "hello")
    send_fn.assert_awaited_once_with("hello")


async def test_send_rendered_response_embed_dict():
    send_fn = AsyncMock()
    embed = object()
    await response_renderer.send_rendered_response(
        send_fn, {"type": "embed", "content": "c", "embed": embed}
    )
    send_fn.assert_awaited_once_with(content="c", embed=embed)
