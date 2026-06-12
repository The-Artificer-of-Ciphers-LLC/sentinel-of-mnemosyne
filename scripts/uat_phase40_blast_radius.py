#!/usr/bin/env python3
"""Phase 40 — two-mode read-only blast-radius audit for the vault-sweeper incident.

PURPOSE
-------
After the vault-sweeper v0.50.3 incident (sentinel/persona.md incorrectly
moved by run_sweep during startup), this script lets an operator confirm
the full blast radius of collateral damage and verify the vault is clean after
remediation (40-04 / 40-05 / 40-07).

It runs in TWO modes:

  MODE 1 — PROVENANCE SCAN
    Walk every .md note in the vault.  Collect notes carrying relocation or
    trash provenance frontmatter (``original_path`` + ``topic_moved_at`` for
    vault relocation; ``original_path`` + ``sweep_at`` for vault trash-move).
    Flag as CRITICAL any note whose ``original_path`` was inside a protected
    namespace (sentinel/, self/, security/).  Optionally filter by a concrete
    ``--since <iso8601>`` incident-window lower bound.

  MODE 2 — INVENTORY / NAMESPACE-POLICY SCAN  (manifest-authoritative)
    Catch provenance-LESS damage: files moved before provenance was written,
    after the v0.50.3 rollback that does not write provenance, or
    deleted-not-moved.  This mode:
      a) Checks EVERY protected namespace's expected/canonical files for MISSING
         entries (across all of sentinel/, self/, security/ — not just
         sentinel/persona.md).
      b) Walks target namespaces the sweeper would sweep-move INTO (e.g.
         learning/persona/, topic directories) and flags files there that look
         like sweep-moved operator files (persona-like filenames or frontmatter).
    The AUTHORITATIVE source of expected canonical files is the --inventory
    manifest when provided.  The built-in hard-coded canonical map is a
    LAST-RESORT FALLBACK used only when no manifest is given — it is
    DRIFT-PRONE (it can silently fall out of sync with the real vault) and
    its use is flagged with a prominent warning.

IMPORTANT — LIVE_TEST GATE
--------------------------
Running WITHOUT ``LIVE_TEST=1`` performs NO AUDIT and exits with a distinct
non-success signal (exit code 2 + "SKIPPED" banner).  This is NOT a clean-
vault result — it means the script did nothing.  An operator must not mistake
"did nothing" for "found nothing".

Set ``LIVE_TEST=1`` to arm the audit.

FLAGS
-----
  --mode {provenance,inventory,both}
      Which scan(s) to run.  Default: both.

  --since <iso8601>
      Concrete incident-window lower bound.  The ``topic_moved_at`` /
      ``sweep_at`` provenance timestamp must be >= this value for a note to
      be included in the provenance scan.  No filter = scan all history.
      Example: ``--since 2026-06-10T00:00:00Z``

  --inventory <path-to-json>
      Path to a known-good JSON manifest that maps each protected namespace
      to its list of expected canonical file paths.  This is the AUTHORITATIVE
      source for the namespace-policy scan (round-3 item 3) — when supplied
      the per-namespace expected-file list comes FROM this manifest; the
      built-in hard-coded canonical map is NOT used.
      Without this flag the script falls back to the built-in canonical map,
      prints a drift-prone warning, and its namespace-policy diff is INCOMPLETE.
      Prefer --inventory for a complete, authoritative diff.

      Manifest format::

          {
            "sentinel/": ["sentinel/persona.md", "sentinel/config.md"],
            "self/": ["self/identity.md"],
            "security/": ["security/policies.md"]
          }

  --dry-run
      Affirmation flag only.  The script is strictly READ-ONLY regardless of
      this flag — it never moves, writes, or deletes any vault note.
      --dry-run does NOT switch the script into a different mode; it is an
      explicit no-mutation affirmation for operator confidence.

EXIT CODES
----------
  0   Armed (LIVE_TEST=1), no CRITICAL findings.
  1   Armed (LIVE_TEST=1), one or more CRITICAL findings.
  2   Not armed (LIVE_TEST not set) — NO AUDIT PERFORMED (not a clean result).

RUNNABLE EXAMPLE
----------------
  LIVE_TEST=1 \\
  UAT_OBSIDIAN_URL=http://localhost:27123 \\
  UAT_OBSIDIAN_KEY=<your-key> \\
  python scripts/uat_phase40_blast_radius.py \\
      --mode both \\
      --since 2026-06-10T00:00:00Z \\
      --inventory ops/inventory.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

try:
    import httpx
except ImportError:
    print(
        "httpx not installed.\n"
        "Run via: uv run --project sentinel-core python scripts/uat_phase40_blast_radius.py"
    )
    sys.exit(1)

try:
    import yaml
except ImportError:
    print(
        "PyYAML not installed.\n"
        "Run via: uv run --project sentinel-core python scripts/uat_phase40_blast_radius.py"
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# Environment / config
# ---------------------------------------------------------------------------

_OBSIDIAN_URL = os.environ.get("UAT_OBSIDIAN_URL", "http://localhost:27123")
_OBSIDIAN_KEY = os.environ.get("UAT_OBSIDIAN_KEY", "")

# Protected namespaces: must match app/config.py Settings.protected_namespaces
# and app/vault.py PROTECTED_NAMESPACES (40-05).  If you extend that tuple,
# extend this one too.
PROTECTED_NAMESPACES: tuple[str, ...] = (
    "sentinel/",   # boot-critical: persona.md absence crash-loops composition.py
    "self/",       # identity-critical: self/identity.md is operator identity context
    "security/",   # operator-curated security namespace; never swept, never moved
)

# ---------------------------------------------------------------------------
# Built-in DRIFT-PRONE hard-coded canonical map (LAST-RESORT FALLBACK ONLY).
#
# THIS MAP IS DRIFT-PRONE.  It can silently fall out of sync with the real
# vault when new canonical files are added or existing ones are renamed.
# It is used ONLY when --inventory is not supplied.  Always prefer --inventory
# for an authoritative, complete per-namespace diff.
#
# Each entry lists files that are boot/identity-CRITICAL for that namespace.
# Flag any file here that is missing as CRITICAL.
#
# NOTE: this enumerates EVERY protected namespace (sentinel/, self/, security/)
# — not just sentinel/persona.md.  An operator running without a manifest still
# gets a per-namespace presence check, but is steered toward --inventory.
# ---------------------------------------------------------------------------
_BUILTIN_CANONICAL_MAP: dict[str, list[str]] = {
    "sentinel/": [
        "sentinel/persona.md",   # boot-critical: absence crash-loops composition.py:424
    ],
    "self/": [
        "self/identity.md",      # identity-critical: operator identity context
    ],
    "security/": [
        # Known files vary by deployment; list the commonly present ones.
        # DRIFT-PRONE: this list may not reflect your actual vault — use --inventory.
    ],
}

# Target namespaces the bad sweeper would sweep-move operator files INTO.
# Any file in these directories whose name or content looks like a sweep-moved
# protected file is flagged even without original_path provenance.
_TARGET_NAMESPACES_TO_SCAN = [
    "learning/persona/",
    "learning/",
    "topic/",
    "topics/",
]

# Persona-like filename basenames (case-insensitive) that suggest relocation.
_PERSONA_LIKE_BASENAMES = {
    "persona.md",
    "identity.md",
}


# ---------------------------------------------------------------------------
# Frontmatter helpers (standalone — no sentinel-core import required)
# ---------------------------------------------------------------------------

import re as _re

_FRONTMATTER_RE = _re.compile(r"^---\s*\n(.*?)\n---\s*\n?", _re.DOTALL)


def _split_frontmatter(body: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body_without_frontmatter)."""
    m = _FRONTMATTER_RE.match(body or "")
    if not m:
        return ({}, body or "")
    try:
        fm = yaml.safe_load(m.group(1)) or {}
        if not isinstance(fm, dict):
            fm = {}
    except Exception:
        fm = {}
    return (fm, body[m.end():])


def _is_protected_path(path: str) -> bool:
    """Return True iff path is under (or is) a protected namespace."""
    normalised = path.lstrip("/")
    for prefix in PROTECTED_NAMESPACES:
        bare = prefix.rstrip("/")
        if normalised == bare or normalised.startswith(prefix):
            return True
    return False


def _parse_iso(ts: str | None) -> datetime | None:
    """Parse an ISO 8601 timestamp; return None on failure."""
    if not ts:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(ts, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _parse_since(since_str: str | None) -> datetime | None:
    """Parse the --since argument; exit with a clear error on bad input."""
    if since_str is None:
        return None
    dt = _parse_iso(since_str)
    if dt is None:
        print(
            f"ERROR: --since value {since_str!r} is not a valid ISO 8601 timestamp.\n"
            "Examples: 2026-06-10T00:00:00Z  or  2026-06-10",
            file=sys.stderr,
        )
        sys.exit(2)
    return dt


def _is_after(ts_str: str | None, since: datetime | None) -> bool:
    """True iff the timestamp in ts_str is >= since (or since is None)."""
    if since is None:
        return True
    dt = _parse_iso(ts_str)
    if dt is None:
        return False
    return dt >= since


# ---------------------------------------------------------------------------
# Vault walk helpers (direct REST; no sentinel-core import)
# ---------------------------------------------------------------------------


async def _list_under(client: httpx.AsyncClient, prefix: str = "") -> list[str]:
    """GET /vault/{prefix}/ — return mixed list of filenames + subdir names."""
    url = (
        f"{_OBSIDIAN_URL}/vault/{prefix}/"
        if prefix
        else f"{_OBSIDIAN_URL}/vault/"
    )
    try:
        resp = await client.get(url, timeout=10.0)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
        files = data if isinstance(data, list) else data.get("files", [])
        return [f if isinstance(f, str) else f.get("path", "") for f in files]
    except Exception:
        return []


async def _read_note(client: httpx.AsyncClient, path: str) -> str:
    """GET /vault/{path} — return body on 200, '' on 404 or error."""
    try:
        resp = await client.get(f"{_OBSIDIAN_URL}/vault/{path}", timeout=10.0)
        if resp.status_code == 404:
            return ""
        resp.raise_for_status()
        return resp.text
    except Exception:
        return ""


async def _head_exists(client: httpx.AsyncClient, path: str) -> bool:
    """Return True iff the vault path exists (200 HEAD)."""
    try:
        resp = await client.get(f"{_OBSIDIAN_URL}/vault/{path}", timeout=5.0)
        return resp.status_code == 200
    except Exception:
        return False


async def _bfs_walk(
    client: httpx.AsyncClient,
    prefix: str = "",
    skip_prefixes: tuple[str, ...] = (".obsidian/",),
) -> list[str]:
    """BFS walk the vault under ``prefix``, returning all .md file paths."""
    queue: list[str] = [prefix]
    result: list[str] = []
    visited: set[str] = set()

    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)

        entries = await _list_under(client, current)
        for entry in entries:
            # Entries from the REST API are relative to the vault root.
            # Directories end with '/'.
            if current:
                full_path = f"{current}/{entry}" if not current.endswith("/") else f"{current}{entry}"
            else:
                full_path = entry

            # Normalise away double slashes
            full_path = full_path.replace("//", "/")

            # Skip configured prefixes
            if any(full_path.startswith(sp) for sp in skip_prefixes):
                continue

            if full_path.endswith("/"):
                # Directory — enqueue for BFS
                dir_key = full_path.rstrip("/")
                if dir_key not in visited:
                    queue.append(dir_key)
            elif full_path.lower().endswith(".md"):
                result.append(full_path)

    return result


# ---------------------------------------------------------------------------
# Scan result types
# ---------------------------------------------------------------------------


class Finding:
    """A single audit finding."""

    def __init__(
        self,
        level: str,       # "CRITICAL" | "INFO"
        mode: str,        # "provenance" | "inventory"
        description: str,
        original_path: str | None = None,
        current_path: str | None = None,
        extra: dict | None = None,
    ) -> None:
        self.level = level
        self.mode = mode
        self.description = description
        self.original_path = original_path
        self.current_path = current_path
        self.extra = extra or {}

    def __str__(self) -> str:
        parts = [f"  [{self.level}] [{self.mode}] {self.description}"]
        if self.original_path:
            parts.append(f"    original_path : {self.original_path}")
        if self.current_path:
            parts.append(f"    current_path  : {self.current_path}")
        for k, v in self.extra.items():
            parts.append(f"    {k:<14}: {v}")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# MODE 1 — PROVENANCE SCAN
# ---------------------------------------------------------------------------


async def run_provenance_scan(
    client: httpx.AsyncClient,
    since: datetime | None,
    verbose: bool = True,
) -> list[Finding]:
    """Walk all .md notes (including _trash/) and flag protected relocations."""
    if verbose:
        print("\n=== MODE 1: PROVENANCE SCAN ===")
        print(
            "  Walking vault for notes carrying original_path / topic_moved_at / sweep_at ..."
        )
        if since:
            print(f"  incident window: >= {since.isoformat()}")

    findings: list[Finding] = []

    # Walk main vault (skip .obsidian/)
    all_notes = await _bfs_walk(client, prefix="", skip_prefixes=(".obsidian/",))

    # Also walk _trash/ separately (trash-move puts files there)
    trash_notes = await _bfs_walk(client, prefix="_trash", skip_prefixes=())

    all_to_check = all_notes + trash_notes

    if verbose:
        print(f"  Found {len(all_to_check)} .md notes to inspect "
              f"({len(all_notes)} in vault, {len(trash_notes)} in _trash/).")

    checked = 0
    for path in all_to_check:
        body = await _read_note(client, path)
        if not body:
            continue

        fm, _ = _split_frontmatter(body)
        original_path: str | None = fm.get("original_path")
        topic_moved_at: str | None = fm.get("topic_moved_at")
        sweep_at: str | None = fm.get("sweep_at")

        if not original_path:
            continue  # No provenance — skip in this mode

        # Apply --since filter using whichever timestamp is present
        timestamp_for_filter = topic_moved_at or sweep_at
        if since and not _is_after(timestamp_for_filter, since):
            continue

        checked += 1
        is_critical = _is_protected_path(original_path)
        level = "CRITICAL" if is_critical else "INFO"

        provenance_type = "relocation" if topic_moved_at else "trash"
        ts = topic_moved_at or sweep_at or "unknown timestamp"

        desc = (
            f"Protected file sweep-moved ({provenance_type}): "
            f"original_path={original_path!r} → current={path!r} at {ts}"
            if is_critical
            else f"Relocation ({provenance_type}): {original_path!r} → {path!r} at {ts}"
        )

        findings.append(
            Finding(
                level=level,
                mode="provenance",
                description=desc,
                original_path=original_path,
                current_path=path,
                extra={"timestamp": ts, "type": provenance_type},
            )
        )

    if verbose:
        criticals = [f for f in findings if f.level == "CRITICAL"]
        infos = [f for f in findings if f.level == "INFO"]
        print(
            f"  Provenance scan complete: {checked} notes with provenance found; "
            f"{len(criticals)} CRITICAL, {len(infos)} INFO."
        )

    return findings


# ---------------------------------------------------------------------------
# MODE 2 — INVENTORY / NAMESPACE-POLICY SCAN
# ---------------------------------------------------------------------------


def _load_inventory(inventory_path: str) -> dict[str, list[str]] | None:
    """Load and return the per-namespace manifest from a JSON file.

    Returns None on parse failure (caller falls back to built-in map).
    """
    try:
        with open(inventory_path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            print(
                f"WARNING: --inventory {inventory_path!r} is not a JSON object — "
                "falling back to built-in drift-prone canonical map.",
                file=sys.stderr,
            )
            return None
        return data
    except FileNotFoundError:
        print(
            f"ERROR: --inventory path {inventory_path!r} not found.",
            file=sys.stderr,
        )
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(
            f"ERROR: --inventory {inventory_path!r} is not valid JSON: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)


def _is_persona_like_content(body: str, path: str) -> bool:
    """Heuristic: does this note look like a sweep-moved sentinel/self operator file?

    Checks:
      - Filename matches known protected basenames (persona.md, identity.md).
      - Frontmatter has source: vault-sweep (sweep-written marker).
      - Body contains a persona/identity heading.
    """
    basename = path.rsplit("/", 1)[-1].lower()
    if basename in _PERSONA_LIKE_BASENAMES:
        return True

    fm, rest = _split_frontmatter(body)
    if fm.get("source") == "vault-sweep":
        return True

    # Look for identity/persona headings in the body
    heading_patterns = [
        "# persona",
        "# identity",
        "# sentinel persona",
        "# operator identity",
        "# character",
    ]
    body_lower = body.lower()
    if any(pattern in body_lower for pattern in heading_patterns):
        return True

    return False


async def run_inventory_scan(
    client: httpx.AsyncClient,
    inventory_path: str | None,
    verbose: bool = True,
) -> list[Finding]:
    """Check every protected namespace for missing canonical files + scan target dirs."""
    if verbose:
        print("\n=== MODE 2: INVENTORY / NAMESPACE-POLICY SCAN ===")

    findings: list[Finding] = []
    using_manifest = False

    # Determine canonical map source (AUTHORITATIVE = manifest; FALLBACK = built-in)
    canonical_map: dict[str, list[str]]
    if inventory_path:
        loaded = _load_inventory(inventory_path)
        if loaded is not None:
            canonical_map = loaded
            using_manifest = True
            if verbose:
                namespaces = list(canonical_map.keys())
                print(
                    f"  Using --inventory manifest (AUTHORITATIVE): {inventory_path!r}\n"
                    f"  Namespaces covered: {namespaces}"
                )
        else:
            # _load_inventory printed its own warning; fall through to built-in
            canonical_map = _BUILTIN_CANONICAL_MAP
    else:
        canonical_map = _BUILTIN_CANONICAL_MAP

    if not using_manifest:
        # Print prominent drift-prone warning
        warning_msg = (
            "\n  WARNING: namespace-policy scan using BUILT-IN CANONICAL MAP — this is "
            "DRIFT-PRONE.\n"
            "  The hard-coded map can silently fall out of sync with the real vault.\n"
            "  Pass --inventory <manifest> for the AUTHORITATIVE, complete diff.\n"
            "  (This run may miss damage that --inventory would catch.)\n"
        )
        print(warning_msg, file=sys.stderr)
        if verbose:
            print(warning_msg.strip())

    # -------------------------------------------------------------------
    # Part A: FULL NAMESPACE-POLICY PRESENCE CHECK
    # Check EVERY protected namespace in canonical_map for missing files.
    # -------------------------------------------------------------------
    if verbose:
        print(
            f"\n  Part A: Checking canonical files across "
            f"{len(canonical_map)} namespace(s) ..."
        )

    for namespace, expected_files in canonical_map.items():
        if not expected_files:
            if verbose:
                print(f"    [{namespace}] No canonical files listed — skipping presence check.")
            continue

        for expected_path in expected_files:
            exists = await _head_exists(client, expected_path)
            if not exists:
                findings.append(
                    Finding(
                        level="CRITICAL",
                        mode="inventory",
                        description=(
                            f"MISSING canonical file in protected namespace {namespace!r}: "
                            f"{expected_path!r} does not exist in the vault"
                        ),
                        original_path=expected_path,
                        current_path=None,
                        extra={
                            "namespace": namespace,
                            "source": "manifest" if using_manifest else "built-in (DRIFT-PRONE)",
                            "action": "Restore via REST PUT /vault/<original_path> (do NOT call vault.move into a protected namespace — 40-05 destination guard blocks it)",
                        },
                    )
                )
                if verbose:
                    print(f"    [CRITICAL] MISSING: {expected_path}")
            else:
                if verbose:
                    print(f"    [OK]       PRESENT: {expected_path}")

    # -------------------------------------------------------------------
    # Part B: PERSONA-LIKE / MISPLACED FILES IN TARGET NAMESPACES
    # Walk directories the sweeper sweep-moves INTO and flag persona-like files.
    # -------------------------------------------------------------------
    if verbose:
        print(
            f"\n  Part B: Scanning target namespaces for misplaced operator files "
            f"(no original_path required) ..."
        )

    for target_prefix in _TARGET_NAMESPACES_TO_SCAN:
        target_notes = await _bfs_walk(
            client,
            prefix=target_prefix.rstrip("/"),
            skip_prefixes=(".obsidian/",),
        )
        if not target_notes:
            continue

        for path in target_notes:
            body = await _read_note(client, path)
            if not body:
                continue

            fm, _ = _split_frontmatter(body)
            original_path: str | None = fm.get("original_path")

            # Flag if: the file was originally from a protected namespace (covered
            # by provenance scan too, but we surface it here for completeness)
            # OR it looks like a persona/identity file without provenance.
            if original_path and _is_protected_path(original_path):
                # Already covered by provenance scan; report in inventory mode too
                findings.append(
                    Finding(
                        level="CRITICAL",
                        mode="inventory",
                        description=(
                            f"Protected file found in target namespace: "
                            f"original_path={original_path!r} → {path!r}"
                        ),
                        original_path=original_path,
                        current_path=path,
                        extra={
                            "namespace": target_prefix,
                            "detection": "original_path provenance",
                            "action": "Restore via REST PUT /vault/<original_path> (do NOT call vault.move into protected namespace — 40-05 blocks it)",
                        },
                    )
                )
            elif not original_path and _is_persona_like_content(body, path):
                # No provenance but looks like an operator file — flag for review
                findings.append(
                    Finding(
                        level="CRITICAL",
                        mode="inventory",
                        description=(
                            f"Persona-like / possibly misplaced operator file in "
                            f"target namespace {target_prefix!r}: {path!r} "
                            "(no original_path frontmatter — damage pre-provenance or post-rollback)"
                        ),
                        original_path=None,
                        current_path=path,
                        extra={
                            "namespace": target_prefix,
                            "detection": "persona-like content (no original_path)",
                            "action": "Manually verify — if operator file, restore via REST PUT /vault/<original_path>",
                        },
                    )
                )

    if verbose:
        criticals = [f for f in findings if f.level == "CRITICAL"]
        print(
            f"\n  Inventory scan complete: {len(criticals)} CRITICAL finding(s)."
        )

    return findings


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------


def _print_report(
    findings: list[Finding],
    using_manifest: bool,
    inventory_path: str | None,
) -> None:
    """Print structured CRITICAL / INFO report."""
    criticals = [f for f in findings if f.level == "CRITICAL"]
    infos = [f for f in findings if f.level == "INFO"]

    print("\n" + "=" * 70)
    print("BLAST-RADIUS AUDIT REPORT")
    print("=" * 70)

    if not using_manifest:
        print(
            "\n  NOTE: inventory mode used BUILT-IN DRIFT-PRONE canonical map.\n"
            "  Run with --inventory <manifest> for an authoritative, complete diff.\n"
        )

    print(f"\nCRITICAL findings ({len(criticals)}):")
    if criticals:
        for f in criticals:
            print(f)
        print(
            "\n  RESTORE INSTRUCTIONS: use REST PUT /vault/<original_path>\n"
            "  with the note body from its current location.\n"
            "  DO NOT call vault.move() into sentinel/ — the 40-05 destination\n"
            "  guard blocks it.  Use a direct REST PUT request instead.\n"
        )
    else:
        print("  None.")

    print(f"\nINFO findings (all relocations in incident window) ({len(infos)}):")
    if infos:
        for f in infos:
            print(f)
    else:
        print("  None.")

    print("\n" + "=" * 70)
    if criticals:
        print(f"RESULT: FAIL — {len(criticals)} CRITICAL finding(s). Restore and re-run.")
    else:
        print("RESULT: CLEAN — no CRITICAL findings.")
    print("=" * 70 + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="uat_phase40_blast_radius.py",
        description=(
            "Two-mode read-only blast-radius audit for Phase 40 vault-sweeper incident.\n"
            "IMPORTANT: Running without LIVE_TEST=1 performs NO AUDIT (exit 2).\n"
            "See module docstring for full documentation."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--mode",
        choices=["provenance", "inventory", "both"],
        default="both",
        help=(
            "Which scan(s) to run: provenance (relocation/trash provenance frontmatter), "
            "inventory (namespace-policy presence check + persona-like target-dir scan), "
            "or both (default)."
        ),
    )
    p.add_argument(
        "--since",
        metavar="ISO8601",
        default=None,
        help=(
            "Incident-window lower bound (concrete ISO 8601 timestamp).  "
            "Only provenance entries with topic_moved_at/sweep_at >= this value are included.  "
            "Example: --since 2026-06-10T00:00:00Z.  "
            "Omit to scan all history."
        ),
    )
    p.add_argument(
        "--inventory",
        metavar="PATH",
        default=None,
        help=(
            "Path to a known-good JSON manifest (AUTHORITATIVE source for namespace-policy scan).  "
            "Format: {\"sentinel/\": [\"sentinel/persona.md\", ...], \"self/\": [...], ...}.  "
            "When supplied the expected-file list comes FROM this manifest (round-3 item 3).  "
            "Without it the script falls back to the DRIFT-PRONE built-in canonical map and "
            "warns at runtime.  Prefer --inventory for a complete, authoritative diff."
        ),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help=(
            "Affirmation flag (read-only regardless of this flag — NOT a mode switch).  "
            "The script never mutates the vault.  --dry-run is an explicit no-mutation "
            "affirmation for operator confidence only."
        ),
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        default=False,
        help="Suppress per-note progress output; show only the final report.",
    )
    return p


async def _main(args: argparse.Namespace) -> int:
    # ------------------------------------------------------------------
    # LIVE_TEST gate: running without LIVE_TEST=1 is a SILENT NO-OP.
    # This is NOT a clean-vault result — no audit is performed.
    # ------------------------------------------------------------------
    if os.environ.get("LIVE_TEST") != "1":
        print(
            "\n*** SKIPPED (no audit performed) ***\n"
            "LIVE_TEST not set — no audit performed; this is NOT a clean-vault result.\n"
            "Set LIVE_TEST=1 to arm the audit.\n",
            file=sys.stderr,
        )
        print(
            "SKIPPED: LIVE_TEST=1 required to arm this audit.\n"
            "This is NOT a clean-vault result — the script performed NO audit.\n"
            "Set LIVE_TEST=1 to run."
        )
        return 2  # Distinct non-success signal — not 0 (clean) and not 1 (CRITICAL found)

    if not _OBSIDIAN_KEY:
        print("ERROR: UAT_OBSIDIAN_KEY env var required (Obsidian Local REST API bearer token).")
        return 1

    since = _parse_since(args.since)
    verbose = not args.quiet
    inventory_path: str | None = args.inventory

    print("-- Phase 40 Blast-Radius Audit --")
    print(f"  vault    : {_OBSIDIAN_URL}")
    print(f"  mode     : {args.mode}")
    print(f"  since    : {args.since or '(all history)'}")
    print(f"  inventory: {inventory_path or '(none — using built-in drift-prone fallback)'}")
    print(f"  dry-run  : {args.dry_run} (affirmation only — script is always read-only)")
    print()

    headers: dict[str, str] = {}
    if _OBSIDIAN_KEY:
        headers["Authorization"] = f"Bearer {_OBSIDIAN_KEY}"

    all_findings: list[Finding] = []
    using_manifest = inventory_path is not None

    async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
        if args.mode in ("provenance", "both"):
            prov_findings = await run_provenance_scan(
                client, since=since, verbose=verbose
            )
            all_findings.extend(prov_findings)

        if args.mode in ("inventory", "both"):
            inv_findings = await run_inventory_scan(
                client, inventory_path=inventory_path, verbose=verbose
            )
            all_findings.extend(inv_findings)

    # If inventory was requested but _load_inventory returned None, using_manifest stays False
    # (the scan itself printed the warning)
    _print_report(all_findings, using_manifest=using_manifest, inventory_path=inventory_path)

    criticals = [f for f in all_findings if f.level == "CRITICAL"]
    return 1 if criticals else 0


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    sys.exit(asyncio.run(_main(args)))


if __name__ == "__main__":
    main()
