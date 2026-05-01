"""Core gateway adapter for Discord command handlers."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


def format_classify_response(data: dict) -> str:
    action = data.get("action")
    if action == "filed":
        path = data.get("path", "?")
        conf = data.get("confidence")
        conf_s = f" ({conf:.1f})" if isinstance(conf, (int, float)) else ""
        return f"Filed to `{path}`{conf_s}"
    if action == "inboxed":
        return "Inboxed (low confidence). `:inbox` to review."
    if action == "dropped":
        return "Dropped as noise."
    return f"Note classify returned: {data}"


async def call_core_note(*, user_id: str, content: str, topic: str | None, sentinel_client, core_url: str, api_key: str) -> str:
    payload = {"content": content, "topic": topic}
    try:
        async with httpx.AsyncClient() as http_client:
            data = await sentinel_client.post_to_module("note/classify", payload, http_client)
    except Exception as exc:
        logger.warning("note/classify call failed: %s", exc)
        return f"Note classify failed: {exc}"
    return format_classify_response(data)


async def call_core_inbox_list(*, user_id: str, core_url: str, api_key: str) -> str:
    try:
        async with httpx.AsyncClient() as http_client:
            resp = await http_client.get(
                f"{core_url.rstrip('/')}/inbox",
                headers={"X-Sentinel-Key": api_key},
                timeout=20.0,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("inbox list call failed: %s", exc)
        return f"Inbox fetch failed: {exc}"
    return data.get("rendered") or "(inbox is empty)"


async def call_core_inbox_classify(*, user_id: str, entry_n: int, topic: str, note_closed_vocab: set[str] | frozenset[str], sentinel_client) -> str:
    if topic not in note_closed_vocab:
        return f"Unknown topic `{topic}`. Valid: {', '.join(sorted(note_closed_vocab))}"
    payload = {"entry_n": entry_n, "topic": topic}
    try:
        async with httpx.AsyncClient() as http_client:
            data = await sentinel_client.post_to_module("inbox/classify", payload, http_client)
    except Exception as exc:
        logger.warning("inbox classify call failed: %s", exc)
        return f"Inbox classify failed: {exc}"
    path = data.get("path", "?")
    return f"Filed entry {entry_n} to `{path}` — re-run `:inbox` to see renumbered entries."


async def call_core_inbox_discard(*, user_id: str, entry_n: int, sentinel_client) -> str:
    payload = {"entry_n": entry_n}
    try:
        async with httpx.AsyncClient() as http_client:
            await sentinel_client.post_to_module("inbox/discard", payload, http_client)
    except Exception as exc:
        logger.warning("inbox discard call failed: %s", exc)
        return f"Inbox discard failed: {exc}"
    return f"Discarded entry {entry_n} — re-run `:inbox` to see renumbered entries."


async def call_core_sweep_start(*, user_id: str, force_reclassify: bool, dry_run: bool, sentinel_client) -> str:
    payload = {"user_id": user_id, "force_reclassify": force_reclassify, "dry_run": dry_run}
    try:
        async with httpx.AsyncClient(timeout=120.0) as http_client:
            data = await sentinel_client.post_to_module("vault/sweep/start", payload, http_client)
    except Exception as exc:
        logger.warning("vault sweep start failed: %s", exc)
        return f"Vault sweep failed to start: {exc}"
    sweep_id = data.get("sweep_id", "?")
    if dry_run:
        report_path = data.get("report_path", "ops/sweeps/dry-run-?.md")
        return (
            f"Dry-run started: `{sweep_id}`. "
            f"Report will be written to `{report_path}` when complete. "
            f"Use `:vault-sweep status` to check progress; open the report file in "
            f"Obsidian once status is `dry-run-complete`."
        )
    return f"Vault sweep started: `{sweep_id}`. Use `:vault-sweep status` to check progress."


async def call_core_sweep_status(*, user_id: str, core_url: str, api_key: str) -> str:
    try:
        async with httpx.AsyncClient() as http_client:
            resp = await http_client.get(
                f"{core_url.rstrip('/')}/vault/sweep/status",
                headers={"X-Sentinel-Key": api_key},
                timeout=20.0,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("vault sweep status failed: %s", exc)
        return f"Vault sweep status fetch failed: {exc}"
    return (
        f"sweep `{data.get('sweep_id', '-')}`: status={data.get('status', '-')}, "
        f"processed={data.get('files_processed', 0)}/{data.get('files_total', 0)}, "
        f"duplicates_moved={data.get('duplicates_moved', 0)}"
    )
