"""Discord embed builder helpers."""

from __future__ import annotations

import discord


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
