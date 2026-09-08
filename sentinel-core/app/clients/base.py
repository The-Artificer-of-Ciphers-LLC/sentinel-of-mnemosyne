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

    async def complete(
        self,
        messages: list[dict],
        stop: list[str] | None = None,
        temperature: float | None = None,
    ) -> str:
        """
        Submit messages list to the AI backend and return the assistant's text response.
        Raises on unrecoverable error (caller is responsible for fallback routing).
        Transient errors are retried internally before raising.

        stop: Both LiteLLMProvider and ProviderRouter have accepted this parameter
        since Phase 42, but the Protocol did not declare it, so MessageProcessor
        (typed against this Protocol) silently dropped it on the chat path.

        temperature: Forwarded to the backend when not None.
        """
        ...
