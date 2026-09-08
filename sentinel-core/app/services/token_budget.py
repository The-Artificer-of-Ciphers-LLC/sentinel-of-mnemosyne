"""Token counting and context window enforcement.

Uses tiktoken cl100k_base as an approximate tokenizer for local models.
cl100k_base is a safe over-estimate — false positives (rejecting valid messages)
fail safely. False negatives are bounded by LM Studio's own rejection.

**The approximation is accepted, and ADR-0007 step 5 makes it NAMED rather than
assumed.** cl100k_base is not Qwen's tokenizer and counting stays approximate;
shipping a real per-family tokenizer is a container-weight decision the ADR
deliberately leaves open, and no tokenizer dependency is added here. What
changed is that a profile now says which encoding its counts were taken with
(``app.model.ModelProfile.tokenizer_encoding``), and an encoding tiktoken does
not recognise DEGRADES LOUDLY to cl100k_base instead of raising —
``tiktoken.get_encoding`` raises ``ValueError`` on an unknown name, and this
sits on the chat path, where an unrecognised name must never take down message
processing.

The TokenBudget class owns a single cached encoding instance, providing
count(), check(), and truncate() behind one interface.

Replaces: app/services/token_guard.py (count_tokens, check_token_limit)
Absorbs:  message_processing._truncate_to_tokens (duplicate encoding logic)
"""

import logging
from typing import Any

import tiktoken

from app.errors import InternalError

logger = logging.getLogger(__name__)

#: The encoding every count falls back to. Safe over-estimate; see the module
#: docstring for why it is accepted rather than fixed.
DEFAULT_ENCODING = "cl100k_base"


def _load_encoding(name: str) -> tuple[str, "tiktoken.Encoding"]:
    """Return ``(encoding_name_in_use, encoding)``, degrading rather than raising.

    ``tiktoken.get_encoding`` raises on an unrecognised name. This sits on the
    chat path, so an unknown name must be survivable: it is logged at WARNING
    and cl100k_base is used instead. The returned name is the one in use, so
    ``encoding_name`` never reports an encoding that was not actually applied.
    """
    if not name:
        name = DEFAULT_ENCODING
    try:
        return name, tiktoken.get_encoding(name)
    except Exception as exc:  # noqa: BLE001 - any tiktoken refusal degrades alike
        logger.warning(
            "Tokenizer encoding %r is not recognised by tiktoken (%s: %s) — "
            "counting with %s instead. Counts stay approximate; the request is "
            "not failed over a tokenizer name",
            name,
            type(exc).__name__,
            exc,
            DEFAULT_ENCODING,
        )
        return DEFAULT_ENCODING, tiktoken.get_encoding(DEFAULT_ENCODING)


class TokenLimitError(InternalError):
    """Raised when token count exceeds the context window."""

    def __init__(self, count: int, limit: int) -> None:
        self.count = count
        self.limit = limit
        super().__init__(f"Message too long: {count} tokens exceeds {limit} limit")


class TokenBudget:
    """Token counting and truncation with a single cached encoding instance.

    The encoding is created once at construction — subsequent calls reuse it.
    Default encoding is "cl100k_base" (OpenAI-compatible).

    An encoding name tiktoken does not recognise is a WARNING and a fall back to
    ``DEFAULT_ENCODING``, never an exception. ``encoding_name`` then reports the
    encoding actually in use, not the one that was asked for — a budget that
    claimed an encoding it is not using would make the naming worthless.

    Attributes:
        encoding_name: The tiktoken encoding name used for counting/truncation.
    """

    def __init__(self, encoding: str = DEFAULT_ENCODING) -> None:
        self._encoding_name, self._enc = _load_encoding(encoding)

    @classmethod
    def for_profile(cls, profile: Any) -> "TokenBudget":
        """The budget for a resolved model profile's declared encoding.

        A profile that names nothing gets ``DEFAULT_ENCODING`` silently — that
        is the ordinary case, not a misconfiguration worth a warning.
        """
        return cls(getattr(profile, "tokenizer_encoding", "") or DEFAULT_ENCODING)

    @property
    def encoding_name(self) -> str:
        """The tiktoken encoding actually used by this budget."""
        return self._encoding_name

    def count(self, messages: list[dict]) -> int:
        """Approximate token count for an OpenAI-format messages array.

        Follows the OpenAI cookbook formula:
          - 3 tokens overhead per message (role, content, separator)
          - token count of each key's string value
          - 3 tokens for reply priming

        Args:
            messages: OpenAI-format message array.

        Returns:
            Approximate token count (integer).
        """
        num_tokens = 0
        for message in messages:
            num_tokens += 3  # per-message overhead
            for value in message.values():
                num_tokens += len(self._enc.encode(str(value)))
        num_tokens += 3  # reply priming
        return num_tokens

    def check(self, messages: list[dict], context_window: int) -> None:
        """Raise TokenLimitError if messages exceed the window.

        Args:
            messages: OpenAI-format message array.
            context_window: Maximum allowed token count.

        Raises:
            TokenLimitError: If message count exceeds context_window.
        """
        count = self.count(messages)
        if count > context_window:
            raise TokenLimitError(count, context_window)

    def truncate(self, text: str, max_tokens: int) -> str:
        """Truncate text to fit within max_tokens.

        Encodes the full text, keeps the first max_tokens tokens,
        decodes back to a string, and appends a truncation marker.

        Args:
            text: The text to truncate.
            max_tokens: Maximum number of tokens to keep (not including marker).

        Returns:
            Truncated text with truncation marker appended if truncation occurred.
                If the text fits within max_tokens, returns it unchanged.
        """
        tokens = self._enc.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return self._enc.decode(tokens[:max_tokens]) + "\n\n[...context truncated to fit token budget]"
