"""Tests for note_classifier service (260427-vl1 Task 3).

Eight behavioral tests covering:
1. Cheap pre-filter on noise openers + empty + short.
2. Cheap pre-filter passes legitimate content through.
3. test- filename heuristic.
4. user_topic bypasses LLM.
5. Happy path JSON parse.
6. Malformed JSON salvages to unsure / 0.0.
7. Unknown topic salvages to unsure.
8. Confidence rounded to one decimal.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.errors import ModelSelectorError
from app.model import ModelProfile
from app.services.note_classifier import (
    _apply_cheap_filter,
    _coerce_topic,
    _slugify,
    classify_note,
    topic_dir_for,
)
from app.services.structured_model import set_structured_active_model
from tests.conftest import ambiguous_structured_seam, unreachable_structured_seam


# --- Cheap filter ---


def test_cheap_filter_noise_basics():
    assert _apply_cheap_filter("hello") == ("noise", 1.0)
    assert _apply_cheap_filter("") == ("noise", 1.0)
    # 19 chars, no opener → leaves to LLM
    assert _apply_cheap_filter("a" * 19) is None
    # opener "ping" — short single word
    assert _apply_cheap_filter("ping") == ("noise", 1.0)


def test_cheap_filter_legit_content_passes():
    assert _apply_cheap_filter("Finished the sing-better course. Took 6 weeks.") is None


def test_cheap_filter_test_filename_short_body():
    """test-* / tmp- / untitled filenames with 20 <= body < 200 → noise.

    Per the frozen filter ordering, body shorter than 20 chars never reaches
    the filename heuristic — it short-circuits at the length check first.
    """
    medium = "placeholder body x" * 5  # 90 chars
    assert _apply_cheap_filter(medium, filename="test-foo.md") == ("noise", 1.0)
    # Long enough body should NOT trigger filename heuristic
    long_body = "x" * 250
    assert _apply_cheap_filter(long_body, filename="test-foo.md") is None


# --- classify_note ---


def _profile(model_id: str = "m") -> ModelProfile:
    """The seam's answer, as the classifier now receives it.

    One value carries the model string, the api base and the stop sequences
    that used to arrive as a three-tuple from ``resolve_structured_model``.
    """
    return ModelProfile(
        model_id=model_id,
        litellm_model=f"openai/{model_id}",
        api_base="http://x",
        task_kind="structured",
    )


def _build_litellm_response(content: str):
    """Construct a litellm-like response object with choices[0].message.content."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.mark.asyncio
async def test_user_topic_bypasses_llm():
    """user_topic in closed vocab → no LLM call."""
    with patch(
        "app.services.note_classifier.acompletion_with_profile",
        new=AsyncMock(return_value=_build_litellm_response('{"topic":"reference"}')),
    ) as mock_llm:
        result = await classify_note("Finished course X", user_topic="learning")
    assert result.topic == "learning"
    assert result.confidence == 1.0
    assert mock_llm.await_count == 0


@pytest.mark.asyncio
async def test_classify_happy_path():
    """Mocked LLM returns clean JSON → result reflects values."""
    with patch(
        "app.services.note_classifier.structured_profile",
        new=AsyncMock(return_value=_profile()),
    ), patch(
        "app.services.note_classifier.acompletion_with_profile",
        new=AsyncMock(
            return_value=_build_litellm_response(
                '{"topic":"reference","confidence":0.91,"title_slug":"some-fact","reasoning":"discrete"}'
            )
        ),
    ):
        result = await classify_note(
            "real content here that survives filter, not too short to pass", user_topic=None
        )
    assert result.topic == "reference"
    assert result.confidence == 0.9  # rounded from 0.91
    assert result.title_slug == "some-fact"
    assert "discrete" in result.reasoning


@pytest.mark.asyncio
async def test_classify_malformed_json_salvages_to_unsure():
    """JSON parse fail → unsure / confidence 0.0."""
    with patch(
        "app.services.note_classifier.structured_profile",
        new=AsyncMock(return_value=_profile()),
    ), patch(
        "app.services.note_classifier.acompletion_with_profile",
        new=AsyncMock(return_value=_build_litellm_response("not json at all {{{")),
    ):
        result = await classify_note(
            "real content here that survives filter, not too short to pass", user_topic=None
        )
    assert result.topic == "unsure"
    assert result.confidence == 0.0
    assert "unparseable" in result.reasoning.lower()


@pytest.mark.asyncio
async def test_classify_unknown_topic_coerces_to_unsure():
    """Topic outside closed vocab → unsure / 0.0."""
    with patch(
        "app.services.note_classifier.structured_profile",
        new=AsyncMock(return_value=_profile()),
    ), patch(
        "app.services.note_classifier.acompletion_with_profile",
        new=AsyncMock(
            return_value=_build_litellm_response(
                '{"topic":"garbled-not-in-vocab","confidence":0.7,"title_slug":"x","reasoning":"y"}'
            )
        ),
    ):
        result = await classify_note(
            "real content here that survives filter, not too short to pass", user_topic=None
        )
    assert result.topic == "unsure"
    assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_classify_confidence_rounded_one_decimal():
    """0.853 should round to 0.9."""
    with patch(
        "app.services.note_classifier.structured_profile",
        new=AsyncMock(return_value=_profile()),
    ), patch(
        "app.services.note_classifier.acompletion_with_profile",
        new=AsyncMock(
            return_value=_build_litellm_response(
                '{"topic":"learning","confidence":0.853,"title_slug":"x","reasoning":"y"}'
            )
        ),
    ):
        result = await classify_note(
            "real content here that survives filter, not too short to pass", user_topic=None
        )
    assert result.confidence == 0.9


# --- The two backend failure modes, kept apart (ADR-0007 decision 4) ---
#
# These replace test_resolve_model_for_classification_except_falls_back_to_
# settings_model_name, whose subject (_resolve_model_for_classification's
# except-handler, which returned settings.model_name when select_model raised)
# no longer exists. Its guarantee — "never fall back to an arbitrary catalog
# entry" — is now stronger and inverted: the ambiguous case returns NOTHING, not
# even the configured default, because a live backend's loaded set is the sole
# source of truth. That inversion is asserted in tests/test_model.py; what is
# asserted HERE is the half only this call site can answer, which is what
# classify_note does with each outcome.


@pytest.mark.asyncio
async def test_classify_note_coerces_to_unsure_when_the_backend_is_unreachable():
    """UNREACHABLE backend → graceful. Resolution does NOT raise.

    The live source fails, the seam falls through to ``StaticModelSource``, and
    MODEL_NAME is served as data — that setting's only surviving role. The
    completion is still attempted, and when it fails classify_note coerces to
    ``unsure`` exactly as it always has. An offline dev box stays usable.
    """
    set_structured_active_model(await unreachable_structured_seam())

    with patch(
        "app.services.note_classifier.acompletion_with_profile",
        new=AsyncMock(side_effect=RuntimeError("LM Studio unreachable")),
    ):
        result = await classify_note(
            "real content here that survives filter, not too short to pass"
        )

    assert result.topic == "unsure"
    assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_classify_note_propagates_an_ambiguous_live_backend():
    """AMBIGUOUS LIVE backend → raise. Same call, opposite handling.

    The backend is up and offering two equally-capable models with nothing to
    disambiguate them. Coercing this to ``unsure`` would be the wrong mercy: it
    would file vault notes using whatever model happened to answer, which is
    the phantom-model failure ADR-0007 exists to remove. It must surface. The
    destructive sweep is separately gated by probe_classifier_model_ready,
    which fails closed on this same condition.
    """
    set_structured_active_model(ambiguous_structured_seam())

    completion = AsyncMock()
    with patch(
        "app.services.note_classifier.acompletion_with_profile", new=completion
    ):
        with pytest.raises(ModelSelectorError):
            await classify_note(
                "real content here that survives filter, not too short to pass"
            )

    assert completion.await_count == 0, (
        "no completion may be issued against a model nothing chose"
    )


# --- helpers ---


def test_coerce_topic():
    assert _coerce_topic("learning") == "learning"
    assert _coerce_topic("garbage") == "unsure"
    assert _coerce_topic("") == "unsure"


def test_slugify():
    assert _slugify("Hello World!") == "hello-world"
    assert _slugify("") == "untitled"
    assert _slugify("Sing-Better Course Completion Notes") == "sing-better-course-completion-notes"
    long = "a" * 100
    assert len(_slugify(long, max_len=60)) <= 60


# --- taxonomy routing (D-03, Pitfall 1) ---


def test_topic_dir_for_journal_derives_from_dict():
    """topic_dir_for('journal') must derive its per-day path from the
    TOPIC_VAULT_PATH dict value (base), not a hardcoded 'journal/' literal
    (Pitfall 1 regression guard — editing the dict alone was a proven no-op)."""
    assert topic_dir_for("journal", today="2026-07-06") == "ops/journal/2026-07-06"


def test_topic_dir_for_para_reroute():
    """D-03 AFTER table: accomplishment/observation file under ops/;
    learning/reference queue to inbox/ pending Reduce."""
    assert topic_dir_for("accomplishment") == "ops/accomplishments"
    assert topic_dir_for("observation") == "ops/observations"
    assert topic_dir_for("learning") == "inbox"
    assert topic_dir_for("reference") == "inbox"
