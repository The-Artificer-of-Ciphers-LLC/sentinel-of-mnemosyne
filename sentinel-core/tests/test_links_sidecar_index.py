"""Tests for the links sidecar index module (NOTE-03, D-04/D-04a)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.errors import SweepInProgressError
from app.services.links_sidecar_index import (
    LINKS_INDEX_PATH,
    build_links_index,
    decode_index_body,
    encode_index_body,
    rebuild_links_index,
    rebuild_links_index_if_stale,
)
from tests.fakes.vault import FakeVault


def _vault_with_notes(notes: dict[str, str]) -> FakeVault:
    """Build a FakeVault pre-populated with notes/ dir listing + bodies.

    Mirrors the flat-notes/ invariant (Pattern 3): every note lives directly
    under notes/, so a single ``dirs["notes"]`` entry is sufficient (no
    subdirectory BFS needed).
    """
    vault = FakeVault(notes=dict(notes))
    filenames = [path.rsplit("/", 1)[-1] for path in notes if path.startswith("notes/")]
    vault.dirs[""] = ["notes/"]
    vault.dirs["notes"] = filenames
    return vault


# --- decode_index_body (self-heal) ---


def test_decode_index_body_valid_json_returns_dict():
    idx = {"notes/a.md": {"content_hash": "h1", "wikilinks": [], "schema": None}}
    raw = json.dumps(idx)
    assert decode_index_body(raw) == idx


def test_decode_index_body_corrupt_content_self_heals_to_empty_dict():
    assert decode_index_body("{not valid json") == {}


def test_decode_index_body_non_dict_json_returns_empty_dict():
    assert decode_index_body("[1, 2, 3]") == {}


def test_decode_index_body_empty_string_self_heals():
    assert decode_index_body("") == {}


def test_encode_decode_round_trip():
    idx = {
        "notes/a.md": {
            "content_hash": "abc123",
            "wikilinks": ["notes/b.md"],
            "schema": {"type": "hub"},
        }
    }
    assert decode_index_body(encode_index_body(idx)) == idx


def test_links_index_path_constant():
    assert LINKS_INDEX_PATH == "ops/graph/links-index.json"


# --- build_links_index ---


@pytest.mark.asyncio
async def test_build_links_index_indexes_notes_with_wikilinks_and_schema():
    body_a = "# Note A\n\nSee [[Note B]].\n"
    body_b = (
        "# Note B\n\n"
        "```_schema\n"
        "type: reference\n"
        "```\n"
    )
    vault = _vault_with_notes({"notes/a.md": body_a, "notes/b.md": body_b})

    index = await build_links_index(vault, existing={})

    assert set(index.keys()) == {"notes/a.md", "notes/b.md"}
    assert index["notes/a.md"]["wikilinks"] == ["Note B"]
    assert index["notes/a.md"]["schema"] is None
    assert index["notes/b.md"]["schema"] == {"type": "reference"}


@pytest.mark.asyncio
async def test_build_links_index_excludes_own_path():
    vault = _vault_with_notes({"notes/a.md": "# A\n"})
    # Defensively seed the sidecar's own path even though the notes-scoped
    # walk cannot reach ops/graph/ — proves the explicit guard, not just the
    # walk scoping.
    vault.notes[LINKS_INDEX_PATH] = "{}"

    index = await build_links_index(vault, existing={})

    assert LINKS_INDEX_PATH not in index
    assert "notes/a.md" in index


@pytest.mark.asyncio
async def test_build_links_index_carries_forward_unchanged_note_by_hash():
    body_a = "# Note A\n\nUnchanged body.\n"
    vault = _vault_with_notes({"notes/a.md": body_a})

    existing = await build_links_index(vault, existing={})
    # Second build with the SAME body — the entry object must be carried
    # forward (same reference), not recomputed.
    rebuilt = await build_links_index(vault, existing=existing)

    assert rebuilt["notes/a.md"] is existing["notes/a.md"]


@pytest.mark.asyncio
async def test_build_links_index_recomputes_changed_note():
    vault = _vault_with_notes({"notes/a.md": "# Note A\n\nOriginal.\n"})
    existing = await build_links_index(vault, existing={})

    vault.notes["notes/a.md"] = "# Note A\n\nChanged body with [[Note B]].\n"
    rebuilt = await build_links_index(vault, existing=existing)

    assert rebuilt["notes/a.md"] is not existing["notes/a.md"]
    assert rebuilt["notes/a.md"]["wikilinks"] == ["Note B"]


# --- rebuild_links_index (unconditional) ---


@pytest.mark.asyncio
async def test_rebuild_links_index_writes_and_returns_fresh_index():
    vault = _vault_with_notes({"notes/a.md": "# Note A\n\n[[Note B]]\n"})

    result = await rebuild_links_index(vault)

    assert "notes/a.md" in result
    persisted = decode_index_body(vault.notes[LINKS_INDEX_PATH])
    assert persisted == result


@pytest.mark.asyncio
async def test_rebuild_links_index_is_non_destructive():
    vault = _vault_with_notes(
        {"notes/a.md": "# Note A\n", "notes/b.md": "# Note B\n"}
    )
    before = set(vault.notes.keys())

    await rebuild_links_index(vault)

    after = set(vault.notes.keys())
    # Only the sidecar path (and the sweep lockfile, acquired/released around
    # the rebuild) may be added; no existing note is removed or altered.
    removed = before - after
    assert removed == set(), f"rebuild_links_index removed notes: {removed}"
    assert vault.notes["notes/a.md"] == "# Note A\n"
    assert vault.notes["notes/b.md"] == "# Note B\n"


# --- rebuild_links_index_if_stale (D-04a hybrid) ---


@pytest.mark.asyncio
async def test_rebuild_links_index_if_stale_returns_existing_when_path_set_unchanged():
    vault = _vault_with_notes({"notes/a.md": "# Note A\n"})
    existing = await build_links_index(vault, existing={})
    vault.notes[LINKS_INDEX_PATH] = encode_index_body(existing)

    result = await rebuild_links_index_if_stale(vault)

    assert result == existing


@pytest.mark.asyncio
async def test_rebuild_links_index_if_stale_rebuilds_on_added_path():
    vault = _vault_with_notes({"notes/a.md": "# Note A\n"})
    existing = await build_links_index(vault, existing={})
    vault.notes[LINKS_INDEX_PATH] = encode_index_body(existing)

    # Add a new note without updating the sidecar — path-set now diverges.
    vault.notes["notes/b.md"] = "# Note B\n"
    vault.dirs["notes"].append("b.md")

    result = await rebuild_links_index_if_stale(vault)

    assert "notes/b.md" in result


@pytest.mark.asyncio
async def test_rebuild_links_index_if_stale_rebuilds_on_removed_path():
    vault = _vault_with_notes(
        {"notes/a.md": "# Note A\n", "notes/b.md": "# Note B\n"}
    )
    existing = await build_links_index(vault, existing={})
    vault.notes[LINKS_INDEX_PATH] = encode_index_body(existing)

    # Remove a note without updating the sidecar.
    del vault.notes["notes/b.md"]
    vault.dirs["notes"].remove("b.md")

    result = await rebuild_links_index_if_stale(vault)

    assert "notes/b.md" not in result
    assert "notes/a.md" in result


@pytest.mark.asyncio
async def test_rebuild_links_index_if_stale_does_not_detect_body_edit_without_path_change():
    """Accepted approximation gap (RESEARCH Pitfall 5, characterized not fixed):
    a hand-edit to an existing note's wikilinks with NO path-set change is
    invisible to the cheap staleness check. This is the documented,
    intentional limitation of the D-04a hybrid freshness model.
    """
    vault = _vault_with_notes({"notes/a.md": "# Note A\n"})
    existing = await build_links_index(vault, existing={})
    vault.notes[LINKS_INDEX_PATH] = encode_index_body(existing)

    # Simulate an out-of-band Obsidian edit: body changes, path-set doesn't.
    vault.notes["notes/a.md"] = "# Note A\n\nNow links to [[Note B]].\n"

    result = await rebuild_links_index_if_stale(vault)

    # The cheap check returns the STALE existing entry unchanged — the new
    # wikilink is NOT reflected. This characterizes the known gap.
    assert result["notes/a.md"]["wikilinks"] == existing["notes/a.md"]["wikilinks"]
    assert result["notes/a.md"]["wikilinks"] == []


@pytest.mark.asyncio
async def test_rebuild_links_index_if_stale_degrades_to_existing_index_when_lock_held():
    vault = _vault_with_notes({"notes/a.md": "# Note A\n"})
    existing = await build_links_index(vault, existing={})
    vault.notes[LINKS_INDEX_PATH] = encode_index_body(existing)

    # Simulate a held sweep lock (fresh, not stale) — acquire_sweep_lock()
    # will return False, forcing rebuild_links_index to raise
    # SweepInProgressError. Uses the real current time (not a fixed past
    # date) so the internal acquire_sweep_lock() call inside
    # rebuild_links_index — which uses the real clock — sees the lock as
    # fresh (age well under the 1h stale-takeover threshold) regardless of
    # wall-clock time when this test runs.
    now = datetime.now(timezone.utc)
    assert await vault.acquire_sweep_lock(now=now) is True

    # Add a new note so the path-set diverges and a rebuild WOULD be
    # triggered, if not for the held lock.
    vault.notes["notes/b.md"] = "# Note B\n"
    vault.dirs["notes"].append("b.md")

    result = await rebuild_links_index_if_stale(vault)

    # Degrades to the existing (stale) index — never raises, never a
    # partial/corrupt result.
    assert result == existing
    assert "notes/b.md" not in result


@pytest.mark.asyncio
async def test_rebuild_links_index_propagates_sweep_in_progress_to_direct_caller():
    """A direct caller of rebuild_links_index (not via the _if_stale wrapper)
    gets the same SweepInProgressError signal a destructive sweep would —
    only rebuild_links_index_if_stale is responsible for catching it.
    """
    vault = _vault_with_notes({"notes/a.md": "# Note A\n"})
    now = datetime.now(timezone.utc)
    assert await vault.acquire_sweep_lock(now=now) is True

    with pytest.raises(SweepInProgressError):
        await rebuild_links_index(vault)
