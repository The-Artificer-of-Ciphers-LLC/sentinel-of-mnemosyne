"""Discord embed builder helpers."""

from __future__ import annotations

import discord


def build_foundry_roll_embed(data: dict) -> "discord.Embed":
    outcome_emojis = {
        "criticalSuccess": "🎯",
        "success": "✅",
        "failure": "❌",
        "criticalFailure": "💀",
    }
    outcome_labels = {
        "criticalSuccess": "Critical Hit!",
        "success": "Success",
        "failure": "Failure",
        "criticalFailure": "Critical Failure!",
    }
    outcome_colors = {
        "criticalSuccess": discord.Color.gold(),
        "success": discord.Color.green(),
        "failure": discord.Color.orange(),
        "criticalFailure": discord.Color.red(),
    }
    outcome = data.get("outcome", "")
    actor = data.get("actor_name", "?")
    target = data.get("target_name")
    narrative = data.get("narrative", "")
    roll_total = data.get("roll_total", "?")
    dc = data.get("dc")
    dc_hidden = data.get("dc_hidden", False)
    item_name = data.get("item_name", "")
    roll_type = data.get("roll_type", "check")

    emoji = outcome_emojis.get(outcome, "🎲")
    label = outcome_labels.get(outcome, outcome.capitalize() if outcome else "Roll")
    color = outcome_colors.get(outcome, discord.Color.blue())

    title = f"{emoji} {label} | {actor} vs {target}" if target else f"{emoji} {label} | {actor} ({roll_type})"
    dc_str = "DC: [hidden]" if dc_hidden else f"DC/AC: {dc}"
    footer_parts = [f"Roll: {roll_total}", dc_str]
    if item_name:
        footer_parts.append(item_name)

    embed = discord.Embed(
        title=title,
        description=narrative[:4000] if narrative else None,
        color=color,
    )
    embed.set_footer(text=" | ".join(footer_parts))
    return embed


def build_harvest_embed(data: dict) -> "discord.Embed":
    monsters = data.get("monsters", []) or []
    aggregated = data.get("aggregated", []) or []
    footer_text = data.get("footer", "")

    if len(monsters) == 1:
        m = monsters[0]
        title = f"{m.get('monster', '?')} (Level {m.get('level', '?')})"
        description_parts: list[str] = []
        if m.get("note"):
            description_parts.append(f"_{m['note']}_")
        if not m.get("verified", True):
            description_parts.append("⚠ Generated — verify against sourcebook")
        description = "\n".join(description_parts)
    else:
        title = f"Harvest report — {len(monsters)} monsters"
        generated_count = sum(1 for m in monsters if not m.get("verified", True))
        description = (
            f"⚠ {generated_count}/{len(monsters)} entries include generated data — verify."
            if generated_count
            else ""
        )

    embed = discord.Embed(title=title, description=description, color=discord.Color.dark_green())
    for comp in aggregated:
        craftable_lines = [
            f"• {c.get('name', '?')} (Crafting DC {c.get('crafting_dc', '?')}, {c.get('value', '?')})"
            for c in comp.get("craftable", []) or []
        ]
        monsters_tally = ", ".join(comp.get("monsters", []) or [])
        field_value = (
            f"Medicine DC {comp.get('medicine_dc', '?')}\n"
            f"From: {monsters_tally}\n"
            + "\n".join(craftable_lines)
        )[:1024]
        embed.add_field(name=comp.get("type", "?"), value=field_value, inline=False)
    embed.set_footer(text=footer_text)
    return embed


def build_session_embed(data: dict) -> "discord.Embed":
    verb_type = data.get("type", "")

    if verb_type == "start":
        embed = discord.Embed(
            title=f"Session started — {data.get('date', '?')}",
            description=f"Note: `{data.get('path', '?')}`",
            color=discord.Color.green(),
        )
        if data.get("recap_available") and not data.get("recap_text"):
            embed.set_footer(text="Use the button below to recap last session.")
    elif verb_type == "log":
        embed = discord.Embed(
            title="Event logged",
            description=f"`{data.get('line', '?')}`",
            color=discord.Color.blue(),
        )
    elif verb_type == "undo":
        removed = data.get("removed", "?")
        remaining = data.get("remaining", "?")
        embed = discord.Embed(
            title="Event removed",
            description=f"Removed: `{removed}`\nEvents remaining: {remaining}",
            color=discord.Color.orange(),
        )
    elif verb_type == "show":
        embed = discord.Embed(
            title=f"Story so far — {data.get('date', '?')}",
            description=data.get("narrative", "_No narrative generated._"),
            color=discord.Color.blue(),
        )
    elif verb_type == "end":
        recap = data.get("recap", "")
        npcs = ", ".join(f"[[{s}]]" for s in (data.get("npcs") or []))
        locations = ", ".join(f"[[{s}]]" for s in (data.get("locations") or []))
        embed = discord.Embed(
            title=f"Session ended — {data.get('date', '?')}",
            description=(recap[:2048] if recap else "_Recap empty._"),
            color=discord.Color.dark_green(),
        )
        if npcs:
            embed.add_field(name="NPCs", value=npcs[:1024], inline=False)
        if locations:
            embed.add_field(name="Locations", value=locations[:1024], inline=False)
    elif verb_type == "end_skeleton":
        embed = discord.Embed(
            title="Session ended (recap failed)",
            description=(
                f"Note written: `{data.get('path', '?')}`\n"
                f"Error: {str(data.get('error', '?'))[:200]}\n\n"
                "_Use `:pf session end --retry-recap` to regenerate the recap._"
            ),
            color=discord.Color.red(),
        )
    else:
        error_msg = data.get("error") or data.get("detail") or str(data)
        embed = discord.Embed(
            title="Session",
            description=str(error_msg)[:2048],
            color=discord.Color.red(),
        )

    return embed


def build_stat_embed(data: dict) -> "discord.Embed":
    fields = data.get("fields", {})
    stats = data.get("stats") or {}
    embed = discord.Embed(
        title=(
            f"{fields.get('name', '?')} "
            f"(Level {fields.get('level', '?')} "
            f"{fields.get('ancestry', '')} {fields.get('class', '')})"
        ),
        description=fields.get("personality", ""),
        color=discord.Color.dark_gold(),
    )
    if stats:
        embed.add_field(name="AC", value=str(stats.get("ac", "—")), inline=True)
        embed.add_field(name="HP", value=str(stats.get("hp", "—")), inline=True)
        embed.add_field(name="​", value="​", inline=True)
        embed.add_field(name="Fort", value=str(stats.get("fortitude", "—")), inline=True)
        embed.add_field(name="Ref", value=str(stats.get("reflex", "—")), inline=True)
        embed.add_field(name="Will", value=str(stats.get("will", "—")), inline=True)
        embed.add_field(name="Speed", value=f"{stats.get('speed', '—')} ft.", inline=False)
        skills = stats.get("skills") or {}
        if skills:
            if isinstance(skills, dict):
                skill_text = ", ".join(
                    f"{k.capitalize()} +{v}" for k, v in skills.items()
                )
            else:
                skill_text = str(skills)
            embed.add_field(
                name="Skills",
                value=skill_text[:900] + ("..." if len(skill_text) > 900 else ""),
                inline=False,
            )
        if stats.get("perception") is not None:
            embed.add_field(name="Perception", value=f"+{stats['perception']}", inline=True)
    embed.set_footer(text=f"Mood: {fields.get('mood', 'neutral')}")
    return embed


def build_ruling_embed(data: dict) -> "discord.Embed":
    marker = data.get("marker", "generated")
    question = data.get("question", "") or ""
    answer = data.get("answer", "") or ""
    why = data.get("why", "") or ""
    source_str = data.get("source")
    citations = data.get("citations", []) or []
    reused = bool(data.get("reused", False))
    reuse_note = data.get("reuse_note", "") or ""
    topic = data.get("topic") or "?"

    title = question[:250] if question else "Rules Ruling"

    description_parts: list[str] = []
    if reused and reuse_note:
        description_parts.append(f"_{reuse_note}_")
    if marker == "generated":
        description_parts.append("⚠ **[GENERATED — verify]**")
    elif marker == "declined":
        description_parts.append("🚫 PF1/pre-Remaster query declined")
    if answer:
        description_parts.append(answer)
    description = "\n\n".join(description_parts)[:4000]

    color = {
        "source": discord.Color.dark_green(),
        "generated": discord.Color.dark_gold(),
        "declined": discord.Color.red(),
    }.get(marker, discord.Color.dark_gold())

    embed = discord.Embed(title=title, description=description, color=color)
    if why:
        embed.add_field(name="Why", value=why[:1024], inline=False)
    if source_str:
        embed.add_field(name="Source", value=source_str[:1024], inline=False)
    if citations:
        cite_lines: list[str] = []
        for c in citations[:3]:
            line = f"• {c.get('book', '?')}"
            if c.get("page"):
                line += f" p. {c['page']}"
            line += f" — {c.get('section', '?')}"
            if c.get("url"):
                line += f" | {c['url']}"
            cite_lines.append(line)
        embed.add_field(name="Citations", value="\n".join(cite_lines)[:1024], inline=False)
    embed.set_footer(text=f"topic: {topic} | ORC license (Paizo) — Foundry pf2e")
    return embed
