"""Direct tests for pathfinder_npc_rich_adapter seam."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pathfinder_npc_rich_adapter


async def test_handle_npc_rich_import_requires_attachment():
    handled, out = await pathfinder_npc_rich_adapter.handle_npc_rich(
        verb="import",
        rest="",
        user_id="u1",
        attachments=None,
        channel=None,
        bot_user=None,
        sentinel_client=AsyncMock(),
        http_client=AsyncMock(),
        build_stat_embed=lambda _r: object(),
        render_say_response=lambda _r: "x",
        extract_thread_history=AsyncMock(return_value=[]),
    )
    assert handled is True
    assert "attach" in out.lower()


async def test_handle_npc_rich_pdf_returns_file_shape():
    client = AsyncMock()
    client.post_to_module = AsyncMock(return_value={"data_b64": "UERG", "filename": "n.pdf"})
    handled, out = await pathfinder_npc_rich_adapter.handle_npc_rich(
        verb="pdf",
        rest="Varek",
        user_id="u1",
        attachments=None,
        channel=None,
        bot_user=None,
        sentinel_client=client,
        http_client=AsyncMock(),
        build_stat_embed=lambda _r: object(),
        render_say_response=lambda _r: "x",
        extract_thread_history=AsyncMock(return_value=[]),
    )
    assert handled is True
    assert out["type"] == "file"
    assert out["filename"] == "n.pdf"


async def test_handle_npc_rich_say_usage_when_missing_pipe():
    handled, out = await pathfinder_npc_rich_adapter.handle_npc_rich(
        verb="say",
        rest="Varek hello",
        user_id="u1",
        attachments=None,
        channel=None,
        bot_user=SimpleNamespace(id=1),
        sentinel_client=AsyncMock(),
        http_client=AsyncMock(),
        build_stat_embed=lambda _r: object(),
        render_say_response=lambda _r: "x",
        extract_thread_history=AsyncMock(return_value=[]),
    )
    assert handled is True
    assert "Usage" in out
