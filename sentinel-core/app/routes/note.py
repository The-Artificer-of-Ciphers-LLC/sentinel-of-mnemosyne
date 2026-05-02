"""Routes for the 2nd-brain note-import + inbox flow (260427-vl1).

Endpoints:
  POST /note/classify           — classify content; file directly or inbox or drop
  GET  /inbox                   — list pending entries with discord-rendered string
  POST /inbox/classify          — file an existing inbox entry under a topic
  POST /inbox/discard           — drop an entry from inbox without filing
  POST /vault/sweep/start       — admin-gated; spawns a sweep task and returns sweep_id
  GET  /vault/sweep/status      — current sweep progress (idle/running/complete)

All Obsidian I/O goes through `request.app.state.vault`. The
classifier is a pure function (no app.state singleton needed).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import secrets
from datetime import datetime, timezone

import yaml
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.services.inbox import (
    INBOX_PATH,
    append_entry,
    build_initial_inbox,
    parse_inbox,
    remove_entry,
    render_for_discord,
)
from app.services.note_classifier import (
    TOPIC_VAULT_PATH,
    ClassificationResult,
    classify_note,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# --- Request / response models ---


class ClassifyRequest(BaseModel):
    content: str
    topic: str | None = None


class ClassifyResponse(BaseModel):
    action: str  # filed | inboxed | dropped
    path: str | None = None
    topic: str | None = None
    confidence: float | None = None
    reason: str | None = None
    entry_n: int | None = None


class InboxClassifyRequest(BaseModel):
    entry_n: int
    topic: str


class InboxDiscardRequest(BaseModel):
    entry_n: int


# --- Helpers ---


def _iso_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _topic_target_path(topic: str, slug: str) -> str:
    """Compute the vault target path for a topic + slug."""
    today = _today_str()
    base = TOPIC_VAULT_PATH.get(topic, "")
    if not base:
        # Should not be called for noise/unsure
        return f"inbox/{slug}-{today}.md"
    if topic == "journal":
        return f"journal/{today}/{slug}.md"
    return f"{base}/{slug}-{today}.md"


def _build_filed_note_markdown(
    content: str, result: ClassificationResult
) -> str:
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


async def _resolve_target_with_collision_suffix(
    vault, topic: str, slug: str
) -> str:
    """Return a target path that does not currently exist in the vault."""
    target = _topic_target_path(topic, slug)
    existing = await vault.read_note(target)
    if existing:
        suffix = secrets.token_hex(4)
        target = _topic_target_path(topic, f"{slug}-{suffix}")
    return target


def _content_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


# --- Routes ---


@router.post("/note/classify", response_model=ClassifyResponse)
async def classify_and_file(req: ClassifyRequest, request: Request) -> ClassifyResponse:
    vault = request.app.state.vault
    result = await classify_note(req.content, user_topic=req.topic)

    if result.topic == "noise":
        return ClassifyResponse(
            action="dropped",
            reason="cheap-filter:noise",
            topic="noise",
            confidence=result.confidence,
        )

    if result.topic == "unsure" or result.confidence < 0.5:
        body = await vault.read_note(INBOX_PATH)
        if not body or not body.strip():
            body = build_initial_inbox()
        new_body = append_entry(
            body,
            req.content,
            result,
            suggested=[result.topic] if result.topic != "unsure" else [],
        )
        await vault.write_note(INBOX_PATH, new_body)
        return ClassifyResponse(
            action="inboxed",
            topic=result.topic,
            confidence=result.confidence,
            path=INBOX_PATH,
        )

    # File directly
    target = await _resolve_target_with_collision_suffix(
        vault, result.topic, result.title_slug or "untitled"
    )
    body = _build_filed_note_markdown(req.content, result)
    await vault.write_note(target, body)
    return ClassifyResponse(
        action="filed",
        path=target,
        topic=result.topic,
        confidence=result.confidence,
    )


@router.get("/inbox")
async def get_inbox(request: Request):
    vault = request.app.state.vault
    body = await vault.read_note(INBOX_PATH)
    entries = parse_inbox(body)
    rendered = render_for_discord(entries)
    return {
        "entries": [e.model_dump() for e in entries],
        "rendered": rendered,
    }


@router.post("/inbox/classify")
async def inbox_classify(req: InboxClassifyRequest, request: Request):
    vault = request.app.state.vault
    body = await vault.read_note(INBOX_PATH)
    entries = parse_inbox(body)

    target_entry = next((e for e in entries if e.entry_n == req.entry_n), None)
    if target_entry is None:
        raise HTTPException(status_code=404, detail="entry not found")

    pre_hash = _content_hash(body)

    # Classify with explicit user_topic for a clean title_slug
    result = await classify_note(target_entry.candidate_text, user_topic=req.topic)

    target = await _resolve_target_with_collision_suffix(
        vault, req.topic, result.title_slug or "untitled"
    )
    note_body = _build_filed_note_markdown(target_entry.candidate_text, result)
    await vault.write_note(target, note_body)

    # Concurrency check: re-read inbox; abort if changed since pre-hash
    fresh_body = await vault.read_note(INBOX_PATH)
    if _content_hash(fresh_body) != pre_hash:
        raise HTTPException(
            status_code=409,
            detail="inbox changed during classify; note filed but inbox not updated — re-run :inbox",
        )

    new_inbox = remove_entry(body, req.entry_n)
    await vault.write_note(INBOX_PATH, new_inbox)

    return {
        "action": "filed",
        "path": target,
        "entry_n": req.entry_n,
        "topic": req.topic,
    }


@router.post("/inbox/discard")
async def inbox_discard(req: InboxDiscardRequest, request: Request):
    vault = request.app.state.vault
    body = await vault.read_note(INBOX_PATH)
    entries = parse_inbox(body)
    target_entry = next((e for e in entries if e.entry_n == req.entry_n), None)
    if target_entry is None:
        raise HTTPException(status_code=404, detail="entry not found")

    pre_hash = _content_hash(body)

    fresh_body = await vault.read_note(INBOX_PATH)
    if _content_hash(fresh_body) != pre_hash:
        raise HTTPException(
            status_code=409,
            detail="inbox changed during discard — re-run :inbox",
        )

    new_inbox = remove_entry(body, req.entry_n)
    await vault.write_note(INBOX_PATH, new_inbox)
    return {"action": "discarded", "entry_n": req.entry_n}


# --- 260427-vl1 Task 7: vault sweeper routes ---


from app.services.vault_sweeper import (  # noqa: E402
    SweepInProgressError,
    _set_status,
    get_status,
    run_sweep,
    reset_status_for_tests,  # noqa: F401
)


class SweepStartRequest(BaseModel):
    user_id: str
    force_reclassify: bool = False
    dry_run: bool = False  # preview moves without modifying the vault


def _is_admin_route(user_id: str) -> bool:
    """Defense-in-depth admin gate at the route layer (Task 8 also gates at bot)."""
    raw = os.environ.get("SENTINEL_ADMIN_USER_IDS", "")
    if raw.strip() == "*":
        return True
    allowed = {u.strip() for u in raw.split(",") if u.strip()}
    return bool(allowed) and user_id in allowed


@router.post("/vault/sweep/start")
async def vault_sweep_start(req: SweepStartRequest, request: Request):
    if not _is_admin_route(req.user_id):
        raise HTTPException(status_code=403, detail="admin only")

    vault = request.app.state.vault
    classifier = request.app.state.note_classifier_fn  # injected at startup
    embedder = request.app.state.note_embedder_fn

    sweep_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Dry-run dispatches as a background task (sync HTTP can't hold open for
    # 200+ classification calls). The proposed_moves are written to a vault
    # file at ops/sweeps/dry-run-{sweep_id}.md when the sweep finishes. The
    # response returns immediately with the future path so the caller knows
    # where to look.
    if req.dry_run:
        # Sweep_id contains colons; sanitize for use in a filename.
        id_part = sweep_id.replace(":", "-")
        report_path = f"ops/sweeps/dry-run-{id_part}.md"

        # Mirror live-sweep status updates so polling /vault/sweep/status works
        # the same way for both kinds.
        _set_status(
            type(
                "S",
                (),
                {
                    "sweep_id": sweep_id,
                    "status": "dry-running",
                    "files_processed": 0,
                    "files_total": 0,
                    "duplicates_moved": 0,
                    "noise_moved": 0,
                    "topic_moves": 0,
                },
            )()
        )

        async def _dry_runner():
            try:
                report = await run_sweep(
                    vault,
                    classifier,
                    embedder,
                    force_reclassify=req.force_reclassify,
                    status_callback=_set_status,
                    dry_run=True,
                )
                # Write the proposed-moves report to the vault as markdown.
                lines = [
                    f"# Dry-run sweep report — {sweep_id}",
                    "",
                    f"- Files scanned: {report.files_processed}/{report.files_total}",
                    f"- Topic relocations proposed: {report.topic_moves}",
                    f"- Noise→trash proposed: {report.noise_moved}",
                    f"- Duplicates→trash proposed: {report.duplicates_moved}",
                    f"- Errors: {len(report.errors)}",
                    "",
                ]
                topic_moves = [
                    m for m in report.proposed_moves if m.get("kind") == "topic"
                ]
                trash_moves = [
                    m for m in report.proposed_moves if m.get("kind") == "trash"
                ]
                if topic_moves:
                    lines.append("## Topic relocations")
                    lines.append("")
                    for m in topic_moves:
                        lines.append(
                            f"- `{m['src']}` → `{m['dst']}` — {m.get('reason', '')}"
                        )
                    lines.append("")
                if trash_moves:
                    lines.append("## Trash moves")
                    lines.append("")
                    for m in trash_moves:
                        lines.append(
                            f"- `{m['src']}` → `{m['dst']}` — {m.get('reason', '')}"
                        )
                    lines.append("")
                if report.errors:
                    lines.append("## Errors")
                    lines.append("")
                    for e in report.errors[:50]:
                        lines.append(f"- {e}")
                    lines.append("")
                body = "\n".join(lines)
                await vault.write_note(report_path, body)
                # Stash report path on status so callers can find it.
                cur = get_status()
                cur["status"] = "dry-run-complete"
                cur["report_path"] = report_path
                cur["topic_moves"] = report.topic_moves
                cur["noise_moved"] = report.noise_moved
                cur["duplicates_moved"] = report.duplicates_moved
                cur["files_processed"] = report.files_processed
                cur["files_total"] = report.files_total
            except SweepInProgressError:
                cur = get_status()
                cur["status"] = "blocked"
            except Exception as exc:
                logger.exception("dry-run sweep crashed: %s", exc)
                cur = get_status()
                cur["status"] = "error"

        asyncio.create_task(_dry_runner())
        return {
            "sweep_id": sweep_id,
            "status": "dry-running",
            "report_path": report_path,
        }

    # Live run: kick off background task, return immediately.
    # Update status immediately so callers see "running" before the task starts.
    _set_status(
        type(
            "S",
            (),
            {
                "sweep_id": sweep_id,
                "status": "running",
                "files_processed": 0,
                "files_total": 0,
                "duplicates_moved": 0,
                "noise_moved": 0,
                "topic_moves": 0,
            },
        )()
    )

    async def _runner():
        try:
            report = await run_sweep(
                vault,
                classifier,
                embedder,
                force_reclassify=req.force_reclassify,
                status_callback=_set_status,
            )
            _set_status(report)
        except SweepInProgressError:
            cur = get_status()
            cur["status"] = "blocked"
        except Exception as exc:
            logger.exception("vault sweep crashed: %s", exc)
            cur = get_status()
            cur["status"] = "error"

    asyncio.create_task(_runner())
    return {"sweep_id": sweep_id, "status": "running"}


@router.get("/vault/sweep/status")
async def vault_sweep_status():
    return get_status()
