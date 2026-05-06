"""Direct tests for IngestCommand (deepened seam).

Tests the new adapter class directly — these replace the old module-level
handle_ingest tests that were removed during deepening.
"""

from unittest.mock import AsyncMock

import pathfinder_ingest_adapter
from pathfinder_types import PathfinderRequest


async def test_handle_ingest_denies_non_admin():
    cmd = pathfinder_ingest_adapter.IngestCommand()
    request = PathfinderRequest(
        noun="ingest", verb="*", rest="archive/cartosia", user_id="u1",
        is_admin=lambda _u: False,
    )
    response = await cmd.handle(request)
    assert "Admin only" in response.content


async def test_handle_ingest_builds_payload_and_summary():
    cmd = pathfinder_ingest_adapter.IngestCommand()
    client = AsyncMock()
    client.post_to_module = AsyncMock(return_value={
        "report_path": "r.md", "npc_count": 1, "skipped_existing": 0,
        "location_count": 0, "homebrew_count": 0, "harvest_count": 0,
        "lore_count": 0, "session_count": 0, "arc_count": 0,
        "faction_count": 0, "dialogue_count": 0, "skip_count": 0,
        "errors": [],
    })
    request = PathfinderRequest(
        noun="ingest", verb="*", rest="archive/cartosia --live --limit 5",
        user_id="u1", is_admin=lambda _u: True,
        sentinel_client=client,
    )
    response = await cmd.handle(request)
    payload = client.post_to_module.call_args[0][1]
    assert payload["dry_run"] is False
    assert payload["limit"] == 5
    assert "live import" in response.content
