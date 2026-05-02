"""Backwards-compat shim for ``ObsidianClient``.

Deleted in task 5 of plan 260502-cky once every call site has migrated to
``app.vault.ObsidianVault`` (and the corresponding ``app.state.vault``
attribute). Until then, this thin subclass keeps the legacy ``search_vault``
and ``list_directory`` method names available without polluting
``ObsidianVault`` itself with the historical names.
"""
from app.vault import ObsidianVault, VaultUnreachableError  # noqa: F401

# Module-level ``logger`` mirrors the historical surface; one test patches
# ``app.clients.obsidian.logger.warning`` directly, so the attribute must
# exist for the duration of the transition window.
import logging as _logging

logger = _logging.getLogger("app.vault")


class ObsidianClient(ObsidianVault):
    """Deprecated alias. Use ``app.vault.ObsidianVault`` instead.

    Re-exposes the legacy method names as bound aliases so existing call
    sites keep working without forcing the renames into the canonical
    adapter."""

    search_vault = ObsidianVault.find
    list_directory = ObsidianVault.list_under


__all__ = ["ObsidianClient", "VaultUnreachableError"]
