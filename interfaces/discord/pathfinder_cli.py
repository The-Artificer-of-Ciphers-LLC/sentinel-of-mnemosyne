"""Pathfinder command-line parsing helpers for Discord commands."""

from __future__ import annotations

PF_NOUNS = frozenset({"npc", "harvest", "rule", "session", "ingest", "cartosia"})


def usage_message() -> str:
    return (
        "Usage: `:pf npc <create|update|show|relate|import|say> ...` "
        "or `:pf harvest <Name>[,<Name>...]` "
        "or `:pf rule <question>|show <topic>|history [N]|list` "
        "or `:pf cartosia <archive_path> [--live] [--limit N]` (admin-only)"
    )


def cartosia_usage_message() -> str:
    return (
        "Usage: `:pf cartosia <archive_path> [--live] [--dry-run] "
        "[--limit N] [--force] [--confirm-large]` (admin-only)"
    )


def unknown_noun_message(noun: str) -> str:
    supported = ", ".join(f"`{n}`" for n in sorted(PF_NOUNS))
    return f"Unknown pf category `{noun}`. Currently supported: {supported}."
