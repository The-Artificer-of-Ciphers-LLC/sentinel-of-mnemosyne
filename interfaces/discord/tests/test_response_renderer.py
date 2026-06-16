"""Direct tests for response_renderer seam."""

from unittest.mock import AsyncMock

import response_renderer


async def test_send_rendered_response_text():
    send_fn = AsyncMock()
    await response_renderer.send_rendered_response(send_fn, "hello")
    send_fn.assert_awaited_once_with("hello")


async def test_send_rendered_response_empty_text_noops():
    send_fn = AsyncMock()
    await response_renderer.send_rendered_response(send_fn, "")
    send_fn.assert_not_awaited()


async def test_send_rendered_response_embed_dict():
    send_fn = AsyncMock()
    embed = object()
    await response_renderer.send_rendered_response(
        send_fn, {"type": "embed", "content": "c", "embed": embed}
    )
    send_fn.assert_awaited_once_with(content="c", embed=embed)


async def test_send_rendered_response_file_dict(monkeypatch):
    class FakeFile:
        def __init__(self, file_obj, *, filename):
            self.file_obj = file_obj
            self.filename = filename

    monkeypatch.setattr(response_renderer.discord, "File", FakeFile, raising=False)
    send_fn = AsyncMock()
    await response_renderer.send_rendered_response(
        send_fn,
        {
            "type": "file",
            "content": "download",
            "file_bytes": b"abc",
            "filename": "result.txt",
        },
    )

    send_fn.assert_awaited_once()
    assert send_fn.await_args.kwargs["content"] == "download"
    assert send_fn.await_args.kwargs["file"].filename == "result.txt"


async def test_send_rendered_response_suppressed_dict_noops():
    send_fn = AsyncMock()
    await response_renderer.send_rendered_response(send_fn, {"type": "suppressed"})
    send_fn.assert_not_awaited()
