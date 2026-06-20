"""Route-shaped contract for Discord ``:pf player`` commands.

The Discord adapter parses command text and renders user-facing responses.
This module owns the route names and payload dictionaries sent to the
Pathfinder module so route contract changes do not spread across every player
command class.
"""
from __future__ import annotations

from typing import Literal

from pathfinder_types import PathfinderModuleCall


PLAYER_STYLE_PRESETS = ("Tactician", "Lorekeeper", "Cheerleader", "Rules-Lawyer Lite")


PlayerModuleCall = PathfinderModuleCall


def _route(verb: str) -> str:
    return f"modules/pathfinder/player/{verb}"


def onboard_call(
    *,
    user_id: str,
    character_name: str,
    preferred_name: str,
    style_preset: str,
) -> PathfinderModuleCall:
    return PathfinderModuleCall(
        route=_route("onboard"),
        payload={
            "user_id": user_id,
            "character_name": character_name,
            "preferred_name": preferred_name,
            "style_preset": style_preset,
        },
    )


def note_call(*, user_id: str, text: str) -> PathfinderModuleCall:
    return PathfinderModuleCall(
        route=_route("note"),
        payload={"user_id": user_id, "text": text},
    )


def ask_call(*, user_id: str, text: str) -> PathfinderModuleCall:
    return PathfinderModuleCall(
        route=_route("ask"),
        payload={"user_id": user_id, "text": text},
    )


def npc_call(*, user_id: str, npc_name: str, note: str) -> PathfinderModuleCall:
    return PathfinderModuleCall(
        route=_route("npc"),
        payload={"user_id": user_id, "npc_name": npc_name, "note": note},
    )


def recall_call(*, user_id: str, query: str) -> PathfinderModuleCall:
    return PathfinderModuleCall(
        route=_route("recall"),
        payload={"user_id": user_id, "query": query},
    )


def todo_call(*, user_id: str, text: str) -> PathfinderModuleCall:
    return PathfinderModuleCall(
        route=_route("todo"),
        payload={"user_id": user_id, "text": text},
    )


def style_call(
    *,
    user_id: str,
    action: Literal["list", "set"],
    preset: str | None = None,
) -> PathfinderModuleCall:
    payload = {"user_id": user_id, "action": action}
    if preset is not None:
        payload["preset"] = preset
    return PathfinderModuleCall(route=_route("style"), payload=payload)


def canonize_call(
    *,
    user_id: str,
    outcome: str,
    question_id: str,
    rule_text: str,
) -> PathfinderModuleCall:
    return PathfinderModuleCall(
        route=_route("canonize"),
        payload={
            "user_id": user_id,
            "outcome": outcome,
            "question_id": question_id,
            "rule_text": rule_text,
        },
    )
