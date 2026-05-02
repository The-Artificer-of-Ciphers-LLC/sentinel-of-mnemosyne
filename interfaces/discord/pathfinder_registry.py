"""Registry builders for Pathfinder dispatch adapters/builders."""

from __future__ import annotations


def adapter_registry(
    *,
    harvest,
    ingest,
    rule,
    session,
    npc_basic,
    npc_rich,
) -> dict:
    return {
        "harvest": harvest,
        "ingest": ingest,
        "rule": rule,
        "session": session,
        "npc_basic": npc_basic,
        "npc_rich": npc_rich,
    }


def builder_registry(
    *,
    build_harvest_embed,
    build_ruling_embed,
    recap_view_cls,
    build_session_embed,
    build_stat_embed,
    render_say_response,
    extract_thread_history,
) -> dict:
    return {
        "build_harvest_embed": build_harvest_embed,
        "build_ruling_embed": build_ruling_embed,
        "recap_view_cls": recap_view_cls,
        "build_session_embed": build_session_embed,
        "build_stat_embed": build_stat_embed,
        "render_say_response": render_say_response,
        "extract_thread_history": extract_thread_history,
    }
