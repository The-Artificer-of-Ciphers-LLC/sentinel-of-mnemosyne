"""HTTP mapping for message processing domain errors."""

from __future__ import annotations


def to_http_status(code: str) -> int:
    if code == "context_overflow":
        return 422
    if code == "provider_unavailable":
        return 503
    if code == "provider_misconfigured":
        return 502
    if code == "security_blocked":
        return 500
    return 502
