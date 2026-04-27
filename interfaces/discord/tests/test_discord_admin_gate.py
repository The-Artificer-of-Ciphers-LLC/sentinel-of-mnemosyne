"""Tests for SENTINEL_ADMIN_USER_IDS gate + :vault-sweep dispatch (260427-vl1 Task 8)."""
from __future__ import annotations

import importlib
from unittest.mock import AsyncMock, patch

import pytest


def _reload_bot(monkeypatch, admin_ids: str):
    """Set the env var and reload bot.py so module-level constants re-parse."""
    monkeypatch.setenv("SENTINEL_ADMIN_USER_IDS", admin_ids)
    import bot  # interfaces/discord/bot.py — adjacent module via PYTHONPATH

    importlib.reload(bot)
    return bot


# --- _is_admin behaviour ---


def test_is_admin_empty_env_fails_closed(monkeypatch):
    bot = _reload_bot(monkeypatch, "")
    assert bot._is_admin("123") is False
    assert bot._is_admin("") is False


def test_is_admin_explicit_allowlist(monkeypatch):
    bot = _reload_bot(monkeypatch, "123,456")
    assert bot._is_admin("123") is True
    assert bot._is_admin("456") is True
    assert bot._is_admin("789") is False


def test_is_admin_wildcard_open(monkeypatch):
    bot = _reload_bot(monkeypatch, "*")
    assert bot._is_admin("123") is True
    assert bot._is_admin("anyone") is True


# --- :vault-sweep dispatch ---


@pytest.mark.asyncio
async def test_vault_sweep_non_admin_refused(monkeypatch):
    bot = _reload_bot(monkeypatch, "")
    result = await bot.handle_sentask_subcommand("vault-sweep", "", "789")
    assert "Admin only" in result
    assert "SENTINEL_ADMIN_USER_IDS" in result


@pytest.mark.asyncio
async def test_vault_sweep_admin_starts(monkeypatch):
    bot = _reload_bot(monkeypatch, "123")
    with patch.object(
        bot, "_call_core_sweep_start", new=AsyncMock(return_value="Vault sweep started: `xyz`")
    ) as mock_start:
        result = await bot.handle_sentask_subcommand("vault-sweep", "", "123")
    mock_start.assert_called_once_with("123", force_reclassify=False)
    assert "Vault sweep started" in result


@pytest.mark.asyncio
async def test_vault_sweep_status(monkeypatch):
    bot = _reload_bot(monkeypatch, "123")
    with patch.object(
        bot, "_call_core_sweep_status", new=AsyncMock(return_value="sweep `x`: status=running")
    ) as mock_status:
        result = await bot.handle_sentask_subcommand("vault-sweep", "status", "123")
    mock_status.assert_called_once_with("123")
    assert "running" in result


@pytest.mark.asyncio
async def test_vault_sweep_force_reclassify(monkeypatch):
    bot = _reload_bot(monkeypatch, "123")
    with patch.object(
        bot, "_call_core_sweep_start", new=AsyncMock(return_value="Vault sweep started")
    ) as mock_start:
        await bot.handle_sentask_subcommand("vault-sweep", "force", "123")
    mock_start.assert_called_once_with("123", force_reclassify=True)
