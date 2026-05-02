"""Compose root for Sentinel Core.

Constructs the application graph from a flat ``AppGraph`` dataclass. Lifespan
delegates wiring here so the construction logic is independently testable.

This module is introduced incrementally:

- Task 1 (this commit): defines ``AppGraph`` only. No ``build_*`` functions.
- Task 2: adds ``build_provider_router``.
- Task 5: adds ``build_application``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    import httpx

    from app.clients.embeddings import Embeddings
    from app.config import Settings
    from app.services.injection_filter import InjectionFilter
    from app.services.message_processing import MessageProcessor
    from app.services.model_registry import ModelInfo
    from app.services.output_scanner import OutputScanner
    from app.services.provider_router import ProviderRouter
    from app.vault import Vault


@dataclass(frozen=True)
class AppGraph:
    """Frozen application graph constructed by ``build_application``.

    Tests construct fakes via explicit kwargs (W1) and assert on observable
    graph state. Lifespan pins each field onto ``app.state`` for back-compat
    with existing routes/tests (Q4(a)).
    """

    settings: "Settings"
    http_client: "httpx.AsyncClient"
    model_registry: "dict[str, ModelInfo]"
    context_window: int
    lmstudio_stop_sequences: list[str]
    ai_provider: "ProviderRouter"
    ai_provider_name: str
    vault: "Vault"
    embedding_model_loaded: bool
    injection_filter: "InjectionFilter"
    output_scanner: "OutputScanner"
    message_processor: "MessageProcessor"
    module_registry: dict[str, Any]
    embeddings: "Embeddings"
    note_classifier_fn: Callable[[str], Awaitable[Any]]
