"""Regression test: importing app.services.recall first must not raise a circular-import error.

CR-02 fix: MessageRequest was imported at module level in recall.py while
message_processing.py imports back from recall at EOF, creating a load-time
cycle.  This test imports recall before message_processing (in a subprocess so
sys.modules state is clean) and asserts that the public names resolve correctly.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys


def _subprocess_env() -> dict[str, str]:
    """Build a subprocess environment that mirrors the pytest/app import environment.

    pytest resolves sentinel_shared via pyproject.toml pythonpath = [".", "../shared"].
    The subprocess needs the same PYTHONPATH so module-top-level imports in
    recall.py (from sentinel_shared.*) do not raise ModuleNotFoundError.
    """
    # sentinel-core/ directory (parent of this test file's tests/ dir)
    sentinel_core = pathlib.Path(__file__).parent.parent.resolve()
    # sentinel_shared lives at repo/shared/ (one level above sentinel-core/)
    shared_dir = (sentinel_core.parent / "shared").resolve()

    extra_paths = [str(sentinel_core), str(shared_dir)]
    existing = os.environ.get("PYTHONPATH", "")
    if existing:
        extra_paths.append(existing)
    new_pythonpath = os.pathsep.join(extra_paths)

    return {**os.environ, "PYTHONPATH": new_pythonpath}


def test_recall_imports_before_message_processing() -> None:
    """recall can be imported first without hitting a circular-import error."""
    code = (
        "import app.services.recall as r; "
        "assert hasattr(r, 'Recall'), 'Recall missing'; "
        "assert hasattr(r, 'RecallConfig'), 'RecallConfig missing'; "
        "assert hasattr(r, 'SEARCH_SCORE_THRESHOLD'), 'SEARCH_SCORE_THRESHOLD missing'; "
        "print('ok')"
    )
    # sentinel-core/ as cwd mirrors how pytest/app resolve package roots
    sentinel_core = pathlib.Path(__file__).parent.parent.resolve()
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(sentinel_core),
        env=_subprocess_env(),
    )
    assert result.returncode == 0, (
        f"Circular-import detected when importing recall first.\n"
        f"stderr: {result.stderr}\n"
        f"stdout: {result.stdout}"
    )
    assert "ok" in result.stdout


def test_message_request_not_in_recall_all() -> None:
    """MessageRequest must NOT be exported from recall.__all__ (it lives in message_processing)."""
    import app.services.recall as r

    assert "MessageRequest" not in r.__all__, (
        "MessageRequest should not be in recall.__all__ — "
        "its canonical home is app.services.message_processing"
    )
