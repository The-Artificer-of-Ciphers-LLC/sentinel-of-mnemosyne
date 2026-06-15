"""Tests for the read-only Pathfinder rule cache catalog."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("OBSIDIAN_BASE_URL", "http://localhost:27123")
os.environ.setdefault("OBSIDIAN_API_KEY", "")
os.environ.setdefault("LITELLM_MODEL", "openai/local-model")
os.environ.setdefault("LITELLM_API_BASE", "http://localhost:1234/v1")


def _ruling_note(
    *,
    question: str,
    topic: str,
    last_reused_at: str,
    composed_at: str = "2026-04-20T12:00:00Z",
    marker: str = "source",
) -> str:
    return (
        "---\n"
        f"question: {question!r}\n"
        "answer: Cached answer.\n"
        "why: Cached reason.\n"
        "source: Pathfinder Player Core\n"
        "citations: []\n"
        f"marker: {marker}\n"
        f"topic: {topic}\n"
        f"composed_at: {composed_at!r}\n"
        f"last_reused_at: {last_reused_at!r}\n"
        "---\n\n"
        "Cached answer.\n"
    )


class _FakeVault:
    def __init__(self, notes: dict[str, str], *, fail_list: bool = False) -> None:
        self._notes = dict(notes)
        self._fail_list = fail_list
        self.get_note = AsyncMock(side_effect=self._get_note)
        self.list_directory = AsyncMock(side_effect=self._list_directory)

    async def _get_note(self, path: str) -> str | None:
        return self._notes.get(path)

    async def _list_directory(self, prefix: str) -> list[str]:
        if self._fail_list:
            raise RuntimeError("list failed")
        return sorted(path for path in self._notes if path.startswith(prefix))


async def test_show_topic_sorts_rulings_by_last_reused_at_and_skips_malformed():
    from app.rule_cache_catalog import RuleCacheCatalog

    vault = _FakeVault(
        {
            "mnemosyne/pf2e/rulings/flanking/old.md": _ruling_note(
                question="Old flanking?",
                topic="flanking",
                last_reused_at="2026-04-20T12:00:00Z",
            ),
            "mnemosyne/pf2e/rulings/flanking/new.md": _ruling_note(
                question="New flanking?",
                topic="flanking",
                last_reused_at="2026-04-21T12:00:00Z",
            ),
            "mnemosyne/pf2e/rulings/flanking/malformed.md": "not frontmatter",
            "mnemosyne/pf2e/rulings/flanking/readme.txt": "ignore",
        }
    )

    result = await RuleCacheCatalog(vault).show_topic("flanking")

    assert result["topic"] == "flanking"
    assert result["count"] == 2
    assert [entry["hash"] for entry in result["rulings"]] == ["new", "old"]
    assert [entry["question"] for entry in result["rulings"]] == [
        "New flanking?",
        "Old flanking?",
    ]
    vault.list_directory.assert_awaited_once_with("mnemosyne/pf2e/rulings/flanking/")


async def test_history_derives_topic_from_path_and_limits_results():
    from app.rule_cache_catalog import RuleCacheCatalog

    vault = _FakeVault(
        {
            "mnemosyne/pf2e/rulings/flanking/a.md": _ruling_note(
                question="Flanking?",
                topic="flanking",
                last_reused_at="2026-04-20T12:00:00Z",
            ),
            "mnemosyne/pf2e/rulings/stealth/b.md": _ruling_note(
                question="Hide?",
                topic="stealth",
                last_reused_at="2026-04-22T12:00:00Z",
            ),
        }
    )

    result = await RuleCacheCatalog(vault).history(1)

    assert result["n"] == 1
    assert len(result["rulings"]) == 1
    assert result["rulings"][0]["hash"] == "b"
    assert result["rulings"][0]["topic"] == "stealth"


async def test_topics_counts_and_sorts_by_last_activity():
    from app.rule_cache_catalog import RuleCacheCatalog

    vault = _FakeVault(
        {
            "mnemosyne/pf2e/rulings/flanking/a.md": _ruling_note(
                question="Flanking old?",
                topic="flanking",
                last_reused_at="2026-04-20T12:00:00Z",
            ),
            "mnemosyne/pf2e/rulings/flanking/b.md": _ruling_note(
                question="Flanking new?",
                topic="flanking",
                last_reused_at="2026-04-23T12:00:00Z",
            ),
            "mnemosyne/pf2e/rulings/stealth/c.md": _ruling_note(
                question="Hide?",
                topic="stealth",
                last_reused_at="2026-04-22T12:00:00Z",
            ),
        }
    )

    result = await RuleCacheCatalog(vault).topics()

    assert result["topics"] == [
        {
            "slug": "flanking",
            "count": 2,
            "last_activity": "2026-04-23T12:00:00Z",
        },
        {
            "slug": "stealth",
            "count": 1,
            "last_activity": "2026-04-22T12:00:00Z",
        },
    ]


async def test_list_failure_degrades_to_empty_catalog():
    from app.rule_cache_catalog import RuleCacheCatalog

    vault = _FakeVault({}, fail_list=True)

    assert await RuleCacheCatalog(vault).history(10) == {"n": 10, "rulings": []}
