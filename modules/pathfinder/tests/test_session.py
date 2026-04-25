"""Tests for session.py pure logic (SES-01..03, D-12..D-17, D-21..D-26).

Wave 0 RED stubs — symbols referenced below land in:
  - app.session (Wave 1 / Plan 34-02)
  - app.routes.session + main.py lifespan (Wave 2-3 / Plans 34-03..34-04)

Imports are function-scope inside each test so pytest collection succeeds
before the implementation lands (pattern from Phase 33 Wave 0 / test_rules.py).
"""
import os

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("SENTINEL_CORE_URL", "http://sentinel-core:8000")
os.environ.setdefault("OBSIDIAN_BASE_URL", "http://localhost:27123")
os.environ.setdefault("OBSIDIAN_API_KEY", "")
os.environ.setdefault("LITELLM_MODEL", "openai/local-model")
os.environ.setdefault("LITELLM_API_BASE", "http://localhost:1234/v1")


import pytest


# ---------------------------------------------------------------------------
# D-14: format_event_line
# ---------------------------------------------------------------------------


def test_format_event_line_typed():
    """D-14: typed event includes [type] bracket, starts with '- ', contains text."""
    from app.session import format_event_line

    result = format_event_line("Party fought 3 goblins", "combat", "America/New_York")
    assert result.startswith("- ")
    assert "[combat]" in result
    assert "Party fought 3 goblins" in result


def test_format_event_line_untyped():
    """D-12: untyped 'note' event omits brackets but keeps text."""
    from app.session import format_event_line

    result = format_event_line("Party regrouped at the inn", "note", "America/New_York")
    assert result.startswith("- ")
    assert "[note]" not in result
    assert "Party regrouped at the inn" in result


def test_format_event_line_all_known_types():
    """D-12: all non-note known types produce [type] bracket; 'note' does not."""
    from app.session import format_event_line

    typed_types = {"combat", "dialogue", "decision", "discovery", "loot"}
    for event_type in typed_types:
        result = format_event_line("text", event_type, "UTC")
        assert f"[{event_type}]" in result, f"Expected [{event_type}] in: {result!r}"

    # 'note' is the untyped fallthrough — no bracket
    result_note = format_event_line("text", "note", "UTC")
    assert "[note]" not in result_note


def test_format_event_line_unknown_type_fallthrough():
    """D-12: unknown type falls through as 'note' — no bracket prefix."""
    from app.session import format_event_line

    result = format_event_line("text", "unknown-xyz", "UTC")
    assert "[unknown-xyz]" not in result
    assert result.startswith("- ")
    assert "text" in result


# ---------------------------------------------------------------------------
# D-15: truncate_event_text (500-char cap, newline rejection)
# ---------------------------------------------------------------------------


def test_truncate_event_text_exactly_500():
    """D-15: exactly 500 chars passes through unchanged."""
    from app.session import truncate_event_text

    text = "x" * 500
    assert truncate_event_text(text) == text


def test_truncate_event_text_501_raises():
    """D-15: 501 chars raises ValueError (hard cap)."""
    from app.session import truncate_event_text

    with pytest.raises(ValueError):
        truncate_event_text("x" * 501)


def test_truncate_event_text_newline_raises():
    """D-15: newline in event text raises ValueError (multi-line rejection)."""
    from app.session import truncate_event_text

    with pytest.raises(ValueError):
        truncate_event_text("line1\nline2")


# ---------------------------------------------------------------------------
# D-12: validate_event_type
# ---------------------------------------------------------------------------


def test_validate_event_type_known_passes():
    """D-12: known type returns itself."""
    from app.session import validate_event_type

    assert validate_event_type("combat") == "combat"


def test_validate_event_type_unknown_returns_note():
    """D-12: unknown type falls through to 'note'."""
    from app.session import validate_event_type

    assert validate_event_type("flurb") == "note"


def test_validate_event_type_empty_returns_note():
    """D-12: empty string falls through to 'note'."""
    from app.session import validate_event_type

    assert validate_event_type("") == "note"


# ---------------------------------------------------------------------------
# D-34 / D-35: session_note_markdown template
# ---------------------------------------------------------------------------


def test_session_note_template_open():
    """D-34/D-35: open session note contains required frontmatter fields and sections in order."""
    from app.session import session_note_markdown

    result = session_note_markdown(
        date="2026-04-25",
        started_at="2026-04-25T19:00:00+00:00",
    )
    # Frontmatter (D-34)
    assert "schema_version: 1" in result
    assert "status: open" in result
    # Section order (D-35): Recap → Story So Far → NPCs Encountered → Locations → Events Log
    recap_pos = result.index("## Recap")
    story_pos = result.index("## Story So Far")
    npcs_pos = result.index("## NPCs Encountered")
    locations_pos = result.index("## Locations")
    events_pos = result.index("## Events Log")
    assert recap_pos < story_pos < npcs_pos < locations_pos < events_pos


def test_session_note_template_has_no_double_schema_version():
    """D-34: schema_version appears exactly once in frontmatter (no duplication)."""
    from app.session import session_note_markdown

    result = session_note_markdown(
        date="2026-04-25",
        started_at="2026-04-25T19:00:00+00:00",
    )
    assert result.count("schema_version") == 1


# ---------------------------------------------------------------------------
# D-21: NPC fast-pass linking
# ---------------------------------------------------------------------------


def test_npc_fast_pass_exact_match():
    """D-21: known NPC names get rewritten to [[slug]] wikilinks."""
    from app.session import apply_npc_links, build_npc_link_pattern

    slug_map = {"varek": "varek", "baron aldric": "baron-aldric"}
    pattern = build_npc_link_pattern(["varek", "baron aldric"])
    result = apply_npc_links("Varek met Baron Aldric today", pattern, slug_map)
    assert result == "[[varek]] met [[baron-aldric]] today"


def test_npc_fast_pass_word_boundary():
    """D-21 anti-pattern: partial word match must NOT trigger (word-boundary guard)."""
    from app.session import apply_npc_links, build_npc_link_pattern

    pattern = build_npc_link_pattern(["varek"])
    slug_map = {"varek": "varek"}
    # "Vare kwent" — 'varek' is not present as a whole word
    result = apply_npc_links("Vare kwent to the market", pattern, slug_map)
    assert result == "Vare kwent to the market"


def test_npc_link_pattern_empty_list_returns_none():
    """D-21: empty NPC roster returns None pattern (no-op linking)."""
    from app.session import build_npc_link_pattern

    assert build_npc_link_pattern([]) is None


# ---------------------------------------------------------------------------
# D-24: slugify_location
# ---------------------------------------------------------------------------


def test_slugify_location_normalizes():
    """D-24: location names normalized to [a-z0-9-] slug format."""
    from app.session import slugify_location

    assert slugify_location("Westcrown") == "westcrown"
    assert slugify_location("The Sandpoint Cathedral") == "the-sandpoint-cathedral"
    assert slugify_location("Thornwood!!") == "thornwood"


# ---------------------------------------------------------------------------
# D-26: detect_npc_slug_collision
# ---------------------------------------------------------------------------


def test_detect_npc_slug_collision_true():
    """D-26: collision detected when location slug equals an NPC slug."""
    from app.session import detect_npc_slug_collision

    assert detect_npc_slug_collision("varek", {"varek", "baron-aldric"}) is True


def test_detect_npc_slug_collision_false():
    """D-26: no collision when location slug differs from all NPC slugs."""
    from app.session import detect_npc_slug_collision

    assert detect_npc_slug_collision("westcrown", {"varek", "baron-aldric"}) is False


# ---------------------------------------------------------------------------
# D-25: build_location_stub_markdown
# ---------------------------------------------------------------------------


def test_build_location_stub_markdown():
    """D-25: location stub contains required frontmatter + placeholder body."""
    from app.session import build_location_stub_markdown

    result = build_location_stub_markdown("Westcrown", "westcrown", "2026-04-25")
    assert "name: Westcrown" in result
    assert "slug: westcrown" in result
    assert "first_seen: 2026-04-25" in result
    assert "schema_version: 1" in result
    assert "# Westcrown" in result
    assert "Auto-created" in result


# ---------------------------------------------------------------------------
# D-04 / RESEARCH §Flag Parsing: parse_session_verb_args
# ---------------------------------------------------------------------------


def test_parse_session_verb_args_force():
    """Flag parsing: --force flag extracted; event text is empty after stripping."""
    from app.session import parse_session_verb_args

    result = parse_session_verb_args("--force", "start")
    assert result.get("force") is True
    assert result.get("args", "") == ""


def test_parse_session_verb_args_log_preserves_text():
    """Flag parsing: log verb — text preserved with no flags stripped."""
    from app.session import parse_session_verb_args

    result = parse_session_verb_args("Party arrived", "log")
    assert result.get("force") is False
    assert result.get("recap") is False
    assert result.get("retry_recap") is False
    assert result.get("args") == "Party arrived"


def test_parse_session_verb_args_retry_recap():
    """Flag parsing: --retry-recap flag extracted for end verb."""
    from app.session import parse_session_verb_args

    result = parse_session_verb_args("--retry-recap", "end")
    assert result.get("retry_recap") is True
