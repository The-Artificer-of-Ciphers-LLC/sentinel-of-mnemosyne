"""Behavioral tests for scripts/anomaly_rate.py.

Exercises ``scan()`` (the importable core) directly against ``FakeVault`` —
no shelling out, no network. ``emit()`` is exercised separately via capsys
to confirm the ``--json`` path reports the same numbers as the human table.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.anomaly_rate import emit, scan  # noqa: E402

from tests.fakes.vault import FakeVault  # noqa: E402


def _note(*, user_id: str = "trekkie", prompt: str = "Hello", response: str = "Hi there!") -> str:
    return (
        f"---\nuser_id: {user_id}\n---\n\n"
        f"## User\n{prompt}\n\n"
        f"## Sentinel\n{response}\n"
    )


def _populate(vault: FakeVault, path: str, body: str) -> None:
    """Register ``path`` under both dirs (so scan()'s list_under walk finds
    it) and notes (so read_note returns its body)."""
    date_dir, filename = path.rsplit("/", 1)
    day = date_dir.rsplit("/", 1)[-1]
    root = date_dir.rsplit("/", 1)[0]

    vault.dirs.setdefault(root, [])
    if f"{day}/" not in vault.dirs[root]:
        vault.dirs[root].append(f"{day}/")

    vault.dirs.setdefault(date_dir, [])
    if filename not in vault.dirs[date_dir]:
        vault.dirs[date_dir].append(filename)

    vault.notes[path] = body


class _RaisingReadVault(FakeVault):
    """FakeVault whose read_note() raises for one targeted path — proves
    scan() never crashes on an unreadable summary."""

    def __init__(self, *args, raise_for: str, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._raise_for = raise_for

    async def read_note(self, path: str) -> str:
        if path == self._raise_for:
            raise OSError("simulated unreadable file")
        return await super().read_note(path)


# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_mixed_clean_and_degenerate_computes_rate():
    vault = FakeVault()
    _populate(vault, "ops/sessions/2026-08-20/trekkie-10-00-00.md", _note(response="A clean, ordinary reply."))
    _populate(vault, "ops/sessions/2026-08-20/trekkie-11-00-00.md", _note(response="la la la"))
    _populate(vault, "ops/sessions/2026-08-21/trekkie-09-00-00.md", _note(response="Another clean reply."))
    _populate(
        vault,
        "ops/sessions/2026-08-21/trekkie-10-00-00.md",
        _note(response="Sure, done.<end_of_turn><start_of_turn>model"),
    )

    result = await scan(vault)

    assert result["total"] == 4
    assert result["flagged"] == 2
    assert result["percentage"] == 50.0
    assert result["signal_counts"].get("consecutive_repetition") == 1
    assert result["signal_counts"].get("control_tokens") == 1
    assert result["skipped"] == 0
    assert result["excluded"] == 0
    assert len(result["flagged_files"]) == 2


@pytest.mark.asyncio
async def test_since_until_restrict_which_day_folders_are_scanned():
    vault = FakeVault()
    _populate(vault, "ops/sessions/2026-08-18/trekkie-10-00-00.md", _note())
    _populate(vault, "ops/sessions/2026-08-20/trekkie-10-00-00.md", _note())
    _populate(vault, "ops/sessions/2026-08-22/trekkie-10-00-00.md", _note())
    _populate(vault, "ops/sessions/2026-08-25/trekkie-10-00-00.md", _note())

    result = await scan(vault, since="2026-08-19", until="2026-08-22")

    assert result["total"] == 2


@pytest.mark.asyncio
async def test_user_restricts_by_id_prefix():
    vault = FakeVault()
    _populate(vault, "ops/sessions/2026-08-20/trekkie-10-00-00.md", _note(user_id="trekkie"))
    _populate(vault, "ops/sessions/2026-08-20/ratetest-11-00-00.md", _note(user_id="ratetest"))
    _populate(vault, "ops/sessions/2026-08-20/ratetest-12-00-00.md", _note(user_id="ratetest"))

    result = await scan(vault, user="ratetest")

    assert result["total"] == 2


@pytest.mark.asyncio
async def test_missing_content_is_skipped_and_counted_not_crashed():
    vault = FakeVault()
    # Register the file in dirs (so scan() discovers it) but never populate
    # its body — read_note() falls back to "" (production's 404 semantics).
    vault.dirs["ops/sessions"] = ["2026-08-20/"]
    vault.dirs["ops/sessions/2026-08-20"] = ["trekkie-10-00-00.md"]

    result = await scan(vault)

    assert result["total"] == 0
    assert result["skipped"] == 1
    assert result["flagged_files"] == []


@pytest.mark.asyncio
async def test_unreadable_summary_exception_is_skipped_not_raised():
    path = "ops/sessions/2026-08-20/trekkie-10-00-00.md"
    vault = _RaisingReadVault(raise_for=path)
    _populate(vault, path, _note())

    result = await scan(vault)  # must not raise

    assert result["skipped"] == 1
    assert result["total"] == 0


@pytest.mark.asyncio
async def test_summary_without_sentinel_section_excluded_from_denominator():
    vault = FakeVault()
    body_no_section = "---\nuser_id: trekkie\n---\n\n## User\nHello\n"
    body_empty_section = "---\nuser_id: trekkie\n---\n\n## User\nHi\n\n## Sentinel\n   \n"
    _populate(vault, "ops/sessions/2026-08-20/trekkie-10-00-00.md", body_no_section)
    _populate(vault, "ops/sessions/2026-08-20/trekkie-11-00-00.md", body_empty_section)
    _populate(vault, "ops/sessions/2026-08-20/trekkie-12-00-00.md", _note())

    result = await scan(vault)

    assert result["total"] == 1
    assert result["excluded"] == 2
    assert result["skipped"] == 0


@pytest.mark.asyncio
async def test_json_emission_matches_human_output_numbers(capsys):
    vault = FakeVault()
    _populate(vault, "ops/sessions/2026-08-20/trekkie-10-00-00.md", _note(response="la la la"))
    _populate(vault, "ops/sessions/2026-08-20/trekkie-11-00-00.md", _note(response="A clean reply."))
    result = await scan(vault)

    emit(result, as_json=True)
    json_out = capsys.readouterr().out
    parsed = json.loads(json_out)
    assert parsed == result

    emit(result, as_json=False, since="2026-08-01")
    human_out = capsys.readouterr().out
    assert str(result["flagged"]) in human_out
    assert f"{result['percentage']}%" in human_out
    assert "since=2026-08-01" in human_out
