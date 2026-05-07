"""Foundry chat memory projection (Phase 37, FCM-01..05).

Reads NeDB-style Foundry chat records and projects them into:

  * per-player chat-map notes (mnemosyne/pf2e/players/{slug}.md) — one
    consolidated put_note per player per import, via
    memory_projection_store.write_player_map_section.

  * per-NPC chat-history rows under ## Foundry Chat History on each NPC
    note (mnemosyne/pf2e/npcs/{slug}.md), via
    memory_projection_store.append_npc_history_row.

The projector NEVER touches profile.md (Pitfall 1: schema-drift prevention).

Idempotency is keyed per (record, target) pair. The dedupe key is:

    f"{_message_key(record)}|target:{target}"

where target is "player_map" or "npc_history" so the same record routed to
two different targets dedupes independently. _message_key reuses the existing
foundry_chat_import recipe: prefer Foundry `_id`, fall back to
`{timestamp}|{speaker}|{content}`.

State file (``.foundry_chat_import_state.json``) is extended in-place with
two new arrays: ``player_projection_keys`` and ``npc_projection_keys``. The
existing ``imported_keys`` array is preserved on read-then-merge so the
foundry_chat_import importer keeps working.

Dry-run path produces an identical metric shape but performs zero writes
(no obsidian calls, no state-file save).
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any, Callable, Literal

from app.foundry_chat_import import _message_key, _speaker, _strip_html
from app.memory_projection_store import (
    append_npc_history_row,
    write_player_map_section,
)

logger = logging.getLogger(__name__)

_PLAYER_MAP_DEFAULT_SECTION = "Chat Timeline"

Target = Literal["player_map", "npc_history"]


def _projection_key(record: dict, target: Target) -> str:
    """Per-target dedupe key. Reuses _message_key recipe; appends target."""
    return f"{_message_key(record)}|target:{target}"


def _load_projection_state(path: Path) -> dict[str, set[str]]:
    """Load projection state from disk.

    Returns a dict with:
      - ``imported_keys``: set[str] (legacy, preserved on save)
      - ``player_projection_keys``: set[str]
      - ``npc_projection_keys``: set[str]

    Missing file or malformed JSON yields all-empty sets. Tolerant of legacy
    state files that contain only ``imported_keys``.
    """
    out: dict[str, set[str]] = {
        "imported_keys": set(),
        "player_projection_keys": set(),
        "npc_projection_keys": set(),
    }
    if not path.exists():
        return out
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return out
    if not isinstance(data, dict):
        return out
    for key in (
        "imported_keys",
        "player_projection_keys",
        "npc_projection_keys",
    ):
        val = data.get(key)
        if isinstance(val, list):
            out[key] = {str(k) for k in val}
    return out


def _save_projection_state(
    path: Path,
    *,
    imported_keys: set[str],
    player_keys: set[str],
    npc_keys: set[str],
) -> None:
    """Atomically write projection state to disk preserving all three arrays."""
    payload = {
        "imported_keys": sorted(imported_keys),
        "player_projection_keys": sorted(player_keys),
        "npc_projection_keys": sorted(npc_keys),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _format_timestamp(ts_ms: Any) -> str:
    """Foundry timestamps are milliseconds since epoch; format as UTC ISO date+time."""
    try:
        ts_int = int(ts_ms)
    except (TypeError, ValueError):
        return "0000-00-00 00:00:00"
    moment = dt.datetime.fromtimestamp(ts_int / 1000.0, tz=dt.timezone.utc)
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def _build_row(record: dict, key: str) -> str:
    ts_iso = _format_timestamp(record.get("timestamp"))
    content = _strip_html(str(record.get("content", "")))
    return f"- [{ts_iso}] (foundry, key={key}) {content}"


async def _maybe_await(value: Any) -> Any:
    """Allow identity_resolver / npc_matcher to be sync or async callables."""
    if hasattr(value, "__await__"):
        return await value
    return value


async def project_foundry_chat_memory(
    *,
    records: list[dict],
    dry_run: bool,
    obsidian_client: Any,
    dedupe_store_path: Path,
    identity_resolver: Callable[[str], Any],
    npc_matcher: Callable[[str], Any],
    options: dict | None = None,
) -> dict:
    """Project Foundry chat records into per-player and per-NPC memory.

    Args:
      records: list of NeDB-style chat records (already filtered/classified upstream).
      dry_run: when True, perform no writes; produce identical metric shape.
      obsidian_client: object exposing async get_note/put_note/patch_heading.
      dedupe_store_path: path to the in-place state file. Created if absent.
      identity_resolver: callable (speaker_token) -> ("player"|"npc"|"unknown", slug_or_raw).
        Tests pass a sync callable; production may pass an async coroutine factory —
        both are tolerated via _maybe_await.
      npc_matcher: callable (speaker_token) -> npc_slug | None. Currently only
        invoked when the resolver returns "npc" with an unresolved slug, as a
        defence-in-depth fallback. Sync or async accepted.
      options: reserved for future per-record section overrides; currently unused.

    Returns:
      dict with keys: player_updates, npc_updates, player_deduped, npc_deduped,
      unmatched_speakers, dry_run.
    """
    options = options or {}
    state = _load_projection_state(dedupe_store_path)
    imported_keys = state["imported_keys"]
    player_keys = state["player_projection_keys"]
    npc_keys = state["npc_projection_keys"]

    # Track in-run additions separately so dedupe within a single run also fires.
    new_player_keys: set[str] = set()
    new_npc_keys: set[str] = set()

    player_updates = 0
    npc_updates = 0
    player_deduped = 0
    npc_deduped = 0
    unmatched_speakers: list[str] = []
    unmatched_seen: set[str] = set()

    # Player-map writes are batched per slug → list[str] of timeline rows.
    # Section override per record is not yet supported (options reserved); we
    # always write to the default ## Chat Timeline section.
    player_batches: dict[str, list[str]] = {}

    for record in records:
        speaker_token = _speaker(record)

        try:
            classification = identity_resolver(speaker_token)
            classification = await _maybe_await(classification)
        except Exception:
            logger.exception(
                "identity_resolver raised for speaker %r; treating as unknown",
                speaker_token,
            )
            classification = ("unknown", speaker_token)

        if not isinstance(classification, tuple) or len(classification) != 2:
            logger.warning(
                "identity_resolver returned unexpected shape %r for speaker %r",
                classification,
                speaker_token,
            )
            classification = ("unknown", speaker_token)

        kind, payload = classification

        if kind == "player":
            slug = str(payload)
            key = _projection_key(record, "player_map")
            if (
                key in player_keys
                or key in new_player_keys
            ):
                player_deduped += 1
                continue
            new_player_keys.add(key)
            row = _build_row(record, key)
            player_batches.setdefault(slug, []).append(row)
            player_updates += 1
            logger.info(
                "project_foundry_chat_memory: queued player-map row for %s key=%s",
                slug,
                key,
            )
            continue

        if kind == "npc":
            npc_slug = payload if payload else None
            if not npc_slug:
                # Defence-in-depth fallback to npc_matcher.
                try:
                    matched = npc_matcher(speaker_token)
                    matched = await _maybe_await(matched)
                except Exception:
                    logger.exception(
                        "npc_matcher raised for speaker %r", speaker_token
                    )
                    matched = None
                npc_slug = matched

            if not npc_slug:
                if speaker_token not in unmatched_seen:
                    unmatched_seen.add(speaker_token)
                    unmatched_speakers.append(speaker_token)
                    logger.warning(
                        "project_foundry_chat_memory: unmatched speaker %r",
                        speaker_token,
                    )
                continue

            key = _projection_key(record, "npc_history")
            if key in npc_keys or key in new_npc_keys:
                npc_deduped += 1
                continue
            new_npc_keys.add(key)
            npc_updates += 1
            logger.info(
                "project_foundry_chat_memory: appending npc history row for %s key=%s",
                npc_slug,
                key,
            )
            if not dry_run:
                row = _build_row(record, key)
                await append_npc_history_row(
                    str(npc_slug), row=row, obsidian=obsidian_client
                )
            continue

        # kind == "unknown" or anything else
        if speaker_token not in unmatched_seen:
            unmatched_seen.add(speaker_token)
            unmatched_speakers.append(speaker_token)
            logger.warning(
                "project_foundry_chat_memory: unmatched speaker %r",
                speaker_token,
            )

    # Flush per-player batches: one consolidated put_note per slug.
    if not dry_run:
        for slug, rows in player_batches.items():
            await write_player_map_section(
                slug,
                section=_PLAYER_MAP_DEFAULT_SECTION,
                lines=rows,
                obsidian=obsidian_client,
            )

        # Persist merged state.
        _save_projection_state(
            dedupe_store_path,
            imported_keys=imported_keys,
            player_keys=player_keys | new_player_keys,
            npc_keys=npc_keys | new_npc_keys,
        )

    return {
        "player_updates": player_updates,
        "npc_updates": npc_updates,
        "player_deduped": player_deduped,
        "npc_deduped": npc_deduped,
        "unmatched_speakers": unmatched_speakers,
        "dry_run": dry_run,
    }
