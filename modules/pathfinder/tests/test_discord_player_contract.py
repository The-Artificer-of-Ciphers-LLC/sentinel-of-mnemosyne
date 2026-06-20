"""Discord player contract builders match Pathfinder route request models."""
from __future__ import annotations

import os
import sys

_DISCORD_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "interfaces", "discord")
)
if _DISCORD_ROOT not in sys.path:
    sys.path.insert(0, _DISCORD_ROOT)

from app.routes.player import (  # noqa: E402
    PlayerAskRequest,
    PlayerCanonizeRequest,
    PlayerNpcRequest,
    PlayerNoteRequest,
    PlayerOnboardRequest,
    PlayerRecallRequest,
    PlayerStyleRequest,
    PlayerTodoRequest,
    VALID_STYLE_PRESETS,
)
from pathfinder_player_contract import (  # noqa: E402
    PLAYER_STYLE_PRESETS,
    ask_call,
    canonize_call,
    note_call,
    npc_call,
    onboard_call,
    recall_call,
    style_call,
    todo_call,
)
from pathfinder_types import PathfinderModuleCall  # noqa: E402


def test_style_presets_match_route_contract():
    assert set(PLAYER_STYLE_PRESETS) == set(VALID_STYLE_PRESETS)


def test_player_contract_returns_shared_module_call():
    call = ask_call(user_id="u1", text="What rule applies?")

    assert isinstance(call, PathfinderModuleCall)


def test_onboard_call_matches_route_model():
    call = onboard_call(
        user_id="u1",
        character_name="Kael Stormblade",
        preferred_name="Kael",
        style_preset="Tactician",
    )

    assert call.route == "modules/pathfinder/player/onboard"
    assert PlayerOnboardRequest(**call.payload).model_dump() == call.payload


def test_note_call_matches_route_model():
    call = note_call(user_id="u1", text="I trust Varek.")

    assert call.route == "modules/pathfinder/player/note"
    assert PlayerNoteRequest(**call.payload).model_dump() == call.payload


def test_ask_call_matches_route_model():
    call = ask_call(user_id="u1", text="What rule applies?")

    assert call.route == "modules/pathfinder/player/ask"
    assert PlayerAskRequest(**call.payload).model_dump() == call.payload


def test_npc_call_matches_route_model():
    call = npc_call(user_id="u1", npc_name="Varek", note="trustworthy")

    assert call.route == "modules/pathfinder/player/npc"
    assert PlayerNpcRequest(**call.payload).model_dump() == call.payload


def test_recall_call_matches_route_model():
    call = recall_call(user_id="u1", query="Varek bridge")

    assert call.route == "modules/pathfinder/player/recall"
    assert PlayerRecallRequest(**call.payload).model_dump() == call.payload


def test_todo_call_matches_route_model():
    call = todo_call(user_id="u1", text="Buy rope")

    assert call.route == "modules/pathfinder/player/todo"
    assert PlayerTodoRequest(**call.payload).model_dump() == call.payload


def test_style_list_call_matches_route_model():
    call = style_call(user_id="u1", action="list")

    assert call.route == "modules/pathfinder/player/style"
    assert PlayerStyleRequest(**call.payload).model_dump() == {
        "user_id": "u1",
        "action": "list",
        "preset": None,
    }


def test_style_set_call_matches_route_model():
    call = style_call(user_id="u1", action="set", preset="Tactician")

    assert call.route == "modules/pathfinder/player/style"
    assert PlayerStyleRequest(**call.payload).model_dump() == call.payload


def test_canonize_call_matches_route_model():
    call = canonize_call(
        user_id="u1",
        outcome="green",
        question_id="q-uuid-1",
        rule_text="Vital strike applies on first attack only",
    )

    assert call.route == "modules/pathfinder/player/canonize"
    assert PlayerCanonizeRequest(**call.payload).model_dump() == call.payload
