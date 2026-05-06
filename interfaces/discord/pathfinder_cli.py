"""Pathfinder command-line parsing helpers for Discord commands."""

from __future__ import annotations

PF_NOUNS = frozenset({"npc", "harvest", "rule", "session", "ingest", "cartosia", "foundry"})


def parse_pf_args(args: str) -> tuple[tuple[str, str, str, list[str]] | None, str | None]:
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
    return (
        "Usage: `:pf npc <create|update|show|relate|import|say> ...` "
        "or `:pf harvest <Name>[,<Name>...]` "
        "or `:pf rule <question>|show <topic>|history [N]|list` "
        "or `:pf cartosia <archive_path> [--live] [--limit N]` (admin-only) "
        "or `:pf foundry import-messages <inbox_dir> [--dry-run|--live] [--limit N]` (admin-only)"
    )


def cartosia_usage_message() -> str:
    return (
        "Usage: `:pf cartosia <archive_path> [--live] [--dry-run] "
        "[--limit N] [--force] [--confirm-large]` (admin-only)"
    )


def unknown_noun_message(noun: str) -> str:
    supported = ", ".join(f"`{n}`" for n in sorted(PF_NOUNS))
    return f"Unknown pf category `{noun}`. Currently supported: {supported}."
