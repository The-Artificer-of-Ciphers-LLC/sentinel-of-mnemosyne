from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Protocol


class _ObsidianLike(Protocol):
    async def put_note(self, path: str, content: str) -> None: ...


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(text: str) -> str:
    no_tags = _TAG_RE.sub(" ", text)
    return _WS_RE.sub(" ", no_tags).strip()


def _classify(record: dict) -> str:
    msg_type = record.get("type")
    content = _strip_html(str(record.get("content", "")))
    if msg_type == 5 or "roll" in content.lower():
        return "roll"
    if msg_type == 0 or content.startswith("(("):
        return "ooc"
    if msg_type in (1, 2, 3):
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
    has_content = "content" in record and isinstance(record.get("content"), str)
    has_speaker = isinstance(record.get("speaker"), dict)
    has_type = isinstance(record.get("type"), int)
    return has_content and (has_speaker or has_type)


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


def _find_nedb_chatlog_file(inbox: Path) -> Path:
    candidates = [p for p in sorted(inbox.iterdir()) if p.is_file()]
    best: tuple[Path, int, int] | None = None
    for p in candidates:
        valid, seen = _probe_nedb_file(p)
        if valid == 0:
            continue
        if best is None or valid > best[1]:
            best = (p, valid, seen)
    if best is None:
        raise FileNotFoundError(
            f"no NeDB-style Foundry chat file found in inbox dir: {inbox}"
        )
    return best[0]


async def import_nedb_chatlogs_from_inbox(
    *,
    inbox_dir: str,
    dry_run: bool,
    limit: int | None,
    obsidian_client: _ObsidianLike,
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

    for line in messages_db.read_text(encoding="utf-8").splitlines():
        if limit is not None and imported_count >= limit:
            break
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            invalid_count += 1
            continue

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
            f"source: {messages_db}",
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

    if not dry_run:
        await obsidian_client.put_note(note_path, note)

    return {
        "source": str(messages_db),
        "note_path": note_path,
        "imported_count": imported_count,
        "invalid_count": invalid_count,
        "class_counts": class_counts,
        "dry_run": dry_run,
    }
