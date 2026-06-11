"""Regression test: importing app.services.recall first must not raise a circular-import error.

CR-02 fix: MessageRequest was imported at module level in recall.py while
message_processing.py imports back from recall at EOF, creating a load-time
cycle.  This test imports recall before message_processing (in a subprocess so
sys.modules state is clean) and asserts that the public names resolve correctly.
"""
from __future__ import annotations

import subprocess
import sys


def test_recall_imports_before_message_processing() -> None:
    """recall can be imported first without hitting a circular-import error."""
    code = (
        "import app.services.recall as r; "
        "assert hasattr(r, 'Recall'), 'Recall missing'; "
        "assert hasattr(r, 'RecallConfig'), 'RecallConfig missing'; "
        "assert hasattr(r, 'SEARCH_SCORE_THRESHOLD'), 'SEARCH_SCORE_THRESHOLD missing'; "
        "print('ok')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
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
