"""Tests for ``app.services.note_schema`` (Phase 45, Plan 02).

Covers the trailing ```_schema fenced-block parser/splitter (D-01, Task 1).
This module is a pure content parser with no I/O of its own and must
never raise on malformed input.
"""
from __future__ import annotations

from app.services import note_schema


# --- Task 1: parse_schema_block / split_schema_block ---


def test_parse_schema_block_returns_dict_for_wellformed_block():
    body = (
        "# Some Note\n\n"
        "Body prose here.\n\n"
        "```_schema\n"
        "type: hub\n"
        "hub: concept-hub\n"
        "```\n"
    )
    parsed = note_schema.parse_schema_block(body)
    assert parsed == {"type": "hub", "hub": "concept-hub"}


def test_parse_schema_block_returns_none_when_absent():
    body = "# Some Note\n\nJust prose, no trailing block at all.\n"
    assert note_schema.parse_schema_block(body) is None


def test_parse_schema_block_returns_none_for_malformed_yaml():
    body = (
        "# Some Note\n\n"
        "```_schema\n"
        "type: [unclosed\n"
        "```\n"
    )
    assert note_schema.parse_schema_block(body) is None


def test_parse_schema_block_returns_none_for_non_dict_yaml():
    body = (
        "# Some Note\n\n"
        "```_schema\n"
        "- just\n"
        "- a\n"
        "- list\n"
        "```\n"
    )
    assert note_schema.parse_schema_block(body) is None


def test_parse_schema_block_returns_none_for_missing_closing_fence():
    body = (
        "# Some Note\n\n"
        "```_schema\n"
        "type: hub\n"
    )
    assert note_schema.parse_schema_block(body) is None


def test_parse_schema_block_only_terminal_block_wins():
    """A stray earlier same-tag fenced block must never win (Pattern 1)."""
    body = (
        "# Some Note\n\n"
        "Here is an example of the format:\n\n"
        "```_schema\n"
        "type: draft\n"
        "```\n\n"
        "More prose after the stray example.\n\n"
        "```_schema\n"
        "type: hub\n"
        "hub: concept-hub\n"
        "```\n"
    )
    parsed = note_schema.parse_schema_block(body)
    assert parsed == {"type": "hub", "hub": "concept-hub"}


def test_parse_schema_block_tolerates_trailing_whitespace():
    body = (
        "# Some Note\n\n"
        "```_schema\n"
        "type: hub\n"
        "```\n\n\n"
    )
    assert note_schema.parse_schema_block(body) == {"type": "hub"}


def test_split_schema_block_returns_original_and_none_when_absent():
    body = "# Some Note\n\nJust prose, no trailing block.\n"
    pre, raw = note_schema.split_schema_block(body)
    assert pre == body
    assert raw is None


def test_split_schema_block_roundtrips_wellformed_block():
    body = (
        "# Some Note\n\n"
        "Body prose here.\n\n"
        "```_schema\n"
        "type: hub\n"
        "```\n"
    )
    pre, raw = note_schema.split_schema_block(body)
    assert raw is not None
    # Round-trips modulo trailing whitespace (RESEARCH Pattern 1 contract).
    assert (pre + raw) == body.rstrip()
    assert pre == "# Some Note\n\nBody prose here.\n\n"
    assert raw == "```_schema\ntype: hub\n```"


def test_split_schema_block_preserves_pre_block_content_with_stray_earlier_block():
    body = (
        "# Some Note\n\n"
        "```_schema\n"
        "type: draft\n"
        "```\n\n"
        "More prose.\n\n"
        "```_schema\n"
        "type: hub\n"
        "```\n"
    )
    pre, raw = note_schema.split_schema_block(body)
    assert raw == "```_schema\ntype: hub\n```"
    assert pre == (
        "# Some Note\n\n"
        "```_schema\n"
        "type: draft\n"
        "```\n\n"
        "More prose.\n\n"
    )
    assert (pre + raw) == body.rstrip()
