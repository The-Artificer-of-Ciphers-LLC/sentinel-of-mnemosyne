"""Pathfinder foundry noun adapter for Discord :pf commands."""

from __future__ import annotations

from pathfinder_types import PathfinderCommand, PathfinderRequest, PathfinderResponse


class FoundryImportMessagesCommand(PathfinderCommand):
    """Handle ``:pf foundry import-messages <inbox_dir> [--dry-run|--live] [--limit N]`` (admin-only)."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        if request.is_admin is None or not request.is_admin(request.user_id):
            return PathfinderResponse(
                kind="text",
                content="Admin only. Set SENTINEL_ADMIN_USER_IDS in your env to use this command.",
            )

        if request.verb != "import-messages":
            return PathfinderResponse(
                kind="text",
                content="Usage: `:pf foundry import-messages <inbox_dir> [--dry-run|--live] [--limit N]` (admin-only)",
            )

        tokens = [t for t in request.rest.split() if t]
        if not tokens:
            return PathfinderResponse(
                kind="text",
                content="Usage: `:pf foundry import-messages <inbox_dir> [--dry-run|--live] [--limit N]` (admin-only)",
            )

        inbox_dir: str | None = None
        dry_run = True
        limit_val: int | None = None

        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok == "--dry-run":
                dry_run = True
            elif tok == "--live":
                dry_run = False
            elif tok == "--limit":
                if i + 1 >= len(tokens) or not tokens[i + 1].lstrip("-").isdigit():
                    return PathfinderResponse(
                        kind="text", content="Usage: `--limit N` requires an integer argument."
                    )
                limit_val = int(tokens[i + 1])
                i += 1
            elif tok.startswith("--"):
                return PathfinderResponse(kind="text", content=f"Unknown flag `{tok}`.")
            else:
                if inbox_dir is None:
                    inbox_dir = tok
                else:
                    inbox_dir = f"{inbox_dir} {tok}"
            i += 1

        if not inbox_dir:
            return PathfinderResponse(
                kind="text",
                content="Usage: `:pf foundry import-messages <inbox_dir> [--dry-run|--live] [--limit N]` (admin-only)",
            )

        payload = {
            "inbox_dir": inbox_dir,
            "dry_run": dry_run,
            "limit": limit_val,
        }
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/foundry/messages/import", payload, request.http_client
        )

        if not isinstance(result, dict):
            return PathfinderResponse(
                kind="text", content=f"Foundry messages import returned unexpected response: {result!r}"
            )

        mode = "dry-run" if result.get("dry_run", dry_run) else "live"
        class_counts = result.get("class_counts", {}) or {}
        summary = (
            f"Foundry chat import {mode} complete.\n"
            f"Source: `{result.get('source', '?')}`\n"
            f"Report: `{result.get('note_path', '?')}`\n"
            f"Imported: {result.get('imported_count', 0)} | Invalid: {result.get('invalid_count', 0)}\n"
            f"IC: {class_counts.get('ic', 0)} | Rolls: {class_counts.get('roll', 0)} | "
            f"OOC: {class_counts.get('ooc', 0)} | System: {class_counts.get('system', 0)}"
        )
        return PathfinderResponse(kind="text", content=summary)
