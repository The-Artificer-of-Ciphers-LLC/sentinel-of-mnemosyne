"""Pathfinder ingest/cartosia noun adapter for Discord :pf commands."""

from __future__ import annotations


async def handle_ingest(
    *,
    noun: str,
    parts: list[str],
    user_id: str,
    is_admin,
    sentinel_client,
    http_client,
) -> str:
    if not is_admin(user_id):
        return "Admin only. Set SENTINEL_ADMIN_USER_IDS in your env to use this command."

    tail = " ".join(parts[1:]).strip()
    tokens = [t for t in tail.split() if t]
    archive_path: str | None = None
    live = False
    force_flag = False
    confirm_large = False
    limit_val: int | None = None
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == "--live":
            live = True
        elif tok == "--dry-run":
            live = False
        elif tok == "--force":
            force_flag = True
        elif tok == "--confirm-large":
            confirm_large = True
        elif tok == "--limit":
            if i + 1 >= len(tokens) or not tokens[i + 1].lstrip("-").isdigit():
                return "Usage: `--limit N` requires an integer argument."
            limit_val = int(tokens[i + 1])
            i += 1
        elif tok.startswith("--"):
            return f"Unknown flag `{tok}`."
        else:
            if archive_path is None:
                archive_path = tok
            else:
                archive_path = f"{archive_path} {tok}"
        i += 1

    if not archive_path:
        if noun == "cartosia":
            return (
                "Usage: `:pf cartosia <archive_path> [--live] [--dry-run] "
                "[--limit N] [--force] [--confirm-large]` (admin-only)"
            )
        return (
            "Usage: `:pf ingest <subfolder> [--live] [--dry-run] "
            "[--limit N] [--force] [--confirm-large]` (admin-only)"
        )

    subfolder_val = "archive/cartosia" if noun == "cartosia" else archive_path
    payload = {
        "archive_root": archive_path,
        "subfolder": subfolder_val,
        "dry_run": not live,
        "limit": limit_val,
        "force": force_flag,
        "confirm_large": confirm_large,
        "user_id": user_id,
    }
    result = await sentinel_client.post_to_module("modules/pathfinder/ingest", payload, http_client)
    if not isinstance(result, dict):
        return f"PF2e archive ingest returned unexpected response: {result!r}"

    report_path = result.get("report_path", "?")
    kind_word = "live import" if live else "dry-run"
    summary = (
        f"PF2e archive ingest {kind_word} complete.\n"
        f"Report: `{report_path}`\n"
        f"NPCs: {result.get('npc_count', 0)} "
        f"(skipped existing: {result.get('skipped_existing', 0)}) | "
        f"Locations: {result.get('location_count', 0)} | "
        f"Homebrew: {result.get('homebrew_count', 0)} | "
        f"Harvest: {result.get('harvest_count', 0)} | "
        f"Lore: {result.get('lore_count', 0)} | "
        f"Sessions: {result.get('session_count', 0)} | "
        f"Arcs: {result.get('arc_count', 0)} | "
        f"Factions: {result.get('faction_count', 0)} | "
        f"Dialogue: {result.get('dialogue_count', 0)} | "
        f"Skipped: {result.get('skip_count', 0)} | "
        f"Errors: {len(result.get('errors', []) or [])}"
    )
    if noun == "cartosia":
        summary = (
            "Deprecated: use `:pf ingest archive/cartosia` instead — "
            "forwarding...\n\n" + summary
        )
    return summary
