"""Health response formatting module."""

from __future__ import annotations

from app.services.runtime_probe import RuntimeProbeSnapshot


def build_health_payload(snapshot: RuntimeProbeSnapshot, embedding_loaded: bool) -> dict[str, str]:
    return {
        "status": "ok",
        "obsidian": "ok" if snapshot.obsidian_ok else "degraded",
        "embedding_model": "loaded" if embedding_loaded else "not_loaded",
    }
