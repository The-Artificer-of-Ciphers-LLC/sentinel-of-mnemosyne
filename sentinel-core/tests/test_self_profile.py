"""Tests for ``app.services.self_profile`` (GH issue #38, core onboarding).

Covers the pure ``is_unfilled`` primitive and the fail-soft ``profile_status``
aggregator, using the canonical ``FakeVault`` test double.
"""
from __future__ import annotations

from app.services.recall import _CANONICAL_SELF_STUB_PATHS, build_self_stub
from app.services.self_profile import (
    CANONICAL_PROFILE_PATHS,
    is_unfilled,
    profile_status,
)
from tests.fakes.vault import FakeVault


def test_canonical_profile_paths_reuses_recall_tuple():
    """CANONICAL_PROFILE_PATHS must be the SAME 4-path tuple recall.py owns —
    never a duplicated/independently-maintained list."""
    assert CANONICAL_PROFILE_PATHS == _CANONICAL_SELF_STUB_PATHS
    assert len(CANONICAL_PROFILE_PATHS) == 4


# --- is_unfilled ---


def test_is_unfilled_byte_equal_stub_is_true():
    path = "self/identity.md"
    assert is_unfilled(path, build_self_stub(path)) is True


def test_is_unfilled_empty_body_is_true():
    assert is_unfilled("self/identity.md", "") is True


def test_is_unfilled_whitespace_only_body_is_true():
    assert is_unfilled("self/identity.md", "   \n\n  ") is True


def test_is_unfilled_missing_body_none_like_is_true():
    # profile_status never passes None (FakeVault always returns str), but
    # is_unfilled itself must not raise on a falsy non-empty-string input.
    assert is_unfilled("self/identity.md", "") is True


def test_is_unfilled_user_edit_is_false():
    path = "self/identity.md"
    assert is_unfilled(path, "# Identity\n\nTom, staff engineer, likes Rust.\n") is False


def test_is_unfilled_stub_plus_trailing_user_line_is_false():
    path = "self/goals.md"
    edited = build_self_stub(path) + "Ship the onboarding flow by Friday.\n"
    assert is_unfilled(path, edited) is False


# --- profile_status ---


async def test_profile_status_all_stubs_incomplete():
    vault = FakeVault(
        notes={p: build_self_stub(p) for p in CANONICAL_PROFILE_PATHS}
    )
    status = await profile_status(vault)
    assert status.complete is False
    assert set(status.unfilled) == set(CANONICAL_PROFILE_PATHS)
    for path in CANONICAL_PROFILE_PATHS:
        assert status.paths[path] == "stub"


async def test_profile_status_all_filled_complete():
    vault = FakeVault(
        notes={
            p: f"# {p}\n\nReal user-authored content, not a stub.\n"
            for p in CANONICAL_PROFILE_PATHS
        }
    )
    status = await profile_status(vault)
    assert status.complete is True
    assert status.unfilled == []
    for path in CANONICAL_PROFILE_PATHS:
        assert status.paths[path] == "filled"


async def test_profile_status_missing_paths_reported_missing():
    vault = FakeVault()  # no notes pre-populated -> read_note returns ""
    status = await profile_status(vault)
    assert status.complete is False
    for path in CANONICAL_PROFILE_PATHS:
        assert status.paths[path] == "missing"


async def test_profile_status_read_error_for_one_path_does_not_raise():
    """A vault read error for ONE path must not raise, and must not stop the
    other paths from being evaluated."""

    class _FlakyVault(FakeVault):
        async def read_note(self, path: str) -> str:
            if path == "self/methodology.md":
                raise RuntimeError("simulated transport failure")
            return await super().read_note(path)

    vault = _FlakyVault(
        notes={
            p: f"# {p}\n\nReal user-authored content.\n"
            for p in CANONICAL_PROFILE_PATHS
            if p != "self/methodology.md"
        }
    )

    status = await profile_status(vault)  # must not raise

    assert status.paths["self/methodology.md"] == "unknown"
    assert "self/methodology.md" in status.unfilled
    assert status.complete is False
    # The other three paths were still evaluated normally.
    for path in CANONICAL_PROFILE_PATHS:
        if path != "self/methodology.md":
            assert status.paths[path] == "filled"
