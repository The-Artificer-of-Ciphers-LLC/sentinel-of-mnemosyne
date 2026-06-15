from pathlib import Path

import pathfinder_cli
from pathfinder_command_catalog import COMMAND_CATALOG, PF_NOUNS


def test_parse_pf_args_unknown_noun_returns_error():
    parsed, err = pathfinder_cli.parse_pf_args("monster show x")
    assert parsed is None
    assert "Unknown" in err


def test_parse_pf_args_valid_tuple():
    parsed, err = pathfinder_cli.parse_pf_args("npc show Varek")
    assert err is None
    assert parsed[0] == "npc"
    assert parsed[1] == "show"


def test_pf_nouns_come_from_catalog():
    assert pathfinder_cli.PF_NOUNS == PF_NOUNS
    assert pathfinder_cli.PF_NOUNS == frozenset(COMMAND_CATALOG)


def test_usage_message_mentions_each_catalog_noun():
    usage = pathfinder_cli.usage_message()
    for noun in COMMAND_CATALOG:
        assert f":pf {noun}" in usage


def test_unknown_noun_lists_catalog_nouns():
    message = pathfinder_cli.unknown_noun_message("monster")
    for noun in COMMAND_CATALOG:
        assert f"`{noun}`" in message


def test_rule_docs_describe_free_text_query():
    repo_root = Path(__file__).resolve().parents[3]
    reference = (repo_root / "docs/reference/discord-commands.md").read_text()
    troubleshoot = (repo_root / "docs/how-to/troubleshoot-discord.md").read_text()

    assert ":pf rule Does Sneak Attack work on grabbed targets?" in reference
    assert "Bare-noun lookup is not supported" not in troubleshoot
