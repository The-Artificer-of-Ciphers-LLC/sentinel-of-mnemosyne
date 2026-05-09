"""Discord command routing module."""

from __future__ import annotations

_HELP_KEYWORDS = frozenset({"commands", "help", "what can you do", "what do you do", "how do i use"})


async def route_message(
    *,
    user_id: str,
    message: str,
    attachments: list | None,
    channel,
    handle_subcommand,
    call_core,
    subcommand_help: str,
    author_display_name: str | None = None,
) -> "str | dict":
    if message.startswith(":"):
        parts = message[1:].split(" ", 1)
        subcmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        return await handle_subcommand(
            subcmd,
            args,
            user_id,
            attachments=attachments,
            channel=channel,
            author_display_name=author_display_name,
        )

    msg_lower = message.lower()
    if len(message) < 120 and any(kw in msg_lower for kw in _HELP_KEYWORDS):
        return subcommand_help

    return await call_core(user_id, message)


async def handle_subcommand(
    *,
    subcmd: str,
    args: str,
    user_id: str,
    attachments: list | None,
    channel,
    pf_dispatch,
    call_core,
    call_core_note,
    call_core_inbox_list,
    call_core_inbox_classify,
    call_core_inbox_discard,
    call_core_sweep_start,
    call_core_sweep_status,
    is_admin,
    note_closed_vocab,
    plugin_prompts: dict[str, str],
    subcommand_prompts: dict[str, str],
    subcommand_help: str,
    author_display_name: str | None = None,
) -> "str | dict":
    if subcmd == "pf":
        return await pf_dispatch(
            args,
            user_id,
            attachments=attachments,
            channel=channel,
            author_display_name=author_display_name,
        )

    if subcmd == "help":
        return subcommand_help

    if subcmd.startswith("plugin:"):
        plugin_name = subcmd[7:]
        if plugin_name == "ask":
            if not args.strip():
                return "Usage: `:plugin:ask <question>` — query the methodology knowledge base."
            return await call_core(user_id, f"Answer this question about my 2nd brain methodology: {args.strip()}")
        if plugin_name == "add-domain":
            if not args.strip():
                return "Usage: `:plugin:add-domain <domain>` — extend vault with a new domain area."
            return await call_core(user_id, f"Extend my vault with a new domain area: {args.strip()}")
        fixed_prompt = plugin_prompts.get(plugin_name)
        if fixed_prompt:
            return await call_core(user_id, fixed_prompt)
        return f"Unknown plugin command `:{subcmd}`. Try `:plugin:help`."

    if subcmd == "capture":
        if not args.strip():
            return "Usage: `:capture <text>` — provide something to capture."
        return await call_core(user_id, f"Capture this insight to my inbox/ for processing: {args.strip()}")

    if subcmd == "seed":
        if not args.strip():
            return "Usage: `:seed <text>` — drop raw content into inbox/."
        return await call_core(user_id, f"Add this raw content to my inbox/ without processing: {args.strip()}")

    if subcmd == "connect":
        if not args.strip():
            return "Usage: `:connect <note title>` — find connections for a note."
        return await call_core(
            user_id,
            f"Find connections for the note '{args.strip()}' and add a wikilink to the appropriate hub MOC.",
        )

    if subcmd == "review":
        if not args.strip():
            return "Usage: `:review <note title>` — verify note quality."
        return await call_core(
            user_id,
            f"Review note quality for '{args.strip()}': check claim title, YAML frontmatter (description, type, topics, status), and wikilinks. Be precise and literal. Do not elaborate beyond the requested format.",
        )

    if subcmd == "graph":
        query = args.strip() or "all"
        prompt = f"Run graph analysis on my vault{': ' + query if query != 'all' else ''}. Report orphans, triangles, link density, and backlinks."
        return await call_core(user_id, prompt)

    if subcmd == "learn":
        if not args.strip():
            return "Usage: `:learn <topic>` — research a topic."
        return await call_core(user_id, f"Research the topic '{args.strip()}' and grow my knowledge graph with new permanent notes.")

    if subcmd == "remember":
        if not args.strip():
            return "Usage: `:remember <observation>` — capture a methodology learning."
        return await call_core(user_id, f"Capture this operational observation to ops/observations/: {args.strip()}")

    if subcmd == "note":
        if not args.strip():
            return "Usage: `:note <content>` or `:note <topic> <content>`"
        topic, _, rest = args.strip().partition(" ")
        if topic in note_closed_vocab and rest.strip():
            return await call_core_note(user_id, content=rest.strip(), topic=topic)
        return await call_core_note(user_id, content=args.strip(), topic=None)

    if subcmd == "vault-sweep":
        if not is_admin(user_id):
            return "Admin only. Set SENTINEL_ADMIN_USER_IDS in your env to use this command."
        verb = (args.strip().split(maxsplit=1) or [""])[0]
        if verb == "status":
            return await call_core_sweep_status(user_id)
        if verb == "dry-run":
            return await call_core_sweep_start(user_id, force_reclassify=False, dry_run=True)
        force = verb == "force"
        return await call_core_sweep_start(user_id, force_reclassify=force)

    if subcmd == "inbox":
        parts = args.strip().split(maxsplit=2)
        if not args.strip():
            return await call_core_inbox_list(user_id)
        verb = parts[0]
        if verb == "classify" and len(parts) >= 3:
            try:
                entry_n = int(parts[1])
            except ValueError:
                return "Usage: `:inbox classify <n> <topic>` — n must be an integer."
            return await call_core_inbox_classify(user_id, entry_n, parts[2])
        if verb == "discard" and len(parts) >= 2:
            try:
                entry_n = int(parts[1])
            except ValueError:
                return "Usage: `:inbox discard <n>` — n must be an integer."
            return await call_core_inbox_discard(user_id, entry_n)
        return "Usage: `:inbox` | `:inbox classify <n> <topic>` | `:inbox discard <n>`"

    if subcmd == "revisit":
        if not args.strip():
            return "Usage: `:revisit <note title>` — revisit and update a note."
        return await call_core(user_id, f"Revisit and update the note '{args.strip()}' with current understanding.")

    fixed_prompt = subcommand_prompts.get(subcmd)
    if fixed_prompt:
        return await call_core(user_id, fixed_prompt)

    return f"Unknown command `:{subcmd}`. Try `:help` for available commands."
