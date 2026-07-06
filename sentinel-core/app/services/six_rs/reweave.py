"""Reweave stage — six_rs/reweave.py (Phase 46 Plan 05, PIPE-04, D-01).

Auto-apply, append-only backward pass: appends a bounded, idempotent
``## Reweave — {date}`` section to an older note -- existing prose is
NEVER rewritten or deleted. Idempotent by the dated section marker
(mirrors ``moc_maintenance.attach_to_hub``'s dedupe-by-marker shape, D-03d
precedent): a second identical pass is a byte-identical no-op. Always a
full-body read -> merge -> single ``write_note`` (never
``vault.patch_append`` -- transaction-less REST vault constraint).

The drafted ``addition_text`` for the section is supplied by the caller
(the Wave-3 orchestrator drafts it via a schema-constrained completion
elsewhere) -- this module owns only the append-only, idempotent WRITE
mechanics, mirroring how ``moc_maintenance.attach_to_hub`` owns only the
wikilink-insert mechanics and never itself decides which member to attach.

T-46-03: ``target_path`` is restricted to ``notes/`` -- Reweave never
mutates a ``self/`` or ``ops/`` protected path.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.graph_analysis import NOTES_ROOT
from app.services.note_schema import split_schema_block

REWEAVE_SECTION_PREFIX = "## Reweave — "

_NOTES_PREFIX = f"{NOTES_ROOT}/"


async def reweave_note(
    vault: Any,
    *,
    target_path: str,
    addition_text: str,
    date: str | None = None,
) -> bool:
    """Append a bounded, idempotent dated Reweave section to ``target_path``.

    Returns ``True`` when a section was appended, ``False`` when the dated
    marker was already present (idempotent no-op, D-01) -- in that case the
    note is left byte-identical, never rewritten.

    Raises ``ValueError`` when ``target_path`` is not under ``notes/``
    (T-46-03) -- Reweave must never mutate a ``self/`` or ``ops/``
    protected path.
    """
    if not target_path.startswith(_NOTES_PREFIX):
        raise ValueError(
            f"reweave_note: target_path must be under {_NOTES_PREFIX!r} "
            f"(T-46-03); got {target_path!r}"
        )

    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    marker = f"{REWEAVE_SECTION_PREFIX}{date}"

    body = await vault.read_note(target_path)
    pre_block_body, trailing_block = split_schema_block(body)

    if marker in pre_block_body:
        return False  # idempotent: dated section already present (D-01)

    stripped = pre_block_body.rstrip("\n")
    section = f"{marker}\n\n{addition_text}\n"
    merged = f"{stripped}\n\n{section}" if stripped else section
    if not merged.endswith("\n"):
        merged += "\n"

    if trailing_block:
        if not merged.endswith("\n\n"):
            merged = f"{merged.rstrip(chr(10))}\n\n"
        # Trailing block is re-appended UNCHANGED and stays the terminal
        # content of the file (note_schema's terminal-block invariant) --
        # never rewritten, never dropped.
        merged = merged + trailing_block + "\n"

    await vault.write_note(target_path, merged)
    return True
