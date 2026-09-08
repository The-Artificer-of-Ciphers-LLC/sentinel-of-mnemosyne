"""Behavioral regression tests for sentinel_shared.model_profiles Qwen3 aliases.

Covers the 2026-05-02 fix: LM Studio reports `arch: qwen3_5_moe` for
qwen3.6-35b-a3b; that key was missing from FAMILY_PROFILES, causing a
WARNING-level log on every primary lookup. Stop-token behavior was already
correct via the substring fallback to qwen2; this fix moves the resolution
to the primary path so the warning stops firing.
"""
from __future__ import annotations

import logging

import pytest

import dataclasses

from sentinel_shared.model_profiles import (
    FAMILY_PROFILES,
    SAFE_DEFAULT,
    FamilyProfile,
    _substring_match,
    get_profile,
)


def test_family_profiles_carry_no_context_window():
    """ADR-0007 step 5: a family constant must not be a second source of the window.

    The field this asserts absent declared 8192 for gemma2 while the live
    gemma-4 served 262144, and 32768 for qwen2 against a real 262144 max /
    119552 loaded. Context windows come from the backend, resolved by
    ``app.model.LMStudioModelSource``'s three-rung ladder; ADR decision 2 was
    amended 2026-09-07 to drop the family rung precisely so this field could
    go.

    Asserted as an ABSENCE on the dataclass rather than against any particular
    number — a test pinning a value would re-create the disagreement.
    """
    field_names = {f.name for f in dataclasses.fields(FamilyProfile)}
    assert "context_window" not in field_names, (
        "FamilyProfile grew a context-window field back. The backend is the "
        "only source of a context window (ADR-0007 decision 2 as amended)."
    )
    for key, profile in FAMILY_PROFILES.items():
        assert not hasattr(profile, "context_window"), f"{key} carries a context window"
    assert not hasattr(SAFE_DEFAULT, "context_window")


def test_qwen3_5_moe_arch_returns_qwen2_profile():
    """Primary arch lookup for qwen3_5_moe must return the qwen2 FamilyProfile.

    This is the exact arch string LM Studio emits for qwen3.6-35b-a3b — the
    one that was firing the FAMILY_PROFILES-miss warning before this fix.
    """
    qwen2_profile = FAMILY_PROFILES["qwen2"]
    assert FAMILY_PROFILES["qwen3_5_moe"] is qwen2_profile
    assert FAMILY_PROFILES["qwen3_5_moe"].stop_sequences == ["<|im_end|>", "<|endoftext|>"]
    # Sanity: all four Qwen3 aliases present
    for alias in ("qwen3", "qwen3_5", "qwen3_5_moe", "qwen3_moe"):
        assert FAMILY_PROFILES[alias] is qwen2_profile, f"{alias} not aliased to qwen2"


@pytest.mark.asyncio
async def test_qwen3_5_moe_arch_does_not_warn(caplog, monkeypatch):
    """get_profile with arch=qwen3_5_moe must not emit a FAMILY_PROFILES-miss warning.

    Mocks the LM Studio /api/v0/models/{model_id} response so the primary
    arch-lookup path is exercised; with the fix in place it succeeds and
    no warning is logged.
    """
    import httpx

    import sentinel_shared.model_profiles as mp

    # Bust the per-process cache so this call actually hits the arch-lookup path
    mp._profile_cache.clear()

    class _FakeResponse:
        def __init__(self, payload):
            self._payload = payload
        def raise_for_status(self):
            return None
        def json(self):
            return self._payload

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *exc):
            return False
        async def get(self, url):
            return _FakeResponse({"arch": "qwen3_5_moe"})

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="sentinel_shared.model_profiles"):
        profile = await get_profile(
            "qwen3.6-35b-a3b-test",
            api_base="http://fake-lmstudio:1234/v1",
            force_refresh=True,
        )

    assert profile is FAMILY_PROFILES["qwen2"]
    miss_warnings = [
        r for r in caplog.records
        if r.levelno >= logging.WARNING
        and "not in FAMILY_PROFILES" in r.getMessage()
    ]
    assert miss_warnings == [], (
        f"Expected no FAMILY_PROFILES-miss warnings, got: "
        f"{[r.getMessage() for r in miss_warnings]}"
    )


def test_qwen3_substring_pattern_matches_qwen3_only_models():
    """Substring fallback for a hypothetical qwen3-only model_id returns qwen2 profile.

    Future-proofs against a model_id that contains 'qwen3' but no other
    qwen marker — verifies the new ('qwen3', 'qwen2') substring pattern.
    """
    profile = _substring_match("qwen3-future-variant-13b")
    assert profile is FAMILY_PROFILES["qwen2"]
    assert profile.stop_sequences == ["<|im_end|>", "<|endoftext|>"]
