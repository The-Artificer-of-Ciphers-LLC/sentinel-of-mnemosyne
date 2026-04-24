#!/usr/bin/env python3
"""Scaffold modules/pathfinder/data/rules-corpus.json from a Foundry pf2e repo clone.

Usage:
    python modules/pathfinder/scripts/scaffold_rules_corpus.py \\
        --pf2e-repo /path/to/foundryvtt/pf2e \\
        --output modules/pathfinder/data/rules-corpus.json \\
        --aon-url-map modules/pathfinder/data/aon-url-map.json

Scope (Phase 33 / D-15): Player Core rules-prose only.
  - packs/pf2e/journals/gm-screen.json               (60+ rule-topic pages)
  - packs/pf2e/conditions/*.json                     (43 condition entries)
  - packs/pf2e/actions/basic/*.json                  (basic actions)
  - packs/pf2e/actions/skill/*.json                  (skill actions — Grapple, Trip, Shove, etc.)

DEFERRED (Phase 33.x):
  - Monster Core rules-prose (Monster Creation, Adjusting Creatures, Building Encounters)
  - GM Core rules-prose beyond what gm-screen.json already surfaces
  - Guns & Gears, Secrets of Magic, Rage of Elements, etc. (advanced books)

Idempotent: re-running overwrites output deterministically.
Logs WARNING for each chunk lacking >= 2 of {book, section, aon_url}
so the human can audit AoN URL-map coverage before committing.

Per CLAUDE.md AI Deferral Ban: script completes fully or raises — no TODOs, no skip-silent.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

logger = logging.getLogger("scaffold-rules-corpus")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

# Page-footer regex: "Pathfinder Player Core pg. 416" or "pg. 411-412".
BOOK_REGEX = re.compile(r"Pathfinder ([A-Za-z& ]+?)(?=\s*pg\.)", re.IGNORECASE)
PAGE_REGEX = re.compile(r"pg\.\s?(\d+(?:-\d+)?)", re.IGNORECASE)
CHAPTER_REGEX = re.compile(r"Section:\s*([^<\n]+)", re.IGNORECASE)


def strip_html(html: str) -> str:
    """Mirror app.rules.strip_rule_html — output must match runtime chunker."""
    soup = BeautifulSoup(html or "", "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"@UUID\[[^\]]*?([A-Za-z0-9-]+)\]", lambda m: m.group(1), text)
    return re.sub(r"\s+", " ", text).strip()


def _auto_topic_tags(text: str, section: str) -> list[str]:
    """Keyword-based many-to-many topic tagging for topic_index optimization.

    The real classifier is an LLM (app.llm.classify_rule_topic, Wave 2);
    this only primes the topic_index so retrieve's topic-filter path has data.
    """
    needle = f"{section} {text}".lower()
    tags: list[str] = []
    if "flank" in needle:
        tags.append("flanking")
    if "off-guard" in needle or "off guard" in needle:
        tags.append("off-guard")
    if "grapple" in needle or "grab" in needle:
        tags.append("grapple")
    if "trip" in needle:
        tags.append("trip")
    if "shove" in needle:
        tags.append("shove")
    if "fall" in needle or "falling" in needle:
        tags.append("falling")
    if "critical" in needle or "attack roll" in needle:
        tags.append("combat")
    if "dc by level" in needle or "set a dc" in needle:
        tags.append("dcs")
    if any(c in needle for c in (
        "frightened", "sickened", "stunned", "paralyzed", "prone",
        "dying", "unconscious", "wounded",
    )):
        tags.append("conditions")
    if "treat wounds" in needle or "heal" in needle:
        tags.append("healing")
    if "dying" in needle or "unconscious" in needle:
        tags.append("dying")
    if "exploration activit" in needle:
        tags.append("exploration")
    if "skill" in section.lower():
        tags.append("skills")
    if "action" in section.lower() or "three-action" in needle:
        tags.append("actions")
    if "darkvision" in needle or "low-light" in needle:
        tags.append("senses")
    if "concealed" in needle or "hidden" in needle or "seek" in needle:
        tags.append("detection")
    if "cover" in needle or "difficult terrain" in needle:
        tags.append("terrain")
    if "spell" in needle and "school" not in needle:
        tags.append("spellcasting")
    if "bulk" in needle or "encumbran" in needle:
        tags.append("encumbrance")
    if "treasure" in needle:
        tags.append("treasure")
    if "identif" in needle:
        tags.append("identification")
    if "hero point" in needle:
        tags.append("hero-points")
    return sorted(set(tags)) or ["misc"]


def load_aon_url_map(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        logger.warning("aon-url-map not found at %s — citations will omit URLs", path)
        return {}
    return json.loads(path.read_text())


def _lookup_aon_url(url_map: dict, book: str, section: str) -> str | None:
    if not url_map:
        return None
    return (url_map.get(book) or {}).get(section)


def _normalize_book_label(raw: str) -> str:
    """Normalize a raw book label to the canonical 'Pathfinder Player Core' form."""
    label = raw.strip()
    if not label.lower().startswith("pathfinder"):
        label = f"Pathfinder {label}"
    return label


def ingest_journal(journal_path: Path, url_map: dict) -> list[dict]:
    """Ingest packs/pf2e/journals/gm-screen.json (and related rules journals)."""
    if not journal_path.exists():
        logger.warning("Journal file missing: %s", journal_path)
        return []
    data = json.loads(journal_path.read_text())
    out: list[dict] = []
    for page in data.get("pages", []):
        name = page.get("name", "").strip()
        content = (page.get("text") or {}).get("content", "") or ""
        text = strip_html(content)
        if not text:
            continue
        m_book = BOOK_REGEX.search(content)
        if m_book:
            book = _normalize_book_label(m_book.group(1))
        else:
            book = "Pathfinder Player Core"
        # D-15 scope lock: skip anything that isn't Player Core.
        if "Player Core" not in book:
            logger.warning("Skipping non-Player-Core journal page: %s (book=%s)", name, book)
            continue
        m_page = PAGE_REGEX.search(content)
        page_str = m_page.group(1) if m_page else None
        m_chapter = CHAPTER_REGEX.search(content)
        chapter = m_chapter.group(1).strip() if m_chapter else None
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        chunk = {
            "id": f"gm-screen:{slug}",
            "book": book,
            "page": page_str,
            "section": name,
            "chapter": chapter,
            "aon_url": _lookup_aon_url(url_map, book, name),
            "text": text,
            "topics": _auto_topic_tags(text, name),
            "source_license": "ORC",
        }
        out.append(chunk)
    return out


def ingest_pack_directory(pack_dir: Path, chapter_label: str, url_map: dict) -> list[dict]:
    """Ingest packs/pf2e/conditions/*.json or packs/pf2e/actions/{basic,skill}/*.json."""
    if not pack_dir.exists():
        logger.warning("Pack directory missing: %s", pack_dir)
        return []
    out: list[dict] = []
    for entry_path in sorted(pack_dir.glob("*.json")):
        try:
            data = json.loads(entry_path.read_text())
        except Exception as exc:
            logger.warning("Failed to parse %s: %s", entry_path, exc)
            continue
        name = data.get("name", "").strip()
        desc_html = (data.get("system", {}).get("description", {}) or {}).get("value", "") or ""
        text = strip_html(desc_html)
        if not text:
            continue
        publication = data.get("system", {}).get("publication", {}) or {}
        book_raw = publication.get("title") or "Pathfinder Player Core"
        book = _normalize_book_label(book_raw) if book_raw else "Pathfinder Player Core"
        # D-15 scope lock.
        if "Player Core" not in book:
            logger.warning("Skipping non-Player-Core entry: %s (book=%s)", name, book)
            continue
        # Try to extract page from publication.footer or embedded text.
        page_str = None
        footer = publication.get("footer") or ""
        m_page = PAGE_REGEX.search(footer) or PAGE_REGEX.search(desc_html)
        if m_page:
            page_str = m_page.group(1)
        slug = entry_path.stem.lower()
        chunk = {
            "id": f"{pack_dir.name}:{slug}",
            "book": book,
            "page": page_str,
            "section": name,
            "chapter": chapter_label,
            "aon_url": _lookup_aon_url(url_map, book, name),
            "text": text,
            "topics": _auto_topic_tags(text, name),
            "source_license": "ORC",
        }
        out.append(chunk)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    p.add_argument("--pf2e-repo", type=Path, required=True,
                   help="Path to a cloned foundryvtt/pf2e repo")
    p.add_argument("--output", type=Path,
                   default=Path("modules/pathfinder/data/rules-corpus.json"))
    p.add_argument("--aon-url-map", type=Path,
                   default=Path("modules/pathfinder/data/aon-url-map.json"))
    args = p.parse_args(argv)

    url_map = load_aon_url_map(args.aon_url_map)
    logger.info("Loaded AoN URL map: %d books", len(url_map))

    chunks: list[dict] = []

    # Journals — the gm-screen is the primary rules-prose source.
    journal_dir = args.pf2e_repo / "packs/pf2e/journals"
    gm_screen = journal_dir / "gm-screen.json"
    if not gm_screen.exists():
        # Older layouts put journals at packs/journals or packs/pf2e-journals
        for alt in (
            args.pf2e_repo / "packs/journals/gm-screen.json",
            args.pf2e_repo / "packs/pf2e-journals/gm-screen.json",
        ):
            if alt.exists():
                gm_screen = alt
                break
    chunks += ingest_journal(gm_screen, url_map)

    # Conditions.
    for cand in (
        args.pf2e_repo / "packs/pf2e/conditions",
        args.pf2e_repo / "packs/conditionitems",
        args.pf2e_repo / "packs/conditions",
    ):
        if cand.exists():
            chunks += ingest_pack_directory(cand, "Conditions", url_map)
            break

    # Basic actions.
    for cand in (
        args.pf2e_repo / "packs/pf2e/actions/basic",
        args.pf2e_repo / "packs/actions/basic",
        args.pf2e_repo / "packs/actionspf2e/basic",
    ):
        if cand.exists():
            chunks += ingest_pack_directory(cand, "Basic Actions", url_map)
            break

    # Skill actions.
    for cand in (
        args.pf2e_repo / "packs/pf2e/actions/skill",
        args.pf2e_repo / "packs/actions/skill",
        args.pf2e_repo / "packs/actionspf2e/skill",
    ):
        if cand.exists():
            chunks += ingest_pack_directory(cand, "Skill Actions", url_map)
            break

    # Some Foundry layouts put actions flat in one pack — try that as a last resort.
    if not any(c["id"].startswith(("actions:", "basic:", "skill:")) for c in chunks):
        for cand in (
            args.pf2e_repo / "packs/pf2e/actionspf2e",
            args.pf2e_repo / "packs/actionspf2e",
            args.pf2e_repo / "packs/actions",
        ):
            if cand.exists():
                chunks += ingest_pack_directory(cand, "Actions", url_map)
                break

    # Coverage warning — RESEARCH §Citation Extraction Procedure step 3.
    weak = [c for c in chunks if sum(
        int(bool(c.get(k))) for k in ("book", "section", "aon_url")
    ) < 2]
    if weak:
        logger.warning(
            "COVERAGE WARNING: %d chunks lack >=2 of {book,section,aon_url}. Review before commit.",
            len(weak),
        )
        for w in weak[:10]:
            logger.warning(
                "  weak: id=%s book=%s section=%s aon_url=%s",
                w["id"], w["book"], w["section"], w["aon_url"],
            )

    out = {
        "version": "1.0",
        "source": f"Foundry pf2e snapshot {args.pf2e_repo.name}",
        "license": "ORC",
        "chunks": chunks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    logger.info("Wrote %d chunks to %s", len(chunks), args.output)

    if len(chunks) < 100:
        logger.error(
            "FAIL: scaffolded corpus has only %d chunks (< 100 minimum). Check pf2e repo layout.",
            len(chunks),
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
