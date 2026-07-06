"""RED scaffold for ``app.services.six_rs.rethink`` (Phase 46, PIPE-05, A3).

Wave 0 (Plan 46-01) pins the intended Rethink API surface ahead of Wave 2
landing the module. Function-scope imports keep pytest collection green
while ``app.services.six_rs.rethink`` does not exist yet -- these tests FAIL
at runtime (ModuleNotFoundError during the test body) until Wave 2 lands
``triage_observations``.

Intended contract (RESEARCH.md Phase Requirements PIPE-05 / Assumptions Log
A3):

    async def triage_observations(vault) -> list[dict]

Reads ``ops/observations/`` (+ ``ops/tensions/`` when present) and, per
item, calls an LLM completion to assign exactly one of the five
dispositions: PROMOTE / IMPLEMENT / METHODOLOGY / ARCHIVE / KEEP. Per A3,
``ops/tensions/`` has no writer anywhere in the codebase today and must be
treated as optionally-empty -- Rethink still triages observations-only
content without raising or reporting zero-tensions as an error.
"""
from __future__ import annotations

import json

_DISPOSITIONS = {"PROMOTE", "IMPLEMENT", "METHODOLOGY", "ARCHIVE", "KEEP"}


async def test_rethink_triage_dispositions():
    """Triage assigns one of PROMOTE/IMPLEMENT/METHODOLOGY/ARCHIVE/KEEP per item."""
    from unittest.mock import AsyncMock, patch

    from app.services.six_rs.rethink import triage_observations
    from tests.fakes.vault import FakeVault

    obs_path = "ops/observations/2026-07-06-some-observation.md"
    vault = FakeVault(notes={obs_path: "The user prefers append-only edits.\n"})
    vault.dirs["ops/observations"] = ["2026-07-06-some-observation.md"]
    vault.dirs["ops"] = ["observations/"]
    vault.dirs["ops/tensions"] = []

    canned = {"disposition": "METHODOLOGY", "reasoning": "captures a working-style rule"}
    fake_response = {"choices": [{"message": {"content": json.dumps(canned)}}]}

    with patch(
        "app.services.six_rs.rethink.acompletion_with_profile",
        new=AsyncMock(return_value=fake_response),
    ):
        results = await triage_observations(vault)

    assert results, "expected at least one triaged item"
    dispositions = {item["disposition"] for item in results}
    assert dispositions <= _DISPOSITIONS
    assert any(item["path"] == obs_path for item in results)


async def test_rethink_tolerates_absent_tensions_dir():
    """A3: an absent/empty ops/tensions/ directory must not raise or block
    triage -- observations-only content still triages successfully."""
    from unittest.mock import AsyncMock, patch

    from app.services.six_rs.rethink import triage_observations
    from tests.fakes.vault import FakeVault

    obs_path = "ops/observations/2026-07-06-solo-observation.md"
    vault = FakeVault(notes={obs_path: "A lone observation with no tensions dir.\n"})
    vault.dirs["ops/observations"] = ["2026-07-06-solo-observation.md"]
    vault.dirs["ops"] = ["observations/"]
    # Deliberately do NOT seed vault.dirs["ops/tensions"] -- list_under() on an
    # absent key must degrade to an empty list (FakeVault default), never raise.

    canned = {"disposition": "KEEP", "reasoning": "no action needed yet"}
    fake_response = {"choices": [{"message": {"content": json.dumps(canned)}}]}

    with patch(
        "app.services.six_rs.rethink.acompletion_with_profile",
        new=AsyncMock(return_value=fake_response),
    ):
        results = await triage_observations(vault)  # must not raise

    assert isinstance(results, list)
    assert any(item["path"] == obs_path for item in results)
