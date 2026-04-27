"""POST /session — DM session notes with timestamped event logging and AI-stylized recap (SES-01..03).

Module-level singletons (obsidian, npc_roster_cache) are assigned by main.py lifespan.
Tests patch them at app.routes.session.{obsidian, npc_roster_cache}.

Pattern mirrors app.routes.rule (multi-verb router, singletons, LLM dispatch).

Singleton test-patching contract:
    with patch('app.routes.session.obsidian', mock_obsidian):
        with patch('app.routes.session.npc_roster_cache', mock_cache):
            ...

D-05: No in-memory session state — every verb reads state from Obsidian.
D-06: start collision: check get_note before put_note; refuse if open note exists.
D-31: end LLM failure writes skeleton note (status=ended, empty recap sections).
D-32: --retry-recap re-reads events log from ended note and reruns generate_session_recap.
"""
from __future__ import annotations

import datetime
import logging
import re

import yaml
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from app.config import settings
from app.llm import generate_session_recap, generate_story_so_far
from app.resolve_model import resolve
from app.session import (
    KNOWN_EVENT_TYPES,
    apply_npc_links,
    build_location_stub_markdown,
    build_npc_link_pattern,
    detect_npc_slug_collision,
    format_event_line,
    session_note_markdown,
    slugify,
    slugify_location,
    truncate_event_text,
    utc_now_iso,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/session", tags=["session"])

# Module-level singletons — set by main.py lifespan, patchable in tests.
obsidian = None  # type: ignore[assignment]  — set to ObsidianClient in lifespan
npc_roster_cache: dict | None = None  # {lowercase_name_or_slug: slug, ...} — set by lifespan


# ---------------------------------------------------------------------------
# Input validator (D-15, T-34-01)
# ---------------------------------------------------------------------------


def _validate_session_event(v: str) -> str:
    """Validate event text per D-15 and T-34-01.

    Max 500 chars. No newlines. No control characters.
    """
    if not isinstance(v, str):
        raise ValueError("event text must be a string")
    v = v.strip()
    if not v:
        raise ValueError("event text cannot be empty")
    if len(v) > 500:
        raise ValueError(f"event too long (max 500 chars, got {len(v)})")
    if re.search(r"[\n\r]", v):
        raise ValueError(
            "event text must not contain newlines — use multiple :pf session log calls"
        )
    if re.search(r"[\x00-\x08\x0b-\x1f\x7f]", v):
        raise ValueError("event text contains invalid control characters")
    return v


# ---------------------------------------------------------------------------
# Pydantic request model
# ---------------------------------------------------------------------------


class SessionRequest(BaseModel):
    """Request shape for POST /session (SES-01..03)."""

    verb: str
    args: str = ""
    flags: dict = Field(default_factory=dict)
    user_id: str = ""

    @field_validator("verb")
    @classmethod
    def _validate_verb(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in {"start", "log", "end", "show", "undo"}:
            raise ValueError(f"unknown session verb: {v!r}")
        return v

    @model_validator(mode="after")
    def _validate_log_args(self) -> "SessionRequest":
        # CR-02: wire _validate_session_event at the model boundary for the log verb.
        # Other verbs expect args to be empty or contain flags — validate only when verb=="log".
        if self.verb == "log":
            self.args = _validate_session_event(self.args)
        return self


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _parse_note_frontmatter(note_text: str) -> dict:
    """Parse YAML frontmatter from a note. Returns empty dict on any failure.

    Pattern from npc.py _parse_frontmatter — never raises.
    """
    try:
        if not note_text.startswith("---"):
            return {}
        end = note_text.find("---", 3)
        if end == -1:
            return {}
        frontmatter_text = note_text[3:end].strip()
        return yaml.safe_load(frontmatter_text) or {}
    except Exception as exc:
        logger.warning("_parse_note_frontmatter: parse failed: %s", exc)
        return {}


async def _build_npc_frontmatter_block(
    npc_slugs: list[str],
    obsidian_client,
) -> str:
    """Fetch NPC note text for each slug; concatenate for LLM context.

    Silently skips 404s (get_note returns None on 404/error — ObsidianClient contract).
    """
    blocks: list[str] = []
    for slug in npc_slugs:
        note = await obsidian_client.get_note(f"mnemosyne/pf2e/npcs/{slug}.md")
        if note is not None:
            blocks.append(note)
    return "\n\n".join(blocks)


async def _create_location_stubs(
    locations: list[str],
    date_str: str,
    npc_slugs: set[str],
    obsidian_client,
) -> None:
    """Create location stub notes for new locations found in the recap.

    D-25: for each location name, slugify, check collision with npc_slugs,
    check if note already exists, create stub if absent.
    T-34-03: slugify_location normalizes to [a-z0-9-] only; path prefix hardcoded.
    """
    for name in locations:
        loc_slug = slugify_location(name)
        if not loc_slug:
            logger.warning("_create_location_stubs: empty slug for location %r — skipping", name)
            continue
        if detect_npc_slug_collision(loc_slug, npc_slugs):
            logger.warning(
                "_create_location_stubs: location slug %r collides with NPC slug — skipping stub creation",
                loc_slug,
            )
            continue
        loc_path = f"mnemosyne/pf2e/locations/{loc_slug}.md"
        existing = await obsidian_client.get_note(loc_path)
        if existing is None:
            stub_md = build_location_stub_markdown(name, loc_slug, date_str)
            try:
                await obsidian_client.put_note(loc_path, stub_md)
                logger.info(
                    "_create_location_stubs: created stub %s for location %r",
                    loc_path, name,
                )
            except Exception as exc:
                logger.warning(
                    "_create_location_stubs: failed to create stub for %r: %s",
                    name, exc,
                )
        else:
            # Location already exists — update mentions field (D-25).
            try:
                fm = _parse_note_frontmatter(existing)
                mentions = fm.get("mentions") or []
                if not isinstance(mentions, list):
                    mentions = []
                if date_str not in mentions:
                    mentions.append(date_str)
                    await obsidian_client.patch_frontmatter_field(loc_path, "mentions", mentions)
            except Exception as exc:
                logger.warning(
                    "_create_location_stubs: failed to update mentions for %r: %s",
                    name, exc,
                )


def _extract_events_log_section(note_text: str) -> tuple[list[str], str]:
    """Extract bullet lines from ## Events Log section.

    Returns (event_lines, events_section_raw_text).
    event_lines: list of "- ..." bullet strings.
    """
    match = re.search(r"## Events Log\s*\n(.*?)(?=\n## |\Z)", note_text, re.DOTALL)
    if not match:
        return [], ""
    section_text = match.group(1).strip()
    lines = [line for line in section_text.splitlines() if line.startswith("- ")]
    return lines, section_text


# ---------------------------------------------------------------------------
# Verb handlers
# ---------------------------------------------------------------------------


async def _handle_start(req: SessionRequest, today_str: str, path: str) -> dict:
    """Handle start verb: create new open session note (D-06 collision enforced)."""
    force = req.flags.get("force", False)
    recap_flag = req.flags.get("recap", False)

    # D-06: collision check — read existing note before writing.
    existing_note = await obsidian.get_note(path)
    forced_prior_recap: str | None = None
    if existing_note is not None:
        fm = _parse_note_frontmatter(existing_note)
        status = fm.get("status", "")
        if status == "open" and not force:
            return {
                "error": (
                    f"A session is already open for {today_str}. "
                    "Use --force to start a new one (existing session will be replaced), "
                    "or :pf session end to close it first."
                ),
                "type": "refuse",
            }
        elif status == "ended" and not force:
            return {
                "error": (
                    f"A session already exists for {today_str} with status=ended. "
                    "Use --force to overwrite."
                ),
                "type": "refuse",
            }
        # Capture recap from the note being overwritten so the post-PUT scan
        # still surfaces it even though the path will be reused (same-day --force).
        if force and status == "ended":
            candidate = fm.get("recap", "")
            if candidate and isinstance(candidate, str):
                forced_prior_recap = candidate

    # Build new open session note.
    started_at = utc_now_iso()
    note_content = session_note_markdown(
        date=today_str,
        started_at=started_at,
        status="open",
    )

    try:
        await obsidian.put_note(path, note_content)
        logger.info("session_start: date=%s user=%s", today_str, req.user_id)
    except Exception as exc:
        logger.error("session_start: Obsidian write failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail={"error": "Obsidian write failed", "detail": str(exc)},
        )

    # D-08/D-09/D-10: check for prior ended session to offer recap.
    # Use the recap captured before the --force overwrite if available; otherwise
    # scan the vault for the most recent ended session on a different date.
    recap_text = None
    recap_available = False
    if forced_prior_recap:
        recap_available = True
        recap_text = forced_prior_recap
    else:
        try:
            prior_sessions = await obsidian.list_directory("mnemosyne/pf2e/sessions/")
            for prior_path in sorted(prior_sessions, reverse=True):
                if prior_path == path:
                    continue
                prior_note = await obsidian.get_note(prior_path)
                if prior_note is None:
                    continue
                prior_fm = _parse_note_frontmatter(prior_note)
                if prior_fm.get("status") == "ended":
                    prior_recap = prior_fm.get("recap", "")
                    if prior_recap and isinstance(prior_recap, str):
                        recap_available = True
                        recap_text = prior_recap
                    break
        except Exception as exc:
            logger.warning("session_start: prior session scan failed: %s", exc)

    return {
        "type": "start",
        "path": path,
        "date": today_str,
        "recap_text": recap_text,
        "recap_available": recap_available,
    }


async def _handle_log(req: SessionRequest, path: str) -> dict:
    """Handle log verb: append formatted event to Events Log heading (D-14, D-16)."""
    # Check note exists and is open.
    note = await obsidian.get_note(path)
    if note is None:
        return {"error": f"No session note found at {path}. Start a session first.", "type": "error"}
    fm = _parse_note_frontmatter(note)
    if fm.get("status") != "open":
        return {
            "error": f"Session is not open (status={fm.get('status', 'unknown')}). Cannot log events.",
            "type": "error",
        }

    # Parse event type and text from args.
    args = req.args
    colon_idx = args.find(":")
    if colon_idx > 0:
        candidate_type = args[:colon_idx].strip().lower()
        if candidate_type in KNOWN_EVENT_TYPES:
            event_type = candidate_type
            text = args[colon_idx + 1:].strip()
        else:
            event_type = "note"
            text = args
    else:
        event_type = "note"
        text = args

    # Validate event text (D-15).
    try:
        text = truncate_event_text(text)
    except ValueError as exc:
        return {"error": str(exc), "type": "error"}

    # NPC fast-pass: apply wikilinks if roster cache is available (D-21).
    linked_text = text
    if npc_roster_cache:
        pattern = build_npc_link_pattern(list(npc_roster_cache.keys()))
        if pattern is not None:
            linked_text = apply_npc_links(text, pattern, npc_roster_cache)

    # Format event line (D-14).
    formatted_line = format_event_line(linked_text, event_type, settings.session_tz)

    # PATCH append to Events Log heading (D-16).
    try:
        await obsidian.patch_heading(path, "Events Log", formatted_line + "\n", operation="append")
    except Exception as exc:
        logger.warning("session_log: PATCH append failed for %s: %s", path, exc)
        return {"error": f"Failed to append event: {exc}", "type": "error"}

    return {"type": "log", "line": formatted_line}


async def _handle_undo(req: SessionRequest, path: str) -> dict:
    """Handle undo verb: remove last bullet from Events Log (D-17)."""
    note = await obsidian.get_note(path)
    if note is None:
        return {"error": f"No session note found at {path}.", "type": "error"}
    fm = _parse_note_frontmatter(note)
    if fm.get("status") != "open":
        return {
            "error": f"Session is not open (status={fm.get('status', 'unknown')}). Cannot undo.",
            "type": "error",
        }

    event_lines, _section_text = _extract_events_log_section(note)
    if not event_lines:
        return {"error": "No events to undo.", "type": "error"}

    removed_line = event_lines[-1]
    remaining_lines = event_lines[:-1]
    remaining_count = len(remaining_lines)

    # Rebuild Events Log section body (WR-02: send "\n" when empty so the heading
    # is preserved; empty string deletes the section content entirely).
    new_events_body = "\n".join(remaining_lines) if remaining_lines else ""
    body_to_send = new_events_body if new_events_body else "\n"

    # Try patch_heading replace first; fall back to GET-then-PUT on failure (D-17).
    try:
        await obsidian.patch_heading(
            path, "Events Log", body_to_send, operation="replace"
        )
    except Exception as patch_exc:
        logger.warning(
            "session_undo: patch_heading replace failed (%s); falling back to GET-then-PUT",
            patch_exc,
        )
        # GET-then-PUT fallback: replace the Events Log section in the full note text.
        events_section_re = re.compile(
            r"(## Events Log\s*\n).*?(?=\n## |\Z)", re.DOTALL
        )
        new_note = events_section_re.sub(
            lambda m: m.group(1) + body_to_send,
            note,
        )
        try:
            await obsidian.put_note(path, new_note)
        except Exception as put_exc:
            logger.error("session_undo: GET-then-PUT fallback failed: %s", put_exc)
            raise HTTPException(
                status_code=503,
                detail={"error": "Obsidian write failed during undo", "detail": str(put_exc)},
            )

    logger.info("session_undo: removed event, remaining=%d", remaining_count)
    return {
        "type": "undo",
        "removed": removed_line,
        "remaining": remaining_count,
    }


async def _handle_show(req: SessionRequest, path: str) -> dict:
    """Handle show verb: generate Story So Far narrative and patch section (D-18/D-19)."""
    note = await obsidian.get_note(path)
    if note is None:
        return {"error": f"No session note found at {path}.", "type": "error"}
    fm = _parse_note_frontmatter(note)
    # show works on both open and ended notes.
    # str() handles datetime.date objects that yaml.safe_load may return for YYYY-MM-DD values.
    date_str = str(fm.get("date", datetime.date.today().isoformat()))

    event_lines, events_section_text = _extract_events_log_section(note)
    events_log = "\n".join(event_lines) if event_lines else "_No events logged yet._"

    r_chat = await resolve("chat")
    model = r_chat.model
    profile_chat = r_chat.profile
    api_base = settings.litellm_api_base or None

    narrative = await generate_story_so_far(
        events_log, model=model, api_base=api_base, profile=profile_chat
    )

    # Patch Story So Far section (D-19).
    try:
        await obsidian.patch_heading(path, "Story So Far", narrative, operation="replace")
    except Exception as exc:
        logger.warning("session_show: patch_heading for Story So Far failed: %s", exc)
        # Degrade gracefully — still return the narrative.

    logger.info("session_show: narrative generated, date=%s user=%s", date_str, req.user_id)
    return {
        "type": "show",
        "narrative": narrative,
        "date": date_str,
    }


async def _handle_end(req: SessionRequest, path: str) -> dict:
    """Handle end verb: generate recap, write full ended note (D-27, D-31, D-32)."""
    retry_recap = req.flags.get("retry_recap", False)

    note = await obsidian.get_note(path)
    if note is None:
        return {"error": f"No session note found at {path}.", "type": "error"}

    fm = _parse_note_frontmatter(note)
    status = fm.get("status", "")

    # D-32 --retry-recap: allow on ended notes; refuse on open-note-only otherwise.
    if status == "ended" and not retry_recap:
        return {
            "error": (
                f"Session {path} is already ended. "
                "Use --retry-recap to regenerate the recap."
            ),
            "type": "error",
        }
    if status not in ("open", "ended"):
        return {
            "error": f"Unexpected session status={status!r}. Cannot end.",
            "type": "error",
        }

    date_str = str(fm.get("date", datetime.date.today().isoformat()))
    raw_started_at = fm.get("started_at")
    if isinstance(raw_started_at, datetime.datetime):
        started_at = raw_started_at.isoformat()
    elif raw_started_at is not None:
        started_at = str(raw_started_at)
    else:
        started_at = utc_now_iso()

    event_lines, _section_text = _extract_events_log_section(note)
    events_log = "\n".join(event_lines) if event_lines else "_No events logged._"

    # Collect NPC slugs from wikilinks in events log only (WR-03: roster excluded —
    # fetching all NPCs inflates LLM context with absent characters).
    wikilink_slugs = set(re.findall(r"\[\[([^\]]+)]]", events_log))
    candidate_npc_slugs = list(wikilink_slugs)

    # Build NPC context block for LLM.
    npc_frontmatter_block = await _build_npc_frontmatter_block(candidate_npc_slugs, obsidian)

    r_chat = await resolve("chat")
    model = r_chat.model
    profile_chat = r_chat.profile
    api_base = settings.litellm_api_base or None
    ended_at = utc_now_iso()

    try:
        recap_data = await generate_session_recap(
            events_log=events_log,
            npc_frontmatter_block=npc_frontmatter_block,
            model=model,
            api_base=api_base,
            profile=profile_chat,
        )
    except Exception as exc:
        # D-31: LLM failure → write skeleton note; hint --retry-recap.
        logger.warning("session_end: LLM recap failed: %s — writing skeleton note", exc)
        skeleton_note = session_note_markdown(
            date=date_str,
            started_at=str(started_at),
            ended_at=ended_at,
            status="ended",
            event_count=len(event_lines),
            events_log_lines=event_lines,
        )
        # Inject retry hint into Recap section.
        retry_hint = (
            "_recap generation failed — run :pf session end --retry-recap to generate later_"
        )
        skeleton_note = skeleton_note.replace(
            "_Session in progress — recap generated at session end._",
            retry_hint,
        )
        try:
            await obsidian.put_note(path, skeleton_note)
        except Exception as write_exc:
            logger.error("session_end: skeleton note write failed: %s", write_exc)
            raise HTTPException(
                status_code=503,
                detail={"error": "Obsidian write failed (skeleton)", "detail": str(write_exc)},
            )
        return {
            "type": "end_skeleton",
            "path": path,
            "error": str(exc),
            "message": (
                "Session ended with skeleton note. "
                "Run :pf session end --retry-recap to generate the recap."
            ),
        }

    # Success path: post-process LLM output.
    raw_npcs = recap_data.get("npcs", [])
    raw_locations = recap_data.get("locations", [])
    npc_notes = recap_data.get("npc_notes_per_character", {})
    recap_text = recap_data.get("recap", "")

    # T-34-02: normalize NPC slugs using slugify() (from app.routes.npc, NOT slugify_location).
    # This maintains consistent slug identity with NPCs created in Phase 29.
    valid_npc_slugs = []
    for raw_slug in raw_npcs:
        normalized = slugify(str(raw_slug))
        if normalized and (
            npc_roster_cache is None
            or normalized in npc_roster_cache.values()
            or normalized in npc_roster_cache
            or raw_slug in npc_roster_cache
        ):
            valid_npc_slugs.append(normalized)

    # T-34-03: normalize location names through slugify_location before Obsidian writes.
    location_slugs = [slugify_location(loc) for loc in raw_locations if loc]

    # D-25: create location stubs for new locations.
    npc_slugs_set = set(npc_roster_cache.keys()) if npc_roster_cache else set()
    await _create_location_stubs(raw_locations, date_str, npc_slugs_set, obsidian)

    # Apply NPC wikilinks to recap text before building the note (CR-01).
    if valid_npc_slugs:
        npc_link_pattern = build_npc_link_pattern(valid_npc_slugs)
        if npc_link_pattern is not None:
            slug_map = {s: s for s in valid_npc_slugs}
            recap_text = apply_npc_links(recap_text, npc_link_pattern, slug_map)

    # Build full ended note.
    full_note = session_note_markdown(
        date=date_str,
        started_at=started_at,
        ended_at=ended_at,
        status="ended",
        event_count=len(event_lines),
        npcs=valid_npc_slugs,
        locations=location_slugs,
        recap=recap_text,
        npc_notes=npc_notes,
        events_log_lines=event_lines,
    )

    try:
        await obsidian.put_note(path, full_note)
        logger.info(
            "session_end: note written, date=%s npcs=%s locations=%s user=%s",
            date_str, valid_npc_slugs, location_slugs, req.user_id,
        )
    except Exception as exc:
        logger.error("session_end: Obsidian write failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail={"error": "Obsidian write failed", "detail": str(exc)},
        )

    return {
        "type": "end",
        "path": path,
        "date": date_str,
        "recap": recap_text[:500],
        "npcs": valid_npc_slugs,
        "locations": location_slugs,
    }


# ---------------------------------------------------------------------------
# Main route — verb dispatcher
# ---------------------------------------------------------------------------


@router.post("")
async def session_dispatch(req: SessionRequest) -> JSONResponse:
    """Dispatch session verb to the appropriate handler.

    All verbs read state from Obsidian (D-05 — no in-memory session state).
    503 returned when obsidian singleton is not yet set by lifespan.
    """
    if obsidian is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "session subsystem not initialised (lifespan incomplete?)"},
        )

    today_str = datetime.date.today().isoformat()
    path = f"mnemosyne/pf2e/sessions/{today_str}.md"
    verb = req.verb

    if verb == "start":
        result = await _handle_start(req, today_str, path)
    elif verb == "log":
        result = await _handle_log(req, path)
    elif verb == "undo":
        result = await _handle_undo(req, path)
    elif verb == "show":
        result = await _handle_show(req, path)
    elif verb == "end":
        result = await _handle_end(req, path)
    else:
        # Should not reach here — field_validator rejects unknown verbs.
        raise HTTPException(status_code=400, detail={"error": f"unknown verb: {verb!r}"})

    return JSONResponse(content=result)
