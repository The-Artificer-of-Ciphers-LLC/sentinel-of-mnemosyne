"""Plan Foundry chat memory projection without touching the Vault."""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Any, Callable, Literal

from app.foundry_chat_import import _message_key, _speaker, _strip_html

logger = logging.getLogger(__name__)

Target = Literal["player_map", "npc_history"]


@dataclass(frozen=True)
class ProjectionState:
    """Existing projection keys loaded from the Foundry import state file."""

    imported_keys: set[str]
    player_projection_keys: set[str]
    npc_projection_keys: set[str]


@dataclass(frozen=True)
class PlayerMapRow:
    slug: str
    key: str
    row: str


@dataclass(frozen=True)
class NpcHistoryRow:
    npc_slug: str
    key: str
    row: str
    speaker_token: str


@dataclass(frozen=True)
class ProjectionPlan:
    """A complete, side-effect-free plan for projecting Foundry chat memory."""

    player_rows: tuple[PlayerMapRow, ...]
    npc_rows: tuple[NpcHistoryRow, ...]
    player_deduped: int
    npc_deduped: int
    unmatched_speakers: tuple[str, ...]

    @property
    def player_updates(self) -> int:
        return len(self.player_rows)

    @property
    def npc_updates(self) -> int:
        return len(self.npc_rows)

    @property
    def player_keys(self) -> set[str]:
        return {row.key for row in self.player_rows}

    @property
    def npc_keys(self) -> set[str]:
        return {row.key for row in self.npc_rows}

    def player_batches(self) -> dict[str, list[str]]:
        batches: dict[str, list[str]] = {}
        for row in self.player_rows:
            batches.setdefault(row.slug, []).append(row.row)
        return batches


def projection_key(record: dict, target: Target) -> str:
    """Per-target dedupe key. Reuses _message_key recipe; appends target."""
    return f"{_message_key(record)}|target:{target}"


def build_projection_row(record: dict, key: str) -> str:
    ts_iso = _format_timestamp(record.get("timestamp"))
    content = _strip_html(str(record.get("content", "")))
    return f"- [{ts_iso}] (foundry, key={key}) {content}"


async def build_foundry_projection_plan(
    *,
    records: list[dict],
    state: ProjectionState,
    identity_resolver: Callable[[str], Any],
    npc_matcher: Callable[[str], Any],
    options: dict | None = None,
    project_player_maps: bool = True,
    project_npc_history: bool = True,
) -> ProjectionPlan:
    """Classify records into projection rows, dedupe counts, and unmatched speakers."""
    _ = options or {}
    new_player_keys: set[str] = set()
    new_npc_keys: set[str] = set()
    npc_matcher_cache: dict[str, str | None] = {}

    player_rows: list[PlayerMapRow] = []
    npc_rows: list[NpcHistoryRow] = []
    player_deduped = 0
    npc_deduped = 0
    unmatched_speakers: list[str] = []
    unmatched_seen: set[str] = set()

    for record in records:
        speaker_token = _speaker(record)
        kind, payload = await _classify_record(
            speaker_token=speaker_token,
            identity_resolver=identity_resolver,
        )

        if kind == "player":
            if not project_player_maps:
                continue
            key = projection_key(record, "player_map")
            if key in state.player_projection_keys or key in new_player_keys:
                player_deduped += 1
                continue
            new_player_keys.add(key)
            slug = str(payload)
            player_rows.append(
                PlayerMapRow(slug=slug, key=key, row=build_projection_row(record, key))
            )
            logger.info(
                "build_foundry_projection_plan: queued player-map row for %s key=%s",
                slug,
                key,
            )
            continue

        if kind == "npc":
            if not project_npc_history:
                continue
            npc_slug = payload if payload else None
            if not npc_slug:
                npc_slug = await _match_npc(
                    speaker_token=speaker_token,
                    npc_matcher=npc_matcher,
                    log_context="npc-classified speaker",
                )

            if not npc_slug:
                _record_unmatched(
                    speaker_token=speaker_token,
                    unmatched_seen=unmatched_seen,
                    unmatched_speakers=unmatched_speakers,
                )
                continue

            key = projection_key(record, "npc_history")
            if key in state.npc_projection_keys or key in new_npc_keys:
                npc_deduped += 1
                continue
            new_npc_keys.add(key)
            npc_rows.append(
                NpcHistoryRow(
                    npc_slug=str(npc_slug),
                    key=key,
                    row=build_projection_row(record, key),
                    speaker_token=speaker_token,
                )
            )
            logger.info(
                "build_foundry_projection_plan: queued npc history row for %s key=%s",
                npc_slug,
                key,
            )
            continue

        if not project_npc_history:
            continue

        if speaker_token not in npc_matcher_cache:
            npc_matcher_cache[speaker_token] = await _match_npc(
                speaker_token=speaker_token,
                npc_matcher=npc_matcher,
                log_context="unknown speaker",
            )

        rescued_slug = npc_matcher_cache[speaker_token]
        if rescued_slug:
            key = projection_key(record, "npc_history")
            if key in state.npc_projection_keys or key in new_npc_keys:
                npc_deduped += 1
                continue
            new_npc_keys.add(key)
            npc_rows.append(
                NpcHistoryRow(
                    npc_slug=str(rescued_slug),
                    key=key,
                    row=build_projection_row(record, key),
                    speaker_token=speaker_token,
                )
            )
            logger.info(
                "build_foundry_projection_plan: rescued unknown speaker %r to npc %s key=%s",
                speaker_token,
                rescued_slug,
                key,
            )
            continue

        _record_unmatched(
            speaker_token=speaker_token,
            unmatched_seen=unmatched_seen,
            unmatched_speakers=unmatched_speakers,
        )

    return ProjectionPlan(
        player_rows=tuple(player_rows),
        npc_rows=tuple(npc_rows),
        player_deduped=player_deduped,
        npc_deduped=npc_deduped,
        unmatched_speakers=tuple(unmatched_speakers),
    )


async def _classify_record(
    *,
    speaker_token: str,
    identity_resolver: Callable[[str], Any],
) -> tuple[Any, Any]:
    try:
        classification = identity_resolver(speaker_token)
        classification = await _maybe_await(classification)
    except Exception:
        logger.exception(
            "identity_resolver raised for speaker %r; treating as unknown",
            speaker_token,
        )
        return ("unknown", speaker_token)

    if not isinstance(classification, tuple) or len(classification) != 2:
        logger.warning(
            "identity_resolver returned unexpected shape %r for speaker %r",
            classification,
            speaker_token,
        )
        return ("unknown", speaker_token)

    return classification


async def _match_npc(
    *,
    speaker_token: str,
    npc_matcher: Callable[[str], Any],
    log_context: str,
) -> str | None:
    try:
        matched = npc_matcher(speaker_token)
        matched = await _maybe_await(matched)
    except Exception:
        logger.exception(
            "npc_matcher raised for %s %r",
            log_context,
            speaker_token,
        )
        return None
    if matched:
        return str(matched)
    return None


def _record_unmatched(
    *,
    speaker_token: str,
    unmatched_seen: set[str],
    unmatched_speakers: list[str],
) -> None:
    if speaker_token in unmatched_seen:
        return
    unmatched_seen.add(speaker_token)
    unmatched_speakers.append(speaker_token)
    logger.warning(
        "build_foundry_projection_plan: unmatched speaker %r",
        speaker_token,
    )


def _format_timestamp(ts_ms: Any) -> str:
    """Foundry timestamps are milliseconds since epoch; format as UTC ISO date+time."""
    try:
        ts_int = int(ts_ms)
    except (TypeError, ValueError):
        return "0000-00-00 00:00:00"
    moment = dt.datetime.fromtimestamp(ts_int / 1000.0, tz=dt.timezone.utc)
    return moment.strftime("%Y-%m-%d %H:%M:%S")


async def _maybe_await(value: Any) -> Any:
    """Allow identity_resolver / npc_matcher to be sync or async callables."""
    if hasattr(value, "__await__"):
        return await value
    return value
