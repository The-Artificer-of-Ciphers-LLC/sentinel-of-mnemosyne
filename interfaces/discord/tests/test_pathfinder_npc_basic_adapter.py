"""Direct tests for pathfinder_npc_basic_adapter seam."""

from unittest.mock import AsyncMock

import pathfinder_npc_basic_adapter


async def test_handle_npc_basic_create_usage():
    handled, out = await pathfinder_npc_basic_adapter.handle_npc_basic(
        verb="create",
        rest="",
        user_id="u1",
        sentinel_client=AsyncMock(),
        http_client=object(),
        valid_relations=frozenset({"knows"}),
    )
    assert handled is True
    assert "Usage" in out


async def test_handle_npc_basic_relate_validates_relation():
    handled, out = await pathfinder_npc_basic_adapter.handle_npc_basic(
        verb="relate",
        rest="A|bad|B",
        user_id="u1",
        sentinel_client=AsyncMock(),
        http_client=object(),
        valid_relations=frozenset({"knows"}),
    )
    assert handled is True
    assert "valid relation" in out


async def test_handle_npc_basic_non_basic_returns_unhandled():
    handled, out = await pathfinder_npc_basic_adapter.handle_npc_basic(
        verb="pdf",
        rest="A",
        user_id="u1",
        sentinel_client=AsyncMock(),
        http_client=object(),
        valid_relations=frozenset({"knows"}),
    )
    assert handled is False
    assert out == ""
