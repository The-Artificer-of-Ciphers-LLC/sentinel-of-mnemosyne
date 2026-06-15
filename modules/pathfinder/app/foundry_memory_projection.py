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

import json
import logging
from pathlib import Path
from typing import Any, Callable

from app.foundry_projection_planner import (
    ProjectionPlan,
    ProjectionState,
    build_foundry_projection_plan,
)
from app.memory_projection_store import (
    append_npc_history_row,
    write_player_map_section,
)

logger = logging.getLogger(__name__)

_PLAYER_MAP_DEFAULT_SECTION = "Chat Timeline"


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


# Success statuses returned by append_npc_history_row that represent a real write.
_NPC_APPEND_SUCCESS = frozenset({"appended", "created"})


async def _do_npc_append(
    *,
    key: str,
    row: str,
    npc_slug: str,
    dry_run: bool,
    obsidian_client: Any,
    new_npc_keys: set[str],
    unmatched_seen: set[str],
    unmatched_speakers: list[str],
    speaker_token: str,
) -> bool:
    """Attempt to append an NPC history row for one record.

    In dry_run mode: always counts as a write (no real call). Returns True.
    In live mode: calls append_npc_history_row; returns True only when the
    return value is in _NPC_APPEND_SUCCESS ("appended" or "created"). If the
    NPC note is missing ("skipped (npc note missing)"), returns False and marks
    the speaker as unmatched so it surfaces in the report.

    The caller is responsible for dedupe-key checking before calling this
    function. The key is added to new_npc_keys only when this function
    returns True.
    """
    if dry_run:
        # Dry-run: count and dedupe as if the write happened; no real call.
        new_npc_keys.add(key)
        return True

    status = await append_npc_history_row(npc_slug, row=row, obsidian=obsidian_client)
    if status in _NPC_APPEND_SUCCESS:
        new_npc_keys.add(key)
        return True

    # Write was skipped (NPC note missing). Treat speaker as unmatched so the
    # caller can surface it, but do NOT add the dedupe key — on a future run
    # when the note is created, the row must still be written.
    logger.warning(
        "_do_npc_append: npc note missing for slug=%s speaker=%r (status=%r); "
        "treating as unmatched",
        npc_slug,
        speaker_token,
        status,
    )
    if speaker_token not in unmatched_seen:
        unmatched_seen.add(speaker_token)
        unmatched_speakers.append(speaker_token)
    return False


async def project_foundry_chat_memory(
    *,
    records: list[dict],
    dry_run: bool,
    obsidian_client: Any,
    dedupe_store_path: Path,
    identity_resolver: Callable[[str], Any],
    npc_matcher: Callable[[str], Any],
    options: dict | None = None,
    project_player_maps: bool = True,
    project_npc_history: bool = True,
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
      npc_matcher: callable (speaker_token) -> npc_slug | None. Invoked as a
        defence-in-depth fallback when the resolver returns "npc" with an
        unresolved slug, AND as a rescue path when the resolver returns "unknown"
        (handles case-sensitive miss in the roster lookup). Sync or async accepted.
      options: reserved for future per-record section overrides; currently unused.
      project_player_maps: when False, player-classified records are skipped entirely
        (no write, no key saved, not added to unmatched).
      project_npc_history: when False, npc-classified records (including unknown-rescue)
        are skipped entirely (no write, no key saved, not added to unmatched).

    Returns:
      dict with keys: player_updates, npc_updates, player_deduped, npc_deduped,
      unmatched_speakers, dry_run.
    """
    state = _load_projection_state(dedupe_store_path)
    projection_state = ProjectionState(
        imported_keys=state["imported_keys"],
        player_projection_keys=state["player_projection_keys"],
        npc_projection_keys=state["npc_projection_keys"],
    )
    plan = await build_foundry_projection_plan(
        records=records,
        state=projection_state,
        identity_resolver=identity_resolver,
        npc_matcher=npc_matcher,
        options=options,
        project_player_maps=project_player_maps,
        project_npc_history=project_npc_history,
    )

    return await _execute_projection_plan(
        plan=plan,
        state=projection_state,
        dry_run=dry_run,
        obsidian_client=obsidian_client,
        dedupe_store_path=dedupe_store_path,
    )


async def _execute_projection_plan(
    *,
    plan: ProjectionPlan,
    state: ProjectionState,
    dry_run: bool,
    obsidian_client: Any,
    dedupe_store_path: Path,
) -> dict:
    successful_npc_keys: set[str] = set()
    unmatched_speakers = list(plan.unmatched_speakers)
    unmatched_seen = set(unmatched_speakers)
    npc_updates = 0

    for row in plan.npc_rows:
        wrote = await _do_npc_append(
            key=row.key,
            row=row.row,
            npc_slug=row.npc_slug,
            dry_run=dry_run,
            obsidian_client=obsidian_client,
            new_npc_keys=successful_npc_keys,
            unmatched_seen=unmatched_seen,
            unmatched_speakers=unmatched_speakers,
            speaker_token=row.speaker_token,
        )
        if wrote:
            npc_updates += 1

    if not dry_run:
        for slug, rows in plan.player_batches().items():
            await write_player_map_section(
                slug,
                section=_PLAYER_MAP_DEFAULT_SECTION,
                lines=rows,
                obsidian=obsidian_client,
            )

        _save_projection_state(
            dedupe_store_path,
            imported_keys=state.imported_keys,
            player_keys=state.player_projection_keys | plan.player_keys,
            npc_keys=state.npc_projection_keys | successful_npc_keys,
        )

    return {
        "player_updates": plan.player_updates,
        "npc_updates": npc_updates,
        "player_deduped": plan.player_deduped,
        "npc_deduped": plan.npc_deduped,
        "unmatched_speakers": unmatched_speakers,
        "dry_run": dry_run,
    }
