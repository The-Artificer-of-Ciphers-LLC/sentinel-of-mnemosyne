"""Tests for app.services.vault_inventory (vault contents meta-question support)."""
from __future__ import annotations

from tests.fakes.vault import FakeVault

from app.services.links_sidecar_index import LINKS_INDEX_PATH, encode_index_body
from app.services.message_processing import MessageRequest
from app.services.recall import Recall, RecallConfig
from app.services.vault_inventory import (
    format_inventory,
    is_inventory_query,
    load_inventory,
)


# ---------------------------------------------------------------------------
# is_inventory_query
# ---------------------------------------------------------------------------


def test_inventory_query_true_cases():
    true_cases = [
        "what is in my second brain",
        "what's in it",
        "what is in it",
        "what do you have on me",
        "summary of the topics",
        "what topics",
        "list the topics",
        "what subjects",
        "what do you know about me",
        "what have you got",
        "what's in my vault",
        "contents of my vault",
        "table of contents",
        "overview of my notes",
        "what notes do you have",
    ]
    for text in true_cases:
        assert is_inventory_query(text), f"expected True for {text!r}"
        # Case-insensitivity + whitespace normalisation
        assert is_inventory_query(text.upper()), f"expected True (upper) for {text!r}"
        assert is_inventory_query("  " + "  ".join(text.split()) + "  "), (
            f"expected True (extra whitespace) for {text!r}"
        )


def test_inventory_query_false_cases():
    false_cases = [
        "what do you know about creative resets?",
        "what is a memory palace?",
        "what's in the music module?",
        "hello",
        "",
        "tell me about my goals",
        "summarise this note for me",
        "what should I work on next based on my current goals?",
    ]
    for text in false_cases:
        assert not is_inventory_query(text), f"expected False for {text!r}"


def test_real_observed_inventory_queries_all_match():
    # Captured verbatim from the production inbox queue and live Discord
    # transcript on 2026-08-29. These are the real questions this feature
    # exists to answer -- do not replace with imagined phrasings.
    real_queries = [
        "what is in my second brain?",
        "that's not what I wanted though, I wanted to know what is in it, and a summary of the topics",
        "show me a summary of my notes",
        "give me a summary of my second brain status",
        "give me a summary of the topics in my vault",
    ]
    for text in real_queries:
        assert is_inventory_query(text), f"expected True for {text!r}"


# ---------------------------------------------------------------------------
# format_inventory
# ---------------------------------------------------------------------------


def test_format_inventory_empty_index():
    assert format_inventory({}) == ""


def test_format_inventory_groups_hub_first():
    index = {
        "notes/creative-resets.md": {"schema": {"type": "permanent"}},
        "notes/second-brain-hub.md": {"schema": {"type": "hub"}},
        "notes/memory-palace.md": {"schema": {"type": "fleeting"}},
    }
    rendered = format_inventory(index)
    assert "Vault inventory: 3 notes." in rendered
    hub_pos = rendered.index("hub (")
    permanent_pos = rendered.index("permanent (")
    fleeting_pos = rendered.index("fleeting (")
    assert hub_pos < permanent_pos
    assert hub_pos < fleeting_pos
    assert "Second brain hub" in rendered
    assert "Creative resets" in rendered
    assert "Memory palace" in rendered


def test_format_inventory_untyped_entries():
    index = {
        "notes/no-schema.md": {},
        "notes/empty-schema.md": {"schema": {}},
        "notes/missing-schema-key.md": {"wikilinks": []},
    }
    rendered = format_inventory(index)
    assert "untyped (3):" in rendered
    assert "No schema" in rendered


def test_format_inventory_truncates_to_max_notes():
    index = {
        f"notes/note-{i}.md": {"schema": {"type": "permanent"}} for i in range(10)
    }
    rendered = format_inventory(index, max_notes=4)
    assert "Vault inventory: 10 notes." in rendered
    assert "... and 6 more" in rendered
    # Exactly 4 note lines rendered
    note_lines = [line for line in rendered.splitlines() if line.startswith("- ")]
    assert len(note_lines) == 4


# ---------------------------------------------------------------------------
# load_inventory
# ---------------------------------------------------------------------------


async def test_load_inventory_reads_and_formats_index():
    index = {
        "notes/hub-a.md": {"schema": {"type": "hub"}},
        "notes/permanent-b.md": {"schema": {"type": "permanent"}},
    }
    vault = FakeVault(notes={LINKS_INDEX_PATH: encode_index_body(index)})
    rendered = await load_inventory(vault)
    assert "Vault inventory: 2 notes." in rendered
    assert "Hub a" in rendered
    assert "Permanent b" in rendered


async def test_load_inventory_empty_vault_returns_blank():
    vault = FakeVault(notes={})
    assert await load_inventory(vault) == ""


async def test_load_inventory_fails_soft_on_read_error():
    class _RaisingVault(FakeVault):
        async def read_note(self, path: str) -> str:
            raise RuntimeError("simulated transport failure")

    vault = _RaisingVault(notes={})
    assert await load_inventory(vault) == ""


async def test_load_inventory_fails_soft_on_malformed_json():
    vault = FakeVault(notes={LINKS_INDEX_PATH: "{not valid json"})
    assert await load_inventory(vault) == ""


async def test_load_inventory_fails_soft_on_non_dict_json():
    vault = FakeVault(notes={LINKS_INDEX_PATH: "[1, 2, 3]"})
    assert await load_inventory(vault) == ""


# ---------------------------------------------------------------------------
# Recall.assemble wiring
# ---------------------------------------------------------------------------


def _make_request(content: str) -> MessageRequest:
    return MessageRequest(
        content=content,
        user_id="trekkie",
        model_name="test-model",
        context_window=8192,
        stop_sequences=None,
    )


async def test_recall_assemble_populates_inventory_for_inventory_query():
    index = {"notes/hub-a.md": {"schema": {"type": "hub"}}}
    vault = FakeVault(notes={LINKS_INDEX_PATH: encode_index_body(index)})
    recall = Recall(vault=vault, config=RecallConfig())
    result = await recall.assemble(_make_request("what is in my second brain"), budget=8192)
    assert result.inventory != ""
    assert "Hub a" in result.inventory


async def test_recall_assemble_leaves_inventory_blank_for_ordinary_query():
    index = {"notes/hub-a.md": {"schema": {"type": "hub"}}}
    vault = FakeVault(notes={LINKS_INDEX_PATH: encode_index_body(index)})
    recall = Recall(vault=vault, config=RecallConfig())
    result = await recall.assemble(_make_request("what do you know about creative resets?"), budget=8192)
    assert result.inventory == ""
