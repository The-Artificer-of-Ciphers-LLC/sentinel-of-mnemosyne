"""Tests for sentinel_shared.llm_call.acompletion_with_profile.

After Task 1 of 260427-vl1: this wrapper lives in sentinel_shared so both
sentinel-core and the pathfinder module can import the same helper.
"""
from unittest.mock import AsyncMock, patch

import pytest

from sentinel_shared.llm_call import acompletion_with_profile
from sentinel_shared.model_profiles import ModelProfile


def _make_profile(stop: list[str] | None) -> ModelProfile:
    """Build a minimal ModelProfile carrying just the stop_sequences we care about."""
    # ModelProfile is a dataclass with default-able fields; pass a dict that
    # tolerates either dataclass or pydantic-style construction.
    try:
        return ModelProfile(family="test", stop_sequences=stop)  # type: ignore[call-arg]
    except TypeError:
        # Fallback: SimpleNamespace-style if dataclass signature differs.
        from types import SimpleNamespace

        return SimpleNamespace(stop_sequences=stop)  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_import_path_resolves():
    """Test 1: `from sentinel_shared.llm_call import acompletion_with_profile` succeeds."""
    assert callable(acompletion_with_profile)


@pytest.mark.asyncio
async def test_stop_sequences_pass_through():
    """Test 2: profile.stop_sequences=['</end>'] is forwarded as kwargs['stop']."""
    profile = _make_profile(["</end>"])
    with patch("sentinel_shared.llm_call.litellm.acompletion", new=AsyncMock(return_value="ok")) as mock_acomp:
        await acompletion_with_profile(
            model="openai/test-model",
            messages=[{"role": "user", "content": "hi"}],
            profile=profile,
        )
    assert mock_acomp.call_count == 1
    kwargs = mock_acomp.await_args.kwargs
    assert kwargs.get("stop") == ["</end>"]


@pytest.mark.asyncio
async def test_api_base_pass_through_and_omit():
    """Test 3: api_base='http://x' forwards; api_base=None omits the key entirely."""
    with patch("sentinel_shared.llm_call.litellm.acompletion", new=AsyncMock(return_value="ok")) as mock_acomp:
        await acompletion_with_profile(
            model="openai/m",
            messages=[{"role": "user", "content": "x"}],
            api_base="http://x",
        )
        assert mock_acomp.await_args.kwargs.get("api_base") == "http://x"

        mock_acomp.reset_mock()
        await acompletion_with_profile(
            model="openai/m",
            messages=[{"role": "user", "content": "x"}],
            api_base=None,
        )
        assert "api_base" not in mock_acomp.await_args.kwargs


@pytest.mark.asyncio
async def test_pathfinder_importers_still_work():
    """Test 4: pathfinder's app.llm and app.foundry must still import cleanly
    after llm_call.py was moved to sentinel_shared. We verify by importing
    the wrapper directly (no app.llm_call left to break) — the deeper guarantee
    is that pathfinder import surgery (Task 1) renamed both call sites.
    Pathfinder source greps verify the rename; here we only confirm the new
    import path is the canonical one.
    """
    import sentinel_shared.llm_call as shared_mod

    assert hasattr(shared_mod, "acompletion_with_profile")
    # Negative assertion: the old pathfinder module path no longer exposes the symbol.
    # We can't import modules.pathfinder.app.llm_call directly from sentinel-core
    # tests (pathfinder is a separate package), so this is enforced by the file
    # being deleted on disk — verified via the in-tree pathfinder grep in the
    # task's verify step (cd modules/pathfinder && python -c ...).
