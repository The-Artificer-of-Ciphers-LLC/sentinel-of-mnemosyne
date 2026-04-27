"""Tests for inbox helpers (260427-vl1 Task 4).

Pure-function tests: no Obsidian I/O. Verify parse/append/remove/render
against in-memory bodies with deterministic timestamps via injected `now`.
"""
from datetime import datetime, timezone


from app.services.inbox import (
    INBOX_PATH,
    PendingEntry,
    append_entry,
    build_initial_inbox,
    parse_inbox,
    remove_entry,
    render_for_discord,
)
from app.services.note_classifier import ClassificationResult


_FIXED_NOW = datetime(2026, 4, 27, 12, 34, 56, tzinfo=timezone.utc)


def test_parse_empty_returns_empty_list():
    assert parse_inbox("") == []
    assert parse_inbox("---\nfoo: bar\n---\n\n") == []


def test_parse_two_entries_round_trip():
    body = build_initial_inbox(now=_FIXED_NOW)
    body = append_entry(
        body,
        "Finished the sing-better course. Took 6 weeks.",
        ClassificationResult(
            topic="unsure", confidence=0.4, title_slug="x", reasoning="ambiguous"
        ),
        suggested=["learning"],
        now=_FIXED_NOW,
    )
    body = append_entry(
        body,
        "Feeling stuck on the bridge passage.",
        ClassificationResult(
            topic="unsure", confidence=0.3, title_slug="y", reasoning="reflective"
        ),
        suggested=["journal"],
        now=_FIXED_NOW,
    )
    entries = parse_inbox(body)
    assert len(entries) == 2
    assert entries[0].entry_n == 1
    assert entries[1].entry_n == 2
    assert "sing-better" in entries[0].candidate_text
    assert entries[0].suggested == ["learning"]
    assert entries[0].confidence == 0.4
    assert entries[0].topic == "unsure"
    assert entries[0].reasoning == "ambiguous"
    assert entries[0].timestamp.startswith("2026-04-27")


def test_append_creates_initial_when_body_empty():
    body = append_entry(
        "",
        "candidate text",
        ClassificationResult(topic="unsure", confidence=0.5, title_slug="x", reasoning="r"),
        suggested=["reference"],
        now=_FIXED_NOW,
    )
    assert "type: pending-classification-inbox" in body
    assert "updated:" in body
    assert "## Entry 1" in body
    assert "candidate text" in body


def test_remove_entry_renumbers():
    body = build_initial_inbox(now=_FIXED_NOW)
    for i, t in enumerate(("first", "second", "third"), start=1):
        body = append_entry(
            body,
            t,
            ClassificationResult(topic="unsure", confidence=0.4, title_slug="x", reasoning="r"),
            suggested=["reference"],
            now=_FIXED_NOW,
        )
    entries = parse_inbox(body)
    assert [e.entry_n for e in entries] == [1, 2, 3]

    body = remove_entry(body, 2, now=_FIXED_NOW)
    after = parse_inbox(body)
    assert [e.entry_n for e in after] == [1, 2]
    # what was previously entry 3 ("third") is now entry 2
    assert after[1].candidate_text == "third"
    assert after[0].candidate_text == "first"


def test_render_for_discord():
    entries = [
        PendingEntry(
            entry_n=1,
            timestamp="2026-04-27T11:00:00Z",
            topic="unsure",
            suggested=["reference"],
            confidence=0.4,
            reasoning="r",
            candidate_text="Finished the sing-better course. Took 6 weeks.",
        ),
        PendingEntry(
            entry_n=2,
            timestamp="2026-04-27T11:05:00Z",
            topic="unsure",
            suggested=["journal"],
            confidence=0.3,
            reasoning="r",
            candidate_text="x" * 200,
        ),
    ]
    rendered = render_for_discord(entries)
    assert rendered.startswith("1. Finished the sing-better course")
    assert "(suggested: reference)" in rendered
    # Second entry preview clipped to 80 chars
    second = rendered.splitlines()[1]
    assert len(second.split(" (suggested:")[0]) <= 84  # "2. " + ≤80
    assert "(suggested: journal)" in rendered


def test_render_empty_inbox():
    assert render_for_discord([]) == "(inbox is empty)"


def test_build_initial_inbox():
    body = build_initial_inbox(now=_FIXED_NOW)
    assert body.startswith("---\n")
    assert "type: pending-classification-inbox" in body
    assert "2026-04-27" in body  # yaml.safe_dump may quote ISO strings
    assert "# Pending Classification" in body


def test_inbox_path_constant():
    assert INBOX_PATH == "inbox/_pending-classification.md"
