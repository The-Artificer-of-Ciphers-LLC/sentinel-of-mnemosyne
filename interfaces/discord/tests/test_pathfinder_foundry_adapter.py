from unittest.mock import AsyncMock

import pathfinder_foundry_adapter
from pathfinder_types import PathfinderRequest


async def test_foundry_import_denies_non_admin():
    cmd = pathfinder_foundry_adapter.FoundryImportMessagesCommand()
    request = PathfinderRequest(
        noun="foundry",
        verb="import-messages",
        rest="/vault/inbox",
        user_id="u1",
        is_admin=lambda _u: False,
    )
    response = await cmd.handle(request)
    assert "Admin only" in response.content


async def test_foundry_import_builds_payload_and_summary():
    cmd = pathfinder_foundry_adapter.FoundryImportMessagesCommand()
    client = AsyncMock()
    client.post_to_module = AsyncMock(
        return_value={
            "source": "/vault/inbox/messages.db",
            "note_path": "mnemosyne/pf2e/sessions/foundry-chat/2026-05-06/chat-import-12-00-00.md",
            "imported_count": 12,
            "invalid_count": 1,
            "class_counts": {"ic": 7, "roll": 3, "ooc": 2, "system": 0},
            "dry_run": False,
        }
    )

    request = PathfinderRequest(
        noun="foundry",
        verb="import-messages",
        rest="/vault/inbox --live --limit 50",
        user_id="u1",
        is_admin=lambda _u: True,
        sentinel_client=client,
    )

    response = await cmd.handle(request)
    payload = client.post_to_module.call_args[0][1]
    assert payload["inbox_dir"] == "/vault/inbox"
    assert payload["dry_run"] is False
    assert payload["limit"] == 50
    assert "Foundry chat import live complete" in response.content
