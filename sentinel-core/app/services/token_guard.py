"""
Token counting and context window enforcement.
Uses tiktoken cl100k_base as an approximate tokenizer for local models.
cl100k_base is a safe over-estimate — false positives (rejecting valid messages)
fail safely. False negatives are bounded by LM Studio's own rejection.
"""
import tiktoken


class TokenLimitError(Exception):
    """Raised when token count exceeds the model's context window."""
    def __init__(self, count: int, limit: int) -> None:
        self.count = count
        self.limit = limit
        super().__init__(f"Message too long: {count} tokens exceeds {limit} limit")


def count_tokens(messages: list[dict]) -> int:
    """
    Approximate token count for an OpenAI-format messages array.
    Follows the OpenAI cookbook formula:
      - 3 tokens overhead per message (role, content, separator)
      - token count of each key's string value
      - 3 tokens for reply priming
    """
    enc = tiktoken.get_encoding("cl100k_base")
    num_tokens = 0
    for message in messages:
        num_tokens += 3  # per-message overhead
        for value in message.values():
            num_tokens += len(enc.encode(str(value)))
    num_tokens += 3  # reply priming
    return num_tokens


def check_token_limit(messages: list[dict], context_window: int) -> None:
    """Raise TokenLimitError if messages exceed context_window."""
    count = count_tokens(messages)
    if count > context_window:
        raise TokenLimitError(count, context_window)
