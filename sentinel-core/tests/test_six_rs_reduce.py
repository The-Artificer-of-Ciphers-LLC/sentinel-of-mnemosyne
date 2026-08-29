"""RED scaffold for ``app.services.six_rs.reduce`` (Phase 46, PIPE-02).

Wave 0 (Plan 46-01) pins the intended Reduce API surface ahead of Wave 2
landing the module. Function-scope imports keep pytest collection green
while ``app.services.six_rs.reduce`` does not exist yet (STATE Phase 33-01
/ 45-01 precedent) -- these tests FAIL at runtime (ModuleNotFoundError
during the test body, never during collection) until Wave 2 lands
``reduce_entry``.

Intended contract (RESEARCH.md Pattern 1 / Architecture Patterns):

    async def reduce_entry(entry_text: str) -> ReduceResult

``ReduceResult`` carries ``claim_title``, ``body``, ``schema_type`` (one of
``permanent`` / ``literature`` / ``fleeting``). ``reduce_entry`` resolves a
model via the shared model-resolution helper and calls
``acompletion_with_profile`` with a ``json_schema`` response format -- the
call site is patched here via ``app.services.six_rs.reduce.acompletion_with_profile``.

Pitfall 6 (enforced at Verify, never at Reduce): Reduce must never call
``note_schema.check_note_compliance`` and must never drop a malformed
completion -- it always yields a fileable, non-empty ``ReduceResult`` so the
orchestrator can file the note tagged ``_schema.status: draft`` (the actual
vault write lives in ``pipeline_orchestrator.py`` / Wave 3, not in this pure
transform -- see the TODO on the second test below).
"""
from __future__ import annotations

import json


async def test_reduce_extracts_claim_and_schema_draft():
    """reduce_entry(entry_text) yields claim_title, body, schema_type (PIPE-02)."""
    from unittest.mock import AsyncMock, patch

    from app.services.six_rs.reduce import reduce_entry

    canned = {
        "claim_title": "Cosine floor governs hub attachment",
        "body": "The hub-lookup floor is reused verbatim from RecallConfig.",
        "schema_type": "permanent",
    }
    fake_response = {
        "choices": [{"message": {"content": json.dumps(canned)}}]
    }

    with patch(
        "app.services.six_rs.reduce.acompletion_with_profile",
        new=AsyncMock(return_value=fake_response),
    ):
        result = await reduce_entry("raw captured text about the hub cosine floor")

    assert result.claim_title == canned["claim_title"]
    assert result.body
    assert result.schema_type in {"permanent", "literature", "fleeting"}


async def test_reduce_malformed_completion_still_filed_as_draft():
    """Pitfall 6: a malformed/garbage completion is coerced, never dropped.

    Reduce must never raise and must never return an empty/None result on
    unparseable LLM output -- it coerces to a safe, non-empty ReduceResult
    (mirrors ``note_classifier.classify_note``'s coerce-to-safe-default
    discipline, PATTERNS.md "Error-coercion pattern") so the orchestrator
    can still file a `_schema.status: draft` note rather than silently
    losing the captured content.

    TODO (Wave 3, pipeline_orchestrator.py): the actual `_schema.status:
    draft` tagging + `notes/{slug}.md` write happens in the orchestrator,
    not in this pure transform -- once Wave 3 lands, add a companion
    orchestrator-level test asserting the draft-tagged note is written to
    the vault even when reduce_entry took this coercion path.
    """
    from unittest.mock import AsyncMock, patch

    from app.services.six_rs.reduce import reduce_entry

    garbage_response = {
        "choices": [{"message": {"content": "not json at all { garbage"}}]
    }

    with patch(
        "app.services.six_rs.reduce.acompletion_with_profile",
        new=AsyncMock(return_value=garbage_response),
    ):
        result = await reduce_entry("some raw inbox text that produced a bad completion")

    # Never dropped: reduce_entry must still return a usable, fileable result.
    assert result is not None
    assert result.body
    assert result.schema_type in {"permanent", "literature", "fleeting"}


def test_fallback_result_defaults_durable_true():
    """Fail SAFE (2026-08-29 incident follow-up): ``_fallback_result`` must
    default ``durable=True`` so an unparseable/failed completion is still
    filed as a draft note rather than silently discarded as "not durable"."""
    from app.services.six_rs.reduce import _fallback_result

    result = _fallback_result("some raw captured text")

    assert result.durable is True


async def test_reduce_completion_durable_false_parses_through():
    """A completion returning ``durable: false`` (conversational
    meta-commentary, not knowledge) parses into ``ReduceResult.durable ==
    False`` -- the escape hatch the orchestrator uses to skip filing."""
    from unittest.mock import AsyncMock, patch

    from app.services.six_rs.reduce import reduce_entry

    canned = {
        "claim_title": "The model's knowledge cutoff is prior to the current date",
        "body": "The model's knowledge cutoff is prior to the current date.",
        "schema_type": "fleeting",
        "durable": False,
    }
    fake_response = {"choices": [{"message": {"content": json.dumps(canned)}}]}

    with patch(
        "app.services.six_rs.reduce.acompletion_with_profile",
        new=AsyncMock(return_value=fake_response),
    ):
        result = await reduce_entry("what's the deal with your knowledge cutoff?")

    assert result.durable is False


async def test_reduce_completion_durable_true_files_as_before():
    """Non-regression: a completion returning ``durable: true`` still parses
    through normally (the pre-existing always-file behaviour for genuine
    knowledge)."""
    from unittest.mock import AsyncMock, patch

    from app.services.six_rs.reduce import reduce_entry

    canned = {
        "claim_title": "Cosine floor governs hub attachment",
        "body": "The hub-lookup floor is reused verbatim from RecallConfig.",
        "schema_type": "permanent",
        "durable": True,
    }
    fake_response = {"choices": [{"message": {"content": json.dumps(canned)}}]}

    with patch(
        "app.services.six_rs.reduce.acompletion_with_profile",
        new=AsyncMock(return_value=fake_response),
    ):
        result = await reduce_entry("raw captured text about the hub cosine floor")

    assert result.durable is True
    assert result.claim_title == canned["claim_title"]


def test_build_schema_block_round_trips_through_check_note_compliance():
    """Net-new build_schema_block() (Plan 46-04): the ONLY constructor for a
    trailing ```_schema fence -- Phase 45 shipped only parsers
    (parse_schema_block / check_note_compliance). A note composed with an H1
    claim title + a wikilink + this builder's output as terminal content must
    satisfy check_note_compliance's has_schema/has_type (the exact gate
    Verify, 46-06, checks against)."""
    from app.services.note_schema import check_note_compliance
    from app.services.six_rs.reduce import build_schema_block

    block = build_schema_block(type="permanent", status="draft")
    body = (
        "# Cosine Floor Governs Hub Attachment\n\n"
        "See [[Other Note]] for the shared threshold.\n\n"
        f"{block}\n"
    )

    result = check_note_compliance(body, filename_slug="cosine-floor-governs-hub-attachment")

    assert result["has_schema"] is True
    assert result["has_type"] is True
    assert "missing _schema block" not in result["failures"]
    assert "missing type key in _schema block" not in result["failures"]


def test_build_schema_block_hub_kwarg_included_only_when_provided():
    """hub kwarg round-trips into the parsed dict when provided; omitted
    entirely (not merely null) when absent -- both cases still has_type True."""
    from app.services.note_schema import parse_schema_block
    from app.services.six_rs.reduce import build_schema_block

    with_hub = build_schema_block(type="permanent", status="draft", hub="Some Hub")
    parsed_with_hub = parse_schema_block(with_hub)
    assert parsed_with_hub is not None
    assert parsed_with_hub["hub"] == "Some Hub"
    assert parsed_with_hub["type"] == "permanent"

    without_hub = build_schema_block(type="permanent", status="draft")
    parsed_without_hub = parse_schema_block(without_hub)
    assert parsed_without_hub is not None
    assert "hub" not in parsed_without_hub
    assert parsed_without_hub["type"] == "permanent"
