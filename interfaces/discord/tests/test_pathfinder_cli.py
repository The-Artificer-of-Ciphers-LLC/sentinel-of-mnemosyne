import pathfinder_cli


def test_parse_pf_args_unknown_noun_returns_error():
    parsed, err = pathfinder_cli.parse_pf_args("monster show x")
    assert parsed is None
    assert "Unknown" in err


def test_parse_pf_args_valid_tuple():
    parsed, err = pathfinder_cli.parse_pf_args("npc show Varek")
    assert err is None
    assert parsed[0] == "npc"
    assert parsed[1] == "show"
