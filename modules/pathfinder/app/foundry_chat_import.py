from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Protocol

try:
    import plyvel  # type: ignore
except Exception:  # pragma: no cover - dependency/runtime specific
    plyvel = None


class _ObsidianLike(Protocol):
    async def put_note(self, path: str, content: str) -> None: ...


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_IMPORTED_SUFFIX_RE = re.compile(r"_imported(?:_\d+)?$")
_DEDUPE_STATE_FILE = ".foundry_chat_import_state.json"


def _strip_html(text: str) -> str:
    no_tags = _TAG_RE.sub(" ", text)
    return _WS_RE.sub(" ", no_tags).strip()


def _classify(record: dict) -> str:
    msg_type = record.get("type")
    content = _strip_html(str(record.get("content", "")))
    msg_type_s = str(msg_type).lower()
    if msg_type == 5 or msg_type_s == "roll" or "roll" in content.lower():
        return "roll"
    if msg_type == 0 or msg_type_s == "ooc" or content.startswith("(("):
        return "ooc"
    if msg_type in (1, 2, 3, 4) or msg_type_s in {"base", "ic", "emote", "incharacter"}:
        return "ic"
    return "system"


def _speaker(record: dict) -> str:
    speaker = record.get("speaker")
    if isinstance(speaker, dict):
        alias = speaker.get("alias")
        if alias:
            return str(alias)
    return "Unknown"


def _is_nedb_chat_record(record: dict) -> bool:
    if not isinstance(record, dict):
        return False
    if not isinstance(record.get("content"), str):
        return False
    msg_type = record.get("type")
    if not isinstance(msg_type, (int, str)):
        return False
    if isinstance(msg_type, int) and msg_type not in {0, 1, 2, 3, 4, 5}:
        return False
    if isinstance(msg_type, str) and msg_type.lower() not in {"base", "ic", "ooc", "roll", "emote", "incharacter", "system"}:
        return False
    if not isinstance(record.get("timestamp"), int):
        return False
    content = _strip_html(record.get("content", ""))
    if not content:
        return False
    return True


def _probe_nedb_file(path: Path, max_lines: int = 50) -> tuple[int, int]:
    valid = 0
    seen = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return (0, 0)
    for line in lines[:max_lines]:
        line = line.strip()
        if not line:
            continue
        seen += 1
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if _is_nedb_chat_record(record):
            valid += 1
    return (valid, seen)


def _is_imported_name(name: str) -> bool:
    return bool(_IMPORTED_SUFFIX_RE.search(name))


def _find_nedb_chatlog_file(inbox: Path) -> Path | None:
    candidates = [p for p in sorted(inbox.iterdir()) if p.is_file() and not _is_imported_name(p.name)]
    best: tuple[Path, int, int] | None = None
    for p in candidates:
        valid, seen = _probe_nedb_file(p)
        if valid == 0:
            continue
        if best is None or valid > best[1]:
            best = (p, valid, seen)
    return best[0] if best is not None else None


def _read_leveldb_records(db_path: Path, limit: int | None) -> list[dict]:
    records: list[dict] = []
    db = plyvel.DB(str(db_path), create_if_missing=False)
    try:
        for key, value in db:
            if not key.startswith(b"!messages!"):
                continue
            try:
                record = json.loads(value.decode("utf-8"))
            except Exception:
                continue
            if _is_nedb_chat_record(record):
                records.append(record)
                if limit is not None and len(records) >= limit:
                    break
    finally:
        db.close()
    return records


def _load_nedb_records_from_leveldb_dir(inbox: Path, limit: int | None) -> list[dict]:
    if plyvel is None:
        raise RuntimeError("plyvel is required for Foundry LevelDB chat import")

    try:
        return _read_leveldb_records(inbox, limit)
    except Exception as exc:
        msg = str(exc)
        if "LOCK" not in msg and "Read-only file system" not in msg:
            raise

    with tempfile.TemporaryDirectory(prefix="foundry-leveldb-") as tmpdir:
        tmp = Path(tmpdir)
        for p in inbox.iterdir():
            if p.is_file() and not _is_imported_name(p.name):
                shutil.copy2(p, tmp / p.name)
        return _read_leveldb_records(tmp, limit)


def _looks_like_leveldb_dir(inbox: Path) -> bool:
    names = {p.name for p in inbox.iterdir() if p.is_file()}
    if "CURRENT" in names:
        return True
    if any(n.startswith("MANIFEST-") for n in names):
        return True
    if any(n.endswith(".ldb") for n in names):
        return True
    return False


def _mark_imported(path: Path) -> Path:
    dst = path.with_name(f"{path.name}_imported")
    suffix = 1
    while dst.exists():
        dst = path.with_name(f"{path.name}_imported_{suffix}")
        suffix += 1
    path.rename(dst)
    return dst


def _mark_leveldb_dir_imported(inbox: Path) -> list[str]:
    renamed: list[str] = []
    candidates = [
        p for p in sorted(inbox.iterdir())
        if p.is_file()
        and not _is_imported_name(p.name)
        and (p.name == "CURRENT" or p.name.startswith("MANIFEST-") or p.suffix.lower() in {".ldb", ".log"})
    ]
    for p in candidates:
        renamed.append(str(_mark_imported(p)))
    return renamed


def _dedupe_state_path(inbox: Path) -> Path:
    return inbox / _DEDUPE_STATE_FILE


def _load_dedupe_keys(inbox: Path) -> set[str]:
    path = _dedupe_state_path(inbox)
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    keys = data.get("imported_keys") if isinstance(data, dict) else None
    if not isinstance(keys, list):
        return set()
    return {str(k) for k in keys}


def _load_projection_state(path: Path) -> dict[str, set[str]]:
    """Load the in-place state file shared with foundry_memory_projection.

    Re-export shim so plan-37-12 callers (and the plan-37-03 backcompat test)
    can import this loader from `app.foundry_chat_import` without depending
    on the projection module symbol.

    Returns a dict with three set[str] buckets:
      - imported_keys: legacy importer dedupe set
      - player_projection_keys: per-player-target projection dedupe set
      - npc_projection_keys: per-NPC-target projection dedupe set

    Pre-Phase-37 state files (only `imported_keys`) load cleanly with empty
    projection sets — no exceptions, no KeyError.
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


def _save_state(
    path: Path,
    *,
    imported_keys: set[str],
    player_keys: set[str] | None = None,
    npc_keys: set[str] | None = None,
) -> None:
    """Write state file. If projection keys are None, preserve legacy single-array shape.

    When player_keys/npc_keys are provided, all three arrays are emitted. This
    matches the foundry_memory_projection write shape exactly.
    """
    if player_keys is None and npc_keys is None:
        payload: dict[str, Any] = {"imported_keys": sorted(imported_keys)}
    else:
        payload = {
            "imported_keys": sorted(imported_keys),
            "player_projection_keys": sorted(player_keys or set()),
            "npc_projection_keys": sorted(npc_keys or set()),
        }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _save_dedupe_keys(inbox: Path, keys: set[str]) -> None:
    """Legacy single-array writer — preserved as a thin wrapper over _save_state.

    When projection state is also tracked on disk, the importer must NOT trample
    the projection arrays. Read-then-merge keeps all three buckets intact.
    """
    path = _dedupe_state_path(inbox)
    existing = _load_projection_state(path)
    player = existing["player_projection_keys"]
    npc = existing["npc_projection_keys"]
    if player or npc:
        _save_state(path, imported_keys=keys, player_keys=player, npc_keys=npc)
    else:
        _save_state(path, imported_keys=keys)


def _message_key(record: dict) -> str:
    if isinstance(record.get("_id"), str) and record["_id"]:
        return f"id:{record['_id']}"
    timestamp = str(record.get("timestamp", ""))
    speaker = _speaker(record)
    content = _strip_html(str(record.get("content", "")))
    return f"fallback:{timestamp}|{speaker}|{content}"


def dedupe_foundry_import_note(markdown: str) -> tuple[str, int]:
    lines = markdown.splitlines()
    out: list[str] = []
    seen: set[str] = set()
    removed = 0
    in_table = False
    for line in lines:
        if line.strip() == "| class | speaker | content |":
            in_table = True
            out.append(line)
            continue
        if in_table and line.strip().startswith("| ---"):
            out.append(line)
            continue
        if in_table and line.strip().startswith("|") and line.strip().endswith("|"):
            key = line.strip()
            if key in seen:
                removed += 1
                continue
            seen.add(key)
        out.append(line)
    return "\n".join(out) + ("\n" if markdown.endswith("\n") else ""), removed


async def import_nedb_chatlogs_from_inbox(
    *,
    inbox_dir: str,
    dry_run: bool,
    limit: int | None,
    obsidian_client: _ObsidianLike,
    project_player_maps: bool = True,
    project_npc_history: bool = True,
    identity_resolver: Callable[[dict], Any] | None = None,
    npc_matcher: Callable[[str], Any] | None = None,
) -> dict:
    """Import Foundry NeDB chat logs copied into an Obsidian inbox folder.

    Probes files in ``inbox_dir`` for line-delimited NeDB-like chat records,
    picks the best match, classifies chat rows, and writes one markdown import
    note into PF2e session storage.
    """
    inbox = Path(inbox_dir)
    if not inbox.exists() or not inbox.is_dir():
        raise FileNotFoundError(f"inbox dir does not exist: {inbox_dir}")

    messages_db = _find_nedb_chatlog_file(inbox)

    class_counts = {"ic": 0, "roll": 0, "ooc": 0, "system": 0}
    imported_count = 0
    invalid_count = 0
    rows: list[str] = []

    records: list[dict] = []
    source_label: str

    imported_sources: list[str] = []
    leveldb_mode = False

    if messages_db is not None:
        source_label = str(messages_db)
        for line in messages_db.read_text(encoding="utf-8").splitlines():
            if limit is not None and len(records) >= limit:
                break
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                invalid_count += 1
                continue
            if _is_nedb_chat_record(record):
                records.append(record)
            else:
                invalid_count += 1
        imported_sources = [str(messages_db)]
    elif _looks_like_leveldb_dir(inbox):
        source_label = f"leveldb://{inbox}"
        records = _load_nedb_records_from_leveldb_dir(inbox, limit)
        leveldb_mode = True
        imported_sources = [
            str(p)
            for p in sorted(inbox.iterdir())
            if p.is_file() and not _is_imported_name(p.name)
        ]
    else:
        raise FileNotFoundError(f"no NeDB-style Foundry chat file found in inbox dir: {inbox}")

    if not records:
        raise FileNotFoundError(f"no importable Foundry chat records found in inbox dir: {inbox}")

    seen_keys = _load_dedupe_keys(inbox)
    new_keys: set[str] = set()

    for record in records:
        key = _message_key(record)
        if key in seen_keys or key in new_keys:
            continue
        new_keys.add(key)
        msg_class = _classify(record)
        speaker = _speaker(record)
        content = _strip_html(str(record.get("content", "")))
        class_counts[msg_class] += 1
        imported_count += 1
        rows.append(f"| {msg_class} | {speaker} | {content} |")

    now = dt.datetime.now(dt.timezone.utc)
    date = now.strftime("%Y-%m-%d")
    ts = now.strftime("%H-%M-%S")
    note_path = f"mnemosyne/pf2e/sessions/foundry-chat/{date}/chat-import-{ts}.md"

    note = "\n".join(
        [
            "---",
            f"source: {source_label}",
            f"imported_at: {now.isoformat()}",
            f"imported_count: {imported_count}",
            f"invalid_count: {invalid_count}",
            "---",
            "",
            "# Foundry Chat Import",
            "",
            "| class | speaker | content |",
            "| --- | --- | --- |",
            *rows,
            "",
        ]
    )

    renamed_sources: list[str] = []
    if not dry_run:
        await obsidian_client.put_note(note_path, note)
        _save_dedupe_keys(inbox, seen_keys | new_keys)
        if leveldb_mode:
            renamed_sources = _mark_leveldb_dir_imported(inbox)
        elif messages_db is not None and not _is_imported_name(messages_db.name):
            renamed_sources = [str(_mark_imported(messages_db))]

    projection_result: dict | None = None
    projection_enabled = project_player_maps or project_npc_history
    if (
        projection_enabled
        and identity_resolver is not None
        and npc_matcher is not None
    ):
        # Local import to keep the legacy import path of this module cheap and
        # avoid a top-level circular import (foundry_memory_projection imports
        # _message_key/_speaker from this module).
        from app.foundry_memory_projection import project_foundry_chat_memory

        projection_result = await project_foundry_chat_memory(
            records=records,
            dry_run=dry_run,
            obsidian_client=obsidian_client,
            dedupe_store_path=_dedupe_state_path(inbox),
            identity_resolver=identity_resolver,
            npc_matcher=npc_matcher,
        )

    result = {
        "source": source_label,
        "note_path": note_path,
        "imported_count": imported_count,
        "invalid_count": invalid_count,
        "class_counts": class_counts,
        "dry_run": dry_run,
        "deduped_count": len(records) - imported_count,
        "imported_sources": imported_sources,
        "renamed_sources": renamed_sources,
        "projection": projection_result,
    }
    return result
