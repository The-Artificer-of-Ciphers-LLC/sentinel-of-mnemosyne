"""Behavioral smoke test for :pf player dispatch wiring (Phase 37-13 Task 2).

Asserts that the PF_NOUNS frozenset and the COMMANDS registry are jointly
wired so that ``:pf player <verb>`` reaches a concrete PathfinderCommand
subclass for every supported verb. Calls the real module loaders and
inspects observable registration state — NOT a source-grep, NOT
``assert True``, NOT a ``mock.assert_called_with`` echo.

Centralised conftest stubs only — no per-file Discord stubs (Phase 33-01
collection-order race protection).
"""

from __future__ import annotations


PLAYER_VERBS = (
    "start",
    "note",
    "ask",
    "npc",
    "recall",
    "todo",
    "style",
    "canonize",
)


def test_pf_nouns_includes_player():
    from pathfinder_cli import PF_NOUNS

    assert "player" in PF_NOUNS


def test_commands_registry_has_player_section():
    from pathfinder_dispatch import COMMANDS

    assert "player" in COMMANDS
    assert isinstance(COMMANDS["player"], dict)


def test_every_player_verb_is_registered_with_callable_handle():
    from pathfinder_dispatch import COMMANDS

    for verb in PLAYER_VERBS:
        assert verb in COMMANDS["player"], f"missing :pf player {verb} registration"
        cmd = COMMANDS["player"][verb]
        assert callable(getattr(cmd, "handle", None)), (
            f":pf player {verb} handler is not callable"
        )


def test_each_verb_maps_to_expected_command_class():
    from pathfinder_dispatch import COMMANDS
    from pathfinder_player_adapter import (
        PlayerAskCommand,
        PlayerCanonizeCommand,
        PlayerNoteCommand,
        PlayerNpcCommand,
        PlayerRecallCommand,
        PlayerStartCommand,
        PlayerStyleCommand,
        PlayerTodoCommand,
    )

    expected: dict[str, type] = {
        "start": PlayerStartCommand,
        "note": PlayerNoteCommand,
        "ask": PlayerAskCommand,
        "npc": PlayerNpcCommand,
        "recall": PlayerRecallCommand,
        "todo": PlayerTodoCommand,
        "style": PlayerStyleCommand,
        "canonize": PlayerCanonizeCommand,
    }
    for verb, cls in expected.items():
        cmd = COMMANDS["player"][verb]
        assert isinstance(cmd, cls), (
            f":pf player {verb} is registered as {type(cmd).__name__}, expected {cls.__name__}"
        )
