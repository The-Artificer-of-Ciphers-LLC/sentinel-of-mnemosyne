"""Discord rule contract builders match Pathfinder route request models."""
from __future__ import annotations

import os
import sys

_DISCORD_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "interfaces", "discord")
)
if _DISCORD_ROOT not in sys.path:
    sys.path.insert(0, _DISCORD_ROOT)

from app.routes.rule import (  # noqa: E402
    RuleHistoryRequest,
    RuleQueryRequest,
    RuleShowRequest,
)
from pathfinder_rule_contract import (  # noqa: E402
    history_call,
    list_call,
    query_call,
    show_call,
)
from pathfinder_types import PathfinderModuleCall  # noqa: E402


def test_query_call_matches_route_model():
    call = query_call(user_id="u1", query="How does flanking work?")

    assert isinstance(call, PathfinderModuleCall)
    assert call.route == "modules/pathfinder/rule/query"
    assert RuleQueryRequest(**call.payload).model_dump() == call.payload


def test_list_call_matches_route_contract():
    call = list_call()

    assert isinstance(call, PathfinderModuleCall)
    assert call.route == "modules/pathfinder/rule/list"
    assert call.payload == {}


def test_show_call_matches_route_model():
    call = show_call(topic="combat")

    assert isinstance(call, PathfinderModuleCall)
    assert call.route == "modules/pathfinder/rule/show"
    assert RuleShowRequest(**call.payload).model_dump() == call.payload


def test_history_call_matches_route_model():
    call = history_call(n=25)

    assert isinstance(call, PathfinderModuleCall)
    assert call.route == "modules/pathfinder/rule/history"
    assert RuleHistoryRequest(**call.payload).model_dump() == call.payload
