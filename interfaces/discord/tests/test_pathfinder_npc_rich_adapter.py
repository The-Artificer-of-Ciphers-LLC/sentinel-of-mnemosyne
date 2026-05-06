"""Direct tests for NPC rich commands (deepened seam).

Tests the new adapter classes directly — these replace the old module-level
handle_npc_rich tests that were removed during deepening.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pathfinder_npc_rich_adapter
from pathfinder_types import PathfinderRequest


async def test_handle_npc_import_requires_attachment():
    cmd = pathfinder_npc_rich_adapter.NpcImportCommand()
    request = PathfinderRequest(
        noun="npc", verb="import", rest="", user_id="u1",
        attachments=None, channel=None, bot_user=None,
    )
    response = await cmd.handle(request)
    assert "attach" in response.content.lower()


async def test_handle_npc_pdf_returns_file_shape():
    cmd = pathfinder_npc_rich_adapter.NpcPdfCommand()
    client = AsyncMock()
    client.post_to_module = AsyncMock(return_value={"data_b64": "UERG", "filename": "n.pdf"})
    request = PathfinderRequest(
        noun="npc", verb="pdf", rest="Varek", user_id="u1",
        sentinel_client=client,
    )
    response = await cmd.handle(request)
    assert response.kind == "file"
    assert response.filename == "n.pdf"


async def test_handle_npc_say_usage_when_missing_pipe():
    cmd = pathfinder_npc_rich_adapter.NpcSayCommand()
    request = PathfinderRequest(
        noun="npc", verb="say", rest="Varek hello", user_id="u1",
        bot_user=SimpleNamespace(id=1),
    )
    response = await cmd.handle(request)
    assert "Usage" in response.content
