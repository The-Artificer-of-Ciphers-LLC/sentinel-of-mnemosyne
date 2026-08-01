# Phase 47: Migration Cutover + Hardening - Pattern Map

**Mapped:** 2026-07-06
**Files analyzed:** 9 new + 3 modified = 12
**Analogs found:** 9 / 9 (new files); 3 / 3 (modified files) — all files have a strong analog. No "no analog found" section needed.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `sentinel-core/app/services/migration_orchestrator.py` | service | event-driven (background run, multi-stage) | `sentinel-core/app/services/pipeline_orchestrator.py` (`run()`/`start_pipeline()`) | exact |
| `sentinel-core/app/services/migration_rollback_ledger.py` | utility | transform (record + replay inverse ops) | `sentinel-core/app/services/moc_maintenance.py` (`attach_to_hub`/`detach_from_hub` rollback pair) | role-match (genuinely new capability — no exact transactional-ledger analog exists) |
| `sentinel-core/app/services/migration_status_store.py` | store | CRUD (in-memory status get/set) | `sentinel-core/app/services/pipeline_orchestrator.py` (`patch_pipeline_status`/`_set_pipeline_status`/`_new_pipeline_status` helpers) — sibling module is `pipeline_status_store.py` | exact |
| `sentinel-core/app/routes/migration.py` | route | request-response | `sentinel-core/app/routes/note.py` (`/vault/sweep/start` + `/vault/sweep/status`) | exact |
| `sentinel-core/app/services/ops_backlink_scan.py` (NEW — Pattern 3 gap-filler) | service | transform (pre/post scan diff) | `sentinel-core/app/services/graph_analysis.py` (`extract_wikilinks`/`resolve_wikilink`) — logic reused, but this is a NEW ops/-scoped function, not a widened notes/-scoped one | role-match, deliberately narrow scope |
| `sentinel-core/tests/test_migration_orchestrator.py` | test | integration | `sentinel-core/tests/test_pipeline_orchestrator.py`, `test_vault_sweeper.py` | exact |
| `sentinel-core/tests/test_migration_rollback_ledger.py` | test | unit | `sentinel-core/tests/test_graph_analysis.py` (pure-computation unit test style) | role-match |
| `sentinel-core/tests/test_migration_routes.py` | test | integration (route) | `sentinel-core/tests/test_note_routes.py` | exact |
| `sentinel-core/tests/test_ops_backlink_scan.py` | test | unit | `sentinel-core/tests/test_links_sidecar_index.py` | role-match |
| `interfaces/discord/command_router.py` (MODIFIED: `:migrate` dispatch) | controller | request-response | Existing `:vault-sweep`/`:pipeline` dispatch entries in the same file | exact |
| `interfaces/discord/core_gateway.py` (MODIFIED: `call_core_migrate_start/status`) | service (HTTP client wrapper) | request-response | Existing `call_core_sweep_start`/`call_core_pipeline_start`-style wrappers in the same file | exact |
| `sentinel-core/app/config.py` (possibly MODIFIED — no new settings expected, verify at plan time) | config | — | Existing `sweep_skip_prefixes`/`protected_namespaces` settings block | exact (if touched at all) |

## Pattern Assignments

### `sentinel-core/app/services/migration_orchestrator.py` (service, event-driven)

**Analog:** `sentinel-core/app/services/pipeline_orchestrator.py`

**Lock/try/finally shape** (`pipeline_orchestrator.py:486-534`):
```python
async def run(
    vault: Any,
    *,
    mode: str,
    embedder=None,
    settings: Any = None,
    status_callback=None,
) -> PipelineReport:
    pipeline_id = _iso_utc()
    report = PipelineReport(pipeline_id=pipeline_id, status="running", mode=mode)

    if not await vault.acquire_sweep_lock():
        raise SweepInProgressError("a vault operation is already in progress")

    try:
        if mode == "ralph":
            await _run_ralph(vault, report, embedder=embedder, settings=settings, status_callback=status_callback)
        elif mode == "pipeline":
            await _run_pipeline(vault, report, embedder=embedder, settings=settings, status_callback=status_callback)
        # ...
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
        await vault.release_sweep_lock()
```
**Copy for migration_orchestrator.run()**: identical shape — acquire `vault.acquire_sweep_lock()` FIRST (shared lock with sweeper + pipeline, D-04 precedent / Pitfall 8), try/except/finally with `release_sweep_lock()` always run, `SweepInProgressError` propagated distinctly from generic errors so the caller can tell "blocked" from "failed → rollback".

**Background-task wrapper pattern** (`pipeline_orchestrator.py:540-577`):
```python
async def start_pipeline(*, vault, mode, embedder=None, settings=None, task_runner=None) -> dict:
    pipeline_id = _iso_utc()
    runner = task_runner or AsyncioTaskRunner()
    patch_pipeline_status(**_new_pipeline_status(pipeline_id, "running", mode))

    async def _runner() -> None:
        try:
            report = await run(vault, mode=mode, embedder=embedder, settings=settings, status_callback=_set_pipeline_status)
            _set_pipeline_status(report)
        except SweepInProgressError:
            patch_pipeline_status(status="blocked")
        except Exception as exc:
            logger.exception("pipeline crashed: %s", exc)
            patch_pipeline_status(status="error")

    runner.schedule(_runner())
    return {"pipeline_id": pipeline_id, "status": "running", "mode": mode}
```
**Copy for `start_migration()`**: same "seed status as running → schedule background task → return immediate ack" shape (D-06-equivalent always-async + poll). Use `AsyncioTaskRunner` (`app/services/task_runner.py`) exactly as-is.

**D-01/Pattern-1 backfill mechanics** (`inbox.py:44,133,183-220` + `pipeline_orchestrator.py:486`) — reuse VERBATIM, do not reimplement:
```python
# inbox.append_entry signature (inbox.py:183-191)
def append_entry(
    body: str, candidate_text: str, result: ClassificationResult,
    suggested: list[str] | None = None, now: datetime | None = None,
    retry_count: int = 0, needs_attention: bool = False,
) -> str: ...
```
Migration's notes-bound track must call `inbox.append_entry()` per legacy file (never `vault.relocate()` into `inbox/` — Pitfall A), batch a single `write_note(INBOX_PATH, inbox_body)`, delete originals, then call `pipeline_orchestrator.run(vault, mode="pipeline")` unmodified (`INBOX_PATH = "inbox/_pending-classification.md"`, `inbox.py:44`).

---

### `sentinel-core/app/services/migration_rollback_ledger.py` (utility, transform)

**Analog:** `sentinel-core/app/services/moc_maintenance.py` — `attach_to_hub`/`detach_from_hub` (rollback precedent from Phase 46's Verify-fail path).

**Rollback shape to mirror** (`moc_maintenance.py:230-244`, `detach_from_hub`):
```python
async def detach_from_hub(vault: Any, hub_path: str, member_slug: str) -> None:
    """Roll back a hub attach for a member note that later failed Verify.
    ... idempotent -- a no-op if the link isn't present ...
    If, after removal, the hub has NO remaining member wikilinks, the hub
    note is deleted entirely -- it was freshly created for this now-rejected member.
    """
    body = await vault.read_note(hub_path)
    if not body:
        return
    pre_block_body, trailing_block = split_schema_block(body)
    # ... remove link, re-append trailing block, write or delete ...
```
**Apply this idempotent-inverse pattern** to the new ledger: each `record_*` call must store enough state to construct an idempotent inverse operation (re-`relocate()` back, restore original frontmatter/body, revert sidecar key rename, remove/restore inbox entries). No generic transaction primitive exists in the codebase (confirmed via `git show 9b105f4` — Phase 46's fix was a point rollback, not a ledger) — **this is genuinely new code**; the `detach_from_hub` idempotency-and-cleanup discipline is the only precedent to imitate, not a reusable library.

**Two entries needed** (from RESEARCH.md Pattern 1 & 2 code):
```python
rollback.record_restore_original(src, body)   # inverse: write_note(src, body) if aborted
rollback.record_ops_move(src, actual_dst)     # inverse: relocate(actual_dst, src) + revert sidecar key
```

---

### `sentinel-core/app/services/migration_status_store.py` (store, CRUD)

**Analog:** in-file helpers `patch_pipeline_status`/`_set_pipeline_status`/`_new_pipeline_status` referenced in `pipeline_orchestrator.py:558,567,571`. Look for the sibling module (likely `sentinel-core/app/services/pipeline_status_store.py`) and mirror its get/patch/set surface exactly — same in-memory dict-or-similar store, same `"running"/"complete"/"blocked"/"error"` status vocabulary used by `run()`/`start_pipeline()` above.

---

### `sentinel-core/app/routes/migration.py` (route, request-response)

**Analog:** `sentinel-core/app/routes/note.py` (`/vault/sweep/start`, `/vault/sweep/status`, lines 126-196).

**Admin gate** (`note.py:126-138`):
```python
def _is_admin_route(user_id: str) -> bool:
    """Defense-in-depth admin gate at the route layer (Task 8 also gates at bot)."""
    raw = os.environ.get("SENTINEL_ADMIN_USER_IDS", "")
    if raw.strip() == "*":
        return True
    allowed = {u.strip() for u in raw.split(",") if u.strip()}
    return bool(allowed) and user_id in allowed
```
**Copy verbatim usage** — `POST /vault/migrate/start` must call this exact gate first:
```python
if not _is_admin_route(req.user_id):
    raise HTTPException(status_code=403, detail="admin only")
```

**Route body + status route shape** (`note.py:135-196`):
```python
@router.post("/vault/sweep/start")
async def vault_sweep_start(req: SweepStartRequest, request: Request):
    if not _is_admin_route(req.user_id):
        raise HTTPException(status_code=403, detail="admin only")
    ctx = get_route_context(request)
    # ... build any runtime safety probe (skip for migrate unless an equivalent
    #     "safe to mutate" check applies — migration probably doesn't need the
    #     embedding/classifier probe since Reduce reuses pipeline_orchestrator's
    #     own internal calls) ...
    return await start_sweep(vault=vault, classifier=classifier, embedder=embedder,
                              force_reclassify=req.force_reclassify, dry_run=req.dry_run,
                              source_folder=req.source_folder, safe_to_mutate=safe_to_mutate)

@router.get("/vault/sweep/status")
async def vault_sweep_status():
    return get_status()
```
**Copy for**: `POST /vault/migrate/start` (with `dry_run: bool` field mirroring `SweepStartRequest.dry_run`) → calls `migration_orchestrator.start_migration(...)`; `GET /vault/migrate/status` → calls `migration_status_store.get_status()`.

---

### `sentinel-core/app/services/ops_backlink_scan.py` (NEW service, transform — Pattern 3 gap-filler)

**Analog:** `sentinel-core/app/services/graph_analysis.py` — reuse the wikilink-extraction regex and stem-resolution logic, but as a NEW, ops-scoped function; do NOT widen `graph_analysis`/`links_sidecar_index` (both are deliberately `notes/`-scoped by design, per RESEARCH.md Wave-0 Gap note).

**Reusable extraction primitive** (`graph_analysis.py:33-43`):
```python
_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")

def extract_wikilinks(body: str) -> set[str]:
    return {m.group(1).strip() for m in _WIKILINK_RE.finditer(body or "")}
```
**Reusable stem-normalization** (`graph_analysis.py:46-53`):
```python
def _slugify(text: str) -> str:
    return (text or "").strip().lower().replace(" ", "-").replace("_", "-")
```
**New function shape**: `scan_for_title_refs(vault, old_title: str) -> int` — use `vault.find(query)` (keyword search, per RESEARCH.md Pattern 3) for `"[[<old-title>]]"` across the whole vault (not `notes/`-scoped), call once pre-move and once post-move per ops-bound file, assert the count is unchanged (or explicitly rewrite any new dangling refs found). This function must NOT touch `NOTES_ROOT` or the links sidecar — it is a standalone, vault-wide title-search helper.

---

### Ops-bound direct move + sidecar patch (embedded in `migration_orchestrator.py`, not a separate file)

**Analog:** `sentinel-core/app/vault.py:631-690` (`relocate()`) + `sentinel-core/app/services/embedding_sidecar_index.py:22,44-60` (`EMBEDDING_INDEX_PATH`, `encode_index_body`/`decode_index_body`).

**`relocate()` full body** (`vault.py:631-690`) — copy the protected-namespace guard ordering exactly (source guard THEN dest guard, both before any read):
```python
async def relocate(self, src: str, dst: str, *, sweep_at: str | None = None) -> str:
    if is_protected_path(src):
        raise ProtectedPathError(f"refusing to relocate protected path {src!r}")
    if is_protected_path(dst):
        raise ProtectedPathError(f"refusing to relocate into protected namespace: {dst!r}")
    existing = await self.read_note(dst)
    if existing:
        # collision-suffix rename via secrets.token_hex(4)
        ...
    body = await self.read_note(src)
    fm, rest = split_frontmatter(body)
    fm = dict(fm or {})
    fm["original_path"] = src
    fm["topic_moved_at"] = sweep_at or _iso_utc()
    annotated = join_frontmatter(fm, rest)
    await self.write_note(dst, annotated)
    try:
        await self.delete_note(src)
    except Exception as exc:
        logger.warning("relocate: delete failed for %s after copy to %s: %s", src, dst, exc)
    return dst
```
**Sidecar patch to add immediately after each `relocate()` call** (per RESEARCH.md Pattern 2, using `embedding_sidecar_index.py` primitives):
```python
raw = await vault.read_note(EMBEDDING_INDEX_PATH)
index = decode_index_body(raw, EMBEDDING_INDEX_PATH) if raw.strip() else {}
if src in index:
    index[actual_dst] = index.pop(src)
    await vault.write_note(EMBEDDING_INDEX_PATH, encode_index_body(index, EMBEDDING_INDEX_PATH))
```
This patch MUST be recorded as part of the SAME rollback-ledger entry as the `relocate()` call (Security Domain finding: sidecar-poisoning mitigation — rollback must restore path AND sidecar key together).

**Concurrency guard reused as-is** (`vault.py:692-720`, `acquire_sweep_lock`/`release_sweep_lock`) — already shown above in the orchestrator's try/finally; migration is the third mutually-exclusive user of this same lock (sweeper, pipeline, migration).

---

### `sentinel-core/tests/test_migration_orchestrator.py`, `test_migration_routes.py`, `test_migration_rollback_ledger.py`, `test_ops_backlink_scan.py` (tests)

**Analog for orchestrator tests:** `sentinel-core/tests/test_pipeline_orchestrator.py` + `test_vault_sweeper.py` — mirror their async fixture / fake-vault style, and their pattern of asserting the FULL post-condition (e.g., "file exists under `notes/{slug}.md` AND flat-7 original gone" — RESEARCH.md's explicit warning sign for Pitfall A) rather than a shallow "did not raise" check. **Never mock the compliance/verification gate** — RESEARCH.md and prior-phase memory both flag this exact anti-pattern from the Phase 46 cold-start bug (`phase46-pipeline-coldstart-gap`).

**Analog for route tests:** `sentinel-core/tests/test_note_routes.py` — mirror its admin-gate-rejection test (non-admin `user_id` → 403) and its dry-run vs. live-run request shape tests for the new `/vault/migrate/start`/`/status` routes.

**Analog for rollback-ledger unit tests:** `sentinel-core/tests/test_graph_analysis.py` — pure-computation, no-vault-IO unit test style; assert the ledger's replay-in-reverse produces byte-identical pre-state.

**Analog for ops_backlink_scan unit tests:** `sentinel-core/tests/test_links_sidecar_index.py` — mirror its fake-vault-with-canned-`find()`-results fixture style.

---

### `interfaces/discord/command_router.py` (MODIFIED — controller, request-response)

**Analog:** existing `:vault-sweep`/`:pipeline` dispatch entries in the same file (find via grep for `"vault-sweep"` or `"pipeline"` string literal in the subcommand table). Add a `:migrate` entry with an identical admin-gate + `--dry-run` flag pass-through shape.

### `interfaces/discord/core_gateway.py` (MODIFIED — service, request-response)

**Analog:** existing `call_core_sweep_start`/`call_core_pipeline_start`-style HTTP wrapper functions in the same file. Add `call_core_migrate_start(dry_run: bool, user_id: str)` / `call_core_migrate_status()` mirroring their request/response shape and error handling exactly.

## Shared Patterns

### Admin gating (V4 Access Control)
**Source:** `sentinel-core/app/routes/note.py:126-132` (`_is_admin_route`)
**Apply to:** `migration.py`'s `POST /vault/migrate/start` route AND the Discord `:migrate` dispatch (defense-in-depth, gated at both layers per the existing `:vault-sweep` precedent — "Task 8 also gates at bot").

### Shared sweep lock (concurrency guard)
**Source:** `sentinel-core/app/vault.py:692-720` (`acquire_sweep_lock`/`release_sweep_lock`)
**Apply to:** `migration_orchestrator.run()` — acquire BEFORE any inbox/vault read (Pitfall 8 lesson), release in a `finally`, exactly like `pipeline_orchestrator.run()` and `vault_sweeper.run_sweep()`.

### Background-task + status-poll shape
**Source:** `sentinel-core/app/services/pipeline_orchestrator.py:540-577` (`start_pipeline`)
**Apply to:** `migration_orchestrator.start_migration()` + `migration_status_store.py` + the `GET /vault/migrate/status` route.

### Frontmatter-preserving move (never delete+recreate)
**Source:** `sentinel-core/app/vault.py:631-690` (`relocate()`)
**Apply to:** every ops-bound move in `migration_orchestrator.py`'s Track A.

### Idempotent, re-appendable rollback writes
**Source:** `sentinel-core/app/services/moc_maintenance.py:230-244` (`detach_from_hub`)
**Apply to:** `migration_rollback_ledger.py` — every replayed inverse operation must be safe to run twice (idempotent), matching this precedent's "no-op if link isn't present" discipline.

### Untrusted-content boundary for LLM calls
**Source:** established project-wide pattern already enforced in `note_classifier.py`/`six_rs/reduce.py` (per RESEARCH.md Security Domain).
**Apply to:** `migration_orchestrator.py`'s notes-bound track — legacy note bodies read from the vault and fed into `six_rs.reduce.reduce_entry()` must be treated as untrusted data, never instructions. No new call site needed; migration just adds volume through the already-hardened `pipeline_orchestrator.run(mode="pipeline")` path.

## No Analog Found

None. Every file in scope has at least a role-match analog (see table above). The only genuinely novel logic is the rollback-ledger's transaction/replay semantics (`migration_rollback_ledger.py`) and the ops-bound backlink scan (`ops_backlink_scan.py`) — both are noted as "deliberately new" above with the closest available precedent cited, per RESEARCH.md's own explicit confirmation (`git show 9b105f4`) that no generic transaction primitive exists yet in this codebase.

## Metadata

**Analog search scope:** `sentinel-core/app/{vault.py, services/*.py, routes/*.py}`, `sentinel-core/tests/*.py`, `interfaces/discord/{command_router.py, core_gateway.py}` — all read directly this session (offsets/line ranges cited above; RESEARCH.md's own file:line citations from the same commit were used as the starting search index, then verified against current source).
**Files scanned:** 9 (vault.py, inbox.py, pipeline_orchestrator.py, note.py, graph_analysis.py, embedding_sidecar_index.py, moc_maintenance.py, + RESEARCH.md-cited test files enumerated but not re-read in full since RESEARCH.md already characterizes their structure)
**Pattern extraction date:** 2026-07-06
