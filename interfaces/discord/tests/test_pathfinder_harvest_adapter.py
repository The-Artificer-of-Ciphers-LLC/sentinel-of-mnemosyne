"""Direct tests for HarvestCommand (deepened seam).

Tests the new adapter class directly — these replace the old module-level
handle_harvest tests that were removed during deepening.
"""

from unittest.mock import AsyncMock

import pathfinder_harvest_adapter
from pathfinder_types import PathfinderRequest


async def test_handle_harvest_usage_when_missing_names():
    cmd = pathfinder_harvest_adapter.HarvestCommand()
    # parts mirrors production: only ["harvest"] → len==1 → no names → usage
    request = PathfinderRequest(
        noun="harvest", verb="*", rest="", user_id="u1",
        parts=["harvest"],
    )
    response = await cmd.handle(request)
    assert "Usage" in response.content


async def test_handle_harvest_posts_names_and_wraps_embed():
    cmd = pathfinder_harvest_adapter.HarvestCommand()
    client = AsyncMock()
    client.post_to_module = AsyncMock(return_value={
        "name": "Boar",
        "path": "/vault/harvest/boar.md",
    })
    # parts mirrors production: "harvest Boar,Wolf" → ["harvest", "Boar,Wolf"]
    request = PathfinderRequest(
        noun="harvest", verb="*", rest="Boar,Wolf",
        user_id="u1", sentinel_client=client,
        parts=["harvest", "Boar,Wolf"],
    )
    response = await cmd.handle(request)
    assert response.kind == "embed"
    payload = client.post_to_module.call_args[0][1]
    assert payload["names"] == ["Boar", "Wolf"]
