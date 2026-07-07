"""RED unit tests for ``app.services.migration_rollback_ledger`` (Phase 47,
Plan 01 Wave 0, D-02/D-02a).

Pure-computation-style unit tests (mirrors ``tests/test_graph_analysis.py``'s
style) exercising ``RollbackLedger`` against a minimal in-memory fake vault.
Fails RED today with a ``ModuleNotFoundError`` -- ``app.services.migration_
rollback_ledger`` does not exist yet. This is the intended Wave 0 state; a
downstream plan (04) lands the module and turns this GREEN.

No generic transaction/rollback primitive exists elsewhere in the codebase
(confirmed via ``git show 9b105f4`` -- Phase 46's Verify-fail rollback is a
point fix, ``moc_maintenance.detach_from_hub``, not a ledger). This is
genuinely new code; ``detach_from_hub``'s idempotent, no-op-if-absent
discipline is the only precedent this module imitates.
"""
from __future__ import annotations

import json

import pytest


class _FakeVault:
    """Minimal in-memory Vault double: dict[str, str] path -> body.

    Deliberately smaller than ``tests/fakes/vault.py``'s full-protocol
    ``FakeVault`` -- the ledger only ever needs read/write/delete/relocate,
    and this test is pure-computation-style (no sweep lock, no find()).
    """

    def __init__(self, notes: dict[str, str] | None = None) -> None:
        self.notes: dict[str, str] = dict(notes or {})

    async def read_note(self, path: str) -> str:
        return self.notes.get(path, "")

    async def write_note(self, path: str, body: str) -> None:
        self.notes[path] = body

    async def delete_note(self, path: str) -> None:
        self.notes.pop(path, None)

    async def relocate(self, src: str, dst: str) -> str:
        body = self.notes.pop(src, "")
        self.notes[dst] = body
        return dst


@pytest.mark.asyncio
async def test_replay_restores_byte_identical_prestate():
    """D-02a: replaying the ledger restores every touched path to its exact
    pre-mutation body -- notes-bound restore, ops-bound move + sidecar-key
    revert, and a rewritten backlink all undo cleanly."""
    from app.services.migration_rollback_ledger import RollbackLedger

    vault = _FakeVault(
        notes={
            "learning/old-note.md": "# Old Note\n\noriginal body\n",
            "journal/2026-01-01-entry.md": "# Journal Entry\n\njournal body\n",
            "notes/other.md": "# Other\n\n[[Old Note]]\n",
            "ops/sweeps/embedding-index.json": json.dumps(
                {"journal/2026-01-01-entry.md": {"embedding_b64": "abc"}}
            ),
        }
    )
    pre_snapshot = dict(vault.notes)

    ledger = RollbackLedger()

    # Notes-bound: capture the original body before the enqueue-time delete.
    original_body = await vault.read_note("learning/old-note.md")
    ledger.record_restore_original("learning/old-note.md", original_body)
    await vault.delete_note("learning/old-note.md")

    # Ops-bound: relocate + sidecar-key rename, tracked as one entry (D-02a:
    # rollback must restore path AND sidecar key together).
    src, dst = "journal/2026-01-01-entry.md", "ops/journal/2026-01-01/2026-01-01-entry.md"
    actual_dst = await vault.relocate(src, dst)
    index = json.loads(await vault.read_note("ops/sweeps/embedding-index.json"))
    index[actual_dst] = index.pop(src)
    await vault.write_note("ops/sweeps/embedding-index.json", json.dumps(index))
    ledger.record_ops_move(src, actual_dst, sidecar_key_moved=True)

    # Backlink rewrite: an old-title reference rewritten to the new claim title.
    before_body = await vault.read_note("notes/other.md")
    ledger.record_backlink_rewrite("notes/other.md", before_body)
    await vault.write_note("notes/other.md", "# Other\n\n[[New Claim Title]]\n")

    # Inbox write: a batched enqueue write to a path that did not exist before.
    inbox_before = await vault.read_note("inbox/_pending-classification.md")
    ledger.record_inbox_write("inbox/_pending-classification.md", inbox_before)
    await vault.write_note(
        "inbox/_pending-classification.md", "# Pending Classification\n\n## Entry 1\n"
    )

    # Confirm the mutations actually happened before replaying.
    assert "learning/old-note.md" not in vault.notes
    assert actual_dst in vault.notes
    assert "[[New Claim Title]]" in vault.notes["notes/other.md"]
    assert "inbox/_pending-classification.md" in vault.notes

    await ledger.replay(vault)

    for path, body in pre_snapshot.items():
        assert vault.notes.get(path) == body, f"{path} not byte-identical after replay"
    assert actual_dst not in vault.notes, "relocated dst must be gone after rollback"
    assert "inbox/_pending-classification.md" not in vault.notes, (
        "a path with no pre-existing body must be removed entirely by replay, "
        "not left as an empty string"
    )


@pytest.mark.asyncio
async def test_replay_reverse_order():
    """Inverse ops execute last-in-first-out: two sequential relocations of
    the SAME file must be unwound in reverse (dst->mid before mid->src),
    or the file ends up stranded at the wrong path."""
    from app.services.migration_rollback_ledger import RollbackLedger

    vault = _FakeVault(notes={"a.md": "start"})
    ledger = RollbackLedger()

    mid = await vault.relocate("a.md", "b.md")
    ledger.record_ops_move("a.md", mid)

    final = await vault.relocate(mid, "c.md")
    ledger.record_ops_move(mid, final)

    assert vault.notes == {"c.md": "start"}

    await ledger.replay(vault)

    assert vault.notes == {"a.md": "start"}


@pytest.mark.asyncio
async def test_replay_is_idempotent():
    """Calling replay twice yields the same restored state -- mirrors
    ``detach_from_hub``'s no-op-if-absent discipline (the second replay
    finds nothing left to undo)."""
    from app.services.migration_rollback_ledger import RollbackLedger

    vault = _FakeVault(notes={"a.md": "start"})
    ledger = RollbackLedger()

    dst = await vault.relocate("a.md", "b.md")
    ledger.record_ops_move("a.md", dst)

    await ledger.replay(vault)
    first_state = dict(vault.notes)

    await ledger.replay(vault)
    second_state = dict(vault.notes)

    assert first_state == second_state == {"a.md": "start"}
