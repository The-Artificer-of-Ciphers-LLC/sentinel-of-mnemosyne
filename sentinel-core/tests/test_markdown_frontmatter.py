"""Behavioral tests for app.markdown_frontmatter."""
from __future__ import annotations

from app.markdown_frontmatter import join_frontmatter, split_frontmatter


def test_split_frontmatter_extracts_yaml():
    body = "---\nkey: value\nnum: 3\n---\n\nbody text"
    fm, rest = split_frontmatter(body)
    assert fm == {"key": "value", "num": 3}
    assert rest == "body text"


def test_split_frontmatter_no_frontmatter_returns_empty_dict_and_body():
    body = "no frontmatter here"
    fm, rest = split_frontmatter(body)
    assert fm == {}
    assert rest == body


def test_split_frontmatter_empty_or_none_body():
    fm, rest = split_frontmatter("")
    assert fm == {}
    assert rest == ""


def test_split_frontmatter_invalid_yaml_returns_empty_dict():
    body = "---\n: not: valid: yaml\n---\nbody"
    fm, rest = split_frontmatter(body)
    assert fm == {}


def test_join_frontmatter_always_emits_block():
    out = join_frontmatter({"a": 1}, "body")
    assert out.startswith("---\n")
    assert "a: 1" in out
    assert out.endswith("body")


def test_join_frontmatter_empty_dict_still_emits_block():
    # Canonical contract: always emit the block, even with empty fm.
    # (Differs from vault.py's old _join_frontmatter optimization.)
    out = join_frontmatter({}, "body")
    assert out.startswith("---\n")
    assert "body" in out


def test_round_trip_preserves_keys():
    original_fm = {"type": "note", "tags": ["a", "b"]}
    body = "the content"
    composed = join_frontmatter(original_fm, body)
    fm, rest = split_frontmatter(composed)
    assert fm == original_fm
    assert rest == body
