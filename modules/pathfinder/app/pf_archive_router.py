"""Cartosia archive router (260427-czb Task 1).

Pure-function classifier over a single (Path, content) input. Returns a
:class:`RouteDecision` describing which vault bucket the file belongs in,
its slug, the destination path, and (for dialogue files) the owner NPC slug.

The router does NOT touch the vault, the LLM, or the network. It is the
first stage of the cartosia importer pipeline; the orchestrator
(``cartosia_import.py``) walks the archive, calls :func:`route` per file,
and then dispatches to the per-bucket writer.

Bucket precedence — high→low:

1. **Filename keyword overrides** — ``Adventure Hooks.md`` and
   ``Harvest Table - X.md`` always win over their parent dir. (Research
   §Edge case 5.)
2. **Dialogue detection** — filename matches ``things said``, ``dialogue``,
   or ``acknowledg`` (case-insensitive). Owner inferred from parent dir if
   that dir is a known NPC slug, else from the filename's leading
   proper-noun token prefix-matched against ``known_npc_slugs``.
3. **NPC content sniff** — ``**Creature N**`` + ``**AC** N`` (Format A) or
   ``### Biography`` + ``### Appearance`` with body (Format B).
4. **Path prefix** — ``Decided Rules/`` → homebrew, ``Crafting System/``
   non-harvest → homebrew, ``Codex of Elemental Gateways/`` → lore/codex,
   ``Cartosia/**`` non-NPC → location.
5. **Special files** — ``session-log.md`` → session at literal
   ``_archive-import.md`` (Pitfall 9). Body < 200 chars → skip.
6. **Fallback** — lore at the deepest non-trivial path segment.

Slug rule: lowercase, ``[^a-z0-9]+`` collapsed to ``-``, trailing/leading
``-`` stripped. ``Veela and Tarek`` → ``veela-and-tarek``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

Bucket = Literal[
    "npc_a",
    "npc_b",
    "npc_dialogue",
    "location",
    "homebrew",
    "harvest",
    "lore",
    "session",
    "arc",
    "faction",
    "skip",
]


@dataclass(frozen=True)
class RouteDecision:
    """Routing verdict for a single archive .md file.

    Attributes:
      bucket: which destination namespace this file belongs in.
      slug: filesystem-safe slug derived from the file or NPC name.
      owner_slug: for ``npc_dialogue`` only — the slug of the owning NPC.
      dest: full vault path (relative to vault root). e.g.
        ``mnemosyne/pf2e/npcs/fenn-the-beggar.md``.
      reason: short human-readable explanation surfaced in the dry-run report.
    """

    bucket: Bucket
    slug: str
    dest: str
    reason: str
    owner_slug: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_CREATURE_RE = re.compile(r"\*\*Creature\s+\d+\*\*")
_AC_RE = re.compile(r"\*\*AC\*\*\s+\d+")
# "Level N NPC" / "Level N NPCs" appearing in a title or first 200 chars of
# the file is a creature-level cue (real archive uses this in lieu of the
# **Creature N** marker — e.g. "Veela & Tarek, the Street Hood Twins (Level 2 NPCs)").
_LEVEL_NPC_RE = re.compile(r"\bLevel\s+\d+\s+NPCs?\b", re.IGNORECASE)
_BIO_RE = re.compile(r"###\s+Biography\b", re.IGNORECASE)
_APPEAR_RE = re.compile(r"###\s+Appearance\b", re.IGNORECASE)
# Real archive often uses **Appearance:** (bold prefix) instead of an
# `### Appearance` header — pair it with `### Biography` as a Format B
# alternate signal. Same body-length rule applies.
_APPEAR_BOLD_RE = re.compile(r"\*\*Appearance:\*\*", re.IGNORECASE)

# Filename keyword tokens for dialogue detection — matched case-insensitively
# against the *stem* (no .md extension) anywhere in the name.
_DIALOGUE_KEYWORDS = ("things said", "dialogue", "acknowledg")

# Filename keywords that hijack routing regardless of parent dir.
_ARC_FILENAME_PREFIXES = ("adventure hooks",)
_HARVEST_FILENAME_PREFIX = "harvest table - "

# Path prefix → bucket mapping (path segments, case-sensitive on disk).
_HOMEBREW_PARENT_DIRS = ("Decided Rules", "Crafting System")
_CODEX_PARENT_DIR = "Codex of Elemental Gateways"

# Skip threshold for stub files (body chars after stripping leading whitespace).
_SKIP_BODY_CHAR_THRESHOLD = 200

# Session-log filename anchor — Pitfall 9: literal `_archive-import.md`.
_SESSION_LOG_FILENAMES = {"session-log.md", "session_log.md"}


def slugify(text: str) -> str:
    """Lowercase, collapse non-alphanumerics to single dashes, strip ends.

    Stable across calls — the importer's dedupe pass relies on this.
    """
    return _SLUG_NON_ALNUM.sub("-", text.lower()).strip("-")


def _has_pf2e_stat_block(content: str) -> bool:
    """Format A sniff: PF2e stat block markers.

    Requires ``**AC** N`` AND a creature-level cue. The cue can be either
    the strict ``**Creature N**`` marker OR a ``Level N NPC[s]`` token
    appearing in the first 400 chars (titles in the real archive often use
    the latter form, e.g. "Veela & Tarek, the Street Hood Twins (Level 2
    NPCs)").
    """
    if not _AC_RE.search(content):
        return False
    if _CREATURE_RE.search(content):
        return True
    head = content[:400]
    return bool(_LEVEL_NPC_RE.search(head))


def _has_format_b_sections(content: str) -> bool:
    """Format B sniff.

    Strong signal: ``### Biography`` AND ``### Appearance`` headers each
    followed by >=10 chars of body within the next 200 chars.

    Real-archive alternate: ``### Biography`` paired with ``**Appearance:**``
    (bold prefix instead of header) — same body-length rule on the
    Biography side; the Appearance bold prefix only needs to exist.

    Defends against empty stub headers (research §Edge cases — empty
    Biography sections are valid per LegendKeeper's template).
    """
    bio = _BIO_RE.search(content)
    if not bio:
        return False
    app_header = _APPEAR_RE.search(content)
    app_bold = _APPEAR_BOLD_RE.search(content)
    if not (app_header or app_bold):
        return False
    # Biography side must have body.
    bio_window = content[bio.end() : bio.end() + 200]
    if len(bio_window.strip()) < 10:
        return False
    # Appearance-header side must have body too. Bold form is treated as
    # sufficient on its own (the bold prefix runs inline with body text).
    if app_header is not None:
        win = content[app_header.end() : app_header.end() + 200]
        if len(win.strip()) < 10 and not app_bold:
            return False
    return True


_PERSONAL_NPC_RES = (
    re.compile(r"\*\*Role:\*\*", re.IGNORECASE),
    re.compile(r"\*\*Function:\*\*", re.IGNORECASE),
    re.compile(r"\*\*Class:\*\*", re.IGNORECASE),
    re.compile(r"\*\*Player:\*\*", re.IGNORECASE),
    re.compile(r"\*\*Status:\*\*\s+(Gone|Active|Captured|Missing)", re.IGNORECASE),
    re.compile(r"###\s+Personality\b", re.IGNORECASE),
    re.compile(r"###\s+Habits\b", re.IGNORECASE),
    re.compile(r"###\s+Goals\b", re.IGNORECASE),
    re.compile(r"###\s+Flaws\b", re.IGNORECASE),
    re.compile(r"###\s+Fears\b", re.IGNORECASE),
)


def _has_personal_npc_markers(content: str) -> bool:
    """True if the body has at least one personal-NPC structural marker.

    Used as a Format-B alternate when neither the strict header pair nor
    a PF2e stat block fires. Disambiguates personal NPC sheets like
    `Apprentice Aldric.md` (has `**Role:**` + `**Function:**`) from true
    factions like `Talons of the Claw.md` (organisational descriptor only).
    """
    return any(pat.search(content) for pat in _PERSONAL_NPC_RES)


def _is_dialogue_filename(stem: str) -> bool:
    lo = stem.lower()
    return any(kw in lo for kw in _DIALOGUE_KEYWORDS)


def _is_arc_filename(stem: str) -> bool:
    lo = stem.lower()
    return any(lo.startswith(p) for p in _ARC_FILENAME_PREFIXES)


def _is_harvest_filename(stem: str) -> bool:
    return stem.lower().startswith(_HARVEST_FILENAME_PREFIX)


def _strip_npc_quotes(name: str) -> str:
    """`Ashen Gorl "The Singed"` → `Ashen Gorl The Singed`.

    Quotes inside NPC names blow up slugify's collapse rules harmlessly, but
    stripping them up front makes the resulting slug match what the importer's
    first pass produces from the directory basename without quotes.
    """
    return name.replace("“", "").replace("”", "").replace('"', "")


def _infer_owner_slug(
    file_path: Path,
    archive_root: Path,
    known_npc_slugs: Iterable[str],
) -> str | None:
    """Resolve the owning NPC for a dialogue file.

    Strategy:
      1. If the immediate parent directory's slug is in ``known_npc_slugs``,
         use it (NPC-as-folder pattern).
      2. Otherwise, walk back through ancestor dirs (up to ``archive_root``)
         and use the first one whose slug is in ``known_npc_slugs``.
      3. Otherwise, take the leading proper-noun token from the filename
         stem (everything up to the first ``-`` or whitespace) and
         prefix-match against ``known_npc_slugs``.
      4. Otherwise, return None.
    """
    known = set(known_npc_slugs)

    # 1+2. Walk parents up to (but not including) archive_root.
    rel = file_path.relative_to(archive_root) if file_path.is_absolute() else file_path
    parts = list(rel.parts[:-1])  # exclude the file itself
    # Skip the special "The NPCs" envelope dir — it's a category, not an NPC.
    for parent_name in reversed(parts):
        if parent_name.lower() in {"the npcs", "the npc"}:
            continue
        candidate = slugify(_strip_npc_quotes(parent_name))
        if candidate in known:
            return candidate

    # 3. Leading proper-noun token from filename.
    stem = file_path.stem
    # Take everything before the first " - " or " Dialogue" / " Things Said" etc.
    head = re.split(r"\s+(?:-|—|–)\s+", stem, maxsplit=1)[0]
    # Drop a trailing "Dialogue" word if present.
    head = re.sub(r"\s+(Dialogue|Things\s+Said|Acknowledg\w*)\b.*$", "", head, flags=re.IGNORECASE)
    head_slug = slugify(_strip_npc_quotes(head))
    if not head_slug:
        return None
    if head_slug in known:
        return head_slug
    # Prefix match.
    for s in sorted(known):
        if s.startswith(head_slug + "-") or s == head_slug:
            return s
    return None


def _archive_relpath(file_path: Path, archive_root: Path) -> Path:
    if file_path.is_absolute():
        try:
            return file_path.relative_to(archive_root)
        except ValueError:
            return file_path
    return file_path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def route(
    file_path: Path,
    content: str,
    *,
    archive_root: Path,
    known_npc_slugs: Iterable[str] = (),
) -> RouteDecision:
    """Classify a single archive .md file.

    See module docstring for bucket precedence.
    """
    rel = _archive_relpath(file_path, archive_root)
    parts = list(rel.parts)
    stem = file_path.stem
    name_lower = file_path.name.lower()

    # ------------------------------------------------------------------
    # Skip first — body too short means we don't even classify.
    # ------------------------------------------------------------------
    body_len = len(content.strip())
    # Dialogue files are legitimately short (a quote line or two). Don't skip
    # them on body length; let the dialogue branch handle them below.
    if (
        body_len < _SKIP_BODY_CHAR_THRESHOLD
        and not _is_arc_filename(stem)
        and not _is_dialogue_filename(stem)
        and not _is_harvest_filename(stem)
    ):
        return RouteDecision(
            bucket="skip",
            slug=slugify(stem),
            dest="",
            reason=f"body length {body_len} < {_SKIP_BODY_CHAR_THRESHOLD} char threshold",
        )

    # ------------------------------------------------------------------
    # Session-log special case (Pitfall 9).
    # ------------------------------------------------------------------
    if name_lower in _SESSION_LOG_FILENAMES:
        return RouteDecision(
            bucket="session",
            slug="_archive-import",
            dest="mnemosyne/pf2e/sessions/_archive-import.md",
            reason="session-log.md → literal _archive-import.md (date in body is prep, not session)",
        )

    # ------------------------------------------------------------------
    # Filename-keyword overrides (Adventure Hooks, Harvest Table).
    # ------------------------------------------------------------------
    if _is_arc_filename(stem):
        # Topic = first non-trivial path segment, default "embercloaks" if
        # the archive layout puts it under The Embercloaks/.
        topic_seg = next(
            (p for p in parts[:-1] if p.lower().startswith("the embercloaks")),
            None,
        )
        topic = "embercloaks" if topic_seg else slugify(parts[0]) if parts else "general"
        slug = f"{slugify(stem)}-{topic}"
        return RouteDecision(
            bucket="arc",
            slug=slug,
            dest=f"mnemosyne/pf2e/lore/arcs/{slug}.md",
            reason="filename keyword 'Adventure Hooks' overrides parent dir",
        )

    if _is_harvest_filename(stem):
        # Strip the "Harvest Table - " prefix to get the monster name.
        monster = stem.split(" - ", 1)[1] if " - " in stem else stem
        slug = slugify(monster)
        return RouteDecision(
            bucket="harvest",
            slug=slug,
            dest=f"mnemosyne/pf2e/harvest/cache/{slug}.md",
            reason="filename matches 'Harvest Table - <monster>'",
        )

    # ------------------------------------------------------------------
    # Dialogue detection (filename keyword).
    # ------------------------------------------------------------------
    if _is_dialogue_filename(stem):
        owner_slug = _infer_owner_slug(file_path, archive_root, known_npc_slugs)
        slug = slugify(stem)
        # Dest is set by the importer (it concatenates dialogue per owner);
        # router still emits a deterministic dest for the dry-run report.
        dest = (
            f"mnemosyne/pf2e/npcs/{owner_slug}/dialogue.md"
            if owner_slug
            else f"mnemosyne/pf2e/npcs/_orphan-dialogue/{slug}.md"
        )
        reason = (
            f"dialogue filename; owner={owner_slug}"
            if owner_slug
            else "dialogue filename; owner unresolved"
        )
        return RouteDecision(
            bucket="npc_dialogue",
            slug=slug,
            dest=dest,
            reason=reason,
            owner_slug=owner_slug,
        )

    # ------------------------------------------------------------------
    # NPC content sniff.
    # ------------------------------------------------------------------
    has_stat = _has_pf2e_stat_block(content)
    has_format_b = _has_format_b_sections(content)

    # Two-NPC files & normal Format A: stat block wins.
    if has_stat:
        # Derive name from filename — strip the trailing "- <subtitle>" if
        # present so `Veela and Tarek - Street Hood Twins` becomes
        # `Veela and Tarek` (research §Edge case 2).
        head = re.split(r"\s+(?:-|—|–)\s+", stem, maxsplit=1)[0]
        slug = slugify(_strip_npc_quotes(head))
        return RouteDecision(
            bucket="npc_a",
            slug=slug,
            dest=f"mnemosyne/pf2e/npcs/{slug}.md",
            reason="PF2e stat block (Creature + AC) detected",
        )

    if has_format_b:
        slug = slugify(_strip_npc_quotes(stem))
        return RouteDecision(
            bucket="npc_b",
            slug=slug,
            dest=f"mnemosyne/pf2e/npcs/{slug}.md",
            reason="Format B (Biography + Appearance with body) detected",
        )

    # ------------------------------------------------------------------
    # No strict NPC sniff. If parent chain includes "The NPCs/", look for
    # personal-NPC markers in the body — `**Role:**`, `**Function:**`,
    # first-person quote blocks, or a `### Personality` / `### Goals` /
    # `### Habits` header — and route as npc_b. Otherwise (no markers
    # AND filename feels factional), faction. Research §Edge case 4 keeps
    # `Talons of the Claw.md` as faction; the markers prevent
    # `Apprentice Aldric.md` and similar character sheets being misrouted.
    # ------------------------------------------------------------------
    parent_lower = [p.lower() for p in parts[:-1]]
    if any(p == "the npcs" for p in parent_lower):
        slug = slugify(_strip_npc_quotes(stem))
        if _has_personal_npc_markers(content):
            return RouteDecision(
                bucket="npc_b",
                slug=slug,
                dest=f"mnemosyne/pf2e/npcs/{slug}.md",
                reason="under The NPCs/ + personal NPC markers (Role/Function/Personality/Goals)",
            )
        return RouteDecision(
            bucket="faction",
            slug=slug,
            dest=f"mnemosyne/pf2e/lore/factions/{slug}.md",
            reason="under The NPCs/ but no PF2e/Format-B/personal-NPC sniff → faction",
        )

    # ------------------------------------------------------------------
    # Path-prefix routing.
    # ------------------------------------------------------------------
    top = parts[0] if parts else ""

    if top in _HOMEBREW_PARENT_DIRS:
        slug = slugify(_strip_npc_quotes(stem))
        return RouteDecision(
            bucket="homebrew",
            slug=slug,
            dest=f"mnemosyne/pf2e/homebrew/{slug}.md",
            reason=f"path prefix '{top}/' → homebrew (sibling of rulings/, NOT under it)",
        )

    if top == _CODEX_PARENT_DIR:
        slug = slugify(_strip_npc_quotes(stem))
        return RouteDecision(
            bucket="lore",
            slug=slug,
            dest=f"mnemosyne/pf2e/lore/codex/{slug}.md",
            reason="path prefix 'Codex of Elemental Gateways/' → lore/codex/",
        )

    if top == "The Embercloaks":
        slug = slugify(_strip_npc_quotes(stem))
        return RouteDecision(
            bucket="lore",
            slug=slug,
            dest=f"mnemosyne/pf2e/lore/embercloaks/{slug}.md",
            reason="path prefix 'The Embercloaks/' → lore/embercloaks/",
        )

    if top == "Cartosia":
        slug = slugify(_strip_npc_quotes(stem))
        # Personal NPC markers under Cartosia/** → npc_b (e.g. Provost
        # Marshall Silas with bold-prefix Appearance + ### Biography that
        # the strict Format-B detector now also catches; this is the
        # belt-and-braces fallback for files with weaker structure).
        if _has_personal_npc_markers(content):
            return RouteDecision(
                bucket="npc_b",
                slug=slug,
                dest=f"mnemosyne/pf2e/npcs/{slug}.md",
                reason="under Cartosia/** + personal NPC markers (Role/Personality/Goals)",
            )
        return RouteDecision(
            bucket="location",
            slug=slug,
            dest=f"mnemosyne/pf2e/locations/{slug}.md",
            reason="path prefix 'Cartosia/' (no NPC/personal-marker sniff) → location",
        )

    # ------------------------------------------------------------------
    # Fallback: lore at the deepest non-trivial top segment.
    # ------------------------------------------------------------------
    topic = slugify(top) if top else "misc"
    slug = slugify(_strip_npc_quotes(stem))
    return RouteDecision(
        bucket="lore",
        slug=slug,
        dest=f"mnemosyne/pf2e/lore/{topic}/{slug}.md",
        reason=f"fallback: lore by top segment '{top}'",
    )
