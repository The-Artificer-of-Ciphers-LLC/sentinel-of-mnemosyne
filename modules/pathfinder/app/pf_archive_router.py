"""PF2e archive router (260427-cui — content-first, archive-agnostic).

Pure-function classifier over a single (Path, content) input. Returns a
:class:`RouteDecision` describing which vault bucket the file belongs in,
its slug, the destination path, and (for dialogue files) the owner NPC slug.

The router does NOT touch the vault, the LLM, or the network. It is the
first stage of the PF2e archive importer pipeline; the orchestrator
(``pf_archive_import.py``) walks the archive, calls :func:`route` per file,
and then dispatches to the per-bucket writer.

Bucket precedence — high→low:

1. **Filename keyword overrides** — ``Adventure Hooks.md`` and
   ``Harvest Table - X.md`` always win over their parent dir.
2. **Skip threshold** — body < 200 chars (and not arc/dialogue/harvest
   filename) → skip.
3. **Session-log special case** — literal ``session-log.md`` → session.
4. **Dialogue detection** — filename matches ``things said``, ``dialogue``,
   or ``acknowledg`` (case-insensitive). Owner inferred via ``known_npc_slugs``.
5. **PF2e content sniff** — Format A (``**Creature N**`` / ``Level N NPC[s]``
   + ``**AC** N``) or Format B (``### Biography`` + ``### Appearance``
   header/bold pair with body).
6. **Folder-shape NPC routing** — any path segment that is a generic NPC
   container token (``npcs``, ``characters``) AND personal-NPC markers in
   body → npc_b; same container without markers → faction.
7. **Content-first homebrew** — body has homebrew structural markers
   (``**Rules:**``, ``**Action:**``, ``**Trigger:**``, ``**Effect:**``,
   ``**Activate**``) → homebrew. Or any path segment is a generic homebrew
   token (``rules``, ``crafting``, ``homebrew``) → homebrew.
8. **Folder-shape location** — basename slug equals the immediate parent
   directory's slug (LegendKeeper "envelope page" pattern) AND a path
   segment is ``locations`` OR top-segment is the same word as the file's
   parent → location. Otherwise: any path segment ``locations`` → location.
9. **Folder-shape faction** — any path segment ``factions`` → faction.
10. **Fallback** — lore at ``mnemosyne/pf2e/lore/<top-segment-slug>/<slug>.md``.

Slug rule: lowercase, ``[^a-z0-9]+`` collapsed to ``-``, trailing/leading
``-`` stripped. ``Veela and Tarek`` → ``veela-and-tarek``. The leading
``the-`` is stripped from path-segment topic slugs (so ``The Embercloaks``
→ ``embercloaks``).
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
# "Level N NPC" / "Level N NPCs" appearing in a title or first 400 chars of
# the file is a creature-level cue (real archive uses this in lieu of the
# **Creature N** marker).
_LEVEL_NPC_RE = re.compile(r"\bLevel\s+\d+\s+NPCs?\b", re.IGNORECASE)
_BIO_RE = re.compile(r"###\s+Biography\b", re.IGNORECASE)
_APPEAR_RE = re.compile(r"###\s+Appearance\b", re.IGNORECASE)
_APPEAR_BOLD_RE = re.compile(r"\*\*Appearance:\*\*", re.IGNORECASE)

# Filename keyword tokens for dialogue detection — matched case-insensitively
# against the *stem* (no .md extension) anywhere in the name.
_DIALOGUE_KEYWORDS = ("things said", "dialogue", "acknowledg")

# Filename keywords that hijack routing regardless of parent dir.
_ARC_FILENAME_PREFIXES = ("adventure hooks",)
_HARVEST_FILENAME_PREFIX = "harvest table - "

# Skip threshold for stub files (body chars after stripping leading whitespace).
_SKIP_BODY_CHAR_THRESHOLD = 200

# Session-log filename anchor — literal ``_archive-import.md``.
_SESSION_LOG_FILENAMES = {"session-log.md", "session_log.md"}

# ---------------------------------------------------------------------------
# Generic folder-shape tokens (lowercased, whole-word match against any
# ancestor path segment). These are NOT archive-specific — a token like
# "rules" matches "Decided Rules" the same as "Homebrew Rules" or any other
# folder name with that word inside it.
# ---------------------------------------------------------------------------

_NPC_CONTAINER_TOKENS = ("npcs", "characters", "npc")
_HOMEBREW_CONTAINER_TOKENS = ("rules", "crafting", "homebrew")
_FACTION_CONTAINER_TOKENS = ("factions",)

# Homebrew content markers (PF2e-shaped action/rule blocks).
_HOMEBREW_MARKER_RES = (
    re.compile(r"\*\*Rules:\*\*", re.IGNORECASE),
    re.compile(r"\*\*Action:\*\*", re.IGNORECASE),
    re.compile(r"\*\*Trigger:\*\*", re.IGNORECASE),
    re.compile(r"\*\*Effect:\*\*", re.IGNORECASE),
    re.compile(r"\*\*Activate\*\*", re.IGNORECASE),
)


def slugify(text: str) -> str:
    """Lowercase, collapse non-alphanumerics to single dashes, strip ends."""
    return _SLUG_NON_ALNUM.sub("-", text.lower()).strip("-")


def _topic_slug(text: str) -> str:
    """Slug for path-segment topics. Strips a leading ``the-`` so a top
    segment like ``The Embercloaks`` becomes ``embercloaks`` (matches the
    natural human-shorthand for the topic; pre-refactor cartosia importer
    embedded this same heuristic for its arc and lore subdirs).
    """
    s = slugify(text)
    if s.startswith("the-"):
        s = s[len("the-"):]
    return s


def _has_pf2e_stat_block(content: str) -> bool:
    """Format A sniff: PF2e stat block markers (``**AC** N`` + creature cue)."""
    if not _AC_RE.search(content):
        return False
    if _CREATURE_RE.search(content):
        return True
    head = content[:400]
    return bool(_LEVEL_NPC_RE.search(head))


def _has_format_b_sections(content: str) -> bool:
    """Format B sniff: ``### Biography`` + ``### Appearance`` (header or bold)."""
    bio = _BIO_RE.search(content)
    if not bio:
        return False
    app_header = _APPEAR_RE.search(content)
    app_bold = _APPEAR_BOLD_RE.search(content)
    if not (app_header or app_bold):
        return False
    bio_window = content[bio.end() : bio.end() + 200]
    if len(bio_window.strip()) < 10:
        return False
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
    """True if the body has at least one personal-NPC structural marker."""
    return any(pat.search(content) for pat in _PERSONAL_NPC_RES)


def _has_homebrew_markers(content: str) -> bool:
    """True if the body has at least one PF2e homebrew action/rule marker."""
    return any(pat.search(content) for pat in _HOMEBREW_MARKER_RES)


def _is_dialogue_filename(stem: str) -> bool:
    lo = stem.lower()
    return any(kw in lo for kw in _DIALOGUE_KEYWORDS)


def _is_arc_filename(stem: str) -> bool:
    lo = stem.lower()
    return any(lo.startswith(p) for p in _ARC_FILENAME_PREFIXES)


def _is_harvest_filename(stem: str) -> bool:
    return stem.lower().startswith(_HARVEST_FILENAME_PREFIX)


def _strip_npc_quotes(name: str) -> str:
    return name.replace("“", "").replace("”", "").replace('"', "")


def _segment_words(parts: Iterable[str]) -> set[str]:
    """Return the lowercased word-tokens that appear in any path segment.

    e.g. parts=["Decided Rules", "Whatever"] → {"decided", "rules", "whatever"}.
    Used by the generic folder-shape detectors so that ``rules`` matches
    ``Decided Rules``, ``Homebrew Rules``, ``House Rules``, etc.
    """
    words: set[str] = set()
    for part in parts:
        for tok in re.split(r"[^a-z0-9]+", part.lower()):
            if tok:
                words.add(tok)
    return words


def _has_segment_token(parts: Iterable[str], tokens: tuple[str, ...]) -> bool:
    """True if any path segment contains any of the given lowercase tokens
    as a whole word (case-insensitive).
    """
    words = _segment_words(parts)
    return any(tok in words for tok in tokens)


def _infer_owner_slug(
    file_path: Path,
    archive_root: Path,
    known_npc_slugs: Iterable[str],
) -> str | None:
    """Resolve the owning NPC for a dialogue file."""
    known = set(known_npc_slugs)

    rel = file_path.relative_to(archive_root) if file_path.is_absolute() else file_path
    parts = list(rel.parts[:-1])  # exclude the file itself
    # Skip generic NPC-envelope dirs — they're categories, not NPCs.
    for parent_name in reversed(parts):
        if parent_name.lower() in {"the npcs", "the npc", "npcs", "characters"}:
            continue
        candidate = slugify(_strip_npc_quotes(parent_name))
        if candidate in known:
            return candidate

    stem = file_path.stem
    head = re.split(r"\s+(?:-|—|–)\s+", stem, maxsplit=1)[0]
    head = re.sub(r"\s+(Dialogue|Things\s+Said|Acknowledg\w*)\b.*$", "", head, flags=re.IGNORECASE)
    head_slug = slugify(_strip_npc_quotes(head))
    if not head_slug:
        return None
    if head_slug in known:
        return head_slug
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
    """Classify a single archive .md file via content-first sniffs.

    See module docstring for bucket precedence.
    """
    rel = _archive_relpath(file_path, archive_root)
    parts = list(rel.parts)
    parent_parts = parts[:-1]
    stem = file_path.stem
    name_lower = file_path.name.lower()

    # ------------------------------------------------------------------
    # Skip first — body too short means we don't even classify.
    # Dialogue/arc/harvest filenames are exempt from skip (they're
    # legitimately short).
    # ------------------------------------------------------------------
    body_len = len(content.strip())
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
    # Session-log special case.
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
        # Topic = first non-trivial path segment, slugified with leading-
        # 'the-' stripped (so 'The Embercloaks' → 'embercloaks').
        topic = _topic_slug(parts[0]) if parts else "general"
        slug = f"{slugify(stem)}-{topic}" if topic else slugify(stem)
        return RouteDecision(
            bucket="arc",
            slug=slug,
            dest=f"mnemosyne/pf2e/lore/arcs/{slug}.md",
            reason="filename keyword 'Adventure Hooks' overrides parent dir",
        )

    if _is_harvest_filename(stem):
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
    # PF2e content sniff (Format A wins over Format B).
    # ------------------------------------------------------------------
    if _has_pf2e_stat_block(content):
        head = re.split(r"\s+(?:-|—|–)\s+", stem, maxsplit=1)[0]
        slug = slugify(_strip_npc_quotes(head))
        return RouteDecision(
            bucket="npc_a",
            slug=slug,
            dest=f"mnemosyne/pf2e/npcs/{slug}.md",
            reason="PF2e stat block (Creature/Level + AC) detected",
        )

    if _has_format_b_sections(content):
        slug = slugify(_strip_npc_quotes(stem))
        return RouteDecision(
            bucket="npc_b",
            slug=slug,
            dest=f"mnemosyne/pf2e/npcs/{slug}.md",
            reason="Format B (Biography + Appearance with body) detected",
        )

    # ------------------------------------------------------------------
    # Folder-shape NPC envelope: any ancestor segment is a generic NPC
    # container (npcs/characters). Personal-NPC markers → npc_b; sparse
    # body with org-shape → faction; otherwise faction (matches the
    # pre-refactor 'under The NPCs/ but no NPC sniff' branch).
    # ------------------------------------------------------------------
    if _has_segment_token(parent_parts, _NPC_CONTAINER_TOKENS):
        slug = slugify(_strip_npc_quotes(stem))
        if _has_personal_npc_markers(content):
            return RouteDecision(
                bucket="npc_b",
                slug=slug,
                dest=f"mnemosyne/pf2e/npcs/{slug}.md",
                reason="under generic NPCs/ container + personal NPC markers (Role/Function/Personality/Goals)",
            )
        return RouteDecision(
            bucket="faction",
            slug=slug,
            dest=f"mnemosyne/pf2e/lore/factions/{slug}.md",
            reason="under generic NPCs/ container, no PF2e/Format-B/personal-NPC sniff → faction",
        )

    # ------------------------------------------------------------------
    # Content-first homebrew detection — markers in body OR generic
    # homebrew folder-token (rules/crafting/homebrew). Phase 33 invariant:
    # destination is a sibling of rulings/, not under it.
    # ------------------------------------------------------------------
    has_hb_markers = _has_homebrew_markers(content)
    has_hb_segment = _has_segment_token(parts, _HOMEBREW_CONTAINER_TOKENS)
    if has_hb_markers or has_hb_segment:
        slug = slugify(_strip_npc_quotes(stem))
        if has_hb_markers:
            reason = "homebrew markers (Rules/Action/Trigger/Effect/Activate) detected"
        else:
            reason = "generic homebrew folder-token (rules/crafting/homebrew) in path"
        return RouteDecision(
            bucket="homebrew",
            slug=slug,
            dest=f"mnemosyne/pf2e/homebrew/{slug}.md",
            reason=reason,
        )

    # ------------------------------------------------------------------
    # Folder-shape personal-NPC fallback: any path segment is generic NPC
    # container OR personal-NPC markers fire even without a container word
    # (e.g. a top-level 'Some Person.md' with ### Personality / ### Goals).
    # ------------------------------------------------------------------
    if _has_personal_npc_markers(content):
        slug = slugify(_strip_npc_quotes(stem))
        return RouteDecision(
            bucket="npc_b",
            slug=slug,
            dest=f"mnemosyne/pf2e/npcs/{slug}.md",
            reason="personal NPC markers (Personality/Goals/Role/Function) detected in body",
        )

    # ------------------------------------------------------------------
    # Folder-shape location detection: LegendKeeper "envelope page"
    # pattern — a folder X/ containing X.md is the page that describes
    # that location. We deliberately do NOT use a generic 'locations'
    # folder-token here: a flat `Locations/Mossy Cave.md` (no envelope)
    # is genuinely lore-prose, not a structured location entry, and
    # belongs under lore/<topic>/. Operators reorganise post-hoc.
    # ------------------------------------------------------------------
    if parent_parts:
        parent_slug = slugify(_strip_npc_quotes(parent_parts[-1]))
        stem_slug = slugify(_strip_npc_quotes(stem))
        if parent_slug and parent_slug == stem_slug:
            return RouteDecision(
                bucket="location",
                slug=stem_slug,
                dest=f"mnemosyne/pf2e/locations/{stem_slug}.md",
                reason="LegendKeeper envelope-page pattern: file basename equals parent dir name → location",
            )

    # ------------------------------------------------------------------
    # Folder-shape faction detection.
    # ------------------------------------------------------------------
    if _has_segment_token(parent_parts, _FACTION_CONTAINER_TOKENS):
        slug = slugify(_strip_npc_quotes(stem))
        return RouteDecision(
            bucket="faction",
            slug=slug,
            dest=f"mnemosyne/pf2e/lore/factions/{slug}.md",
            reason="under generic Factions/ container",
        )

    # ------------------------------------------------------------------
    # Fallback: lore at the slugified top segment as topic subdir.
    # ------------------------------------------------------------------
    top = parts[0] if parts else ""
    topic = _topic_slug(top) if top else "misc"
    if not topic:
        topic = "misc"
    slug = slugify(_strip_npc_quotes(stem))
    return RouteDecision(
        bucket="lore",
        slug=slug,
        dest=f"mnemosyne/pf2e/lore/{topic}/{slug}.md",
        reason=f"fallback: lore by top-segment topic '{topic}'",
    )
