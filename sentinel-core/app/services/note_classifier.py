"""Note classifier service for sentinel-core's 2nd-brain feature.

Classifies a piece of free-form text into one of seven topic slugs (closed
vocabulary). Cheap regex pre-filter runs first to reject obvious noise
without an LLM call. On JSON parse failure or unknown topic, salvages to
``unsure`` (mirrors pathfinder's ``classify_rule_topic`` discipline).

Pipeline:
  1. If user supplied explicit ``user_topic`` ∈ closed vocab → return immediately
     with confidence=1.0. No LLM call.
  2. ``_apply_cheap_filter(text)`` → if returns ("noise", 1.0), return that.
  3. Resolve LLM model + profile + api_base, build a system prompt enumerating
     the 7 slugs, call ``acompletion_with_profile`` with JSON-mode response_format.
  4. Parse the response JSON. On any failure, coerce to ``unsure`` with conf=0.0.

Decisions and confidence-threshold semantics belong to the route layer
(``app/routes/note.py``); this service just returns the classifier's verdict.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Literal

from pydantic import BaseModel, Field

from app.config import settings
from app.services.model_selector import (
    ensure_litellm_prefix,
    get_loaded_models,
    select_model,
    strip_litellm_prefix,
)
from sentinel_shared.llm_call import acompletion_with_profile
from sentinel_shared.model_profiles import get_profile

logger = logging.getLogger(__name__)


# Closed-vocabulary taxonomy (CONTEXT.md Q1 → flat 7 categories)
TopicSlug = Literal[
    "learning",
    "accomplishment",
    "journal",
    "reference",
    "observation",
    "noise",
    "unsure",
]

CLOSED_VOCAB: frozenset[str] = frozenset(
    {"learning", "accomplishment", "journal", "reference", "observation", "noise", "unsure"}
)

# Vault directory mapping per CONTEXT.md
TOPIC_VAULT_PATH: dict[str, str] = {
    "learning": "learning",
    "accomplishment": "accomplishments",
    "journal": "journal",  # subdir per-day appended at file time
    "reference": "references",
    "observation": "ops/observations",
    "noise": "",  # never filed
    "unsure": "inbox",  # _pending-classification.md
}


def topic_dir_for(topic: str, *, today: str | None = None) -> str:
    """Return the vault directory for ``topic``.

    Single source of truth for "where does a note of topic X belong"
    used by both the explicit `:note` filer (which appends a slug+date
    filename) and the vault sweeper (which preserves the original
    filename when relocating).

    Returns empty string for topics that have no canonical filing
    location: ``noise`` (drop or trash) and ``unsure`` (handled via
    the pending-classification inbox, not a normal directory).

    For ``journal``, returns ``journal/{YYYY-MM-DD}`` so each day's
    entries are grouped. Pass ``today`` to override (used by tests).
    """
    base = TOPIC_VAULT_PATH.get(topic, "")
    if not base:
        return ""
    if topic == "journal":
        if today is None:
            from datetime import datetime, timezone
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return f"journal/{today}"
    return base


class ClassificationResult(BaseModel):
    """Verdict from the classifier — pure, route-agnostic."""

    topic: TopicSlug
    confidence: float = Field(ge=0.0, le=1.0)
    title_slug: str = Field(default="", max_length=60)
    reasoning: str = ""


# Cheap pre-filter regexes — frozen per RESEARCH §2 (do not modify)
_OPENERS = re.compile(
    r"^\s*(hi|hello|hey|test|are you there|what can you do|ping|yo|sup|"
    r"thanks|thank you|ok|okay)\b",
    re.IGNORECASE,
)
_TEST_FILENAME = re.compile(r"^(test-|tmp-|untitled)", re.IGNORECASE)


def _apply_cheap_filter(
    text: str, filename: str | None = None
) -> tuple[str, float] | None:
    """Return ("noise", 1.0) if text is obvious noise, else None.

    Frozen heuristic; do not change without updating CONTEXT.md and RESEARCH.md.
    """
    body = (text or "").strip()
    if not body:
        return ("noise", 1.0)
    if len(body) < 20:
        # additional safety: if it starts with an opener, definitely noise
        if _OPENERS.match(body):
            return ("noise", 1.0)
        # short but doesn't match opener → leave to LLM (could be legit one-line journal)
        return None
    if filename and _TEST_FILENAME.match(filename) and len(body) < 200:
        return ("noise", 1.0)
    if _OPENERS.match(body) and "\n" not in body and len(body) < 80:
        return ("noise", 1.0)
    return None


def _coerce_topic(raw: str) -> TopicSlug:
    """Return raw if in the closed vocabulary, else 'unsure'."""
    if isinstance(raw, str) and raw in CLOSED_VOCAB:
        return raw  # type: ignore[return-value]
    return "unsure"


_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _slugify(text: str, max_len: int = 60) -> str:
    """Convert text to kebab-case slug, lowercase, ≤ max_len chars."""
    if not text:
        return "untitled"
    s = text.strip().lower()
    s = _SLUG_NON_ALNUM.sub("-", s).strip("-")
    if not s:
        return "untitled"
    if len(s) > max_len:
        s = s[:max_len].rstrip("-") or "untitled"
    return s


# Frozen system prompt — instruct the model to return JSON {topic, confidence, title_slug, reasoning}
_CLASSIFIER_SYSTEM_PROMPT = """\
You are a strict topic classifier for a personal 2nd-brain note-taking system.

Classify the user's content into EXACTLY ONE of these seven slugs (closed vocabulary):

- learning       — skill/course progress, completions, study notes
- accomplishment — one-off achievements, milestones, things finished
- journal        — reflections, feelings, daily entries
- reference      — discrete facts or useful info to remember (about the world)
- observation    — methodology learnings about how the user works/thinks
- noise          — small talk, "hello", "thanks", low-signal chatter
- unsure         — confidence is genuinely below 0.5; you cannot decide

Respond ONLY with a JSON object of this exact shape (no prose, no code fences):

{
  "topic": "<one of the 7 slugs above>",
  "confidence": <number between 0.0 and 1.0>,
  "title_slug": "<kebab-case, ≤ 60 chars>",
  "reasoning": "<≤ 2 sentences>"
}

If the topic does not fit any of the 6 concrete slugs cleanly, choose "unsure"
with confidence < 0.5. Do not invent new slugs.
"""


async def _resolve_model_for_classification() -> tuple[str, object | None, str | None]:
    """Resolve (model_id, profile, api_base) for a structured-output classification call.

    Falls back gracefully when LM Studio is unreachable — returns a best-effort
    model string from settings; the LLM call may still fail, in which case
    classify_note() coerces to ``unsure``.
    """
    api_base = settings.lmstudio_base_url or "http://host.docker.internal:1234"
    api_base_v1 = f"{api_base.rstrip('/')}/v1" if not api_base.rstrip("/").endswith("/v1") else api_base
    try:
        loaded = await get_loaded_models(api_base_v1)
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("note_classifier: get_loaded_models failed: %s", exc)
        loaded = []

    # Honor MODEL_PREFERRED for the structured task kind too — operators set
    # this when they want one specific model for everything (avoids LM Studio
    # TTL-unloading multiple models, pinning to known-working ones).
    preferences: dict[str, str] = {}
    preferred = settings.model_preferred or settings.model_name
    if preferred:
        preferences["structured"] = preferred

    try:
        model_id = select_model(
            "structured",
            loaded,
            preferences=preferences,
            default=settings.model_name or None,
        )
    except Exception as exc:
        logger.warning("note_classifier: select_model failed (%s); falling back to first loaded", exc)
        model_id = loaded[0] if loaded else (settings.model_name or "openai/local-model")

    # Ensure litellm provider prefix — HF-style namespaces (qwen/qwen2.5-coder-14b)
    # are NOT litellm provider tags, so '/' alone is not a sufficient guard.
    prefixed_model_id = ensure_litellm_prefix(model_id)

    # get_profile hits LM Studio's /api/v0/models/{id} which needs the BARE id,
    # not the litellm-prefixed form. Strip the openai/ prefix back off.
    bare_model_id = strip_litellm_prefix(prefixed_model_id)

    try:
        profile = await get_profile(bare_model_id, api_base=api_base)
    except Exception as exc:
        logger.warning("note_classifier: get_profile failed (%s); using None", exc)
        profile = None

    return prefixed_model_id, profile, api_base


async def classify_note(
    candidate_text: str, user_topic: str | None = None
) -> ClassificationResult:
    """Classify ``candidate_text`` into one of the 7 topic slugs.

    If ``user_topic`` is supplied and falls in the closed vocab, the classifier
    is bypassed and confidence is 1.0. Otherwise, the cheap pre-filter runs
    first; survivors are sent to the LLM in JSON mode. JSON parse errors and
    unknown slugs coerce to ``unsure`` with confidence 0.0.
    """
    text = candidate_text or ""

    # 1. Explicit user topic bypasses everything
    if user_topic and user_topic in CLOSED_VOCAB:
        return ClassificationResult(
            topic=user_topic,  # type: ignore[arg-type]
            confidence=1.0,
            title_slug=_slugify(text[:60]) if text else "untitled",
            reasoning="explicit user topic",
        )

    # 2. Cheap pre-filter
    cheap = _apply_cheap_filter(text)
    if cheap is not None:
        topic, conf = cheap
        return ClassificationResult(
            topic=topic,  # type: ignore[arg-type]
            confidence=round(conf, 1),
            title_slug=_slugify(text[:60]) if text else "untitled",
            reasoning="cheap pre-filter match",
        )

    # 3. LLM classification
    model_id, profile, api_base = await _resolve_model_for_classification()

    messages = [
        {"role": "system", "content": _CLASSIFIER_SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]

    try:
        response = await acompletion_with_profile(
            model=model_id,
            messages=messages,
            profile=profile,
            api_base=api_base,
            api_key="lmstudio",  # LM Studio dummy key — litellm requires this even though LM Studio ignores it
            # LM Studio's OpenAI-compatible API rejects {"type": "json_object"};
            # use json_schema with explicit shape instead. Falls back to JSON parse + coerce-to-unsure.
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "classification",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "topic": {
                                "type": "string",
                                "enum": list(CLOSED_VOCAB),
                            },
                            "confidence": {"type": "number"},
                            "title_slug": {"type": "string"},
                            "reasoning": {"type": "string"},
                        },
                        "required": ["topic", "confidence", "title_slug", "reasoning"],
                        "additionalProperties": False,
                    },
                },
            },
            temperature=0.0,
        )
    except Exception as exc:
        logger.warning("note_classifier: LLM call failed: %s", exc)
        return ClassificationResult(
            topic="unsure",
            confidence=0.0,
            title_slug=_slugify(text[:60]),
            reasoning="classifier LLM call failed",
        )

    # Extract content (litellm response shape: choices[0].message.content)
    raw_content: str = ""
    try:
        if isinstance(response, dict):
            raw_content = response["choices"][0]["message"]["content"]
        else:
            raw_content = response.choices[0].message.content  # type: ignore[attr-defined]
    except Exception as exc:
        logger.warning("note_classifier: response shape unexpected: %s", exc)
        raw_content = ""

    try:
        parsed = json.loads(raw_content) if raw_content else {}
    except Exception as exc:
        logger.warning("note_classifier: JSON parse failed: %s; raw=%r", exc, raw_content[:200])
        return ClassificationResult(
            topic="unsure",
            confidence=0.0,
            title_slug=_slugify(text[:60]),
            reasoning="classifier output unparseable",
        )

    topic = _coerce_topic(parsed.get("topic", ""))
    raw_conf = parsed.get("confidence", 0.0)
    try:
        conf = float(raw_conf)
    except (TypeError, ValueError):
        conf = 0.0
    conf = max(0.0, min(1.0, conf))
    conf = round(conf, 1)

    title_slug = parsed.get("title_slug", "") or _slugify(text[:60])
    title_slug = _slugify(title_slug)
    reasoning = str(parsed.get("reasoning", "")).strip()[:500]

    # If topic was coerced to unsure due to unknown slug, force conf to 0.0
    if topic == "unsure" and parsed.get("topic", "") not in CLOSED_VOCAB:
        conf = 0.0
        if not reasoning:
            reasoning = "classifier output unparseable"

    return ClassificationResult(
        topic=topic,
        confidence=conf,
        title_slug=title_slug,
        reasoning=reasoning,
    )
