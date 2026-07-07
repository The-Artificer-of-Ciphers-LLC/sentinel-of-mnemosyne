"""Verify stage — six_rs/verify.py (Phase 46 Plan 04, PIPE-07, D-02).

Decides pass/fail for one Reduce-produced note by reusing the
already-shipped ``note_schema.check_note_compliance`` (D-02a, Phase 45,
``note_schema.py:121``) — this module never re-implements the
``_schema``/claim-title/wikilink checks. On failure it reports whether the
caller should requeue the entry (``retry_count < VERIFY_RETRY_CAP``) or mark
it ``needs_attention`` once the named retry cap (D-02b) is reached — never
silently dropped, never looped forever (D-02).

``verify_note`` is a pure decision function: it accepts ``vault``/
``note_path`` for API-shape parity with the Wave-3 orchestrator's call site,
but performs no vault I/O of its own — the actual requeue-to-``inbox/``
write and retry-count persistence live in the orchestrator (46-06), which
acts on this function's returned outcome dict.
"""
from __future__ import annotations

import logging

from app.services.note_schema import check_note_compliance

logger = logging.getLogger(__name__)

# D-02b: named retry cap — never a bare magic number at any call site.
VERIFY_RETRY_CAP = 2

# Cheap, additive signal for claim_title_assist — a claim-shaped title
# usually asserts something (contains a verb-like word), whereas a bare
# topic label ("Notes on X") usually doesn't. Deliberately small and
# permissive: this only ADDS a signal on top of check_note_compliance's
# structural has_claim_title check: it never gates compliance on its own.
_CLAIM_VERB_HINTS: frozenset[str] = frozenset(
    {
        "is", "are", "was", "were", "governs", "requires", "enables",
        "causes", "prevents", "supports", "breaks", "improves", "reduces",
        "increases", "produces", "yields", "means", "implies", "confirms",
        "explains", "shows", "demonstrates", "affects", "controls",
    }
)


async def verify_note(
    vault,
    *,
    note_path: str,
    body: str,
    filename_slug: str,
    retry_count: int = 0,
) -> dict:
    """Decide pass/fail for one note via ``check_note_compliance`` (D-02a).

    Thin wrapper — delegates ALL ``_schema``/title/wikilink checks to
    ``note_schema.check_note_compliance``; never re-derives them. Returns a
    dict describing the decision:

    - ``passed``: True iff compliance reported zero failures.
    - ``requeued``: True when the note failed AND is still below the retry
      cap (the orchestrator should requeue it to ``inbox/`` with
      ``retry_count`` incremented).
    - ``retry_count``: the retry count to persist next (unchanged on pass,
      unchanged at the cap, incremented by one otherwise).
    - ``needs_attention``: True once a failing note has reached
      ``VERIFY_RETRY_CAP`` — the orchestrator should stop requeuing and
      surface it in the outcome report instead (D-02b).
    - ``compliance``: the raw ``check_note_compliance`` result, for callers
      that want the specific failure list.

    ``vault``/``note_path`` are accepted for call-site parity with the
    orchestrator (and to leave room for a vault-aware claim-title assist
    later); this function performs no vault I/O — the Wave-3 orchestrator
    owns the actual requeue write + retry-count persistence.
    """
    compliance = check_note_compliance(body, filename_slug)
    passed = not compliance.get("failures")

    if passed:
        return {
            "passed": True,
            "requeued": False,
            "retry_count": retry_count,
            "needs_attention": False,
            "compliance": compliance,
        }

    if retry_count >= VERIFY_RETRY_CAP:
        logger.info(
            "verify_note: %s (slug=%s) reached VERIFY_RETRY_CAP=%d — marking needs_attention",
            note_path, filename_slug, VERIFY_RETRY_CAP,
        )
        return {
            "passed": False,
            "requeued": False,
            "retry_count": retry_count,
            "needs_attention": True,
            "compliance": compliance,
        }

    return {
        "passed": False,
        "requeued": True,
        "retry_count": retry_count + 1,
        "needs_attention": False,
        "compliance": compliance,
    }


async def claim_title_assist(title: str) -> bool:
    """OPTIONAL claim-title natural-language assist (D-02a, Claude's discretion).

    Implemented as a cheap, pure-Python heuristic rather than an LLM call
    (documented choice — see SUMMARY): ``check_note_compliance``'s
    ``has_claim_title`` already performs the mandatory structural check
    (H1 present, more than one word). This function adds one more
    permissive signal — whether the title contains a
    verb-like word, which a bare topic label ("Notes on X") usually lacks —
    without introducing an LLM round-trip, network dependency, or any
    possibility of raising. Never used to FAIL a note on its own; it is
    additive information only.
    """
    if not title or not title.strip():
        return False
    words = title.strip().split()
    if len(words) < 3:
        return False
    lowered = {w.lower().strip(".,;:!?") for w in words}
    return bool(lowered & _CLAIM_VERB_HINTS)
