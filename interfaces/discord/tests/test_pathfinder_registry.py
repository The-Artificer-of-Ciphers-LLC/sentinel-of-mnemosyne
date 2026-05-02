import pathfinder_registry


def test_adapter_registry_contains_expected_keys():
    reg = pathfinder_registry.adapter_registry(
        harvest=1, ingest=2, rule=3, session=4, npc_basic=5, npc_rich=6
    )
    assert set(reg.keys()) == {"harvest", "ingest", "rule", "session", "npc_basic", "npc_rich"}


def test_builder_registry_contains_expected_keys():
    reg = pathfinder_registry.builder_registry(
        build_harvest_embed=1,
        build_ruling_embed=2,
        recap_view_cls=3,
        build_session_embed=4,
        build_stat_embed=5,
        render_say_response=6,
        extract_thread_history=7,
    )
    assert set(reg.keys()) == {
        "build_harvest_embed",
        "build_ruling_embed",
        "recap_view_cls",
        "build_session_embed",
        "build_stat_embed",
        "render_say_response",
        "extract_thread_history",
    }
