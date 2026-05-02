"""Pure helpers for the pending-classification inbox.

Source of truth: a single Obsidian markdown note at ``inbox/_pending-classification.md``
with a frontmatter block plus zero or more ``## Entry N`` sections. The user
or the bot can mutate the file; helpers here are pure (body in → body out)
so callers compose their own GET-then-PUT semantics in the route layer.

Format (RESEARCH §5):

    ---
    type: pending-classification-inbox
    updated: 2026-04-27T11:00:00Z
    ---

    # Pending Classification

    Edit the `topic:` field on any entry to file it; the bot picks up changes
    on the next `:inbox`. Or use `:inbox classify <n> <topic>` /
    `:inbox discard <n>` from Discord.

    ## Entry 1
    - timestamp: 2026-04-27T11:00:00Z
    - topic: unsure
    - suggested: reference, observation
    - confidence: 0.4
    - reasoning: short reasoning text

    > Candidate text body, possibly multi-line, prefixed with > on each line.

This module is I/O-free. Wire Obsidian reads/writes in the route layer.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Iterable

from pydantic import BaseModel, Field

from app.markdown_frontmatter import join_frontmatter, split_frontmatter
from app.services.note_classifier import ClassificationResult


INBOX_PATH = "inbox/_pending-classification.md"


class PendingEntry(BaseModel):
    """One pending classification entry parsed from the inbox markdown."""

    entry_n: int
    timestamp: str = ""
    topic: str = "unsure"
    suggested: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    reasoning: str = ""
    candidate_text: str = ""


def _iso_utc(now: datetime | None = None) -> str:
    n = now or datetime.now(timezone.utc)
    return n.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_ENTRY_HEADER_RE = re.compile(r"^## Entry (\d+)\s*$", re.MULTILINE)
# _FRONTMATTER_RE / _split_frontmatter / _join_frontmatter migrated to
# app.markdown_frontmatter (260502-g8c Task 3).


def build_initial_inbox(now: datetime | None = None) -> str:
    """Return the canonical empty inbox body (frontmatter + header + instructions)."""
    fm = {
        "type": "pending-classification-inbox",
        "updated": _iso_utc(now),
    }
    body = (
        "# Pending Classification\n\n"
        "Edit the `topic:` field on any entry to file it; the bot picks up\n"
        "changes on the next `:inbox`. Or use `:inbox classify <n> <topic>`\n"
        "or `:inbox discard <n>` from Discord.\n"
    )
    return join_frontmatter(fm, body)


def _parse_entry_section(section_text: str, entry_n: int) -> PendingEntry:
    """Parse one Entry block (text between section headers, no header itself)."""
    fields: dict[str, str] = {}
    candidate_lines: list[str] = []
    for raw_line in section_text.splitlines():
        line = raw_line.rstrip()
        if not line:
            if candidate_lines:
                candidate_lines.append("")
            continue
        if line.startswith("> "):
            candidate_lines.append(line[2:])
        elif line.startswith(">"):
            candidate_lines.append(line[1:].lstrip())
        elif line.startswith("- ") and ":" in line:
            key, _, val = line[2:].partition(":")
            fields[key.strip().lower()] = val.strip()
        # ignore stray prose

    suggested_raw = fields.get("suggested", "")
    suggested = [s.strip() for s in suggested_raw.split(",") if s.strip()] if suggested_raw else []

    try:
        confidence = float(fields.get("confidence", "0") or 0)
    except ValueError:
        confidence = 0.0

    return PendingEntry(
        entry_n=entry_n,
        timestamp=fields.get("timestamp", ""),
        topic=fields.get("topic", "unsure") or "unsure",
        suggested=suggested,
        confidence=confidence,
        reasoning=fields.get("reasoning", ""),
        candidate_text="\n".join(candidate_lines).strip(),
    )


def parse_inbox(body: str) -> list[PendingEntry]:
    """Parse inbox body into PendingEntry list, ordered by entry_n."""
    if not body or not body.strip():
        return []
    _, rest = split_frontmatter(body)
    headers = list(_ENTRY_HEADER_RE.finditer(rest))
    if not headers:
        return []
    entries: list[PendingEntry] = []
    for i, m in enumerate(headers):
        entry_n = int(m.group(1))
        start = m.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(rest)
        section = rest[start:end]
        entries.append(_parse_entry_section(section, entry_n))
    entries.sort(key=lambda e: e.entry_n)
    return entries


def _render_entry(e: PendingEntry) -> str:
    """Render one entry as canonical markdown block (no header line)."""
    suggested = ", ".join(e.suggested)
    quoted = "\n".join(f"> {ln}" if ln else ">" for ln in (e.candidate_text or "").splitlines())
    if not quoted:
        quoted = "> "
    return (
        f"- timestamp: {e.timestamp}\n"
        f"- topic: {e.topic}\n"
        f"- suggested: {suggested}\n"
        f"- confidence: {e.confidence}\n"
        f"- reasoning: {e.reasoning}\n"
        f"\n{quoted}\n"
    )


def _rebuild_body(fm: dict, entries: Iterable[PendingEntry]) -> str:
    header = (
        "# Pending Classification\n\n"
        "Edit the `topic:` field on any entry to file it; the bot picks up\n"
        "changes on the next `:inbox`. Or use `:inbox classify <n> <topic>`\n"
        "or `:inbox discard <n>` from Discord.\n\n"
    )
    chunks = [header]
    for e in entries:
        chunks.append(f"## Entry {e.entry_n}\n{_render_entry(e)}\n")
    return join_frontmatter(fm, "".join(chunks))


def append_entry(
    body: str,
    candidate_text: str,
    result: ClassificationResult,
    suggested: list[str] | None = None,
    now: datetime | None = None,
) -> str:
    """Append a new entry; renumber sequentially; refresh `updated:` frontmatter."""
    if not body or not body.strip():
        body = build_initial_inbox(now)
    fm, _ = split_frontmatter(body)
    if not fm:
        fm = {"type": "pending-classification-inbox"}
    fm["updated"] = _iso_utc(now)
    fm.setdefault("type", "pending-classification-inbox")

    entries = parse_inbox(body)
    next_n = (max((e.entry_n for e in entries), default=0)) + 1

    new_entry = PendingEntry(
        entry_n=next_n,
        timestamp=_iso_utc(now),
        topic=result.topic,
        suggested=list(suggested or []),
        confidence=float(result.confidence),
        reasoning=(result.reasoning or "")[:300],
        candidate_text=candidate_text or "",
    )
    return _rebuild_body(fm, entries + [new_entry])


def remove_entry(body: str, entry_n: int, now: datetime | None = None) -> str:
    """Remove the named entry, renumber the rest sequentially, refresh updated."""
    fm, _ = split_frontmatter(body)
    if not fm:
        fm = {"type": "pending-classification-inbox"}
    fm["updated"] = _iso_utc(now)
    fm.setdefault("type", "pending-classification-inbox")

    kept = [e for e in parse_inbox(body) if e.entry_n != entry_n]
    # renumber
    renumbered = []
    for i, e in enumerate(kept, start=1):
        renumbered.append(e.model_copy(update={"entry_n": i}))
    return _rebuild_body(fm, renumbered)


def render_for_discord(entries: list[PendingEntry]) -> str:
    """Numbered list with 80-char preview and suggested topic in parens."""
    if not entries:
        return "(inbox is empty)"
    lines = []
    for e in entries:
        preview = (e.candidate_text or "").replace("\n", " ").strip()
        if len(preview) > 80:
            preview = preview[:77] + "..."
        suggestion = e.topic
        if e.suggested:
            suggestion = e.suggested[0]
        lines.append(f"{e.entry_n}. {preview} (suggested: {suggestion})")
    return "\n".join(lines)
