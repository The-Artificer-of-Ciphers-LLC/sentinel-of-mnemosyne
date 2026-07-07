"""Tests for ``app.services.note_schema`` (Phase 45, Plan 02).

Covers the trailing ```_schema fenced-block parser/splitter (D-01, Task 1)
and the structural claim-title + wikilink + per-note compliance helpers
(D-05, Task 2). This module is a pure content parser with no I/O of its
own and must never raise on malformed input.
"""
from __future__ import annotations

import ast
import inspect

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


# --- Task 2: has_claim_title / has_wikilink / check_note_compliance ---


def test_has_claim_title_accepts_real_multiword_claim():
    body = "# Retrieval Beats Generation For Hub Matching\n\nProse.\n"
    assert note_schema.has_claim_title(body, "some-other-slug") is True


def test_has_claim_title_accepts_multiword_title_matching_its_slug():
    # A multi-word H1 that slugifies to its own filename is the NORMAL
    # case in this system (filenames are derived from titles), not a
    # degenerate echo -- it must pass.
    body = "# concept hub\n\nProse.\n"
    assert note_schema.has_claim_title(body, "concept_hub") is True


def test_has_claim_title_accepts_short_punctuation_free_claim():
    # Exact pipeline false-negative case: a short multi-word claim whose
    # H1 slugifies to precisely its own filename slug.
    body = "# Mitochondria Produce Cellular Energy\n\nbody\n"
    assert (
        note_schema.has_claim_title(body, "mitochondria-produce-cellular-energy")
        is True
    )


def test_has_claim_title_rejects_single_word_title():
    body = "# Hub\n\nProse.\n"
    assert note_schema.has_claim_title(body, "some-other-slug") is False


def test_has_claim_title_rejects_missing_h1():
    body = "Just prose, no heading at all.\n"
    assert note_schema.has_claim_title(body, "some-slug") is False


def test_has_wikilink_true_when_target_present():
    body = "Prose referencing [[Concept Hub]] inline.\n"
    assert note_schema.has_wikilink(body) is True


def test_has_wikilink_false_when_absent():
    body = "Prose with no wikilinks at all.\n"
    assert note_schema.has_wikilink(body) is False


def test_check_note_compliance_all_pass():
    body = (
        "# Retrieval Beats Generation For Hub Matching\n\n"
        "See [[Concept Hub]] for background.\n\n"
        "```_schema\n"
        "type: note\n"
        "```\n"
    )
    result = note_schema.check_note_compliance(body, "some-other-slug")
    assert result["has_schema"] is True
    assert result["has_type"] is True
    assert result["has_claim_title"] is True
    assert result["has_wikilink"] is True
    assert result["failures"] == []


def test_check_note_compliance_reports_all_failures_deterministically():
    body = "# some-slug\n\nNo wikilinks, no schema block.\n"
    result = note_schema.check_note_compliance(body, "some-slug")
    assert result["has_schema"] is False
    assert result["has_claim_title"] is False
    assert result["has_wikilink"] is False
    assert "missing _schema block" in result["failures"]
    assert "missing claim-style title" in result["failures"]
    assert "missing wikilink" in result["failures"]


def test_check_note_compliance_never_raises_on_malformed_input():
    # None body, no filename slug -- must degrade to a FAIL entry rather
    # than raise (T-45-DOS1).
    result = note_schema.check_note_compliance(None, None)  # type: ignore[arg-type]
    assert isinstance(result, dict)
    assert result["has_schema"] is False
    assert result["failures"]


def test_note_schema_module_has_no_llm_or_network_imports():
    """Determinism gate for SC-4 / D-05 / T-45-DET.

    note_schema.py must make zero network/LLM/embedding calls -- enforced
    by asserting no forbidden top-level symbol is imported anywhere in
    the module source.
    """
    source = inspect.getsource(note_schema)
    tree = ast.parse(source)
    imported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_names.add(node.module.split(".")[0])

    forbidden = {"httpx", "openai", "litellm", "aiohttp", "requests"}
    assert not (imported_names & forbidden), (
        f"note_schema.py must not import LLM/network symbols; "
        f"found {imported_names & forbidden}"
    )
