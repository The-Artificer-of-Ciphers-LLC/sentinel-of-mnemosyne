"""Pure detector for degenerate/anomalous LLM chat-completion output.

WHY THIS EXISTS:
The local chat model (google/gemma-4-31b, served over an LM Studio LM Link
tunnel) intermittently emits degenerate output. One live production response
on 2026-08-29 contained the non-word "la-system" four times in place of
ordinary adjectives. Seven subsequent identical requests were clean, so the
rate is low and the fault could NOT be reproduced on demand. Historically
this model has also produced "la la la", "rdrdrdrd", raw
``<start_of_turn>``/``<end_of_turn>`` markers, and repetition loops when its
serving configuration is wrong.

The point of this module is NOT to fix or block that -- it is to make the
fault MEASURABLE. Right now a garbled answer is invisible unless a human
happens to read it, which is exactly how a silent index degradation went
unnoticed for a month in this same system. We need a real rate before
changing any serving configuration.

``detect_anomalies`` is pure: no I/O, no logging, never raises. Callers own
what to do with the result (log it, count it, alert on it). This module does
NOT gate or alter responses -- that is ``output_scanner``'s job.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

# --- Signal (c): consecutive_repetition constants ---------------------------
# Same word repeated back-to-back this many times or more (catches "la la la").
_CONSECUTIVE_WORD_REPEAT_MIN = 3
# Same non-trivial line/sentence repeated this many times or more.
_CONSECUTIVE_LINE_REPEAT_MIN = 3

# --- Signal (d): low_diversity constants ------------------------------------
# Below this many words, vocabulary is naturally repetitive (short replies
# like "Got it.") -- skip the check entirely to avoid false positives on
# short, clean answers.
_LOW_DIVERSITY_MIN_WORDS = 60
# Unique-word ratio (unique / total, case-folded) below this on a
# long-enough response indicates a degenerate loop. A normal multi-paragraph
# answer with headings/bullets/prose (including the real ~1900-char
# corrupted-but-otherwise-prose sample recovered 2026-08-29, see
# ops/sessions/2026-08-29/probe-verify-23-06-02.md) sits well above this;
# degenerate loops ("la la la la...") collapse to a handful of unique tokens
# repeated many times, well under this ratio.
_LOW_DIVERSITY_RATIO_THRESHOLD = 0.30

# --- Signal (e): novel_repeated_token constants -----------------------------
# Hyphenated tokens whose leading fragment is at most this many characters
# are treated as a suspicious shape (e.g. "la-system", "rd-thing").
_NOVEL_TOKEN_FRAGMENT_MAX_LEN = 3
# Must repeat at least this many times in content to count as a signal.
# The real 2026-08-29 sample had "la-system" appear 5 times, giving margin.
_NOVEL_TOKEN_MIN_REPEATS = 3

# Log-excerpt cap used by callers (kept here so callers share one constant).
EXCERPT_MAX_CHARS = 200

_CONTROL_TOKEN_PATTERN = re.compile(
    r"<start_of_turn>|<end_of_turn>|<\|[^|>]{1,32}\|?>"
)

_WORD_PATTERN = re.compile(r"[A-Za-z0-9']+(?:-[A-Za-z0-9']+)*")

_HYPHEN_TOKEN_PATTERN = re.compile(
    r"\b[A-Za-z]{1,%d}-[A-Za-z]+\b" % _NOVEL_TOKEN_FRAGMENT_MAX_LEN
)


@dataclass(frozen=True)
class AnomalyResult:
    """Result of ``detect_anomalies``. Frozen -- callers must not mutate.

    ``signals`` names every heuristic that tripped (empty list = clean).
    ``metrics`` carries small supporting values (offending token,
    repetition counts, unique-word ratio) for logging/debugging.
    """

    signals: list[str] = field(default_factory=list)
    suspicious: bool = False
    metrics: dict[str, object] = field(default_factory=dict)


def _max_consecutive_repeat(seq: list[str]) -> tuple[str, int]:
    """Return (value, run_length) for the longest run of an identical,
    consecutive, non-empty item in ``seq``. ("", 0) if seq is empty."""
    best_val = ""
    best_run = 0
    prev: str | None = None
    run = 0
    for item in seq:
        if item == prev:
            run += 1
        else:
            run = 1
            prev = item
        if run > best_run:
            best_run = run
            best_val = item
    return best_val, best_run


def _detect_anomalies_impl(
    content: str, prompt_text: str, finish_reason: str | None
) -> AnomalyResult:
    text = content if isinstance(content, str) else str(content or "")
    signals: list[str] = []
    metrics: dict[str, object] = {}

    # (a) empty
    if not text.strip():
        signals.append("empty")

    # (b) control_tokens -- raw chat-template markers must never leak.
    control_match = _CONTROL_TOKEN_PATTERN.search(text)
    if control_match:
        signals.append("control_tokens")
        metrics["control_token"] = control_match.group(0)

    # (c) consecutive_repetition -- same word or same line 3+ times running.
    words = _WORD_PATTERN.findall(text.lower())
    rep_word, rep_word_count = _max_consecutive_repeat(words)
    lines = [ln.strip() for ln in re.split(r"[\n.!?]+", text) if ln.strip()]
    rep_line, rep_line_count = _max_consecutive_repeat(lines)
    if (
        rep_word_count >= _CONSECUTIVE_WORD_REPEAT_MIN
        or rep_line_count >= _CONSECUTIVE_LINE_REPEAT_MIN
    ):
        signals.append("consecutive_repetition")
        if rep_word_count >= _CONSECUTIVE_WORD_REPEAT_MIN:
            metrics["repeated_word"] = rep_word
            metrics["repeated_word_count"] = rep_word_count
        if rep_line_count >= _CONSECUTIVE_LINE_REPEAT_MIN:
            metrics["repeated_line"] = rep_line[:80]
            metrics["repeated_line_count"] = rep_line_count

    # (d) low_diversity -- tiny vocabulary relative to length, long enough
    # that natural prose would never look like this.
    if len(words) >= _LOW_DIVERSITY_MIN_WORDS:
        unique_ratio = len(set(words)) / len(words)
        metrics["unique_word_ratio"] = round(unique_ratio, 3)
        if unique_ratio < _LOW_DIVERSITY_RATIO_THRESHOLD:
            signals.append("low_diversity")

    # (e) novel_repeated_token -- narrow, targeted heuristic for the actual
    # observed defect (short-hyphen-fragment tokens like "la-system"). This
    # will NOT catch every corruption class -- it only catches this shape.
    prompt_lower = prompt_text.lower() if isinstance(prompt_text, str) else ""
    hyphen_counts = Counter(m.group(0).lower() for m in _HYPHEN_TOKEN_PATTERN.finditer(text))
    for token, count in hyphen_counts.items():
        if count >= _NOVEL_TOKEN_MIN_REPEATS and token not in prompt_lower:
            signals.append("novel_repeated_token")
            metrics["novel_token"] = token
            metrics["novel_token_count"] = count
            break

    # (f) truncated -- model ran to the token ceiling without emitting a stop.
    if finish_reason == "length":
        signals.append("truncated")

    return AnomalyResult(signals=signals, suspicious=bool(signals), metrics=metrics)


def detect_anomalies(
    content: str, *, prompt_text: str = "", finish_reason: str | None = None
) -> AnomalyResult:
    """Inspect a completed LLM response for signs of degenerate output.

    Pure function: no I/O, no logging. Never raises -- any internal failure
    degrades to a clean (no-signals) result so this can never become a
    second failure mode on top of whatever it's trying to observe.
    """
    try:
        return _detect_anomalies_impl(content, prompt_text, finish_reason)
    except Exception:
        return AnomalyResult(signals=[], suspicious=False, metrics={})
