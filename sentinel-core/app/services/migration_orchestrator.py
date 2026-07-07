"""Migration orchestrator — the flat-7 -> ops//notes/ cutover (Phase 47,
MIG-01/MIG-02).

Clones ``pipeline_orchestrator.run``'s lock/try/finally shape verbatim
(D-04/Pitfall 8): the shared sweep lock is acquired FIRST, before any vault
read, and released in a ``finally``; a lock already held by a concurrent
sweep/pipeline/migration run raises ``SweepInProgressError`` distinctly
from a generic failure.

Two tracks (D-01):
  - **Track A (ops-bound)**: ``journal/`` -> ``ops/journal/{YYYY-MM-DD}/``
    and ``accomplishments/`` -> ``ops/accomplishments/``, each a
    frontmatter-preserving ``relocate()`` plus an inline embedding
    sidecar-key patch (Pattern 2, D-04 "no re-embed"), gated by the
    ops-scoped backlink scan (Pattern 3, D-03 verify-then-trust).
  - **Track B (notes-bound)**: ``learning/``/``reference(s)/`` -> enqueued
    via ``inbox.append_entry()`` and routed through the reused 6 Rs
    ``pipeline_orchestrator.run(mode="pipeline")`` (Pattern 1). Not wired
    by this plan (Plan 04) — ``_discover_flat7`` still reports these files
    for the dry-run preview, carrying a placeholder destination.

``dry_run=True`` performs ZERO vault mutations: the discovery pass alone
populates ``report.planned_moves`` and the run returns before any track's
loop executes (assert-zero-writes contract, D-02).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.errors import SweepInProgressError
from app.routes.graph import _hub_paths as _graph_hub_paths
from app.routes.graph import _notes_map_from_index as _graph_notes_map
from app.services import graph_analysis, pipeline_orchestrator
from app.services.embedding_sidecar_index import (
    EMBEDDING_INDEX_PATH,
    NOMIC_DOCUMENT_PREFIX,
    decode_index_body,
    encode_index_body,
    fresh_entry,
)
from app.services.graph_analysis import NOTES_ROOT
from app.services.inbox import INBOX_PATH, append_entry
from app.services.links_sidecar_index import rebuild_links_index_if_stale
from app.services.migration_rollback_ledger import RollbackLedger
from app.services.migration_status_store import (
    new_status as _new_status,
    patch_status as _patch_status,
    set_status as _set_status_from_report,
)
from app.services.note_classifier import ClassificationResult, topic_dir_for
from app.services.ops_backlink_scan import scan_for_title_refs
from app.services.task_runner import AsyncioTaskRunner, TaskRunner
from app.services.vault_sweeper import _embedding_model_id
from app.time_utils import _iso_utc, _today_str

logger = logging.getLogger(__name__)

# Structural claim-title check, mirrors note_schema._H1_RE: any Markdown H1
# line, anywhere in the body. Wikilinks reference notes by their display
# title (Pattern 4 / Obsidian resolution semantics), never the raw flat-7
# filename -- this is what scan_for_title_refs must search for.
_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)

# Ops-bound (Track A) legacy directory candidates.
_JOURNAL_DIR = "journal"
_ACCOMPLISHMENT_DIRS = ("accomplishments", "accomplishment")  # Pitfall E

# Notes-bound (Track B, Plan 04) legacy directory candidates -- discovered
# here for the dry-run preview only; Track A never moves them.
_LEARNING_DIR = "learning"
_REFERENCE_DIRS = ("references", "reference")  # Pitfall E

_TRACK_B_PENDING_DST = "notes/ (pending Reduce -- Track B, Plan 04)"


@dataclass
class MigrationReport:
    """Explicit per-track outcome report for one migration run (mirrors
    ``PipelineReport``'s explicit-per-phase-count discipline, D-03a)."""

    migration_id: str
    status: str = "running"  # idle | running | complete | blocked | error
    dry_run: bool = False
    planned_moves: list[dict[str, str]] = field(default_factory=list)
    ops_moved: list[dict[str, str]] = field(default_factory=list)
    notes_backfilled: int = 0
    verify_failed: int = 0
    new_orphans: int = 0
    rolled_back: bool = False
    errors: list[str] = field(default_factory=list)


# --- Discovery ----------------------------------------------------------


async def _list_dir_files(vault: Any, dirname: str) -> list[str]:
    """Return bare filenames (excluding subdirectory entries) directly
    under ``dirname``."""
    entries = await vault.list_under(dirname)
    return [e for e in entries if e and not e.endswith("/")]


async def _discover_flat7(vault: Any) -> list[dict[str, str]]:
    """Discover every legacy flat-7 file across all four categories.

    Probes BOTH singular and plural spellings for reference(s)/
    accomplishment(s) (Pitfall E) and reports files found under EITHER
    spelling — a vault may have content split across both, so this merges
    rather than picking one. Computes a real ops-bound destination for
    journal/accomplishment(s) (Track A) via
    ``note_classifier.topic_dir_for``; notes-bound learning/reference(s)
    files (Track B, Plan 04) are discovered for the dry-run preview only,
    carrying a placeholder destination until Plan 04 wires the
    Reduce-backed enqueue.
    """
    today = _today_str()
    discovered: list[dict[str, str]] = []

    for filename in await _list_dir_files(vault, _JOURNAL_DIR):
        src = f"{_JOURNAL_DIR}/{filename}"
        dst_dir = topic_dir_for("journal", today=today)
        discovered.append(
            {"src": src, "dst": f"{dst_dir}/{filename}", "track": "ops", "category": "journal"}
        )

    # A vault whose journal is already date-organized nests entries one level
    # down (journal/2026-07-06/foo.md); the flat top-level scan above misses
    # them, which would grandfather real journal notes (violates MIG-01 /
    # the "journal/ contains zero remaining notes" post-condition). Recurse
    # exactly one level into journal subdirs, preserving the original subdir
    # (its date) under ops/journal/{subdir}/ so the journal's existing
    # temporal organization survives the move.
    for entry in await vault.list_under(_JOURNAL_DIR):
        if not entry.endswith("/"):
            continue
        subdir = entry.rstrip("/").rsplit("/", 1)[-1]
        if not subdir:
            continue
        subpath = f"{_JOURNAL_DIR}/{subdir}"
        for filename in await _list_dir_files(vault, subpath):
            src = f"{subpath}/{filename}"
            dst_dir = topic_dir_for("journal", today=subdir)
            discovered.append(
                {"src": src, "dst": f"{dst_dir}/{filename}", "track": "ops", "category": "journal"}
            )

    for dirname in _ACCOMPLISHMENT_DIRS:
        for filename in await _list_dir_files(vault, dirname):
            src = f"{dirname}/{filename}"
            dst_dir = topic_dir_for("accomplishment")
            discovered.append(
                {
                    "src": src,
                    "dst": f"{dst_dir}/{filename}",
                    "track": "ops",
                    "category": "accomplishment",
                }
            )

    for filename in await _list_dir_files(vault, _LEARNING_DIR):
        src = f"{_LEARNING_DIR}/{filename}"
        discovered.append(
            {"src": src, "dst": _TRACK_B_PENDING_DST, "track": "notes", "category": "learning"}
        )

    for dirname in _REFERENCE_DIRS:
        for filename in await _list_dir_files(vault, dirname):
            src = f"{dirname}/{filename}"
            discovered.append(
                {"src": src, "dst": _TRACK_B_PENDING_DST, "track": "notes", "category": "reference"}
            )

    return discovered


def _extract_title(body: str, src: str) -> str:
    """Return the note's H1 claim title, or its filename stem if absent.

    Wikilinks reference notes by their display title, never the raw flat-7
    filename -- this is what ``scan_for_title_refs`` must search for.
    """
    match = _H1_RE.search(body or "")
    if match:
        return match.group(1).strip()
    stem = src.rsplit("/", 1)[-1]
    if stem.endswith(".md"):
        stem = stem[: -len(".md")]
    return stem


# --- Track A: ops-bound direct move + sidecar patch ----------------------


async def _patch_sidecar_key(vault: Any, src: str, dst: str) -> bool:
    """Rename the embedding sidecar's key ``src`` -> ``dst`` in place, value
    untouched (Pattern 2 / D-04 "no re-embed").

    Returns True if a rename happened, False if ``src`` had no sidecar
    entry (nothing to patch — the note had no embedding yet and the
    ordinary sweep will pick it up fresh under its new path, D-04a).
    """
    raw = await vault.read_note(EMBEDDING_INDEX_PATH)
    if not raw.strip():
        return False
    index = decode_index_body(raw, EMBEDDING_INDEX_PATH)
    if src not in index:
        return False
    index[dst] = index.pop(src)
    await vault.write_note(EMBEDDING_INDEX_PATH, encode_index_body(index, EMBEDDING_INDEX_PATH))
    return True


async def _move_ops_bound(
    vault: Any,
    src: str,
    dst: str,
    rollback: RollbackLedger,
    ledger_backlinks: list[dict[str, Any]],
) -> str:
    """Relocate one ops-bound file, patch its embedding-sidecar key inline
    (Pattern 2/D-04, no re-embed), record both in ONE rollback-ledger entry
    (T-47-03), and gate on the vault-wide pre/post backlink scan (Pattern
    3/D-03 verify-then-trust).

    A post<pre shortfall (a broken ops-bound backlink) is appended to
    ``ledger_backlinks`` for the rollback-trigger logic to consume — never
    silently ignored.
    """
    body = await vault.read_note(src)
    title = _extract_title(body, src)

    pre = await scan_for_title_refs(vault, title)

    actual_dst = await vault.relocate(src, dst)
    sidecar_key_moved = await _patch_sidecar_key(vault, src, actual_dst)
    rollback.record_ops_move(
        src, actual_dst, sidecar_key_moved=sidecar_key_moved, original_body=body
    )

    post = await scan_for_title_refs(vault, title)
    if post < pre:
        ledger_backlinks.append(
            {"src": src, "dst": actual_dst, "title": title, "pre": pre, "post": post}
        )

    return actual_dst


async def _run_track_a(
    vault: Any,
    report: MigrationReport,
    rollback: RollbackLedger,
    ledger_backlinks: list[dict[str, Any]],
) -> None:
    """Ops-bound direct-move track (D-01: ops-bound moves run first)."""
    discovered = await _discover_flat7(vault)
    for item in discovered:
        if item["track"] != "ops":
            continue
        actual_dst = await _move_ops_bound(
            vault, item["src"], item["dst"], rollback, ledger_backlinks
        )
        report.ops_moved.append({"src": item["src"], "dst": actual_dst})


# --- Track B: notes-bound enqueue + reused Reduce backfill (Plan 04) -----


async def _ensure_embedded(
    vault: Any,
    note_paths: list[str],
    embedder: "Callable[[list[str]], Awaitable[list[list[float]]]]",
) -> None:
    """Embed-on-Reduce (D-04): trigger one targeted single-note embed per
    freshly-filed ``notes/{slug}.md`` path.

    The reused ``pipeline_orchestrator.run(mode="pipeline")`` computes a
    transient ``note_vector`` only for Reflect's cosine hub-match
    (``six_rs/reflect.find_and_attach_hub``) -- it never persists a sidecar
    entry (confirmed: ``pipeline_orchestrator.py`` never imports
    ``encode_index_body``). Without this step every notes-bound filed note
    would go unembedded until the next sweep, and waiting is not an option
    here: these notes now live under ``notes/``, but the ORIGINAL capture
    briefly lived in ``inbox/``, which is in ``SWEEP_SKIP_PREFIXES`` -- so
    an embed gap introduced here would not self-heal the way an ordinary
    sweep-eligible path does.
    """
    if not note_paths:
        return
    raw = await vault.read_note(EMBEDDING_INDEX_PATH)
    index = decode_index_body(raw, EMBEDDING_INDEX_PATH) if raw.strip() else {}
    active_model = _embedding_model_id()
    changed = False
    for path in note_paths:
        if path in index:
            continue
        body = await vault.read_note(path)
        try:
            vectors = await embedder([NOMIC_DOCUMENT_PREFIX + body])
        except Exception as exc:
            logger.warning(
                "migration_orchestrator: embed-on-Reduce failed for %s: %s", path, exc
            )
            continue
        if not vectors:
            continue
        index[path] = fresh_entry(body, vectors[0], active_model)
        changed = True
    if changed:
        await vault.write_note(
            EMBEDDING_INDEX_PATH, encode_index_body(index, EMBEDDING_INDEX_PATH)
        )


async def _enqueue_notes_bound(
    vault: Any,
    report: MigrationReport,
    rollback: RollbackLedger,
    *,
    embedder: "Callable[[list[str]], Awaitable[list[list[float]]]] | None",
    settings: Any,
) -> tuple[list[str], list[str]]:
    """Track B (D-01/Pattern 1): enqueue every notes-bound legacy file via
    ``inbox.append_entry()``, delete the originals, then reuse
    ``pipeline_orchestrator.run(vault, mode="pipeline")`` UNMODIFIED to
    produce born-compliant ``notes/{slug}.md`` -- NEVER a bare
    ``relocate()`` into ``inbox/`` (Pitfall A).

    Returns ``(old_titles, new_notes_paths)`` -- the enqueued legacy
    claim-ish titles (from each original file's H1) and the freshly-created
    ``notes/`` paths (path-set diff pre/post the pipeline run), for the
    caller's best-effort backlink-rewrite mapping (D-03). The reused
    ``PipelineReport`` carries no per-entry old->new correspondence (Reduce/
    Reflect/Verify run verbatim, unmodified per RESEARCH's "Don't
    Hand-Roll"), so an EXACT trace cannot be derived without touching Phase
    46 code -- out of scope for this plan.
    """
    discovered = await _discover_flat7(vault)
    notes_bound = [item for item in discovered if item["track"] == "notes"]
    if not notes_bound:
        return [], []

    inbox_body = await vault.read_note(INBOX_PATH)
    pre_write_inbox_body = inbox_body
    old_titles: list[str] = []

    for item in notes_bound:
        src = item["src"]
        body = await vault.read_note(src)
        old_titles.append(_extract_title(body, src))
        topic = "learning" if item["category"] == "learning" else "reference"
        inbox_body = append_entry(
            inbox_body,
            candidate_text=body,
            result=ClassificationResult(
                topic=topic,
                confidence=1.0,
                title_slug="",
                reasoning="Phase 47 backfill migration",
            ),
        )
        rollback.record_restore_original(src, body)

    rollback.record_inbox_write(INBOX_PATH, pre_write_inbox_body)
    await vault.write_note(INBOX_PATH, inbox_body)

    for item in notes_bound:
        await vault.delete_note(item["src"])

    pre_notes_filenames = set(await _list_dir_files(vault, NOTES_ROOT))

    pipe_report = await pipeline_orchestrator.run(
        vault, mode="pipeline", embedder=embedder, settings=settings
    )

    report.notes_backfilled += max(0, pipe_report.reduced - pipe_report.verify_failed)
    report.verify_failed += pipe_report.verify_failed
    if pipe_report.errors:
        report.errors.extend(pipe_report.errors)

    post_notes_filenames = set(await _list_dir_files(vault, NOTES_ROOT))
    new_filenames = sorted(post_notes_filenames - pre_notes_filenames)
    new_notes_paths = [f"{NOTES_ROOT}/{fn}" for fn in new_filenames]

    if embedder is not None:
        await _ensure_embedded(vault, new_notes_paths, embedder)

    return old_titles, new_notes_paths


def _build_rewrite_mapping(old_titles: list[str], new_notes_paths: list[str]) -> dict[str, str]:
    """Best-effort old-title -> new-claim-title correspondence for D-03.

    The reused ``pipeline_orchestrator.run(mode="pipeline")`` processes
    queued entries in REVERSE entry_n order (last-enqueued first,
    ``pipeline_orchestrator._run_pipeline``) and its ``PipelineReport``
    carries no per-entry old->new path mapping; deriving an exact trace
    would require modifying Phase 46 code, which is explicitly out of
    scope ("reused verbatim", RESEARCH "Don't Hand-Roll"). Migration's own
    entries are enqueued as a contiguous, highest-entry_n block, so pairing
    ``reversed(old_titles)`` against the newly-created ``notes/`` slugs is
    the best available approximation.

    This is deliberately NOT relied upon for correctness: the D-03a graph
    orphan-diff (``_graph_orphan_diff``) is the hard backstop -- any
    backlink this mapping mispairs or misses still surfaces as a new orphan
    under ``notes/`` and forces a full rollback, per the Locked Decision.
    """
    return {
        old: new for old, new in zip(reversed(old_titles), new_notes_paths) if old and new
    }


async def _rewrite_backlinks_after_reduce(
    vault: Any,
    mapping: dict[str, str],
    rollback: RollbackLedger,
) -> None:
    """D-03 active backlink rewrite: for each ``old_title -> new_claim_title``
    pair, find vault-wide ``[[old_title]]`` references and rewrite them to
    ``[[new_claim_title]]``, recording each edit for rollback.
    """
    if not mapping:
        return
    for old_title, new_path in mapping.items():
        if not old_title or not new_path or old_title == new_path:
            continue
        new_body = await vault.read_note(new_path)
        new_title = _extract_title(new_body, new_path)
        if not new_title or new_title == old_title:
            continue
        old_link = f"[[{old_title}]]"
        new_link = f"[[{new_title}]]"
        hits = await vault.find(old_link)
        for hit in hits:
            path = hit.get("filename") or hit.get("path")
            if not path or path == new_path:
                continue
            before_body = await vault.read_note(path)
            if old_link not in before_body:
                continue
            rollback.record_backlink_rewrite(path, before_body)
            after_body = before_body.replace(old_link, new_link)
            await vault.write_note(path, after_body)


# --- D-03a hard backstop: pre/post :graph orphan diff (Reduce track only) -


async def _graph_orphan_diff(vault: Any) -> set[str]:
    """Return the current ``notes/``-scoped orphan-path set via the SAME
    code path ``GET /vault/graph`` uses (D-03a backstop for the Reduce
    track only -- Pattern 3: ``:graph`` is structurally blind to ``ops/``,
    which is why Track A uses the separate ``scan_for_title_refs`` instead).
    """
    index = await rebuild_links_index_if_stale(vault)
    notes_map = _graph_notes_map(index)
    hub_paths = _graph_hub_paths(index)
    report = graph_analysis.build_graph_report(notes_map, hub_paths)
    return set(report.orphans)


def _should_rollback(
    raised_exc: "Exception | None", new_orphans: int, ops_shortfall: bool
) -> bool:
    """Locked Decision (resolves RESEARCH Open Question 1): full atomic
    rollback iff ANY of --

      1. a hard exception escaped a REST mutation (``relocate``/
         ``write_note``/``delete_note``/``read_note`` raising, an unhandled
         crash, OR ``SweepInProgressError`` raised mid-body);
      2. the D-03a ``:graph`` post-pre orphan diff found >=1 NEW orphan
         (``notes/``-scoped);
      3. the Track A ops-bound ``scan_for_title_refs`` post<pre shortfall
         for any moved file that could not be repaired by a rewrite.

    A pipeline dead-letter alone (``report.verify_failed`` non-empty, run
    ``status="complete"``, no new orphans) is explicitly NOT a trigger --
    Phase 46's own graceful-degrade contract (a bad LLM completion stays in
    ``inbox/``, never silently dropped) is a designed, non-corrupting
    outcome, not vault corruption.
    """
    return raised_exc is not None or new_orphans > 0 or ops_shortfall


# --- Orchestrator entrypoint ---------------------------------------------


async def run(
    vault: Any,
    *,
    dry_run: bool,
    embedder: "Callable[[list[str]], Awaitable[list[list[float]]]] | None" = None,
    settings: Any = None,
    status_callback: "Callable[[MigrationReport], None] | None" = None,
) -> MigrationReport:
    """Run (or preview) the flat-7 -> ops//notes/ migration cutover.

    Acquires the shared sweep lock FIRST (D-04/Pitfall 8), mirroring
    ``pipeline_orchestrator.run``'s precedent; a lock already held raises
    ``SweepInProgressError`` before any read (dry-run or live).

    For a live run, Track A (ops-bound direct move) runs first while this
    migration's own lock is held -- ``relocate()``/``scan_for_title_refs``
    never touch the shared lock themselves, so no nesting risk there. The
    lock is then explicitly RELEASED before Track B: both
    ``pipeline_orchestrator.run(mode="pipeline")`` and
    ``links_sidecar_index.rebuild_links_index`` (called transitively via
    ``_graph_orphan_diff`` below when the ``notes/`` sidecar is stale) each
    acquire this SAME shared lock internally -- without releasing first,
    either call would immediately raise ``SweepInProgressError`` with zero
    work done (a guaranteed self-deadlock, not a genuine failure; confirmed
    against ``pipeline_orchestrator.run():505-506`` and
    ``links_sidecar_index.rebuild_links_index:118-119``). The lock is
    re-acquired once Track B/the graph-diff/the backlink-rewrite finish, so
    the rollback-trigger decision and any ``rollback.replay()`` still run
    under migration's own exclusivity.

    Per the Locked Decision, NO exception escaping the live-run body is
    re-raised: a hard failure (including a failed lock re-acquisition,
    treated as "SweepInProgressError raised mid-body") is captured and
    triggers ``rollback.replay()`` instead, so the caller always gets back
    a ``MigrationReport`` describing the outcome (``rolled_back``/
    ``status``/``errors``) rather than an exception. Only the very initial
    lock-acquisition failure (this migration run could not even start)
    still raises, unchanged from before.
    """
    migration_id = _iso_utc()
    report = MigrationReport(migration_id=migration_id, status="running", dry_run=dry_run)

    if not await vault.acquire_sweep_lock():
        raise SweepInProgressError("a vault operation is already in progress")

    try:
        if dry_run:
            # Assert-zero-writes contract (D-02): discovery only, return
            # before any mutation.
            report.planned_moves = await _discover_flat7(vault)
            report.status = "complete"
            return report

        rollback = RollbackLedger()
        ledger_backlinks: list[dict[str, Any]] = []
        raised_exc: Exception | None = None

        try:
            # --- Track A: ops-bound direct moves -------------------------
            await _run_track_a(vault, report, rollback, ledger_backlinks)

            # Hand off to Track B -- see the docstring above for why the
            # lock must be released here.
            await vault.release_sweep_lock()
            try:
                graph_pre = await _graph_orphan_diff(vault)

                old_titles, new_notes_paths = await _enqueue_notes_bound(
                    vault, report, rollback, embedder=embedder, settings=settings
                )

                mapping = _build_rewrite_mapping(old_titles, new_notes_paths)
                await _rewrite_backlinks_after_reduce(vault, mapping, rollback)

                graph_post = await _graph_orphan_diff(vault)
                report.new_orphans = len(graph_post - graph_pre)
            except Exception as exc:
                raised_exc = exc
            finally:
                if not await vault.acquire_sweep_lock() and raised_exc is None:
                    raised_exc = SweepInProgressError(
                        "migration_orchestrator: lock re-acquisition failed after Track B"
                    )
        except Exception as exc:
            raised_exc = exc

        ops_shortfall = any(entry["post"] < entry["pre"] for entry in ledger_backlinks)

        if _should_rollback(raised_exc, report.new_orphans, ops_shortfall):
            try:
                await rollback.replay(vault)
            except Exception as replay_exc:
                report.errors.append(f"rollback replay failed: {replay_exc}")
            report.rolled_back = True
            report.status = "error"
            if raised_exc is not None:
                report.errors.append(str(raised_exc))
        else:
            report.status = "complete"

        if status_callback:
            status_callback(report)

        return report
    finally:
        await vault.release_sweep_lock()


# --- Background-task wrapper ----------------------------------------------


async def start_migration(
    *,
    vault: Any,
    dry_run: bool,
    embedder: "Callable[[list[str]], Awaitable[list[list[float]]]] | None" = None,
    settings: Any = None,
    task_runner: "TaskRunner | None" = None,
) -> dict:
    """Schedule a migration run as a background task, returning an
    immediate "running" ack (mirrors ``pipeline_orchestrator.start_pipeline``
    exactly: seed status -> schedule -> ack).
    """
    migration_id = _iso_utc()
    runner = task_runner or AsyncioTaskRunner()
    mode = "dry_run" if dry_run else "live"
    _patch_status(**_new_status(migration_id, "running", mode))

    async def _runner() -> None:
        try:
            report = await run(
                vault,
                dry_run=dry_run,
                embedder=embedder,
                settings=settings,
                status_callback=_set_status,
            )
            _set_status(report)
        except SweepInProgressError:
            _patch_status(status="blocked")
        except Exception as exc:
            logger.exception("migration crashed: %s", exc)
            _patch_status(status="error")

    runner.schedule(_runner())
    return {"migration_id": migration_id, "status": "running", "mode": mode}


def _set_status(report: MigrationReport) -> None:
    _set_status_from_report(report)
