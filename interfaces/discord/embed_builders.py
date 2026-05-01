"""Discord embed builder helpers."""

from __future__ import annotations

import discord


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
