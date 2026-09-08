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

PER-MODEL BREAKDOWN, AND WHY IT IS ONLY PARTLY TRUSTWORTHY (ADR-0007 step 5):
Each summary's frontmatter carries a ``model:`` line, so the rate can be
attributed to the model that actually produced each response. This is the
measurement the whole ADR was staged around -- step 1 landed the stop-sequence
fix ALONE so a change in this rate could be attributed to it rather than to a
fifteen-file refactor.

But that line only became truthful when ADR-0007 step 2 fixed Defect B. Before
that fix every summary recorded the configured ``MODEL_NAME`` default rather
than the model that answered, and the deployed container was recording
``google/gemma-4-31b`` while LM Studio served ``qwen/qwen3.8-27b``. **A
breakdown spanning that cutover therefore has untrustworthy older rows: they
are labelled with configuration, not with evidence.** They are reported rather
than dropped -- the responses were real and the aggregate is unaffected -- but
do not read a pre-cutover per-model row as a fact about that model. Use
``--since`` to scope a comparison to summaries written after the cutover.

Usage (inside the container / venv):
    python scripts/anomaly_rate.py
    python scripts/anomaly_rate.py --since 2026-08-20 --until 2026-08-28
    python scripts/anomaly_rate.py --user trekkie --json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter

import httpx

from app.config import settings
from app.services.response_anomaly import detect_anomalies
from app.vault import ObsidianVault, Vault, _parse_session_summary

SESSIONS_ROOT = "ops/sessions"

#: Bucket for a summary whose frontmatter names no model, or whose frontmatter
#: cannot be parsed at all. Named explicitly rather than dropped: a summary with
#: no model line is still a scored response, and silently omitting it would make
#: the per-model totals disagree with the aggregate -- which is exactly how a
#: breakdown becomes a thing nobody trusts.
UNKNOWN_MODEL = "(unknown)"

#: The leading ``---\n...\n---`` block, and one ``key: value`` line inside it.
#: Deliberately the same shape ``app.vault._parse_session_summary`` uses; that
#: parser is the adapter edge this script reuses, but it does not RETURN the
#: model, so the one field this script needs is read here.
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_MODEL_LINE_RE = re.compile(r"^model:\s*(.+)$", re.MULTILINE)


def _model_of(raw: str) -> str:
    """The ``model:`` frontmatter value, or ``UNKNOWN_MODEL``. Never raises.

    A summary predating the frontmatter field, one with malformed frontmatter,
    and one with an empty value all land in the same explicit bucket. The
    never-raises contract of the whole script holds here too: this is called on
    every summary, and a regex surprise must not be able to end the run.
    """
    try:
        block = _FRONTMATTER_RE.match(raw)
        if block is None:
            return UNKNOWN_MODEL
        found = _MODEL_LINE_RE.search(block.group(1))
        if found is None:
            return UNKNOWN_MODEL
        return found.group(1).strip() or UNKNOWN_MODEL
    except Exception:
        return UNKNOWN_MODEL


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
        "by_model": {model: {"total": int, "flagged": int, "percentage": float}},
      }

    ``by_model`` is an ADDITION: every other figure is computed exactly as
    before, and its per-model ``total`` values always sum to the aggregate
    ``total``. Summaries with no parseable ``model:`` frontmatter land under
    :data:`UNKNOWN_MODEL` rather than being dropped. See the module docstring
    for why pre-Defect-B rows are labelled with configuration rather than
    evidence.
    """
    total = 0
    flagged = 0
    skipped = 0
    excluded = 0
    signal_counts: Counter[str] = Counter()
    flagged_files: list[dict] = []
    per_model_total: Counter[str] = Counter()
    per_model_flagged: Counter[str] = Counter()

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
            model = _model_of(raw)
            per_model_total[model] += 1
            result = detect_anomalies(response, prompt_text=parsed.user_msg)
            if result.suspicious:
                flagged += 1
                per_model_flagged[model] += 1
                for sig in result.signals:
                    signal_counts[sig] += 1
                flagged_files.append({"path": path, "signals": list(result.signals)})

    percentage = round((flagged / total * 100), 1) if total else 0.0

    by_model = {
        model: {
            "total": model_total,
            "flagged": per_model_flagged[model],
            "percentage": round((per_model_flagged[model] / model_total * 100), 1),
        }
        # Busiest model first, then alphabetically, so repeated runs order the
        # same way and two outputs can be diffed.
        for model, model_total in sorted(
            per_model_total.items(), key=lambda kv: (-kv[1], kv[0])
        )
    }

    return {
        "total": total,
        "flagged": flagged,
        "percentage": percentage,
        "skipped": skipped,
        "excluded": excluded,
        "signal_counts": dict(signal_counts),
        "flagged_files": flagged_files,
        "by_model": by_model,
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

    if result.get("by_model"):
        lines.append("  by model:")
        for model, stats in result["by_model"].items():
            lines.append(
                f"    {model}: {stats['flagged']}/{stats['total']} "
                f"({stats['percentage']}%)"
            )
        lines.append(
            "    note: summaries written before ADR-0007 step 2's Defect B fix "
            "record the configured MODEL_NAME, not the model that answered — "
            "pre-cutover rows are labelled with configuration, not evidence."
        )

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
