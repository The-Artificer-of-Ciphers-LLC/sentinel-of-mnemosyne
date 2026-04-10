"""
AIProvider Protocol — the single interface all AI backend clients must implement.
LiteLLMProvider is the primary implementation. OllamaProvider and LlamaCppProvider are stubs.
"""
from typing import Protocol


class AIProvider(Protocol):
    """
    Protocol for all AI backend clients.
    Implementations: LiteLLMProvider (primary), OllamaProvider (stub), LlamaCppProvider (stub).
    """

    async def complete(self, messages: list[dict]) -> str:
        """
        Submit messages list to the AI backend and return the assistant's text response.
        Raises on unrecoverable error (caller is responsible for fallback routing).
        Transient errors are retried internally before raising.
        """
        ...
