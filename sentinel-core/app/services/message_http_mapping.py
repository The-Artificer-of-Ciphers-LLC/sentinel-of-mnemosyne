"""HTTP mapping for message-route exceptions."""

from __future__ import annotations

from fastapi import HTTPException

from app.errors import (
    ContextError,
    MessageProcessingError,
    ProviderUnavailableError,
    SecurityError,
)


def map_message_exception(exc: Exception) -> HTTPException:
    if isinstance(exc, MessageProcessingError):
        match getattr(exc, "code", None):
            case "context_overflow":
                status_code = 422
            case "provider_unavailable":
                status_code = 503
            case "security_blocked":
                status_code = 500
            case _:
                status_code = 502
        return HTTPException(status_code=status_code, detail=str(exc))

    if isinstance(exc, SecurityError):
        return HTTPException(status_code=500, detail=str(exc))
    if isinstance(exc, ProviderUnavailableError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, ContextError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=502, detail=str(exc))
