"""
AIProvider Protocol — the single interface all AI backend clients must implement.
LiteLLMProvider is the primary implementation. OllamaProvider and LlamaCppProvider are stubs.
"""
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.model import ModelProfile


class AIProvider(Protocol):
    """
    Protocol for all AI backend clients.
    Implementations: LiteLLMProvider (primary), OllamaProvider (stub), LlamaCppProvider (stub).
    """

    async def complete(
        self,
        messages: list[dict],
        profile: "ModelProfile | None" = None,
        stop: list[str] | None = None,
        temperature: float | None = None,
    ) -> str:
        """
        Submit messages list to the AI backend and return the assistant's text response.
        Raises on unrecoverable error (caller is responsible for fallback routing).
        Transient errors are retried internally before raising.

        profile: the ``ModelProfile`` the Active model seam resolved for this call
        (ADR-0007). It carries the model id, the api base, the context window and
        the stop sequences as ONE value, replacing the three loose scalars that
        used to be threaded separately. ``None`` means "use whatever this
        implementation was constructed with" — the static cloud case, and the
        posture every call site had before ADR-0007 step 3.

        **This Protocol is widened FIRST and the implementations follow it, not
        the other way round.** ``stop`` existed on both ``LiteLLMProvider`` and
        ``ProviderRouter`` since Phase 42 while this Protocol declared only
        ``messages``, so ``MessageProcessor`` — typed against the Protocol —
        silently dropped it on the chat path for months (the defect commit
        93df616 fixed). A Protocol that lags its implementations is not a
        contract; it is a way to lose arguments quietly.

        stop: an explicit per-call override of ``profile.stop_sequences``. It
        survives ADR-0007 step 3 because ``POST /provider/complete`` carries a
        ``stop`` field in its request body that a module may set for its own
        prompt shape. When supplied it wins; otherwise the profile answers.

        temperature: Forwarded to the backend when not None.
        """
        ...
