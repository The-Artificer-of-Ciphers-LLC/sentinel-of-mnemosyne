"""Domain error hierarchy for Sentinel Core.

All exceptions that cross a module boundary (services → routes, or services
→ other services) must inherit from this hierarchy.  This gives every error a
stable type that routes can match on, and gives tests a single import point
for all error assertions.

Hierarchy:

    SentinelError  →  Exception
    ├── DomainError          # user/admin-actionable — routes match on these
    │   ├── ContextError       # token budget exceeded, context overflow
    │   ├── SecurityError      # response blocked by output scanner
    │   └── WorkflowError      # entry not found, inbox conflict, sweep in progress
    ├── InfrastructureError  # external system failures — graceful degrade handles these
    │   ├── VaultUnreachableError
    │   ├── ProviderUnavailableError
    │   └── ProviderError
    └── InternalError        # bugs in the system — should never reach routes (502)

Backward compatibility: original class names are preserved as subclasses of
the hierarchy.  Any external code importing ``from app.vault import
VaultUnreachableError`` continues to work — it is just now also a
``SentinelError``.

ADR-0001 (startup contract) and ADR-0002 (vault seam location) are not
affected — they reference ``VaultUnreachableError`` by name, which still
exists as a concrete class.
"""

# ── Base classes ────────────────────────────────────────────────────────────


class SentinelError(Exception):
    """Base for all domain-layer errors that cross module boundaries."""


# ── DomainError — user/admin-actionable (routes match on these) ─────────────


class DomainError(SentinelError):
    """Domain workflow violation — the user or operator should act on this."""


class ContextError(DomainError):
    """Token budget exceeded, context overflow.

    Mirrors the original ``MessageProcessingError(code='context_overflow')``
    contract but with a stable type for route matching.  The original message
    string is available via ``str(exc)``.
    """


class SecurityError(DomainError):
    """Response blocked by output scanner — potential secret leakage."""


class WorkflowError(SentinelError):
    """Workflow state violation (entry not found, inbox conflict, sweep in progress)."""


class EntryNotFound(WorkflowError):
    """Raised when an inbox entry N does not exist."""


class InboxChangedConflict(WorkflowError):
    """Raised when the inbox was modified between read and write."""


class SweepInProgressError(WorkflowError):
    """Raised when a fresh lockfile blocks a new sweep."""


# ── InfrastructureError — expected failures, graceful degrade handles these ──


class InfrastructureError(SentinelError):
    """External system failure — handled by existing try/except + degrade logic.

    These are *expected* in the Sentinel architecture (vault being down,
    AI provider timing out).  They are included for locality — new
    infrastructure errors do not silently become bare ``Exception`` — and
    testability (you can assert on exact failure types).

    Routes do NOT match on these; existing service-layer try/except blocks
    handle them before they reach route handlers.
    """


class VaultUnreachableError(InfrastructureError):
    """Raised when the vault is unreachable (transport failure / 5xx).

    Preserved from ``app.vault`` for backward compatibility.  Pairs with
    ADR-0001: vault-up + persona 404 → hard fail; vault-down → graceful
    degrade.
    """


class ProviderUnavailableError(InfrastructureError):
    """Raised when primary (and fallback, if configured) providers both fail.

    Preserved from ``app.services.provider_router`` for backward compatibility.
    """


class ProviderError(InfrastructureError):
    """HTTP errors from the AI backend (rate limits, auth failures).

    These are *not* fallback triggers — they propagate unchanged to the
    caller (ProviderRouter only falls back on connectivity errors).
    """


class ContextLengthError(DomainError):
    """Raised when a provider rejects a completion because the prompt+context
    exceeds model capacity.

    Originally defined in ``app.services.provider_router`` but semantically a
    domain concept ("your prompt is too long"), not an infrastructure failure.

    Translated from vendor ``BadRequestError`` in
    ``app.clients.litellm_provider``.
    """


# ── InternalError — bugs in the system (should never reach routes) ──────────


class InternalError(SentinelError):
    """Programming mistake — should never reach route handlers (maps to 502)."""


class ModelSelectorError(InternalError):
    """Raised when no model can be resolved: empty discovery AND no default."""


# ── Infrastructure errors that live in clients/ or services/ but should
#    also be typed here for hierarchy completeness ───────────────────────────


class EmbeddingModelUnavailable(InfrastructureError):
    """Raised when LM Studio reports no embedding model loaded.

    Originally defined in ``app.clients.embeddings``; vendor SDK exception
    translation lives there for the AI-agnostic guardrail.  This subclass
    gives it a stable type for tests and future route handling.
    """


class TokenLimitError(InternalError):
    """Raised when token count exceeds the context window.

    Originally defined in ``app.services.token_budget``.  It is an
    InternalError because it represents a bug in the caller's budgeting
    logic (the message should have been truncated before reaching this
    point).  If it escapes, the route handler returns 502.
    """


class MessageProcessingError(DomainError):
    """Original error class — preserved for backward compatibility.

    This class used to carry a ``code`` string attribute.  New code should
    use the typed subclasses (ContextError, SecurityError) instead of this
    generic class.  The ``code`` attribute is preserved on instances for
    logging and test compatibility, but route handlers should match on the
    specific error type.

    This class itself is a DomainError so that existing code catching it
    continues to work.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code  # type: ignore[reportAttributeAccessIssue]
        super().__init__(message)
