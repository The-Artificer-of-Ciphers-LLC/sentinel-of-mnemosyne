"""Atomic rollback ledger for the Phase 47 migration cutover (D-02/D-02a).

Records the inverse of every mutating REST op the migration orchestrator
performs, and replays them in reverse (LIFO) order on any hard failure so
the vault is restored to its exact pre-migration state. This module
performs NO forward migration mutations and holds NO business logic beyond
record + replay.

No generic transaction/rollback primitive exists elsewhere in the codebase
(confirmed via ``git show 9b105f4`` -- Phase 46's Verify-fail rollback is a
point fix, ``moc_maintenance.detach_from_hub``, not a ledger). This is
genuinely new code; ``detach_from_hub``'s idempotent, no-op-if-absent
discipline (a no-op if the thing to undo isn't there) is the only
precedent this module imitates.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.services.embedding_sidecar_index import (
    EMBEDDING_INDEX_PATH,
    decode_index_body,
    encode_index_body,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _RestoreOriginal:
    """Inverse of a notes-bound delete: re-write ``body`` to ``src``."""

    src: str
    body: str


@dataclass(frozen=True)
class _OpsMove:
    """Inverse of an ops-bound relocate: relocate ``dst`` back to ``src``,
    binding the embedding-sidecar key rename into the SAME entry (T-47-03:
    never restore the file without also reverting the sidecar key).

    ``original_body`` (optional, Phase 47 Plan 04 fix) captures the note's
    EXACT pre-relocate body. ``ObsidianVault.relocate()`` unconditionally
    overwrites ``original_path``/``topic_moved_at`` frontmatter on every
    call it makes (``app/vault.py:631-690``) -- a naive "relocate back"
    inverse would therefore leave stray provenance fields the pre-migration
    note never had, breaking the D-02a byte-identical restoration
    contract. When ``original_body`` is supplied, replay restores it via a
    direct ``write_note`` instead of a second ``relocate()`` call. Older
    callers that do not supply it fall back to the original relocate-based
    inverse (backward compatible)."""

    src: str
    dst: str
    sidecar_key_moved: bool
    original_body: str | None = None


@dataclass(frozen=True)
class _BacklinkRewrite:
    """Inverse of a D-03 backlink rewrite: restore ``before_body``."""

    note_path: str
    before_body: str


@dataclass(frozen=True)
class _InboxWrite:
    """Inverse of an inbox queue write: restore the prior body, or delete
    the path entirely if it did not exist before (delete-if-absent, per
    Plan 01's pinned contract)."""

    path: str
    before_body: str


class RollbackLedger:
    """Records inverse-op descriptors in order; ``replay`` unwinds them in
    reverse (LIFO) order, idempotently.

    Holds an ordered list of inverse-op descriptors (one dataclass per op
    kind). Each ``record_*`` call appends a descriptor capturing exactly
    the state needed to reconstruct the inverse -- no forward mutation
    happens here.
    """

    def __init__(self) -> None:
        self._ops: list[Any] = []

    def record_restore_original(self, src: str, body: str) -> None:
        """Store an inverse that re-writes ``body`` to ``src`` (undo of a
        notes-bound delete)."""
        self._ops.append(_RestoreOriginal(src=src, body=body))

    def record_ops_move(
        self,
        src: str,
        dst: str,
        *,
        sidecar_key_moved: bool = False,
        original_body: str | None = None,
    ) -> None:
        """Store an inverse that restores ``dst`` -> ``src`` AND, if
        ``sidecar_key_moved``, reverts the embedding-index key ``dst`` ->
        ``src`` -- as ONE entry (T-47-03: never restore a file without its
        sidecar). Pass ``original_body`` (the pre-relocate body) for a
        byte-exact restore that avoids ``relocate()``'s own
        provenance-frontmatter side effect (see ``_OpsMove`` docstring)."""
        self._ops.append(
            _OpsMove(
                src=src,
                dst=dst,
                sidecar_key_moved=sidecar_key_moved,
                original_body=original_body,
            )
        )

    def record_backlink_rewrite(self, note_path: str, before_body: str) -> None:
        """Store an inverse that restores ``before_body`` to ``note_path``
        (undo of a D-03 backlink rewrite)."""
        self._ops.append(_BacklinkRewrite(note_path=note_path, before_body=before_body))

    def record_inbox_write(self, path: str, before_body: str) -> None:
        """Store an inverse that restores the prior inbox queue body (or
        removes the path entirely if it had no prior body)."""
        self._ops.append(_InboxWrite(path=path, before_body=before_body))

    async def replay(self, vault: Any) -> None:
        """Execute all recorded inverses in REVERSE (LIFO) order, each
        idempotently; a second replay is a no-op.

        Best-effort full unwind: a single failed inverse is logged and does
        NOT stop the remaining inverses from replaying (so one bad undo
        does not strand the rest), but an aggregate error is raised at the
        end if any inverse failed.
        """
        errors: list[str] = []
        for op in reversed(self._ops):
            try:
                await self._replay_one(vault, op)
            except Exception as exc:  # noqa: BLE001 -- best-effort full unwind
                logger.exception(
                    "RollbackLedger.replay: inverse op failed: %r", op
                )
                errors.append(f"{op!r}: {exc}")

        if errors:
            raise RuntimeError(
                f"RollbackLedger.replay: {len(errors)} inverse op(s) failed: "
                + "; ".join(errors)
            )

    async def _replay_one(self, vault: Any, op: Any) -> None:
        if isinstance(op, _RestoreOriginal):
            await vault.write_note(op.src, op.body)
            return

        if isinstance(op, _OpsMove):
            if op.original_body is not None:
                # Byte-exact restore (Phase 47 Plan 04 fix): relocate()
                # unconditionally overwrites original_path/topic_moved_at
                # frontmatter on every call, so a second "relocate back"
                # would leave stray provenance fields the pre-migration
                # note never had. Write the captured pre-move body back
                # directly, then remove the moved-to copy if still present
                # (idempotent -- a no-op if already rolled back).
                current = await vault.read_note(op.dst)
                if current:
                    await vault.delete_note(op.dst)
                await vault.write_note(op.src, op.original_body)
            else:
                # Backward-compatible fallback for callers that don't
                # capture the pre-move body: idempotent -- only relocate
                # back if the moved file is still at dst (mirrors
                # detach_from_hub's "no-op if absent" discipline).
                current = await vault.read_note(op.dst)
                if current:
                    await vault.relocate(op.dst, op.src)
            if op.sidecar_key_moved:
                await self._revert_sidecar_key(vault, op.src, op.dst)
            return

        if isinstance(op, _BacklinkRewrite):
            await vault.write_note(op.note_path, op.before_body)
            return

        if isinstance(op, _InboxWrite):
            if op.before_body:
                await vault.write_note(op.path, op.before_body)
            else:
                await vault.delete_note(op.path)
            return

        raise TypeError(f"RollbackLedger: unknown inverse op type: {op!r}")

    async def _revert_sidecar_key(self, vault: Any, src: str, dst: str) -> None:
        """Rename the embedding-sidecar key ``dst`` -> ``src`` back, if present.

        Idempotent: a no-op if the sidecar has no entry under ``dst`` (already
        reverted, or never had one).
        """
        raw = await vault.read_note(EMBEDDING_INDEX_PATH)
        if not raw.strip():
            return
        index = decode_index_body(raw, EMBEDDING_INDEX_PATH)
        if dst in index:
            index[src] = index.pop(dst)
            await vault.write_note(
                EMBEDDING_INDEX_PATH, encode_index_body(index, EMBEDDING_INDEX_PATH)
            )
