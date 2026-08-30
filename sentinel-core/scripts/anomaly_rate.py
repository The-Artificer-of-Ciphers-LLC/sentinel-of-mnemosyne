"""Measure the local chat model's degenerate-response rate from vault session summaries.

WHY THIS EXISTS (do not "simplify" this back into a log grep):
The obvious instrument -- grepping the container's stdout logs for the
``response-anomaly:`` warning emitted by ``app.services.response_anomaly``
-- is a BAD measurement tool, because Docker destroys container logs every
time the container is recreated. During a day of deploys this kept
reporting ``messages=0 anomalies=0``, which is worthless: the log history
the grep depended on no longer existed.

Session summaries are the right substrate. Every completed exchange is
persisted to the vault at
``ops/sessions/<YYYY-MM-DD>/<user_id>-<HH-MM-SS>.md`` and survives
container restarts, redeploys, and image rebuilds -- it goes back as far
as the vault does. Running ``detect_anomalies`` over that history produces
a real, comparable rate (e.g. 76 responses across 12 days, 4 flagged,
5.3%), which is what you need to compare a serving configuration BEFORE
and AFTER a cutover. Do not replace this with a log grep.

Usage (inside the container / venv):
    python scripts/anomaly_rate.py
    python scripts/anomaly_rate.py --since 2026-08-20 --until 2026-08-28
    python scripts/anomaly_rate.py --user trekkie --json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter

import httpx

from app.config import settings
from app.services.response_anomaly import detect_anomalies
from app.vault import ObsidianVault, Vault, _parse_session_summary

SESSIONS_ROOT = "ops/sessions"


async def scan(
    vault: Vault,
    *,
    since: str | None = None,
    until: str | None = None,
    user: str | None = None,
) -> dict:
    """Walk ``ops/sessions/*/`` and compute the degenerate-response rate.

    ``since``/``until`` are inclusive ``YYYY-MM-DD`` bounds on the session-day
    folder name. ``user`` restricts to summaries whose filename starts with
    ``f"{user}-"`` (the same convention ``FakeVault``/``ObsidianVault`` use
    for the hot-session-tier lookup).

    Reuses ``app.vault._parse_session_summary`` (the same adapter-edge parser
    production uses for the hot session tier) to split each summary into its
    ``## User`` prompt and ``## Sentinel`` response, and
    ``app.services.response_anomaly.detect_anomalies`` to score the response.
    Never raises: a malformed or unreadable summary is skipped and counted,
    not fatal to the run.

    Returns a JSON-serializable dict:
      {
        "total": int,            # responses actually scored (denominator)
        "flagged": int,
        "percentage": float,     # flagged / total * 100, rounded to 1 decimal
        "skipped": int,          # malformed / unreadable summaries
        "excluded": int,         # summaries with no (or empty) ## Sentinel section
        "signal_counts": {signal: count, ...},
        "flagged_files": [{"path": str, "signals": [str, ...]}, ...],
      }
    """
    total = 0
    flagged = 0
    skipped = 0
    excluded = 0
    signal_counts: Counter[str] = Counter()
    flagged_files: list[dict] = []

    try:
        day_entries = await vault.list_under(SESSIONS_ROOT)
    except Exception:
        day_entries = []

    dates = sorted(entry.rstrip("/") for entry in day_entries if entry.endswith("/"))

    for date in dates:
        if since and date < since:
            continue
        if until and date > until:
            continue

        try:
            entries = await vault.list_under(f"{SESSIONS_ROOT}/{date}")
        except Exception:
            continue

        filenames = sorted(e for e in entries if not e.endswith("/") and e.endswith(".md"))

        for filename in filenames:
            if user and not filename.startswith(f"{user}-"):
                continue

            path = f"{SESSIONS_ROOT}/{date}/{filename}"
            try:
                raw = await vault.read_note(path)
                if not raw or not raw.strip():
                    skipped += 1
                    continue
                parsed = _parse_session_summary(path, raw)
                if parsed is None:
                    skipped += 1
                    continue
            except Exception:
                skipped += 1
                continue

            response = parsed.sentinel_msg
            if not response or not response.strip():
                excluded += 1
                continue

            total += 1
            result = detect_anomalies(response, prompt_text=parsed.user_msg)
            if result.suspicious:
                flagged += 1
                for sig in result.signals:
                    signal_counts[sig] += 1
                flagged_files.append({"path": path, "signals": list(result.signals)})

    percentage = round((flagged / total * 100), 1) if total else 0.0

    return {
        "total": total,
        "flagged": flagged,
        "percentage": percentage,
        "skipped": skipped,
        "excluded": excluded,
        "signal_counts": dict(signal_counts),
        "flagged_files": flagged_files,
    }


def _format_human(
    result: dict, *, since: str | None, until: str | None, user: str | None
) -> str:
    scope_bits = []
    if since:
        scope_bits.append(f"since={since}")
    if until:
        scope_bits.append(f"until={until}")
    if user:
        scope_bits.append(f"user={user}")
    scope = f" ({', '.join(scope_bits)})" if scope_bits else ""

    lines = [
        f"Anomaly rate{scope}",
        f"  responses scanned : {result['total']}",
        f"  flagged           : {result['flagged']}",
        f"  rate              : {result['percentage']}%",
        f"  skipped (malformed/unreadable) : {result['skipped']}",
        f"  excluded (no response)         : {result['excluded']}",
    ]

    if result["signal_counts"]:
        lines.append("  signal breakdown:")
        for sig, count in sorted(result["signal_counts"].items(), key=lambda kv: -kv[1]):
            lines.append(f"    {sig}: {count}")

    if result["flagged_files"]:
        lines.append("  flagged files:")
        for entry in result["flagged_files"]:
            lines.append(f"    {entry['path']}: {', '.join(entry['signals'])}")

    return "\n".join(lines)


def emit(
    result: dict,
    *,
    as_json: bool,
    since: str | None = None,
    until: str | None = None,
    user: str | None = None,
) -> None:
    """Print ``result`` in either JSON or human table form."""
    if as_json:
        print(json.dumps(result))
    else:
        print(_format_human(result, since=since, until=until, user=user))


async def _run(args: argparse.Namespace) -> int:
    async with httpx.AsyncClient() as http_client:
        vault = ObsidianVault(http_client, settings.obsidian_api_url, settings.obsidian_api_key)
        result = await scan(vault, since=args.since, until=args.until, user=args.user)

    emit(result, as_json=args.json, since=args.since, until=args.until, user=args.user)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Measure the degenerate-response rate of the local chat model "
            "from persisted vault session summaries (ops/sessions/), not "
            "container logs (which are destroyed on every recreate)."
        )
    )
    parser.add_argument(
        "--since", help="Only scan session-day folders on/after this date (YYYY-MM-DD)."
    )
    parser.add_argument(
        "--until", help="Only scan session-day folders on/before this date (YYYY-MM-DD)."
    )
    parser.add_argument("--user", help="Only scan summaries for this user id prefix.")
    parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON instead of the human table."
    )
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
