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
