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


async def test_rethink_coerces_malformed_completion_to_keep():
    """A malformed completion for one item coerces to KEEP and never aborts
    the batch -- the well-formed sibling item still gets its real
    disposition."""
    from unittest.mock import AsyncMock, patch

    from app.services.six_rs.rethink import triage_observations
    from tests.fakes.vault import FakeVault

    good_path = "ops/observations/2026-07-06-good-observation.md"
    bad_path = "ops/observations/2026-07-06-bad-observation.md"
    vault = FakeVault(
        notes={
            good_path: "A well-formed observation.\n",
            bad_path: "An observation whose completion comes back malformed.\n",
        }
    )
    vault.dirs["ops/observations"] = [
        "2026-07-06-good-observation.md",
        "2026-07-06-bad-observation.md",
    ]

    good_canned = {"disposition": "PROMOTE", "reasoning": "durable knowledge"}
    responses = {
        good_path: {"choices": [{"message": {"content": json.dumps(good_canned)}}]},
        bad_path: {"choices": [{"message": {"content": "not-json{{{"}}]},
    }

    async def _fake_completion(*, messages, **_kwargs):
        item_text = messages[-1]["content"]
        for path, body in vault.notes.items():
            if body == item_text:
                return responses[path]
        raise AssertionError(f"unexpected item text: {item_text!r}")

    with patch(
        "app.services.six_rs.rethink.acompletion_with_profile",
        new=AsyncMock(side_effect=_fake_completion),
    ):
        results = await triage_observations(vault)  # must not raise

    by_path = {item["path"]: item["disposition"] for item in results}
    assert by_path[good_path] == "PROMOTE"
    assert by_path[bad_path] == "KEEP"


# --- ADR-0007 step 4: the two backend failure modes, at THIS call site -------


async def test_rethink_triages_against_the_static_profile_when_backend_unreachable():
    """UNREACHABLE → resolution does not raise; the triage completion happens."""
    import json
    from unittest.mock import AsyncMock, patch

    from app.services.six_rs.rethink import triage_observations
    from app.services.structured_model import set_structured_active_model
    from tests.conftest import unreachable_structured_seam
    from tests.fakes.vault import FakeVault

    set_structured_active_model(await unreachable_structured_seam())

    path = "ops/observations/2026-07-06-observation.md"
    vault = FakeVault(notes={path: "A well-formed observation.\n"})
    vault.dirs["ops/observations"] = ["2026-07-06-observation.md"]

    canned = {"disposition": "PROMOTE", "reasoning": "durable knowledge"}
    with patch(
        "app.services.six_rs.rethink.acompletion_with_profile",
        new=AsyncMock(
            return_value={"choices": [{"message": {"content": json.dumps(canned)}}]}
        ),
    ) as completion:
        results = await triage_observations(vault)

    assert completion.await_count == 1
    assert completion.await_args.kwargs["profile"].model_id == "local-model"
    assert results[0]["disposition"] == "PROMOTE"


async def test_rethink_coerces_to_keep_without_completing_on_an_ambiguous_backend():
    """AMBIGUOUS LIVE → KEEP, and no completion is issued.

    KEEP is the never-crash-the-loop default, so on its own it proves nothing
    about which failure occurred. The load-bearing assertion is that no model
    was called: an item must never be triaged — and so never archived — by a
    model nothing chose.
    """
    from unittest.mock import AsyncMock, patch

    from app.services.six_rs.rethink import triage_observations
    from app.services.structured_model import set_structured_active_model
    from tests.conftest import ambiguous_structured_seam
    from tests.fakes.vault import FakeVault

    set_structured_active_model(ambiguous_structured_seam())

    path = "ops/observations/2026-07-06-observation.md"
    vault = FakeVault(notes={path: "A well-formed observation.\n"})
    vault.dirs["ops/observations"] = ["2026-07-06-observation.md"]

    completion = AsyncMock()
    with patch("app.services.six_rs.rethink.acompletion_with_profile", new=completion):
        results = await triage_observations(vault)  # must not raise

    assert completion.await_count == 0
    assert results[0]["disposition"] == "KEEP"
