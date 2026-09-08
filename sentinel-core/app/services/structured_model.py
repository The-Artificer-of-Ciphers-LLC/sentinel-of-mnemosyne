"""The process-wide handle on the Active model seam, for structured callers.

ADR-0007 step 4. ``model_resolution.resolve_structured_model`` used to answer
"which model does the structured path use" with its own discovery call, its own
per-model capability fan-out and its own scoring pass — a second implementation
of the question ``app/model.py`` now owns. This module holds **no resolution
logic at all**: it is a one-object registry so the five structured-completion
call sites can reach the SAME :class:`~app.model.ActiveModel` the chat path
resolves through.

Why a process-level handle rather than dependency injection: the five callers
(``note_classifier.classify_note`` and the four ``six_rs`` / orchestrator
stages) are module-level coroutines with no graph reference to thread a seam
through. Sharing one object is also what makes the ADR's stated latency
consequence real — a 6 Rs pipeline run used to issue roughly ``1 + N + 1``
metadata fetches, one per stage plus one per loaded model; through a shared
seam it issues at most one model-list fetch per TTL window for the whole run.

The four dependency-injection keyword overrides ``resolve_structured_model``
carried existed only so tests could substitute fakes. They are deliberately NOT
carried forward: the seam's substitute for a live backend is
:class:`~app.model.StaticModelSource`, a real adapter, and a test that wants a
different backend registers a real ``ActiveModel`` over one via
:func:`set_structured_active_model`.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    import httpx

    from app.model import ActiveModel, ModelProfile

logger = logging.getLogger(__name__)

#: Registered by ``composition.initialize_startup`` so the structured path and
#: the chat path share one seam, one TTL window and one last-known-good memory.
_active_model: "ActiveModel | None" = None

#: Only ever populated by the lazy fallback below, and only outside a normal
#: application start (a script, a REPL, a test that never composed the graph).
_lazy_client: "httpx.AsyncClient | None" = None


def set_structured_active_model(active_model: "ActiveModel | None") -> None:
    """Register the seam the structured call sites resolve through."""
    global _active_model
    _active_model = active_model


def reset_structured_active_model() -> None:
    """Drop the registered seam so the next call resolves afresh. Tests use this.

    Deliberately does NOT drop ``_lazy_client``: that client is never closed,
    so discarding it per reset would leak one socket pool per test rather than
    keeping a single one for the process.
    """
    global _active_model
    _active_model = None


async def _lazily_composed_seam() -> "ActiveModel":
    """Compose a seam for callers that never ran the composition root.

    Deliberately delegates to ``composition.build_active_model`` rather than
    assembling sources here — a second assembly would be a second answer to
    "what does this deployment's seam look like", which is the class of
    duplication this whole step removes. Imported inside the function because
    ``composition`` imports ``note_classifier``, which imports this module.
    """
    global _active_model, _lazy_client

    import httpx  # noqa: PLC0415

    from app.composition import build_active_model  # noqa: PLC0415
    from app.config import settings  # noqa: PLC0415

    if _lazy_client is None:
        _lazy_client = httpx.AsyncClient()
    _active_model = await build_active_model(settings, _lazy_client)
    logger.info(
        "Structured model seam composed lazily — no composition root registered "
        "one for this process"
    )
    return _active_model


async def structured_profile() -> "ModelProfile":
    """The profile a structured-output completion should be made against.

    RAISES ``ModelSelectorError`` when a LIVE backend offers candidates that
    cannot be disambiguated (ADR-0007 decision 4 as amended 2026-09-08). That is
    a different failure from an UNREACHABLE backend, which does not raise at
    all: the seam falls through to ``StaticModelSource`` and answers from
    ``MODEL_NAME``, which is that setting's only surviving role. Callers must
    keep the two apart — a stage that swallows the refusal turns a "the operator
    must say which model" condition back into the phantom-model bug, and a stage
    that treats an offline dev box as fatal makes it unusable.
    """
    seam = _active_model
    if seam is None:
        seam = await _lazily_composed_seam()
    return await seam.for_task("structured")
