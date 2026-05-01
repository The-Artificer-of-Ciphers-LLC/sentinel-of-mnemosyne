"""Pathfinder NPC basic verb adapter for Discord :pf commands."""

from __future__ import annotations


async def handle_npc_basic(
    *,
    verb: str,
    rest: str,
    user_id: str,
    sentinel_client,
    http_client,
    valid_relations: frozenset[str],
) -> tuple[bool, str]:
    if verb == "create":
        name, _, description = rest.partition("|")
        if not name.strip():
            return True, "Usage: `:pf npc create <name> | <description>`"
        payload = {
            "name": name.strip(),
            "description": description.strip(),
            "user_id": user_id,
        }
        result = await sentinel_client.post_to_module(
            "modules/pathfinder/npc/create", payload, http_client
        )
        return True, (
            f"NPC **{result.get('name', name.strip())}** created.\n"
            f"Path: `{result.get('path', '?')}`\n"
            f"Ancestry: {result.get('ancestry', '?')} | Class: {result.get('class', '?')} | Level: {result.get('level', '?')}"
        )

    if verb == "update":
        name, _, correction = rest.partition("|")
        if not name.strip() or not correction.strip():
            return True, "Usage: `:pf npc update <name> | <correction>`"
        payload = {
            "name": name.strip(),
            "correction": correction.strip(),
            "user_id": user_id,
        }
        result = await sentinel_client.post_to_module(
            "modules/pathfinder/npc/update", payload, http_client
        )
        return True, f"NPC **{name.strip()}** updated. Fields changed: {', '.join(result.get('changed_fields', []))}"

    if verb == "show":
        npc_name = rest.strip()
        if not npc_name:
            return True, "Usage: `:pf npc show <name>`"
        result = await sentinel_client.post_to_module(
            "modules/pathfinder/npc/show", {"name": npc_name, "user_id": user_id}, http_client
        )
        lines = [
            f"**{result.get('name', npc_name)}** "
            f"(Level {result.get('level', '?')} {result.get('ancestry', '?')} {result.get('class', '?')})",
            f"*{result.get('personality', '')}*",
            result.get('backstory', '')[:200],
        ]
        stats = result.get("stats") or {}
        if stats:
            lines.append(
                f"AC {stats.get('ac', '—')} | HP {stats.get('hp', '—')} | "
                f"Fort {stats.get('fortitude', '—')} Ref {stats.get('reflex', '—')} Will {stats.get('will', '—')}"
            )
        rels = result.get("relationships") or []
        if rels:
            rel_text = ", ".join(f"{r.get('target')} ({r.get('relation')})" for r in rels)
            lines.append(f"Relationships: {rel_text}")
        lines.append(f"*Mood: {result.get('mood', 'neutral')} | {result.get('path', '')}*")
        return True, "\n".join(lines)

    if verb == "relate":
        relate_parts = [p.strip() for p in rest.split("|")]
        if len(relate_parts) < 3 or not all(relate_parts[:3]):
            return True, (
                "Usage: `:pf npc relate <npc-name> | <relation> | <target-npc-name>`\n"
                f"Valid relations: {', '.join(sorted(valid_relations))}"
            )
        npc_name, relation, target = relate_parts[0], relate_parts[1], relate_parts[2]
        if relation not in valid_relations:
            return True, (
                f"`{relation}` is not a valid relation type.\n"
                f"Valid options: {', '.join(sorted(valid_relations))}"
            )
        await sentinel_client.post_to_module(
            "modules/pathfinder/npc/relate",
            {"name": npc_name, "relation": relation, "target": target},
            http_client,
        )
        return True, f"Relationship added: **{npc_name}** {relation} **{target}**."

    return False, ""
