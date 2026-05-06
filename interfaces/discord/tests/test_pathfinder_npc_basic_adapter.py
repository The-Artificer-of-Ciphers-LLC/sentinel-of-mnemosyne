"""Direct tests for NPC basic commands (deepened seam).

Tests the new adapter classes directly — these replace the old module-level
handle_npc_basic tests that were removed during deepening.
"""

from unittest.mock import AsyncMock

import pathfinder_npc_basic_adapter
from pathfinder_types import PathfinderRequest


async def test_handle_npc_create_usage():
    cmd = pathfinder_npc_basic_adapter.NpcCreateCommand()
    request = PathfinderRequest(
        noun="npc", verb="create", rest="", user_id="u1"
    )
    response = await cmd.handle(request)
    assert "Usage" in response.content


async def test_handle_npc_relate_validates_relation():
    cmd = pathfinder_npc_basic_adapter.NpcRelateCommand()
    request = PathfinderRequest(
        noun="npc", verb="relate", rest="A|bad|B", user_id="u1",
        valid_relations=frozenset({"knows"}),
    )
    response = await cmd.handle(request)
    assert "valid relation" in response.content
