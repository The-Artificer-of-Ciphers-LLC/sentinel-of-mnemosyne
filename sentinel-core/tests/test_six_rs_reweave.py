"""RED scaffold for ``app.services.six_rs.reweave`` (Phase 46, PIPE-04, D-01).

Wave 0 (Plan 46-01) pins the intended Reweave API surface ahead of Wave 2
landing the module. Function-scope import keeps pytest collection green
while ``app.services.six_rs.reweave`` does not exist yet -- this test FAILS
at runtime (ModuleNotFoundError during the test body) until Wave 2 lands
``reweave_note``.

Intended contract (CONTEXT.md D-01 / PATTERNS.md "Idempotent append-only
write"):

    async def reweave_note(
        vault, *, target_path: str, addition_text: str, date: str | None = None,
    ) -> None

Auto-apply, append-only: each reweave candidate gets a bounded
``## Reweave — {date}`` section appended to the target note; existing prose
is never rewritten or deleted. Idempotent by the dated section marker --
mirrors ``moc_maintenance.attach_to_hub``'s dedupe-by-marker shape (D-03d
precedent) -- so a second identical reweave pass must never stack a
duplicate section. Always full-body read -> merge -> single ``write_note``
(never ``vault.patch_append``, transaction-less REST vault constraint).
"""
from __future__ import annotations

import re


async def test_reweave_append_idempotent():
    """A second identical reweave pass does not stack a duplicate section."""
    from app.services.six_rs.reweave import reweave_note
    from tests.fakes.vault import FakeVault

    target_path = "notes/older-note.md"
    original_body = "# Older Note\n\nSome durable prose that must survive untouched.\n"
    vault = FakeVault(notes={target_path: original_body})
    reweave_date = "2026-07-06"

    await reweave_note(
        vault,
        target_path=target_path,
        addition_text="New connection: see [[Fresh Note]] for related context.",
        date=reweave_date,
    )
    once = vault.notes[target_path]

    await reweave_note(
        vault,
        target_path=target_path,
        addition_text="New connection: see [[Fresh Note]] for related context.",
        date=reweave_date,
    )
    twice = vault.notes[target_path]

    assert once == twice, "re-running an identical reweave pass must be a no-op"
    marker_count = len(re.findall(r"## Reweave — 2026-07-06", twice))
    assert marker_count == 1, (
        f"expected exactly one dated Reweave section, found {marker_count}"
    )
    # Original prose is never rewritten or deleted (append-only, D-01).
    assert "Some durable prose that must survive untouched." in twice


async def test_reweave_preserves_trailing_schema_block():
    """The appended section lands BEFORE the trailing _schema block, and the
    block is re-appended unchanged and last in the file (note_schema's
    terminal-block invariant)."""
    from app.services.six_rs.reweave import reweave_note
    from tests.fakes.vault import FakeVault

    target_path = "notes/schema-note.md"
    original_body = (
        "# Schema Note\n\nDurable prose.\n\n```_schema\ntype: permanent\nstatus: final\n```\n"
    )
    vault = FakeVault(notes={target_path: original_body})

    await reweave_note(
        vault,
        target_path=target_path,
        addition_text="See [[Other Note]] for related context.",
        date="2026-07-07",
    )
    updated = vault.notes[target_path]

    assert "Durable prose." in updated
    assert "## Reweave — 2026-07-07" in updated
    assert updated.rstrip().endswith("```")
    # The dated section must precede the trailing _schema block, not follow it.
    section_idx = updated.index("## Reweave — 2026-07-07")
    schema_idx = updated.rindex("```_schema")
    assert section_idx < schema_idx


async def test_reweave_rejects_target_outside_notes():
    """T-46-03: reweave must never write to a self/ or ops/ protected path."""
    from app.services.six_rs.reweave import reweave_note
    from tests.fakes.vault import FakeVault

    vault = FakeVault(notes={"self/identity.md": "# I am ...\n"})

    import pytest

    with pytest.raises(ValueError):
        await reweave_note(
            vault,
            target_path="self/identity.md",
            addition_text="should never be written",
            date="2026-07-06",
        )
    assert vault.notes["self/identity.md"] == "# I am ...\n"
