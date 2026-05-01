"""Pathfinder NPC rich verb adapter for Discord :pf commands."""

from __future__ import annotations

import base64
import json

import discord


async def handle_npc_rich(
    *,
    verb: str,
    rest: str,
    user_id: str,
    attachments: list | None,
    channel,
    bot_user,
    sentinel_client,
    http_client,
    build_stat_embed,
    render_say_response,
    extract_thread_history,
) -> tuple[bool, "str | dict"]:
    if verb == "import":
        if not attachments:
            return True, (
                "Usage: `:pf npc import` — attach a Foundry actor list JSON file "
                "as a reply in this thread."
            )
        attachment = attachments[0]
        fetch_resp = await http_client.get(str(attachment.url), timeout=10.0)
        fetch_resp.raise_for_status()
        actors_json = fetch_resp.text
        result = await sentinel_client.post_to_module(
            "modules/pathfinder/npc/import",
            {"actors_json": actors_json, "user_id": user_id},
            http_client,
        )
        imported = result.get("imported_count", 0)
        skipped = result.get("skipped", [])
        lines = [f"Imported **{imported}** NPC(s)."]
        if skipped:
            lines.append(f"Skipped (already exist): {', '.join(skipped)}")
        return True, "\n".join(lines)

    if verb == "export":
        npc_name = rest.strip()
        if not npc_name:
            return True, "Usage: `:pf npc export <name>`"
        result = await sentinel_client.post_to_module(
            "modules/pathfinder/npc/export-foundry", {"name": npc_name}, http_client
        )
        json_bytes = json.dumps(result["actor"], indent=2).encode("utf-8")
        return True, {
            "type": "file",
            "content": f"Foundry actor JSON for **{npc_name}**:",
            "file_bytes": json_bytes,
            "filename": result["filename"],
        }

    if verb == "token":
        npc_name = rest.strip()
        if not npc_name:
            return True, "Usage: `:pf npc token <name>`"
        result = await sentinel_client.post_to_module(
            "modules/pathfinder/npc/token", {"name": npc_name}, http_client
        )
        return True, result.get("prompt", "No prompt generated.")

    if verb == "token-image":
        npc_name = rest.strip()
        if not npc_name:
            return True, "Usage: `:pf npc token-image <name>` — attach a PNG as a reply in this thread."
        if not attachments:
            return True, (
                f"Usage: `:pf npc token-image {npc_name}` — attach the Midjourney-"
                "generated PNG as a reply in this thread."
            )
        attachment = attachments[0]
        content_type = getattr(attachment, "content_type", "") or ""
        if not content_type.startswith("image/"):
            return True, (
                f"Expected an image attachment (got `{content_type or 'unknown'}`). "
                "Midjourney exports PNG — re-attach the PNG and try again."
            )
        fetch_resp = await http_client.get(str(attachment.url), timeout=30.0)
        fetch_resp.raise_for_status()
        image_bytes = fetch_resp.content
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        result = await sentinel_client.post_to_module(
            "modules/pathfinder/npc/token-image",
            {"name": npc_name, "image_b64": image_b64},
            http_client,
        )
        return True, (
            f"Token image saved for **{npc_name}** "
            f"({result.get('size_bytes', len(image_bytes))} bytes) → `{result.get('token_path', '?')}`.\n"
            f"Run `:pf npc pdf {npc_name}` to see it embedded in the stat card."
        )

    if verb == "stat":
        npc_name = rest.strip()
        if not npc_name:
            return True, "Usage: `:pf npc stat <name>`"
        result = await sentinel_client.post_to_module(
            "modules/pathfinder/npc/stat", {"name": npc_name}, http_client
        )
        return True, {"type": "embed", "content": "", "embed": build_stat_embed(result)}

    if verb == "pdf":
        npc_name = rest.strip()
        if not npc_name:
            return True, "Usage: `:pf npc pdf <name>`"
        result = await sentinel_client.post_to_module(
            "modules/pathfinder/npc/pdf", {"name": npc_name}, http_client
        )
        pdf_bytes = base64.b64decode(result["data_b64"])
        return True, {
            "type": "file",
            "content": f"PDF stat card for **{npc_name}**:",
            "file_bytes": pdf_bytes,
            "filename": result["filename"],
        }

    if verb == "say":
        if "|" not in rest:
            return True, "Usage: `:pf npc say <Name>[,<Name>...] | <party line>`"
        names_raw, _, party_line = rest.partition("|")
        names = [n.strip() for n in names_raw.split(",") if n.strip()]
        if not names:
            return True, "Usage: `:pf npc say <Name>[,<Name>...] | <party line>`"

        history: list = []
        if channel is not None and isinstance(channel, discord.Thread):
            try:
                bot_user_id = bot_user.id if bot_user is not None else 0
                history = await extract_thread_history(
                    thread=channel,
                    current_npc_names=set(names),
                    bot_user_id=bot_user_id,
                    limit=50,
                )
            except Exception:
                history = []

        payload = {
            "names": names,
            "party_line": party_line.strip(),
            "user_id": user_id,
            "history": history,
        }
        result = await sentinel_client.post_to_module(
            "modules/pathfinder/npc/say", payload, http_client
        )
        return True, render_say_response(result)

    return True, (
        f"Unknown npc command `{verb}`. "
        "Available: `create`, `update`, `show`, `relate`, `import`, `export`, `token`, `token-image`, `stat`, `pdf`, `say`."
    )
