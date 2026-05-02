"""Vault sweeper: walk → classify → embed → de-dup → trash-move.

Idempotent via `sweep_pass` frontmatter. Never deletes — moves to
``_trash/{YYYY-MM-DD}/``. Skips ``_trash/``, ``pf2e/``, ``ops/sessions/``,
``ops/sweeps/``, and ``inbox/`` subtrees (RESEARCH Pitfall 5).

Embedding similarity de-dup: cosine ≥ 0.92 → connected components → keep
the older + longer note in each cluster.

Lockfile sentinel ``ops/sweeps/_in-progress.md`` prevents overlapping sweeps
(stale > 1h is taken over with a WARNING — RESEARCH Pitfall 1).
"""
from __future__ import annotations

import base64
import logging
import re
from datetime import datetime, timezone
from typing import AsyncIterator, Awaitable, Callable

import numpy as np
import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


SWEEP_SKIP_PREFIXES: tuple[str, ...] = (
    "_trash/",
    "pf2e/",
    "ops/sessions/",
    "ops/sweeps/",
    "inbox/",
)
"""Module-level fallback default. The runtime denylist is read from
``settings.sweep_skip_prefixes`` via ``_active_skip_prefixes()`` so operators
can extend it via env without code change. This constant is preserved as a
backstop in case settings import fails (and to keep the existing public
import surface stable for callers that referenced it directly)."""


def _active_skip_prefixes() -> tuple[str, ...]:
    """Return the live skip-prefix tuple from settings, falling back to the
    module-level default if settings is unimportable (e.g. during isolated
    unit tests of the helpers).
    """
    try:
        from app.config import settings
        return tuple(settings.sweep_skip_prefixes)
    except Exception:
        return SWEEP_SKIP_PREFIXES

LOCKFILE_PATH = "ops/sweeps/_in-progress.md"
STALE_LOCK_SECONDS = 3600  # 1 hour


def _embedding_model_id() -> str:
    """Return the configured embedding model id for frontmatter recording.

    Lazy settings lookup mirrors ``_active_skip_prefixes`` so isolated unit
    tests of helpers don't fail on settings import. Falls back to the
    historical default if settings is unimportable. (260502-1zv D-03 — single
    source of truth: ``Settings.embedding_model``.)
    """
    try:
        from app.config import settings
        return settings.embedding_model
    except Exception:
        return "text-embedding-nomic-embed-text-v1.5"


class SweepReport(BaseModel):
    sweep_id: str
    status: str = "complete"  # idle | running | complete | error
    files_processed: int = 0
    files_total: int = 0
    duplicates_moved: int = 0
    noise_moved: int = 0
    topic_moves: int = 0  # misplaced→topic-folder relocations
    errors: list[str] = Field(default_factory=list)
    # In dry_run mode, populated with {kind, src, dst, reason} dicts
    # describing every move the sweeper WOULD make. Empty for live runs.
    proposed_moves: list[dict] = Field(default_factory=list)


class SweepInProgressError(RuntimeError):
    """Raised when an existing fresh lockfile blocks a new sweep."""


# --- Time / utility ---


def _iso_utc(now: datetime | None = None) -> str:
    n = now or datetime.now(timezone.utc)
    return n.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today_str(now: datetime | None = None) -> str:
    n = now or datetime.now(timezone.utc)
    return n.astimezone(timezone.utc).strftime("%Y-%m-%d")


def _parse_iso(stamp: str) -> datetime | None:
    if not stamp:
        return None
    try:
        s = stamp.rstrip("Z")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


# --- Frontmatter helpers ---


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def split_frontmatter(body: str) -> tuple[dict, str]:
    """Return (frontmatter, rest_body). Empty FM → ({}, body)."""
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


def join_frontmatter(fm: dict, rest: str) -> str:
    if not fm:
        return rest
    block = yaml.safe_dump(
        fm, sort_keys=False, allow_unicode=True, default_flow_style=False
    ).strip()
    return f"---\n{block}\n---\n\n{rest.lstrip()}"


# --- Embedding (de)serialization — copied verbatim from pathfinder rules.py ---


def encode_embedding(vec) -> str:
    """base64-encode a list[float] or np.ndarray as float32 little-endian bytes."""
    if isinstance(vec, str):
        return vec
    arr = np.asarray(vec, dtype=np.float32)
    return base64.b64encode(arr.tobytes()).decode("ascii")


def decode_embedding(s) -> list[float]:
    """Decode base64 embedding back to list[float]."""
    if isinstance(s, list):
        return [float(x) for x in s]
    if isinstance(s, np.ndarray):
        return s.astype(np.float32).tolist()
    if isinstance(s, str):
        if not s:
            return []
        try:
            raw = base64.b64decode(s.encode("ascii"))
            return np.frombuffer(raw, dtype=np.float32).tolist()
        except Exception as exc:
            logger.warning("Failed to decode embedding base64: %s", exc)
            return []
    return []


# --- Cosine + cluster ---


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two 1-D vectors. Zero-norm → 0.0."""
    av = np.asarray(a, dtype=np.float32)
    bv = np.asarray(b, dtype=np.float32)
    na = float(np.linalg.norm(av))
    nb = float(np.linalg.norm(bv))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(av, bv) / (na * nb))


def find_dup_clusters(matrix: np.ndarray, threshold: float = 0.92) -> list[list[int]]:
    """Connected-components on cosine ≥ threshold pairs. Returns groups of 2+ indices."""
    if matrix is None or matrix.size == 0:
        return []
    n = matrix.shape[0]
    if n < 2:
        return []

    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    safe = np.where(norms == 0.0, 1.0, norms)
    sim = (matrix @ matrix.T) / (safe * safe.T)
    np.fill_diagonal(sim, 0.0)

    visited: set[int] = set()
    clusters: list[list[int]] = []
    for i in range(n):
        if i in visited:
            continue
        cluster = [i]
        stack = [i]
        visited.add(i)
        while stack:
            j = stack.pop()
            for k in np.where(sim[j] >= threshold)[0]:
                k_int = int(k)
                if k_int not in visited:
                    visited.add(k_int)
                    cluster.append(k_int)
                    stack.append(k_int)
        if len(cluster) > 1:
            clusters.append(sorted(cluster))
    return clusters


# --- Skip logic ---


def _should_skip(path: str, frontmatter: dict, current_pass: str) -> bool:
    """True when this path should be left alone in the current pass."""
    if any(path.startswith(p) for p in _active_skip_prefixes()):
        return True
    if not isinstance(frontmatter, dict):
        return False
    if frontmatter.get("sweep_pass") == current_pass and frontmatter.get(
        "topic"
    ) and frontmatter.get("embedding_b64"):
        return True
    return False


# --- Walk ---


async def walk_vault(client, root: str = "") -> AsyncIterator[str]:
    """BFS over Obsidian directory listings; yield .md paths only.

    Skips SWEEP_SKIP_PREFIXES at queue-pop time. Frozen-at-start: callers
    should collect into a list before mutating the vault.
    """
    queue: list[str] = [root]
    skip_prefixes = _active_skip_prefixes()
    while queue:
        dir_path = queue.pop(0)
        if any(dir_path.startswith(p.rstrip("/")) and dir_path != "" for p in skip_prefixes):
            continue
        listing = await client.list_directory(dir_path)
        for entry in listing:
            if not entry:
                continue
            full = f"{dir_path}/{entry}".strip("/") if dir_path else entry.strip("/")
            # Re-check skip prefixes against the candidate
            if any(full.startswith(p.rstrip("/")) for p in skip_prefixes):
                continue
            if entry.endswith("/"):
                queue.append(full.rstrip("/"))
            elif entry.endswith(".md"):
                yield full


# --- Trash move (migrated to ObsidianVault.move_to_trash in 260502-cky) ---
# The sweeper no longer owns trash/relocate/lock primitives. Decision logic
# below (is_in_topic_dir, propose_topic_move, run_sweep orchestration)
# stays here; I/O goes through the injected ``vault``.


# --- Topic-folder move (misplaced note → correct topic dir) ---


def is_in_topic_dir(path: str, topic_dir: str) -> bool:
    """True when ``path`` is already within ``topic_dir``.

    Handles the journal nested-date case: ``journal/2026-04-27/foo.md`` is
    considered in-dir for any ``journal/...`` topic_dir, not just exact
    same-day match. The sweeper does not relocate journal entries between
    days — only flags a wrong-topic placement.
    """
    if not topic_dir:
        return False
    # Same dir or any subdirectory of topic_dir's root family.
    # For journal/2026-04-27, the family root is "journal/"; so journal/.../
    # is considered "in topic_dir family".
    family_root = topic_dir.split("/", 1)[0] + "/"
    return path.startswith(family_root)


def propose_topic_move(
    src_path: str, topic: str, *, today: str | None = None
) -> str | None:
    """Return the destination path a topic-move WOULD use, or None if no
    move is needed (already in topic family) or topic has no canonical dir.

    Used by ``run_sweep(dry_run=True)`` to populate ``proposed_moves``
    without touching the vault.
    """
    from app.services.note_classifier import topic_dir_for

    topic_dir = topic_dir_for(topic, today=today)
    if not topic_dir:
        return None
    if is_in_topic_dir(src_path, topic_dir):
        return None
    filename = src_path.rsplit("/", 1)[-1]
    return f"{topic_dir}/{filename}"


# --- Lockfile (migrated to ObsidianVault.acquire_sweep_lock / release_sweep_lock) ---


# --- Sweep orchestrator ---


async def run_sweep(
    client,
    classifier: Callable[[str], Awaitable["object"]],
    embedder: Callable[[list[str]], Awaitable[list[list[float]]]],
    *,
    force_reclassify: bool = False,
    status_callback: Callable[[SweepReport], None] | None = None,
    dry_run: bool = False,
) -> SweepReport:
    """Walk vault, classify, embed, de-dup, relocate-misplaced, move-to-trash.

    Args:
        client: ObsidianClient (or fake) with list_directory/read_note/
            write_note/delete_note/patch_append.
        classifier: async fn(text) → ClassificationResult (or compatible).
            Bound caller passes ``classify_note`` from note_classifier.
        embedder: async fn(list[str]) → list[list[float]]. Caller binds the
            current LLM endpoint. Failure raises and degrades de-dup.
        force_reclassify: re-classify already-marked notes.
        status_callback: optional progress hook called after each file.
        dry_run: when True, populate ``report.proposed_moves`` with every
            move the sweeper WOULD make and write nothing to the vault.
            Operator runs this first to preview before authorizing a real
            sweep. Lockfile is still acquired/released (one preview at a
            time is correct semantics).
    """
    sweep_id = _iso_utc()
    report = SweepReport(sweep_id=sweep_id, status="running")

    if not await client.acquire_sweep_lock():
        raise SweepInProgressError("a sweep is already running")

    try:
        # 1. Walk → freeze list at start
        paths: list[str] = []
        async for p in walk_vault(client):
            paths.append(p)
        report.files_total = len(paths)

        survivors: list[tuple[str, dict, str, "object"]] = []  # path, fm, body, classification

        for path in paths:
            try:
                body = await client.read_note(path)
                fm, rest = split_frontmatter(body)
                if not force_reclassify and _should_skip(path, fm, sweep_id):
                    report.files_processed += 1
                    if status_callback:
                        status_callback(report)
                    continue

                # Cheap-filter check before LLM (delegated to classifier)
                result = await classifier(rest if rest.strip() else body)

                if getattr(result, "topic", None) == "noise":
                    if dry_run:
                        today = _today_str()
                        report.proposed_moves.append({
                            "kind": "trash",
                            "src": path,
                            "dst": f"_trash/{today}/{path.rsplit('/', 1)[-1]}",
                            "reason": "cheap-filter:noise",
                        })
                    else:
                        await client.move_to_trash(
                            path, reason="cheap-filter:noise", sweep_at=sweep_id
                        )
                    report.noise_moved += 1
                    report.files_processed += 1
                    if status_callback:
                        status_callback(report)
                    continue

                # Misplaced-note relocation: if classified topic has a canonical
                # directory and the current path isn't already in that family,
                # move (or propose to move) the note to {topic_dir}/{filename}.
                topic = getattr(result, "topic", None)
                proposed_dst = (
                    propose_topic_move(path, topic) if topic else None
                )
                if proposed_dst is not None:
                    if dry_run:
                        report.proposed_moves.append({
                            "kind": "topic",
                            "src": path,
                            "dst": proposed_dst,
                            "reason": f"topic={topic} (confidence={result.confidence:.2f})",
                        })
                        # 260427-cza: parity with the live `else` branch below
                        # which increments topic_moves. Without this, dry-run
                        # reports `topic_moves: 0` while listing N proposals.
                        report.topic_moves += 1
                        # Don't add to survivors in dry-run — we're not writing
                        # frontmatter or computing embeddings. Just report.
                        report.files_processed += 1
                        if status_callback:
                            status_callback(report)
                        continue
                    else:
                        try:
                            new_path = await client.relocate(
                                path, proposed_dst, sweep_at=sweep_id
                            )
                            report.topic_moves += 1
                            # Continue processing using the new path so
                            # frontmatter + embedding land at the right location.
                            path = new_path
                            # Re-read body from new location for survivors entry
                            body = await client.read_note(path)
                            fm, rest = split_frontmatter(body)
                        except Exception as exc:
                            report.errors.append(f"topic_move {path}: {exc}")
                            report.files_processed += 1
                            if status_callback:
                                status_callback(report)
                            continue

                # Write back classification frontmatter (preserve extras)
                new_fm = dict(fm)
                new_fm["topic"] = result.topic
                new_fm["confidence"] = float(result.confidence)
                new_fm["sweep_pass"] = sweep_id
                new_fm["source"] = new_fm.get("source") or "vault-sweep"
                if result.title_slug:
                    new_fm.setdefault("title_slug", result.title_slug)

                survivors.append((path, new_fm, rest, result))
                report.files_processed += 1
                if status_callback:
                    status_callback(report)
            except Exception as exc:
                msg = f"{path}: {exc}"
                logger.warning("sweep error: %s", msg)
                report.errors.append(msg)

        # 2. Embed all surviving bodies — degrade gracefully on failure
        bodies = [s[2] for s in survivors]
        embeddings: list[list[float]] | None = None
        if bodies:
            try:
                embeddings = await embedder(bodies)
            except Exception as exc:
                logger.warning("sweep: embedding endpoint failed (%s); skipping de-dup", exc)
                embeddings = None

        # 3. Write classification + (optional) embedding back to each note.
        # Skipped entirely in dry_run — no vault mutations are allowed.
        if not dry_run:
            for idx, (path, fm, rest, _) in enumerate(survivors):
                try:
                    if embeddings and idx < len(embeddings):
                        fm["embedding_model"] = _embedding_model_id()
                        fm["embedding_b64"] = encode_embedding(embeddings[idx])
                    new_body = join_frontmatter(fm, rest)
                    await client.write_note(path, new_body)
                except Exception as exc:
                    report.errors.append(f"write_back {path}: {exc}")

        # 4. De-dup
        moves: list[tuple[str, str, str]] = []  # (src, dst, reason)
        if embeddings and len(embeddings) >= 2:
            matrix = np.asarray(embeddings, dtype=np.float32)
            clusters = find_dup_clusters(matrix, threshold=0.92)
            for cluster in clusters:
                # Keeper rule: max(cluster, key=(-mtime, len(body))) — older wins
                # We don't have mtime from Obsidian REST, so fall back to:
                # keeper = the longest body in the cluster (older proxy unavailable).
                keeper_idx = max(
                    cluster, key=lambda i: len(survivors[i][2])
                )
                for i in cluster:
                    if i == keeper_idx:
                        continue
                    src = survivors[i][0]
                    conf = float(survivors[i][3].confidence)
                    keeper_path = survivors[keeper_idx][0]
                    if dry_run:
                        today = _today_str()
                        proposed = f"_trash/{today}/{src.rsplit('/', 1)[-1]}"
                        report.proposed_moves.append({
                            "kind": "trash",
                            "src": src,
                            "dst": proposed,
                            "reason": f"duplicate of {keeper_path} (cosine≥0.92, conf={conf:.1f})",
                        })
                        report.duplicates_moved += 1
                        continue
                    try:
                        dst = await client.move_to_trash(
                            src,
                            reason=f"duplicate of {keeper_path}",
                            sweep_at=sweep_id,
                        )
                        moves.append((src, dst, f"duplicate (cosine≥0.92, conf={conf:.1f})"))
                        report.duplicates_moved += 1
                    except Exception as exc:
                        report.errors.append(f"trash {src}: {exc}")

        # 5. Per-sweep log — never written in dry-run
        if not dry_run and (moves or report.noise_moved):
            log_path = f"ops/sweeps/{_today_str()}.md"
            log_lines = [f"\n## Sweep {sweep_id}\n"]
            for src, dst, reason in moves:
                log_lines.append(f"- `{src}` → `{dst}` — {reason}\n")
            log_lines.append(
                f"\nProcessed: {report.files_processed}/{report.files_total}; "
                f"noise: {report.noise_moved}; duplicates: {report.duplicates_moved}\n"
            )
            log_block = "".join(log_lines)
            try:
                existing = await client.read_note(log_path)
                if existing:
                    await client.patch_append(log_path, log_block)
                else:
                    await client.write_note(
                        log_path, f"# Sweep log {_today_str()}\n{log_block}"
                    )
            except Exception as exc:
                logger.warning("sweep log write failed: %s", exc)
                report.errors.append(f"log: {exc}")

        report.status = "complete"
        return report
    except SweepInProgressError:
        report.status = "blocked"
        raise
    except Exception as exc:
        report.status = "error"
        report.errors.append(str(exc))
        raise
    finally:
        await client.release_sweep_lock()


# --- Module-level status (for /vault/sweep/status route) ---

_SWEEP_STATUS: dict[str, object] = {
    "sweep_id": None,
    "status": "idle",
    "files_processed": 0,
    "files_total": 0,
    "duplicates_moved": 0,
    "noise_moved": 0,
}


def get_status() -> dict:
    return dict(_SWEEP_STATUS)


def _set_status(report: SweepReport) -> None:
    _SWEEP_STATUS.update(
        sweep_id=report.sweep_id,
        status=report.status,
        files_processed=report.files_processed,
        files_total=report.files_total,
        duplicates_moved=report.duplicates_moved,
        noise_moved=report.noise_moved,
    )


def reset_status_for_tests() -> None:
    _SWEEP_STATUS.update(
        sweep_id=None,
        status="idle",
        files_processed=0,
        files_total=0,
        duplicates_moved=0,
        noise_moved=0,
    )
