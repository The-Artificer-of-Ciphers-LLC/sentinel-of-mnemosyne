"""Runtime probe module for health/status adapters."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.runtime_config import RuntimeConfig
from app.services.model_selector import probe_embedding_model_loaded
from app.vault import Vault


@dataclass(frozen=True)
class RuntimeProbeSnapshot:
    obsidian_ok: bool
    embedding_loaded: bool


async def probe_runtime(
    *,
    vault: Vault | None,
    http_client: httpx.AsyncClient | None,
    runtime_config: RuntimeConfig,
    include_embedding_probe: bool,
) -> RuntimeProbeSnapshot:
    obsidian_ok = False
    if vault is not None:
        try:
            obsidian_ok = await vault.check_health()
        except Exception:
            pass

    embedding_loaded = False
    if include_embedding_probe and http_client is not None:
        try:
            embedding_loaded = await probe_embedding_model_loaded(
                http_client,
                runtime_config.lmstudio_base_url,
                runtime_config.embedding_model,
            )
        except Exception:
            pass

    return RuntimeProbeSnapshot(
        obsidian_ok=obsidian_ok,
        embedding_loaded=embedding_loaded,
    )
