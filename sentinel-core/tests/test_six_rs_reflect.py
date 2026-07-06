"""RED scaffold for ``app.services.six_rs.reflect`` (Phase 46, D-07, T-46-03).

Wave 0 (Plan 46-01) pins the intended Reflect API surface ahead of Wave 2
landing the module. Function-scope imports keep pytest collection green
while ``app.services.six_rs.reflect`` does not exist yet -- these tests FAIL
at runtime (ModuleNotFoundError during the test body) until Wave 2 lands
``find_and_attach_hub``.

Intended contract (RESEARCH.md Pattern 4 / PATTERNS.md reflect section):

    async def find_and_attach_hub(
        vault, *, note_path: str, note_vector, index: dict, active_model: str,
    ) -> str | None

Embedding-first: calls ``moc_maintenance.find_hub_candidate`` (reused
verbatim, never a fresh cosine loop) restricted to ``notes/``-scoped hub
candidates, then ``moc_maintenance.attach_to_hub``/``create_or_update_hub``
on a match. T-46-03: reflect must never treat a ``self/`` path as an
eligible hub target -- a wikilink must never be created FROM a ``notes/``
note INTO ``self/`` (information-disclosure guard), even if a ``self/`` note
happens to embed closer than any real hub.
"""
from __future__ import annotations

import numpy as np

from sentinel_shared.embedding_codec import encode_embedding


def _entry(vector: list[float], *, model: str = "test-model") -> dict:
    return {
        "embedding_b64": encode_embedding(vector),
        "embedding_model": model,
        "content_hash": "deadbeef",
        "embedding_dim": len(vector),
    }


async def test_reflect_embedding_first_hub_match():
    """Embedding-first lookup returns the highest-cosine hub above the floor
    and calls attach_to_hub (D-07, no fresh cosine implementation)."""
    from unittest.mock import AsyncMock, patch

    from app.services.six_rs.reflect import find_and_attach_hub
    from tests.fakes.vault import FakeVault

    hub_path = "notes/recall-hub.md"
    vault = FakeVault(notes={hub_path: "# Recall Hub\n\n```_schema\ntype: hub\n```\n"})
    index = {
        hub_path: _entry([1.0, 0.0]),  # cosine 1.0 -- clears the floor
        "notes/off-topic-hub.md": _entry([0.0, 1.0]),  # cosine 0.0 -- below floor
    }

    with patch(
        "app.services.six_rs.reflect.attach_to_hub", new=AsyncMock()
    ) as attach_mock:
        result = await find_and_attach_hub(
            vault,
            note_path="notes/member-note.md",
            note_vector=np.asarray([1.0, 0.0], dtype=np.float32),
            index=index,
            active_model="test-model",
        )

    assert result == hub_path
    attach_mock.assert_awaited()
    call_args = attach_mock.await_args
    assert hub_path in call_args.args or hub_path in call_args.kwargs.values()


async def test_reflect_no_wikilink_from_notes_into_self():
    """T-46-03: a self/ note must never become a hub-attach target.

    Even when a ``self/`` path would embed closer than any real hub, reflect
    must never select it as an attach target and must never mutate it --
    the information-disclosure guard is a hard architectural exclusion, not
    merely a cosine-floor accident.
    """
    from unittest.mock import AsyncMock, patch

    from app.services.six_rs.reflect import find_and_attach_hub
    from tests.fakes.vault import FakeVault

    real_hub_path = "notes/topic-hub.md"
    self_path = "self/identity.md"
    original_self_body = "# I am ...\n"
    vault = FakeVault(
        notes={
            real_hub_path: "# Topic Hub\n\n```_schema\ntype: hub\n```\n",
            self_path: original_self_body,
        }
    )
    # self/identity.md embeds IDENTICALLY to the query -- if reflect naively
    # scored every index entry it would win outright; the guard must exclude
    # it before scoring, not merely lose a tie.
    index = {
        real_hub_path: _entry([0.6, 0.8]),
        self_path: _entry([1.0, 0.0]),
    }

    with patch(
        "app.services.six_rs.reflect.attach_to_hub", new=AsyncMock()
    ) as attach_mock:
        result = await find_and_attach_hub(
            vault,
            note_path="notes/member-note.md",
            note_vector=np.asarray([1.0, 0.0], dtype=np.float32),
            index=index,
            active_model="test-model",
        )

    assert result != self_path
    for call in attach_mock.await_args_list:
        assert self_path not in call.args
        assert self_path not in call.kwargs.values()
    assert vault.notes[self_path] == original_self_body


async def test_reflect_fallback_creates_hub_when_no_candidate_clears_floor():
    """D-07 fallback: when nothing clears the cosine floor, reflect proposes
    a concept slug (LLM naming, propose_hub_slug) then create_or_update_hub
    -- never a fresh cosine implementation, never silently skipping."""
    from unittest.mock import AsyncMock, patch

    from app.services.six_rs.reflect import find_and_attach_hub
    from tests.fakes.vault import FakeVault

    note_path = "notes/member-note.md"
    vault = FakeVault(notes={note_path: "# Member Note\n\nSome content.\n"})
    index = {
        "notes/off-topic-hub.md": _entry([0.0, 1.0]),  # cosine 0.0 -- below floor
    }

    with patch(
        "app.services.six_rs.reflect.propose_hub_slug",
        new=AsyncMock(return_value="new-concept"),
    ) as propose_mock, patch(
        "app.services.six_rs.reflect.create_or_update_hub",
        new=AsyncMock(return_value="notes/new-concept.md"),
    ) as create_mock:
        result = await find_and_attach_hub(
            vault,
            note_path=note_path,
            note_vector=np.asarray([1.0, 0.0], dtype=np.float32),
            index=index,
            active_model="test-model",
        )

    assert result == "notes/new-concept.md"
    propose_mock.assert_awaited_once()
    create_mock.assert_awaited_once()
    _, create_kwargs = create_mock.await_args
    assert create_kwargs["concept_slug"] == "new-concept"
    assert create_kwargs["member_slug"] == "member-note"
