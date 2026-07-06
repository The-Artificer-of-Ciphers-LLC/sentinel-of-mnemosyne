"""RED scaffold for ``app.services.six_rs.verify`` (Phase 46, PIPE-07, D-02).

Wave 0 (Plan 46-01) pins the intended Verify API surface ahead of Wave 2
landing the module. Function-scope imports keep pytest collection green
while ``app.services.six_rs.verify`` does not exist yet -- these tests FAIL
at runtime (ModuleNotFoundError during the test body) until Wave 2 lands
``verify_note`` / ``VERIFY_RETRY_CAP``.

Intended contract (CONTEXT.md D-02/D-02a/D-02b / PATTERNS.md verify
section):

    VERIFY_RETRY_CAP: int  # named constant, suggested default 2 (D-02b)

    async def verify_note(
        vault, *, note_path: str, body: str, filename_slug: str,
        retry_count: int = 0,
    ) -> dict

Compliance is decided by the already-shipped
``note_schema.check_note_compliance`` (D-02a) -- verify.py must call it
directly, never re-implement ``has_schema``/``has_wikilink`` checks. On
failure the note is requeued to ``inbox/`` with an incremented retry count
(never landed in ``notes/``); once ``retry_count >= VERIFY_RETRY_CAP`` it
stops requeuing and is left in ``inbox/`` marked ``needs-attention``,
surfaced in the outcome report rather than silently dropped or looped
forever (D-02b).
"""
from __future__ import annotations


async def test_verify_failure_requeues_with_retry_cap():
    """Failing compliance requeues with retry_count+1; stops at the cap (D-02b)."""
    from unittest.mock import patch

    from app.services.six_rs.verify import VERIFY_RETRY_CAP, verify_note

    failing_result = {
        "has_schema": False,
        "has_type": False,
        "has_claim_title": False,
        "has_wikilink": False,
        "failures": ["missing _schema block", "missing wikilink"],
    }

    with patch(
        "app.services.six_rs.verify.check_note_compliance",
        return_value=failing_result,
    ):
        from tests.fakes.vault import FakeVault

        vault = FakeVault()
        outcome = await verify_note(
            vault,
            note_path="notes/draft-note.md",
            body="# Draft Note\n\nno schema, no links\n",
            filename_slug="draft-note",
            retry_count=0,
        )
        assert outcome["passed"] is False
        assert outcome["requeued"] is True
        assert outcome["retry_count"] == 1
        assert outcome.get("needs_attention", False) is False

        # Drive retry_count to the cap -- must stop requeuing and mark
        # needs-attention rather than looping forever (D-02).
        at_cap = await verify_note(
            vault,
            note_path="notes/draft-note.md",
            body="# Draft Note\n\nno schema, no links\n",
            filename_slug="draft-note",
            retry_count=VERIFY_RETRY_CAP,
        )
        assert at_cap["passed"] is False
        assert at_cap["needs_attention"] is True


async def test_verify_reuses_check_note_compliance():
    """Compliance decision comes from note_schema.check_note_compliance reuse,
    not a re-implemented parser (D-02a)."""
    from unittest.mock import patch

    from app.services.six_rs.verify import verify_note

    passing_result = {
        "has_schema": True,
        "has_type": True,
        "has_claim_title": True,
        "has_wikilink": True,
        "failures": [],
    }

    with patch(
        "app.services.six_rs.verify.check_note_compliance",
        return_value=passing_result,
    ) as compliance_mock:
        from tests.fakes.vault import FakeVault

        vault = FakeVault()
        body = "# A Genuinely Claim-Shaped Title\n\nSee [[Other Note]].\n\n```_schema\ntype: permanent\n```\n"
        outcome = await verify_note(
            vault,
            note_path="notes/good-note.md",
            body=body,
            filename_slug="good-note",
            retry_count=0,
        )

    compliance_mock.assert_called_once()
    call = compliance_mock.call_args
    assert body in call.args or body in call.kwargs.values()
    assert outcome["passed"] is True
    assert outcome["requeued"] is False
