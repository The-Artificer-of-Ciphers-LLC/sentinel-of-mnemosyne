"""Route-shaped contract for Discord ``:pf rule`` commands.

The Discord adapter parses command text and renders user-facing responses.
This module owns the route names and payload dictionaries sent to the
Pathfinder module so route contract changes do not spread across every rule
command class.
"""
from __future__ import annotations

from pathfinder_types import PathfinderModuleCall


def _route(verb: str) -> str:
    return f"modules/pathfinder/rule/{verb}"


def query_call(*, user_id: str, query: str) -> PathfinderModuleCall:
    return PathfinderModuleCall(
        route=_route("query"),
        payload={"query": query, "user_id": user_id},
    )


def list_call() -> PathfinderModuleCall:
    return PathfinderModuleCall(route=_route("list"), payload={})


def show_call(*, topic: str) -> PathfinderModuleCall:
    return PathfinderModuleCall(route=_route("show"), payload={"topic": topic})


def history_call(*, n: int) -> PathfinderModuleCall:
    return PathfinderModuleCall(route=_route("history"), payload={"n": n})
