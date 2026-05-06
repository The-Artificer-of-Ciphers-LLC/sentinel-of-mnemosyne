"""Registry module for runtime-registered Sentinel modules."""

from __future__ import annotations

from typing import Any


def register_module(registry: dict[str, Any], registration: Any) -> None:
    registry[registration.name] = registration


def list_modules_payload(registry: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": reg.name,
            "base_url": reg.base_url,
            "routes": [{"path": r.path, "description": r.description} for r in reg.routes],
        }
        for reg in registry.values()
    ]


def resolve_module(registry: dict[str, Any], name: str) -> Any:
    module = registry.get(name)
    if module is None:
        raise KeyError(f"Module '{name}' not registered")
    return module
