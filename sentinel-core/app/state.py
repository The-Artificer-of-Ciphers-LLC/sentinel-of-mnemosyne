"""Application state for route handlers.

This module defines ``RouteContext``, a single dataclass that bundles every
dependency a route handler needs. Lifespan pins one ``RouteContext`` onto
``app.state.route_ctx`` instead of scattering 15+ individual attributes on
``app.state`` (Q4(a)).

Before this change: every route handler reached into ``request.app.state.X``
for 15+ different fields (vault, settings, context_window, etc.). Adding a
new capability required updating ``composition.py`` AND every route handler.

After this change: routes go through one object (`route_ctx`) — adding a
capability = update RouteContext + pin once.

Backward compatibility: the old ``app.state.X`` fields are still pinned for
existing integration tests that read them directly (see lifespan in ``main.py``
— they pin both old fields AND the new RouteContext).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from fastapi import Request

if TYPE_CHECKING:
    import httpx

    from app.config import Settings
    from app.services.message_processing import MessageProcessor
    from app.vault import Vault

logger = logging.getLogger(__name__)


async def _missing_classifier(*_args: Any, **_kwargs: Any) -> Any:
    raise RuntimeError("note classifier not configured on app state")


async def _missing_embedder(*_args: Any, **_kwargs: Any) -> list[float]:
    raise RuntimeError("note embedder not configured on app state")


@dataclass(frozen=True)
class RouteContext:
    """Single object route handlers use instead of scattered app.state fields."""

    vault: "Vault"
    processor: "MessageProcessor | None" = None
    settings: "Settings | None" = None
    http_client: "httpx.AsyncClient | None" = None
    context_window: int = 4096
    lmstudio_stop_sequences: list[str] = field(default_factory=list)
    classify: Callable[[str], Awaitable[Any]] = _missing_classifier
    embedder: Callable[[list[str]], Awaitable[list[float]]] = _missing_embedder
    module_registry: dict[str, Any] = field(default_factory=dict)
    ai_provider_name: str | None = None


def get_route_context(request: Request) -> RouteContext:
    """Get route context from request.

    Route handlers require ``app.state.route_ctx`` to be pinned by lifespan
    (or explicitly seeded by tests).
    """
    ctx = getattr(request.app.state, "route_ctx", None)
    if ctx is None:
        raise RuntimeError("route_ctx not configured on app state")
    return ctx
