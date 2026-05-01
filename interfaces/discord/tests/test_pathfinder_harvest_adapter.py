"""Direct tests for pathfinder_harvest_adapter seam."""

from unittest.mock import AsyncMock

import pathfinder_harvest_adapter


async def test_handle_harvest_usage_when_missing_names():
    out = await pathfinder_harvest_adapter.handle_harvest(
        parts=["harvest"],
        user_id="u1",
        sentinel_client=AsyncMock(),
        http_client=object(),
        build_harvest_embed=lambda _r: object(),
    )
    assert "Usage" in out


async def test_handle_harvest_posts_names_and_wraps_embed():
    client = AsyncMock()
    client.post_to_module = AsyncMock(return_value={"ok": True})
    embed_obj = object()
    out = await pathfinder_harvest_adapter.handle_harvest(
        parts=["harvest", "Boar,Wolf"],
        user_id="u1",
        sentinel_client=client,
        http_client=object(),
        build_harvest_embed=lambda _r: embed_obj,
    )
    assert out["type"] == "embed"
    assert out["embed"] is embed_obj
    payload = client.post_to_module.call_args[0][1]
    assert payload["names"] == ["Boar", "Wolf"]
