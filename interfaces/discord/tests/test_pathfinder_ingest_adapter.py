"""Direct tests for pathfinder_ingest_adapter seam."""

from unittest.mock import AsyncMock

import pathfinder_ingest_adapter


async def test_handle_ingest_denies_non_admin():
    out = await pathfinder_ingest_adapter.handle_ingest(
        noun="ingest",
        parts=["ingest", "archive/cartosia"],
        user_id="u1",
        is_admin=lambda _u: False,
        sentinel_client=AsyncMock(),
        http_client=object(),
    )
    assert "Admin only" in out


async def test_handle_ingest_builds_payload_and_summary():
    client = AsyncMock()
    client.post_to_module = AsyncMock(return_value={"report_path": "r.md", "npc_count": 1, "skipped_existing": 0, "location_count": 0, "homebrew_count": 0, "harvest_count": 0, "lore_count": 0, "session_count": 0, "arc_count": 0, "faction_count": 0, "dialogue_count": 0, "skip_count": 0, "errors": []})
    out = await pathfinder_ingest_adapter.handle_ingest(
        noun="ingest",
        parts=["ingest", "archive/cartosia", "--live", "--limit", "5"],
        user_id="u1",
        is_admin=lambda _u: True,
        sentinel_client=client,
        http_client=object(),
    )
    payload = client.post_to_module.call_args[0][1]
    assert payload["dry_run"] is False
    assert payload["limit"] == 5
    assert "live import" in out
