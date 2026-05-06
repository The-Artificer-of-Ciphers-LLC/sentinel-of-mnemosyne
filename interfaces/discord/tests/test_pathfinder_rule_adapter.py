"""Direct tests for Rule commands (deepened seam).

Tests the new adapter classes directly — these replace the old module-level
handle_rule tests that were removed during deepening.
"""

from unittest.mock import AsyncMock

import pathfinder_rule_adapter
from pathfinder_types import PathfinderRequest


async def test_handle_rule_query_usage_when_empty():
    cmd = pathfinder_rule_adapter.RuleQueryCommand()
    request = PathfinderRequest(
        noun="rule", verb="query", rest="", user_id="u1"
    )
    response = await cmd.handle(request)
    assert "Usage" in response.content


async def test_handle_rule_history_caps_n():
    cmd = pathfinder_rule_adapter.RuleHistoryCommand()
    client = AsyncMock()
    client.post_to_module = AsyncMock(return_value={"rulings": []})
    request = PathfinderRequest(
        noun="rule", verb="history", rest="500", user_id="u1",
        sentinel_client=client,
    )
    response = await cmd.handle(request)
    assert response.content == "_No rulings yet._"
    payload = client.post_to_module.call_args[0][1]
    assert payload["n"] == 50
