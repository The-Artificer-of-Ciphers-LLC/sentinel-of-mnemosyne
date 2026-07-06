"""Read-only wikilink-graph inspection routes (NOTE-03, SC-3/SC-4).

Endpoints:
  GET /vault/graph  — GraphReport (note_count, orphans, backlinks, hub_count, link_density)
  GET /vault/stats  — condensed stats view over the same GraphReport computation
  GET /vault/check  — per-note NOTE-01 structural compliance (missing _schema /
                      claim-title / wikilink), zero LLM calls (D-05)

Deliberately mirror the `/vault/sweep/*` route shape (``note.py``) in their use
of ``get_route_context``, but carry NO admin gate and NO model-readiness
probe: the sidecar rebuild these routes trigger is pure Python and
non-destructive to user content (research Anti-Patterns; Assumption A3),
unlike the destructive `/vault/sweep/start` route which stays admin-gated.

Each handler calls ``links_sidecar_index.rebuild_links_index_if_stale`` for
D-04a hybrid freshness before computing anything, so a fresh sidecar never
triggers a full vault walk. ``rebuild_links_index_if_stale`` already degrades
internally when the sweep lock is held (never raises to its caller) — the
``SweepInProgressError`` handling below is a defensive route-layer guard for
that documented contract, surfaced as a ``caveat`` field rather than a 500.

/vault/graph and /vault/stats derive an in-memory notes map directly from the
sidecar's already-extracted ``wikilinks`` list (a synthetic ``[[target]]``-only
body reconstruction) so ``graph_analysis.build_graph_report`` can re-derive
edges without any additional per-note vault reads. /vault/check needs actual
note bodies (claim-title / wikilink-presence checks require the real text,
which the sidecar does not store) so it does one ``read_note`` per already-known
path from the index — never a directory walk.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.errors import SweepInProgressError
from app.services import graph_analysis, note_schema
from app.services.links_sidecar_index import (
    LINKS_INDEX_PATH,
    decode_index_body,
    rebuild_links_index_if_stale,
)
from app.state import get_route_context

logger = logging.getLogger(__name__)
router = APIRouter()


# --- Response models ---


class GraphResponse(BaseModel):
    note_count: int
    orphans: list[str]
    backlinks: dict[str, list[str]]
    hub_count: int
    link_density: float
    caveat: str | None = None


class StatsResponse(BaseModel):
    note_count: int
    hub_count: int
    orphan_count: int
    avg_notes_per_hub: float
    link_density: float
    caveat: str | None = None


class NoteCheckEntry(BaseModel):
    path: str
    has_schema: bool
    has_type: bool
    has_claim_title: bool
    has_wikilink: bool
    failures: list[str]


class CheckResponse(BaseModel):
    note_count: int
    compliant_count: int
    results: list[NoteCheckEntry]
    caveat: str | None = None


# --- Helpers ---


async def _load_index_with_caveat(vault: Any) -> tuple[dict[str, dict[str, Any]], str | None]:
    """D-04a hybrid freshness read, with a defensive lock-held caveat.

    ``rebuild_links_index_if_stale`` already catches ``SweepInProgressError``
    internally and degrades to the existing index — this never actually
    raises today. The guard below exists so that contract stays true even if
    the callee's degrade path changes, and so the caveat is explicit in the
    response rather than silently absorbed.
    """
    try:
        index = await rebuild_links_index_if_stale(vault)
        return index, None
    except SweepInProgressError:
        logger.warning(
            "graph routes: sweep lock held — serving existing (possibly stale) index"
        )
        try:
            raw = await vault.read_note(LINKS_INDEX_PATH)
            existing = decode_index_body(raw) if raw and raw.strip() else {}
        except Exception:
            existing = {}
        return existing, "graph index may be stale: a vault sweep currently holds the lock"


def _hub_paths(index: dict[str, dict[str, Any]]) -> set[str]:
    """Paths whose parsed ``_schema`` block declares ``type: hub``."""
    hubs: set[str] = set()
    for path, entry in index.items():
        schema = entry.get("schema") or {}
        if schema.get("type") == "hub":
            hubs.add(path)
    return hubs


def _notes_map_from_index(index: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Synthesize a path->body map from already-extracted sidecar wikilinks.

    ``graph_analysis.build_graph_report`` re-derives edges via
    ``extract_wikilinks(body)`` per note; reconstructing a minimal body of
    ``[[target]]`` tokens from the sidecar's pre-computed wikilinks list lets
    it do so without any additional vault reads.
    """
    return {
        path: "\n".join(f"[[{target}]]" for target in entry.get("wikilinks", []))
        for path, entry in index.items()
    }


def _filename_slug(path: str) -> str:
    stem = path.rsplit("/", 1)[-1]
    if stem.endswith(".md"):
        stem = stem[: -len(".md")]
    return stem


# --- Routes ---


@router.get("/vault/graph", response_model=GraphResponse)
async def get_vault_graph(request: Request) -> GraphResponse:
    ctx = get_route_context(request)
    index, caveat = await _load_index_with_caveat(ctx.vault)
    notes_map = _notes_map_from_index(index)
    hub_paths = _hub_paths(index)
    report = graph_analysis.build_graph_report(notes_map, hub_paths)
    return GraphResponse(
        note_count=report.note_count,
        orphans=report.orphans,
        backlinks=report.backlinks,
        hub_count=report.hub_count,
        link_density=report.link_density,
        caveat=caveat,
    )


@router.get("/vault/stats", response_model=StatsResponse)
async def get_vault_stats(request: Request) -> StatsResponse:
    ctx = get_route_context(request)
    index, caveat = await _load_index_with_caveat(ctx.vault)
    notes_map = _notes_map_from_index(index)
    hub_paths = _hub_paths(index)
    report = graph_analysis.build_graph_report(notes_map, hub_paths)
    avg_notes_per_hub = (report.note_count / report.hub_count) if report.hub_count else 0.0
    return StatsResponse(
        note_count=report.note_count,
        hub_count=report.hub_count,
        orphan_count=len(report.orphans),
        avg_notes_per_hub=avg_notes_per_hub,
        link_density=report.link_density,
        caveat=caveat,
    )


@router.get("/vault/check", response_model=CheckResponse)
async def get_vault_check(request: Request) -> CheckResponse:
    ctx = get_route_context(request)
    vault = ctx.vault
    index, caveat = await _load_index_with_caveat(vault)

    results: list[NoteCheckEntry] = []
    compliant_count = 0
    for path in sorted(index.keys()):
        body = await vault.read_note(path)
        slug = _filename_slug(path)
        result = note_schema.check_note_compliance(body, slug)
        results.append(NoteCheckEntry(path=path, **result))
        if not result["failures"]:
            compliant_count += 1

    return CheckResponse(
        note_count=len(index),
        compliant_count=compliant_count,
        results=results,
        caveat=caveat,
    )
