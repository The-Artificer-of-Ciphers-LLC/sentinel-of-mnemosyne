"""Core gateway adapter for Discord command handlers."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

# D-04a: concurrency refusal wording surfaced when the shared vault-mutation
# lock (sweep/pipeline mutex) is already held.
_PIPELINE_BLOCKED_MESSAGE = (
    "A vault operation is already in progress — please try again shortly."
)


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


async def call_core_pipeline_start(*, user_id: str, mode: str, sentinel_client) -> str:
    payload = {"user_id": user_id, "mode": mode}
    try:
        async with httpx.AsyncClient(timeout=120.0) as http_client:
            data = await sentinel_client.post_to_module("vault/pipeline/start", payload, http_client)
    except Exception as exc:
        logger.warning("vault pipeline start failed: %s", exc)
        return f"Pipeline failed to start: {exc}"
    if data.get("status") == "blocked":
        return _PIPELINE_BLOCKED_MESSAGE
    pipeline_id = data.get("pipeline_id", "?")
    return (
        f"Pipeline started: `{pipeline_id}` (mode={mode}). "
        f"Use `:{mode} status` to check progress."
    )


async def call_core_pipeline_status(*, user_id: str, core_url: str, api_key: str) -> str:
    try:
        async with httpx.AsyncClient() as http_client:
            resp = await http_client.get(
                f"{core_url.rstrip('/')}/vault/pipeline/status",
                headers={"X-Sentinel-Key": api_key},
                timeout=20.0,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("vault pipeline status failed: %s", exc)
        return f"Pipeline status fetch failed: {exc}"
    if data.get("status") == "blocked":
        return _PIPELINE_BLOCKED_MESSAGE
    return (
        f"pipeline `{data.get('pipeline_id', '-')}`: status={data.get('status', '-')}, "
        f"mode={data.get('mode', '-')}, "
        f"processed={data.get('entries_processed', 0)}/{data.get('entries_total', 0)}, "
        f"reduced={data.get('reduced', 0)}, hubs_touched={data.get('hubs_touched', 0)}, "
        f"reweave_edits={data.get('reweave_edits', 0)}, "
        f"verify_failed={data.get('verify_failed', 0)}, verify_requeued={data.get('verify_requeued', 0)}"
    )


async def call_core_migrate_start(*, user_id: str, dry_run: bool, sentinel_client) -> str:
    payload = {"user_id": user_id, "dry_run": dry_run}
    try:
        async with httpx.AsyncClient(timeout=120.0) as http_client:
            data = await sentinel_client.post_to_module("vault/migrate/start", payload, http_client)
    except Exception as exc:
        logger.warning("vault migrate start failed: %s", exc)
        return f"Vault migrate failed to start: {exc}"
    migration_id = data.get("migration_id", "?")
    if dry_run:
        return (
            f"Migration dry-run started: `{migration_id}`. "
            f"Use `:migrate status` to check progress."
        )
    return f"Migration started: `{migration_id}`. Use `:migrate status` to check progress."


async def call_core_migrate_status(*, user_id: str, core_url: str, api_key: str) -> str:
    try:
        async with httpx.AsyncClient() as http_client:
            resp = await http_client.get(
                f"{core_url.rstrip('/')}/vault/migrate/status",
                headers={"X-Sentinel-Key": api_key},
                timeout=20.0,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("vault migrate status failed: %s", exc)
        return f"Vault migrate status fetch failed: {exc}"
    return (
        f"migration `{data.get('migration_id', '-')}`: status={data.get('status', '-')}, "
        f"mode={data.get('mode', '-')}, "
        f"ops_moved={len(data.get('ops_moved') or [])}, "
        f"notes_backfilled={data.get('notes_backfilled', 0)}, "
        f"verify_failed={data.get('verify_failed', 0)}, "
        f"new_orphans={data.get('new_orphans', 0)}, "
        f"rolled_back={data.get('rolled_back', False)}"
    )


async def call_core_graph(*, user_id: str, core_url: str, api_key: str) -> str:
    try:
        async with httpx.AsyncClient() as http_client:
            resp = await http_client.get(
                f"{core_url.rstrip('/')}/vault/graph",
                headers={"X-Sentinel-Key": api_key},
                timeout=20.0,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("vault graph call failed: %s", exc)
        return f"Vault graph fetch failed: {exc}"
    orphans = data.get("orphans") or []
    caveat = data.get("caveat")
    caveat_s = f" ({caveat})" if caveat else ""
    return (
        f"Graph: {data.get('note_count', 0)} notes, {len(orphans)} orphans, "
        f"{data.get('hub_count', 0)} hubs, link_density={data.get('link_density', 0):.2f}{caveat_s}"
    )


async def call_core_stats(*, user_id: str, core_url: str, api_key: str) -> str:
    try:
        async with httpx.AsyncClient() as http_client:
            resp = await http_client.get(
                f"{core_url.rstrip('/')}/vault/stats",
                headers={"X-Sentinel-Key": api_key},
                timeout=20.0,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("vault stats call failed: %s", exc)
        return f"Vault stats fetch failed: {exc}"
    caveat = data.get("caveat")
    caveat_s = f" ({caveat})" if caveat else ""
    return (
        f"Stats: {data.get('note_count', 0)} notes, {data.get('hub_count', 0)} hubs, "
        f"{data.get('orphan_count', 0)} orphans, "
        f"avg_notes_per_hub={data.get('avg_notes_per_hub', 0):.1f}, "
        f"link_density={data.get('link_density', 0):.2f}{caveat_s}"
    )


async def call_core_profile_status(*, core_url: str, api_key: str) -> dict | None:
    """GET /self/profile/status (ungated). Returns the parsed status dict, or
    None if Core is unreachable/erroring — callers must degrade (log + skip)
    rather than crash, per the onboarding nudge/dialog resilience contract."""
    try:
        async with httpx.AsyncClient() as http_client:
            resp = await http_client.get(
                f"{core_url.rstrip('/')}/self/profile/status",
                headers={"X-Sentinel-Key": api_key},
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("self/profile/status call failed: %s", exc)
        return None


async def call_core_profile_write(
    *, user_id: str, path: str, content: str, sentinel_client, http_client, force: bool = False
) -> dict:
    """POST /self/profile via the module-proxy client.

    Mirrors post_to_module's raise-on-error posture (NOT the swallow-to-string
    posture of call_core_note/etc.) so callers can react to the domain-specific
    409 ("already filled") without it being masked as a generic failure string.

    Raises:
        httpx.HTTPStatusError: On 4xx/5xx (e.g. 409 already-filled, 422 bad path).
        httpx.ConnectError / httpx.TimeoutException: If sentinel-core is unreachable.
    """
    payload: dict = {"user_id": user_id, "path": path, "content": content}
    if force:
        payload["force"] = True
    return await sentinel_client.post_to_module("self/profile", payload, http_client)


async def call_core_check(*, user_id: str, core_url: str, api_key: str) -> str:
    try:
        async with httpx.AsyncClient() as http_client:
            resp = await http_client.get(
                f"{core_url.rstrip('/')}/vault/check",
                headers={"X-Sentinel-Key": api_key},
                timeout=20.0,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("vault check call failed: %s", exc)
        return f"Vault check fetch failed: {exc}"
    note_count = data.get("note_count", 0)
    compliant_count = data.get("compliant_count", 0)
    results = data.get("results") or []
    failing = [r for r in results if r.get("failures")]
    caveat = data.get("caveat")
    caveat_s = f" ({caveat})" if caveat else ""
    lines = [f"Check: {compliant_count}/{note_count} notes compliant{caveat_s}"]
    for entry in failing[:10]:
        lines.append(f"  FAIL {entry.get('path', '?')}: {', '.join(entry.get('failures', []))}")
    if len(failing) > 10:
        lines.append(f"  ...and {len(failing) - 10} more")
    return "\n".join(lines)
