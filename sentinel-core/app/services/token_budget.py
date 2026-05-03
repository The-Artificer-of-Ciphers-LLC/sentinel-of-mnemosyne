"""Token counting and context window enforcement.

Uses tiktoken cl100k_base as an approximate tokenizer for local models.
cl100k_base is a safe over-estimate — false positives (rejecting valid messages)
fail safely. False negatives are bounded by LM Studio's own rejection.

The TokenBudget class owns a single cached encoding instance, providing
count(), check(), and truncate() behind one interface.

Replaces: app/services/token_guard.py (count_tokens, check_token_limit)
Absorbs:  message_processing._truncate_to_tokens (duplicate encoding logic)
"""

import tiktoken


class TokenLimitError(Exception):
    """Raised when token count exceeds the context window."""

    def __init__(self, count: int, limit: int) -> None:
        self.count = count
        self.limit = limit
        super().__init__(f"Message too long: {count} tokens exceeds {limit} limit")


class TokenBudget:
    """Token counting and truncation with a single cached encoding instance.

    The encoding is created once at construction — subsequent calls reuse it.
    Default encoding is "cl100k_base" (OpenAI-compatible).

    Attributes:
        encoding_name: The tiktoken encoding name used for counting/truncation.
    """

    def __init__(self, encoding: str = "cl100k_base") -> None:
        self._encoding_name = encoding
        self._enc = tiktoken.get_encoding(encoding)

    @property
    def encoding_name(self) -> str:
        """The tiktoken encoding name used by this budget."""
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
