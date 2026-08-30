"""Behavioral tests for app.services.response_anomaly.detect_anomalies().

Each signal is exercised in isolation with a crafted example. The most
important test is the false-positive guard: a realistic, well-formed
assistant answer must produce suspicious=False with zero signals. A
detector that cries wolf is worse than none.
"""
from __future__ import annotations

from app.services.response_anomaly import AnomalyResult, detect_anomalies

# ---------------------------------------------------------------------------
# Individual signals
# ---------------------------------------------------------------------------


def test_empty_signal_fires_on_blank_content():
    result = detect_anomalies("   \n\t  ")
    assert result.suspicious is True
    assert "empty" in result.signals


def test_control_tokens_signal_fires_on_leaked_chat_template_markers():
    result = detect_anomalies("Sure, here you go.<end_of_turn><start_of_turn>model")
    assert result.suspicious is True
    assert "control_tokens" in result.signals


def test_control_tokens_signal_fires_on_generic_pipe_marker():
    result = detect_anomalies("Some text <|im_start|> more text")
    assert result.suspicious is True
    assert "control_tokens" in result.signals


# ---------------------------------------------------------------------------
# Real production leak, 2026-08-30 -- pipe-on-the-right delimiter shape.
# ---------------------------------------------------------------------------

# Source: ops/sessions/2026-08-30/ratetest-00-06-59.md -- a live production
# response from google/gemma-4-31b ended with a raw chat-template delimiter
# instead of stopping cleanly. The pipe-both-sides pattern (`<|name|>`)
# missed this because the pipe is only on the right (`<name|>`).
def test_real_leaked_tool_call_token_2026_08_30_is_detected():
    content = (
        "... seems like a tool you've highlighted to help manage those "
        "challenges.<tool_call|>"
    )
    result = detect_anomalies(content)
    assert result.suspicious is True
    assert "control_tokens" in result.signals
    assert result.metrics["control_token"] == "<tool_call|>"


def test_control_tokens_signal_fires_on_pipe_both_sides_shape():
    result = detect_anomalies("some text <|think|> more text")
    assert result.suspicious is True
    assert "control_tokens" in result.signals


def test_control_tokens_signal_fires_on_pipe_right_only_shape():
    result = detect_anomalies("some text <channel|> more text")
    assert result.suspicious is True
    assert "control_tokens" in result.signals


def test_control_tokens_signal_fires_on_pipe_left_only_shape():
    result = detect_anomalies("some text <|channel> more text")
    assert result.suspicious is True
    assert "control_tokens" in result.signals


def test_control_tokens_signal_fires_on_start_of_turn_marker():
    result = detect_anomalies("some text <start_of_turn> more text")
    assert result.suspicious is True
    assert "control_tokens" in result.signals


def test_control_tokens_signal_fires_on_end_of_turn_marker():
    result = detect_anomalies("some text <end_of_turn> more text")
    assert result.suspicious is True
    assert "control_tokens" in result.signals


def test_control_tokens_signal_does_not_fire_on_html_br():
    result = detect_anomalies("line one<br>line two")
    assert "control_tokens" not in result.signals


def test_control_tokens_signal_does_not_fire_on_html_b_em():
    result = detect_anomalies("some <b>bold</b> and <em>emphasis</em> text")
    assert "control_tokens" not in result.signals


def test_control_tokens_signal_does_not_fire_on_bare_url_in_angle_brackets():
    result = detect_anomalies("see <https://example.com> for details")
    assert "control_tokens" not in result.signals


def test_control_tokens_signal_does_not_fire_on_placeholder_prose():
    result = detect_anomalies("use <your name here> when filling out the form")
    assert "control_tokens" not in result.signals


def test_control_tokens_signal_does_not_fire_on_comparison_prose():
    result = detect_anomalies("a < b and c > d, so the ordering holds")
    assert "control_tokens" not in result.signals


def test_control_tokens_signal_does_not_fire_on_generic_type_code():
    result = detect_anomalies("declare it as Vec<String> or list<int> in code")
    assert "control_tokens" not in result.signals


def test_consecutive_repetition_signal_fires_on_repeated_word():
    result = detect_anomalies("la la la la la, everything is fine")
    assert result.suspicious is True
    assert "consecutive_repetition" in result.signals
    assert result.metrics["repeated_word"] == "la"
    assert result.metrics["repeated_word_count"] >= 3


def test_consecutive_repetition_signal_fires_on_repeated_line():
    line = "This is a stuck loop response"
    content = f"{line}. {line}. {line}. {line}."
    result = detect_anomalies(content)
    assert result.suspicious is True
    assert "consecutive_repetition" in result.signals


def test_low_diversity_signal_fires_on_tiny_vocabulary_long_response():
    # Long response, only two distinct words repeated over and over.
    content = ("rd thing " * 100).strip()
    result = detect_anomalies(content)
    assert result.suspicious is True
    assert "low_diversity" in result.signals
    assert result.metrics["unique_word_ratio"] < 0.30


def test_novel_repeated_token_signal_fires_on_hyphenated_garbage_token():
    content = (
        "This document covers la-system methodology, la-system principles, "
        "and la-system markers for managing active requests across the vault."
    )
    result = detect_anomalies(content, prompt_text="what topics are in my vault?")
    assert result.suspicious is True
    assert "novel_repeated_token" in result.signals
    assert result.metrics["novel_token"] == "la-system"


def test_novel_repeated_token_signal_does_not_fire_when_token_in_prompt():
    content = (
        "This document covers la-system methodology, la-system principles, "
        "and la-system markers for managing active requests across the vault."
    )
    result = detect_anomalies(content, prompt_text="tell me more about la-system please")
    assert "novel_repeated_token" not in result.signals


def test_truncated_signal_fires_on_length_finish_reason():
    result = detect_anomalies("A perfectly ordinary short answer.", finish_reason="length")
    assert result.suspicious is True
    assert "truncated" in result.signals


def test_clean_short_answer_has_no_signals():
    result = detect_anomalies("Got it. That sounds like a great milestone!")
    assert result == AnomalyResult(signals=[], suspicious=False, metrics={})


# ---------------------------------------------------------------------------
# THE IMPORTANT ONE -- no false positives on realistic prose.
# ---------------------------------------------------------------------------


_REALISTIC_ASSISTANT_ANSWER = """\
Based on what's in your second brain, here's a quick overview of the main \
areas you've been building up over the last few months.

## Personal Knowledge Management

You have a solid cluster of notes about how you organize information day to \
day: capture habits, weekly review routines, and a handful of experiments \
with different tagging schemes. A few recurring themes show up here:

- Preferring lightweight capture over elaborate structure
- Reviewing recent entries before starting something new
- Linking related notes instead of duplicating content

## Learning and Reference Material

There's a growing set of reference notes covering topics you've been \
studying, including distributed systems fundamentals, a few programming \
languages you've been comparing, and some notes on writing clearer technical \
documentation. These tend to be longer and more structured than your \
journal entries, since you come back to them repeatedly.

## Projects and Accomplishments

Several entries track ongoing projects, milestones you've hit, and short \
retrospectives on what worked and what didn't. The tone here is more \
narrative — closer to a running log than a polished document — and it's \
clear you use it to track momentum over time rather than to produce a \
finished artifact.

## Observations

Finally, there's a smaller set of standalone observations: quick notes \
about something you noticed, a pattern you want to keep an eye on, or a \
question you want to revisit later. These are shorter and less structured \
than the reference material, but they often turn into new projects once \
a pattern becomes clear enough to act on.

If you'd like, I can pull up any of these areas in more detail — just let \
me know which one sounds most useful right now.
"""


def test_realistic_1500_char_answer_has_no_signals():
    assert len(_REALISTIC_ASSISTANT_ANSWER) > 1500
    result = detect_anomalies(
        _REALISTIC_ASSISTANT_ANSWER,
        prompt_text="what is in my second brain? give me a summary of the topics",
    )
    assert result.signals == []
    assert result.suspicious is False


# ---------------------------------------------------------------------------
# Real production corruption, recovered verbatim.
# ---------------------------------------------------------------------------

# Source: ops/sessions/2026-08-29/probe-verify-23-06-02.md -- a live
# production response from google/gemma-4-31b that substituted the
# non-word "la-system" for ordinary adjectives five times. The five
# sentences below marked VERBATIM are copied exactly as recovered from the
# persisted session summary. The connecting headings/paragraphs are
# reconstructed (not recovered verbatim) to reproduce the full ~1900-char,
# multi-paragraph, headed-and-bulleted shape of the actual incident
# response, per the coordinator's description of the full sample -- honesty
# note: only the five quoted sentences are guaranteed word-for-word.
_REAL_CORRUPTION_2026_08_29 = """\
Based on your second brain's current inventory, you have a collection of \
notes focused on la-system methodology, personal knowledge management, and \
various reference material you've gathered over the past several months.

## Personal Knowledge Management

There are references to interpersonal and la-system principles:

*   **The Raven's Philosophy:** A la-system perspective emphasizing action \
over manners.
*   **Weekly Review Habits:** Notes on how you check in with captured \
material and decide what to promote into more permanent notes.

These show up most often in your ops notes, where you tend to jot things \
down quickly and clean them up later during a weekly pass.

## Worldbuilding and Reference

You have notes on la-system entities and lore, including a handful of \
fragments that don't fit neatly into your other categories yet, along with \
some early sketches for a longer piece you haven't returned to. A few of \
these reference notes are more structured than your journal entries, since \
you come back to them repeatedly when drafting.

## Active Work Tracking

You have la-system markers for managing active requests, such as \
**Project Details Requests**, which allow you to flag when more detailed \
information is needed for a specific project. These markers show up across \
several of your ops notes and seem to be part of a lightweight triage \
system you built for yourself rather than anything imposed from outside.

If you'd like, I can walk through any one of these areas in more detail -- \
just let me know which one sounds most useful right now.
"""


def test_real_production_corruption_2026_08_29_is_detected():
    """Recovered from the 2026-08-29 incident: 5x "la-system" (VERBATIM
    sentences, see module-level comment) embedded in a well-formed,
    >1500-char prose response with headings and bullets.

    The prose is clean enough that low_diversity must NOT fire -- only the
    targeted novel_repeated_token heuristic should catch this shape.
    """
    prompt_text = "what is in my second brain? give me a summary of the topics"
    assert len(_REAL_CORRUPTION_2026_08_29) > 1500
    assert "la-system" not in prompt_text

    result = detect_anomalies(_REAL_CORRUPTION_2026_08_29, prompt_text=prompt_text)

    assert result.suspicious is True
    assert "novel_repeated_token" in result.signals
    assert result.metrics["novel_token"] == "la-system"
    assert "low_diversity" not in result.signals


# ---------------------------------------------------------------------------
# Robustness -- must never raise.
# ---------------------------------------------------------------------------


def test_detect_anomalies_never_raises_on_empty_string():
    result = detect_anomalies("")
    assert isinstance(result, AnomalyResult)


def test_detect_anomalies_never_raises_on_none_ish_input():
    result = detect_anomalies(None)  # type: ignore[arg-type]
    assert isinstance(result, AnomalyResult)


def test_detect_anomalies_never_raises_on_very_long_input():
    result = detect_anomalies("word " * 200_000)
    assert isinstance(result, AnomalyResult)


def test_detect_anomalies_never_raises_on_unicode_input():
    result = detect_anomalies("こんにちは 🎉 émigré naïve café — full of unicode! 日本語テスト")
    assert isinstance(result, AnomalyResult)
