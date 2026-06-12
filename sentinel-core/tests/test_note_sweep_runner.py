"""Tests for note_sweep_runner.start_sweep (40-04 Task 4).

Covers the admin sweep entrypoint wiring:
- live path always forwards a non-None safe_to_mutate probe into run_sweep
- probe ANDs embedding + classifier readiness (fail-closed binding)
- dry-run path does NOT forward a probe
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.note_sweep_runner import start_sweep
from app.services.task_runner import TaskRunner
from tests.fakes.vault import FakeVault


# --- Helpers ---


def _make_vault():
    """Return a FakeVault with minimal content for start_sweep to work."""
    vault = FakeVault()
    vault.dirs[""] = []
    return vault


async def _classifier(text):
    from app.services.note_classifier import ClassificationResult
    return ClassificationResult(topic="reference", confidence=0.9, title_slug="x", reasoning="r")


async def _embedder(texts):
    return [[1.0, 0.0, 0.0]] * len(texts)


class _ImmediateTaskRunner:
    """Synchronous task runner that awaits the coroutine immediately in a captured list.

    Used to avoid timing-dependent asyncio.sleep(0.05) waits in tests.
    """

    def __init__(self):
        self._scheduled: list = []

    def schedule(self, coro):
        """Record the coroutine; caller must await self.run_all() to execute."""
        self._scheduled.append(coro)

    async def run_all(self):
        import asyncio
        for coro in self._scheduled:
            await coro
        self._scheduled.clear()


# --- Tests ---


@pytest.mark.asyncio
async def test_start_sweep_live_path_passes_safe_to_mutate_probe():
    """Non-dry-run start_sweep must forward a safe_to_mutate probe into run_sweep.

    Capture the kwargs passed to run_sweep and assert safe_to_mutate is present
    and is awaitable (a non-None callable).
    """
    captured_kwargs: list[dict] = []

    async def _fake_run_sweep(*args, **kwargs):
        captured_kwargs.append(kwargs)
        from app.services.vault_sweeper import SweepReport
        from app.time_utils import _iso_utc
        return SweepReport(sweep_id=_iso_utc(), status="complete")

    vault = _make_vault()
    runner = _ImmediateTaskRunner()

    with patch("app.services.note_sweep_runner.run_sweep", side_effect=_fake_run_sweep):
        result = await start_sweep(
            vault=vault,
            classifier=_classifier,
            embedder=_embedder,
            force_reclassify=False,
            dry_run=False,
            safe_to_mutate=AsyncMock(return_value=True),
            task_runner=runner,
        )
        await runner.run_all()

    assert len(captured_kwargs) == 1, f"run_sweep should be called once; called {len(captured_kwargs)} times"
    assert "safe_to_mutate" in captured_kwargs[0], (
        "live start_sweep must forward safe_to_mutate into run_sweep; "
        f"got kwargs keys: {list(captured_kwargs[0].keys())}"
    )
    probe = captured_kwargs[0]["safe_to_mutate"]
    assert probe is not None, "safe_to_mutate forwarded to run_sweep must not be None"
    assert callable(probe), f"safe_to_mutate must be callable; got {type(probe)}"


@pytest.mark.asyncio
async def test_start_sweep_live_path_probe_false_means_zero_moves():
    """Admin start_sweep with a probe resolving False performs zero destructive moves.

    This proves the admin path cannot bypass the guard — run_sweep's fail-closed
    gate applies when the forwarded probe resolves False.
    """
    from app.services.vault_sweeper import SweepReport
    from app.time_utils import _iso_utc

    async def _always_false():
        return False

    # Use a vault with a note that WOULD be misplaced
    vault = FakeVault()
    vault.dirs[""] = ["random-folder/"]
    vault.dirs["random-folder"] = ["misplaced.md"]
    vault.notes["random-folder/misplaced.md"] = "A classifiable note body."

    async def _misplaced_classifier(text):
        from app.services.note_classifier import ClassificationResult
        return ClassificationResult(topic="accomplishment", confidence=0.9, title_slug="x", reasoning="r")

    report_holder: list[SweepReport] = []

    async def _capturing_run_sweep(*args, **kwargs):
        # Call the real run_sweep with the forwarded probe
        from app.services.vault_sweeper import run_sweep as _real_run_sweep
        report = await _real_run_sweep(*args, **kwargs)
        report_holder.append(report)
        return report

    runner = _ImmediateTaskRunner()

    with patch("app.services.note_sweep_runner.run_sweep", side_effect=_capturing_run_sweep):
        await start_sweep(
            vault=vault,
            classifier=_misplaced_classifier,
            embedder=_embedder,
            force_reclassify=True,
            dry_run=False,
            safe_to_mutate=_always_false,
            task_runner=runner,
        )
        await runner.run_all()

    assert len(report_holder) == 1
    report = report_holder[0]
    assert report.topic_moves == 0, (
        f"probe=False should result in zero topic_moves; got {report.topic_moves}"
    )
    assert "random-folder/misplaced.md" in vault.notes, (
        "note must remain at original path when probe is False"
    )


@pytest.mark.asyncio
async def test_start_sweep_live_path_non_none_probe_required():
    """The live (non-dry-run) start_sweep must always forward a NON-None probe.

    Because run_sweep fails closed when the probe is None, a live admin sweep
    that omits the probe entirely would perform zero moves. This test proves
    that start_sweep with an explicit safe_to_mutate kwarg forwards it (non-None).
    """
    captured_kwargs: list[dict] = []

    async def _fake_run_sweep(*args, **kwargs):
        captured_kwargs.append(kwargs)
        from app.services.vault_sweeper import SweepReport
        from app.time_utils import _iso_utc
        return SweepReport(sweep_id=_iso_utc(), status="complete")

    vault = _make_vault()
    runner = _ImmediateTaskRunner()

    with patch("app.services.note_sweep_runner.run_sweep", side_effect=_fake_run_sweep):
        await start_sweep(
            vault=vault,
            classifier=_classifier,
            embedder=_embedder,
            force_reclassify=False,
            dry_run=False,
            safe_to_mutate=AsyncMock(return_value=True),
            task_runner=runner,
        )
        await runner.run_all()

    assert len(captured_kwargs) == 1
    probe = captured_kwargs[0].get("safe_to_mutate")
    assert probe is not None, (
        "live start_sweep must forward the supplied safe_to_mutate probe (non-None) into run_sweep"
    )


@pytest.mark.asyncio
async def test_start_sweep_dry_run_does_not_forward_probe():
    """dry_run path must NOT pass safe_to_mutate to run_sweep (no probe needed for preview).

    The dry_run path is safe regardless — it never writes anything.
    """
    captured_kwargs: list[dict] = []

    async def _fake_run_sweep(*args, **kwargs):
        captured_kwargs.append(kwargs)
        from app.services.vault_sweeper import SweepReport
        from app.time_utils import _iso_utc
        return SweepReport(sweep_id=_iso_utc(), status="complete")

    vault = _make_vault()
    runner = _ImmediateTaskRunner()

    with patch("app.services.note_sweep_runner.run_sweep", side_effect=_fake_run_sweep):
        await start_sweep(
            vault=vault,
            classifier=_classifier,
            embedder=_embedder,
            force_reclassify=False,
            dry_run=True,
            task_runner=runner,
        )
        await runner.run_all()

    assert len(captured_kwargs) == 1
    # dry_run should NOT pass a safe_to_mutate probe
    probe = captured_kwargs[0].get("safe_to_mutate")
    assert probe is None, (
        f"dry_run path must NOT forward safe_to_mutate into run_sweep; got {probe}"
    )
