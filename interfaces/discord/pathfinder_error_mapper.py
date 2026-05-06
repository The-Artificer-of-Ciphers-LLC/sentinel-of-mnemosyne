"""Error mapping for Pathfinder command dispatch."""

from __future__ import annotations


def map_http_status(status: int, detail: str) -> str:
    if status == 409:
        return f"NPC already exists: {detail}"
    if status == 404:
        detail_l = (detail or "").lower()
        if "npc" in detail_l:
            return "NPC not found."
        return f"Pathfinder module error (HTTP 404): {detail}"
    return f"Pathfinder module error (HTTP {status}): {detail}"
