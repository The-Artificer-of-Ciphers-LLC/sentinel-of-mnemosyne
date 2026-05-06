"""Note Intake module.

Owns note-ingestion policy for classify/file/inbox/discard flows.
Transport-neutral: raises typed domain errors; routes map to HTTP.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Awaitable, Callable

import yaml

from app.errors import EntryNotFound, InboxChangedConflict
from app.services.inbox import (
    INBOX_PATH,
    append_entry,
    build_initial_inbox,
    parse_inbox,
    remove_entry,
)
from app.services.note_classifier import ClassificationResult, TOPIC_VAULT_PATH
from app.time_utils import _iso_utc, _today_str


class NoteIntake:
    def __init__(
        self,
        vault,
        classify_note_fn: Callable[[str, str | None], Awaitable[ClassificationResult]],
    ) -> None:
        self._vault = vault
        self._classify_note = classify_note_fn

    async def classify_and_apply(self, content: str, topic: str | None = None) -> dict:
        result = await self._classify_note(content, user_topic=topic)

        if result.topic == "noise":
            return {
                "action": "dropped",
                "reason": "cheap-filter:noise",
                "topic": "noise",
                "confidence": result.confidence,
            }

        if result.topic == "unsure" or result.confidence < 0.5:
            body = await self._vault.read_note(INBOX_PATH)
            if not body or not body.strip():
                body = build_initial_inbox()
            new_body = append_entry(
                body,
                content,
                result,
                suggested=[result.topic] if result.topic != "unsure" else [],
            )
            await self._vault.write_note(INBOX_PATH, new_body)
            return {
                "action": "inboxed",
                "topic": result.topic,
                "confidence": result.confidence,
                "path": INBOX_PATH,
            }

        target = await self._resolve_target_with_collision_suffix(
            result.topic, result.title_slug or "untitled"
        )
        body = self._build_filed_note_markdown(content, result)
        await self._vault.write_note(target, body)
        return {
            "action": "filed",
            "path": target,
            "topic": result.topic,
            "confidence": result.confidence,
        }

    async def inbox_classify(self, entry_n: int, topic: str) -> dict:
        body = await self._vault.read_note(INBOX_PATH)
        entries = parse_inbox(body)

        target_entry = next((e for e in entries if e.entry_n == entry_n), None)
        if target_entry is None:
            raise EntryNotFound("entry not found")

        pre_hash = self._content_hash(body)

        result = await self._classify_note(target_entry.candidate_text, user_topic=topic)

        target = await self._resolve_target_with_collision_suffix(
            topic, result.title_slug or "untitled"
        )
        note_body = self._build_filed_note_markdown(target_entry.candidate_text, result)
        await self._vault.write_note(target, note_body)

        fresh_body = await self._vault.read_note(INBOX_PATH)
        if self._content_hash(fresh_body) != pre_hash:
            raise InboxChangedConflict(
                "inbox changed during classify; note filed but inbox not updated — re-run :inbox"
            )

        new_inbox = remove_entry(body, entry_n)
        await self._vault.write_note(INBOX_PATH, new_inbox)

        return {
            "action": "filed",
            "path": target,
            "entry_n": entry_n,
            "topic": topic,
        }

    async def inbox_discard(self, entry_n: int) -> dict:
        body = await self._vault.read_note(INBOX_PATH)
        entries = parse_inbox(body)
        target_entry = next((e for e in entries if e.entry_n == entry_n), None)
        if target_entry is None:
            raise EntryNotFound("entry not found")

        pre_hash = self._content_hash(body)

        fresh_body = await self._vault.read_note(INBOX_PATH)
        if self._content_hash(fresh_body) != pre_hash:
            raise InboxChangedConflict("inbox changed during discard — re-run :inbox")

        new_inbox = remove_entry(body, entry_n)
        await self._vault.write_note(INBOX_PATH, new_inbox)
        return {"action": "discarded", "entry_n": entry_n}

    @staticmethod
    def _topic_target_path(topic: str, slug: str) -> str:
        today = _today_str()
        base = TOPIC_VAULT_PATH.get(topic, "")
        if not base:
            return f"inbox/{slug}-{today}.md"
        if topic == "journal":
            return f"journal/{today}/{slug}.md"
        return f"{base}/{slug}-{today}.md"

    def _build_filed_note_markdown(self, content: str, result: ClassificationResult) -> str:
        fm = {
            "topic": result.topic,
            "title_slug": result.title_slug,
            "confidence": float(result.confidence),
            "created": _iso_utc(),
            "source": "note-import",
        }
        fm_block = yaml.safe_dump(
            fm, sort_keys=False, allow_unicode=True, default_flow_style=False
        ).strip()
        title = (content or "").strip().splitlines()[0][:60] or result.title_slug or "Untitled"
        return f"---\n{fm_block}\n---\n\n# {title}\n\n{content}\n"

    async def _resolve_target_with_collision_suffix(self, topic: str, slug: str) -> str:
        target = self._topic_target_path(topic, slug)
        existing = await self._vault.read_note(target)
        if existing:
            suffix = secrets.token_hex(4)
            target = self._topic_target_path(topic, f"{slug}-{suffix}")
        return target

    @staticmethod
    def _content_hash(body: str) -> str:
        return hashlib.sha256(body.encode("utf-8")).hexdigest()
