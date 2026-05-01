"""Pathfinder noun/verb dispatcher for Discord :pf commands."""

from __future__ import annotations


async def dispatch(
    *,
    noun: str,
    verb: str,
    rest: str,
    parts: list[str],
    user_id: str,
    attachments: list | None,
    channel,
    bot_user,
    sentinel_client,
    http_client,
    is_admin,
    valid_relations,
    adapters,
    builders,
) -> "str | dict":
    if noun == "harvest":
        return await adapters["harvest"].handle_harvest(
            parts=parts,
            user_id=user_id,
            sentinel_client=sentinel_client,
            http_client=http_client,
            build_harvest_embed=builders["build_harvest_embed"],
        )

    if noun in ("cartosia", "ingest"):
        return await adapters["ingest"].handle_ingest(
            noun=noun,
            parts=parts,
            user_id=user_id,
            is_admin=is_admin,
            sentinel_client=sentinel_client,
            http_client=http_client,
        )

    if noun == "rule":
        return await adapters["rule"].handle_rule(
            verb=verb,
            rest=rest,
            parts=parts,
            user_id=user_id,
            channel=channel,
            sentinel_client=sentinel_client,
            http_client=http_client,
            build_ruling_embed=builders["build_ruling_embed"],
        )

    if noun == "session":
        return await adapters["session"].handle_session(
            verb=verb,
            rest=rest,
            user_id=user_id,
            channel=channel,
            sentinel_client=sentinel_client,
            http_client=http_client,
            recap_view_cls=builders["recap_view_cls"],
            build_session_embed=builders["build_session_embed"],
        )

    handled, npc_basic_response = await adapters["npc_basic"].handle_npc_basic(
        verb=verb,
        rest=rest,
        user_id=user_id,
        sentinel_client=sentinel_client,
        http_client=http_client,
        valid_relations=valid_relations,
    )
    if handled:
        return npc_basic_response

    handled, npc_rich_response = await adapters["npc_rich"].handle_npc_rich(
        verb=verb,
        rest=rest,
        user_id=user_id,
        attachments=attachments,
        channel=channel,
        bot_user=bot_user,
        sentinel_client=sentinel_client,
        http_client=http_client,
        build_stat_embed=builders["build_stat_embed"],
        render_say_response=builders["render_say_response"],
        extract_thread_history=builders["extract_thread_history"],
    )
    if handled:
        return npc_rich_response

    return f"Unknown pf category `{noun}`."
