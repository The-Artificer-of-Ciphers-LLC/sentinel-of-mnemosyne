"""Pure session helpers for Phase 34 (SES-01..03, D-12..D-17, D-21..D-26).

All functions are pure logic — no I/O, no HTTP, no Discord. They form the
foundation layer consumed by app/routes/session.py (Wave 2) and app/llm.py
session-recap helpers (Wave 3).
"""
import datetime
import logging
import re

import yaml
from zoneinfo import ZoneInfo  # stdlib Python 3.9+; do NOT import pytz

logger = logging.getLogger(__name__)


def _slugify(name: str) -> str:
    """Slug generator — same normalization as Phase 29 app/routes/npc.py slugify.

    Inlined to avoid importing app.routes.npc (which pulls in reportlab/numpy,
    breaking host-side tests outside the Docker container). The pattern is
    identical: [a-z0-9-] only, longest-runs collapsed to single hyphen.
    Callers should treat this as 'from app.routes.npc import slugify'.
    """
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")



# Closed enum of recognized event types (D-12).
# 'note' is the untyped fallthrough — omits bracket prefix in formatted lines.
KNOWN_EVENT_TYPES: frozenset = frozenset(
    {"combat", "dialogue", "decision", "discovery", "loot", "note"}
)


# ---------------------------------------------------------------------------
# Event type validation (D-12)
# ---------------------------------------------------------------------------


def validate_event_type(event_type: str) -> str:
    """Return event_type if it is a known type, else 'note'.

    D-12: unknown types fall through as the default 'note' type.
    Empty string → 'note'.
    """
    if event_type in KNOWN_EVENT_TYPES:
        return event_type
    return "note"


# ---------------------------------------------------------------------------
# Event text validation (D-15)
# ---------------------------------------------------------------------------


def truncate_event_text(text: str, limit: int = 500) -> str:
    """Validate and strip event text.

    D-15: raises ValueError if text exceeds `limit` chars or contains newlines.
    Returns the stripped text unchanged (no silent truncation — caller must split).
    """
    text = text.strip()
    if "\n" in text or "\r" in text:
        raise ValueError("event text must not contain newlines")
    if len(text) > limit:
        raise ValueError(
            f"event too long (max {limit} chars, got {len(text)})"
        )
    return text


# ---------------------------------------------------------------------------
# Timestamp formatting (D-13)
# ---------------------------------------------------------------------------


def format_event_timestamp(tz_name: str = "America/New_York") -> str:
    """Return current time formatted as HH:MM in the configured timezone.

    Uses UTC internally; ZoneInfo handles DST automatically.
    D-13: SESSION_TZ env var; default America/New_York.
    """
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    local_now = utc_now.astimezone(ZoneInfo(tz_name))
    return local_now.strftime("%H:%M")


def utc_now_iso() -> str:
    """Return current UTC timestamp as ISO 8601 string for frontmatter fields."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Event line formatting (D-14)
# ---------------------------------------------------------------------------


def format_event_line(text: str, event_type: str, tz_name: str) -> str:
    """Format a single event log line for PATCH-append to ## Events Log.

    D-14: typed events → "- HH:MM [type] text"
          untyped/note events → "- HH:MM text" (no brackets)
    D-12: unknown types fall through as 'note' (no bracket).
    """
    time_str = format_event_timestamp(tz_name)
    canonical_type = validate_event_type(event_type)
    if canonical_type != "note":
        return f"- {time_str} [{canonical_type}] {text}"
    return f"- {time_str} {text}"


# ---------------------------------------------------------------------------
# NPC fast-pass slug matching (D-21)
# ---------------------------------------------------------------------------


def build_npc_link_pattern(names: list[str]) -> re.Pattern | None:
    """Build a combined word-boundary regex for NPC slug + name matching.

    D-21 fast pass: longest names sorted first to avoid substring shadowing.
    Returns None when names list is empty (no-op path for callers).
    """
    if not names:
        return None
    # Longest-first so multi-word names match before their single-word substrings.
    sorted_names = sorted(names, key=len, reverse=True)
    alternatives = [re.escape(n) for n in sorted_names]
    return re.compile(
        r"\b(" + "|".join(alternatives) + r")\b",
        re.IGNORECASE,
    )


def apply_npc_links(
    text: str,
    pattern: re.Pattern,
    slug_map: dict[str, str],
) -> str:
    """Replace NPC name occurrences with [[slug]] Obsidian wikilinks.

    slug_map: {lowercase_name_or_slug -> canonical_slug}
    Only rewrites matches that resolve to a known slug in slug_map.
    Unknown matches are left as-is (conservative — no false wikilinks).
    """

    def replacer(m: re.Match) -> str:
        matched = m.group(1)
        slug = slug_map.get(matched.lower())
        return f"[[{slug}]]" if slug else matched

    return pattern.sub(replacer, text)


# ---------------------------------------------------------------------------
# Location slug helpers (D-24, D-25, D-26)
# ---------------------------------------------------------------------------


def slugify_location(name: str) -> str:
    """Normalize a location name to a stable lowercase filename slug.

    Reuses the Phase 29 slugify pattern — [a-z0-9-] only.
    D-24: consistent with NPC slugs so cross-entity collision detection works.
    """
    return _slugify(name)


def detect_npc_slug_collision(location_slug: str, npc_slugs: set[str]) -> bool:
    """Return True when location_slug exactly matches an existing NPC slug.

    D-26: if collision, caller should skip auto-stub creation and log warning.
    """
    return location_slug in npc_slugs


def build_location_stub_markdown(name: str, slug: str, date: str) -> str:
    """Build minimal frontmatter + placeholder body for a new location stub.

    D-25: frontmatter fields: name, slug, first_seen, mentions, schema_version.
    Body: heading + one-liner placeholder for the DM to fill later.

    Date strings are written unquoted (plain YAML scalars) because yaml.dump
    would quote ISO dates as YAML timestamps. Manually construct the date lines.
    """
    fm_lines = [
        f"name: {name}",
        f"slug: {slug}",
        f"first_seen: {date}",
        "mentions:",
        f"- {date}",
        "schema_version: 1",
    ]
    fm_yaml = "\n".join(fm_lines)
    body = f"# {name}\n\n_Auto-created from session {date} — fill in details when ready._"
    return f"---\n{fm_yaml}\n---\n\n{body}\n"


# ---------------------------------------------------------------------------
# Session note markdown template (D-34, D-35)
# ---------------------------------------------------------------------------


def session_note_markdown(
    date: str,
    started_at: str,
    ended_at: str | None = None,
    status: str = "open",
    event_count: int = 0,
    npcs: list[str] | None = None,
    locations: list[str] | None = None,
    recap: str = "",
    story_so_far: str = "",
    npc_notes: dict[str, str] | None = None,
    events_log_lines: list[str] | None = None,
) -> str:
    """Build the complete session note markdown (D-34 frontmatter + D-35 sections).

    D-34: frontmatter fields: schema_version, date, status, started_at, ended_at,
          event_count, npcs, locations, recap.
    D-35: section order — Recap → Story So Far → NPCs Encountered → Locations → Events Log.
    CRITICAL: schema_version appears exactly once.
    """
    # Build frontmatter manually to avoid PyYAML quoting ISO dates as timestamps.
    # yaml.dump quotes YYYY-MM-DD strings; we need plain (unquoted) scalars for
    # human-readable Obsidian notes. Non-date fields use yaml.dump for correct
    # serialization of lists, null, etc.
    ended_at_line = "ended_at: null" if ended_at is None else f"ended_at: {ended_at}"
    npcs_list = npcs or []
    locations_list = locations or []
    npcs_yaml = yaml.dump(npcs_list, default_flow_style=True).strip()
    locations_yaml = yaml.dump(locations_list, default_flow_style=True).strip()
    # Escape recap for inline YAML (quote if it contains special chars).
    recap_yaml = yaml.dump(recap).strip()
    fm_yaml = (
        f"schema_version: 1\n"
        f"date: {date}\n"
        f"status: {status}\n"
        f"started_at: {started_at}\n"
        f"{ended_at_line}\n"
        f"event_count: {event_count}\n"
        f"npcs: {npcs_yaml}\n"
        f"locations: {locations_yaml}\n"
        f"recap: {recap_yaml}"
    ).strip()

    # -- ## Recap section --
    if recap:
        recap_body = recap
    else:
        recap_body = "_Session in progress — recap generated at session end._"

    # -- ## Story So Far section --
    if story_so_far:
        story_body = story_so_far
    else:
        story_body = "_No narrative yet — use `:pf session show` to generate._"

    # -- ## NPCs Encountered section --
    if npc_notes:
        npc_lines = "\n".join(
            f"- [[{slug}]] — {note}" for slug, note in npc_notes.items()
        )
        npcs_body = npc_lines
    else:
        npcs_body = "_Populated at session end._"

    # -- ## Locations section --
    if locations:
        loc_lines = "\n".join(f"- [[{loc}]]" for loc in locations)
        locations_body = loc_lines
    else:
        locations_body = "_Populated at session end._"

    # -- ## Events Log section --
    if events_log_lines:
        events_body = "\n".join(events_log_lines)
    else:
        events_body = ""

    return (
        f"---\n{fm_yaml}\n---\n\n"
        f"## Recap\n\n{recap_body}\n\n"
        f"## Story So Far\n\n{story_body}\n\n"
        f"## NPCs Encountered\n\n{npcs_body}\n\n"
        f"## Locations\n\n{locations_body}\n\n"
        f"## Events Log\n\n{events_body}"
    )


# ---------------------------------------------------------------------------
# Flag parsing for session verbs (D-04, RESEARCH §Flag Parsing)
# ---------------------------------------------------------------------------


async def build_npc_roster_cache(obsidian_client) -> dict:
    """Build {lowercase_name_or_slug: canonical_slug} map from vault NPC notes.

    Called by main.py lifespan at startup (D-22). Used by log verb for fast-pass
    wikilink rewriting. Returns empty dict if vault is unreachable or has no NPCs.
    Silently skips malformed notes.
    """
    roster: dict[str, str] = {}
    try:
        npc_paths = await obsidian_client.list_directory("mnemosyne/pf2e/npcs/")
    except Exception as exc:
        logger.warning("build_npc_roster_cache: list_directory failed: %s", exc)
        return roster

    for path in npc_paths:
        if not path.endswith(".md"):
            continue
        try:
            note = await obsidian_client.get_note(path)
            if note is None:
                continue
            # Extract slug from path (filename without .md extension).
            slug = path.rsplit("/", 1)[-1].replace(".md", "")
            roster[slug] = slug
            # Also index by NPC name from frontmatter if available.
            if note.startswith("---"):
                end = note.find("---", 3)
                if end > 0:
                    fm_text = note[3:end].strip()
                    try:
                        fm = yaml.safe_load(fm_text) or {}
                        name = fm.get("name", "")
                        if name and isinstance(name, str):
                            roster[name.lower()] = slug
                    except Exception:
                        pass
        except Exception as exc:
            logger.warning("build_npc_roster_cache: failed to process %s: %s", path, exc)
    return roster


def parse_session_verb_args(rest: str, verb: str) -> dict:
    """Parse flags from the remainder of a session command string.

    D-04 / RESEARCH §Flag Parsing — only verbs that accept flags have them parsed:
      start → --force, --recap
      end   → --retry-recap
      log, show, undo → no flag parsing; full rest string is event text

    Returns dict with keys: force, recap, retry_recap, args.
    """
    force = False
    recap = False
    retry_recap = False
    args = rest

    if verb in ("start",):
        force = "--force" in rest
        recap = "--recap" in rest
        for flag in ("--force", "--recap"):
            args = args.replace(flag, "")
        args = args.strip()

    elif verb in ("end",):
        retry_recap = "--retry-recap" in rest
        for flag in ("--retry-recap",):
            args = args.replace(flag, "")
        args = args.strip()

    # log, show, undo: no flag parsing — entire rest is the event text

    return {
        "force": force,
        "recap": recap,
        "retry_recap": retry_recap,
        "args": args,
    }
