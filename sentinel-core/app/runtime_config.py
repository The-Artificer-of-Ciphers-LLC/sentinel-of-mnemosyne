"""Runtime configuration view used across route/service seams."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuntimeConfig:
    model_name: str
    ai_provider: str
    pi_harness_url: str
    lmstudio_base_url: str
    embedding_model: str


def runtime_config_from_settings(settings: Any) -> RuntimeConfig:
    return RuntimeConfig(
        model_name=settings.model_name,
        ai_provider=settings.ai_provider,
        pi_harness_url=settings.pi_harness_url,
        lmstudio_base_url=settings.lmstudio_base_url,
        embedding_model=settings.embedding_model,
    )
