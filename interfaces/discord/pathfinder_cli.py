"""Pathfinder command-line parsing helpers for Discord commands."""

from __future__ import annotations

from pathfinder_command_catalog import (
    CARTOSIA_USAGE,
    PF_NOUNS,
    top_level_usage_message,
)


def parse_pf_args(
    args: str,
) -> tuple[tuple[str, str, str, list[str]] | None, str | None]:
    parts = args.strip().split(" ", 2)
    if len(parts) >= 1 and parts[0].lower() == "cartosia" and len(parts) < 2:
        return None, cartosia_usage_message()
    if len(parts) < 2:
        return None, usage_message()
    noun, verb = parts[0].lower(), parts[1].lower()
    rest = parts[2] if len(parts) > 2 else ""
    if noun not in PF_NOUNS:
        return None, unknown_noun_message(noun)
    return (noun, verb, rest, parts), None


def usage_message() -> str:
    return top_level_usage_message()


def cartosia_usage_message() -> str:
    return CARTOSIA_USAGE


def unknown_noun_message(noun: str) -> str:
    supported = ", ".join(f"`{n}`" for n in sorted(PF_NOUNS))
    return f"Unknown pf category `{noun}`. Currently supported: {supported}."
