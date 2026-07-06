# Phase 46: 6 Rs Pipeline Orchestrator - Pattern Map

**Mapped:** 2026-07-06
**Files analyzed:** 13 (5 new services + 5 six_rs modules counted as 1 template + 1 route + 1 inbox modification + 3 discord files + tests)
**Analogs found:** 13 / 13

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `sentinel-core/app/services/pipeline_orchestrator.py` | service (background orchestrator) | batch / event-driven | `sentinel-core/app/services/vault_sweeper.py` (`run_sweep`, `:412-750`) | exact |
| `sentinel-core/app/services/pipeline_status_store.py` | store (in-memory) | CRUD (get/set) | `sentinel-core/app/services/sweep_status_store.py` (whole file, 43 lines) | exact |
| `sentinel-core/app/services/pipeline_runner.py` (optional split) | service (background-task wrapper) | event-driven | `sentinel-core/app/services/note_sweep_runner.py` (`start_sweep`, `:33-151`) | exact |
| `sentinel-core/app/services/six_rs/reduce.py` | service (structured LLM completion) | transform / request-response | `sentinel-core/app/services/note_classifier.py` (`_resolve_model_for_classification` `:190-246`, `classify_note` `:249+`) | exact |
| `sentinel-core/app/services/six_rs/reflect.py` | service (embedding lookup + write) | transform | `sentinel-core/app/services/moc_maintenance.py` (`find_hub_candidate` `:83-118`, `attach_to_hub` `:153-178`) | exact |
| `sentinel-core/app/services/six_rs/reweave.py` | service (append-only mutation) | transform / file-I/O | `moc_maintenance.attach_to_hub` (idempotent append shape) + `note_classifier` (LLM call shape) | role-match |
| `sentinel-core/app/services/six_rs/verify.py` | service (validation) | transform | `sentinel-core/app/services/note_schema.py` (`check_note_compliance` `:121-154`) | exact |
| `sentinel-core/app/services/six_rs/rethink.py` | service (triage LLM) | transform | `note_classifier.py` (structured-completion template) | role-match |
| `sentinel-core/app/routes/pipeline.py` | route (admin-gated background-task trigger) | request-response | `sentinel-core/app/routes/note.py` (`/vault/sweep/start`, `/vault/sweep/status`, `:108-196`) | exact |
| `sentinel-core/app/services/inbox.py` (MODIFIED — add `retry_count`) | model/utility (pure parse/render) | CRUD | itself (existing `PendingEntry`, `_parse_entry_section`, `_render_entry`, `append_entry`) | exact (self-extension) |
| `interfaces/discord/command_router.py` (MODIFIED) | route/dispatcher | request-response | itself — existing `vault-sweep` branch (`:144-153`) | exact |
| `interfaces/discord/core_gateway.py` (MODIFIED — add `call_core_pipeline_start/status`) | service (HTTP client wrapper) | request-response | itself — `call_core_sweep_start`/`call_core_sweep_status` (`:78-115`) | exact |
| `interfaces/discord/bot.py` (MODIFIED — remove dead prompts, add wrappers) | wiring/config | request-response | itself — `_call_core_sweep_start`/`_call_core_sweep_status` (`:259-275`) + `_SUBCOMMAND_PROMPTS` (`:175-188`) + kwargs dict (`:544-570`) | exact |
| `sentinel-core/tests/test_pipeline_orchestrator.py`, `tests/test_six_rs_*.py` | test | — | `sentinel-core/tests/test_note_sweep_runner.py` (`:1-60`) + `tests/fakes/vault.py` (`FakeVault`, `:28-203`) | exact |

## Pattern Assignments

### `sentinel-core/app/services/pipeline_orchestrator.py` (service, batch/event-driven)

**Analog:** `sentinel-core/app/services/vault_sweeper.py`

**Imports pattern** (from `vault_sweeper.py` top, mirrored):
```python
from __future__ import annotations
from typing import Awaitable, Callable
from pydantic import BaseModel, Field
from app.errors import SweepInProgressError
from app.services.sweep_status_store import ...  # → pipeline_status_store equivalent
```

**Lock acquisition + fail-closed try/finally shape** (`vault_sweeper.py:480-483, 740-750`):
```python
if not await client.acquire_sweep_lock():
    raise SweepInProgressError("a sweep is already running")
try:
    # ... walk / process ...
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
```
Per D-04, `pipeline_orchestrator.run()` reuses this EXACT lock (no new lockfile) — the error message string should read something like `"a vault operation is already in progress"` (D-04a) while still raising the same `SweepInProgressError` type (message communicates which op, not the exception class).

**Report model pattern** (`vault_sweeper.py:132-143`, clone as `PipelineReport`):
```python
class SweepReport(BaseModel):
    sweep_id: str
    status: str = "complete"  # idle | running | complete | error
    files_processed: int = 0
    files_total: int = 0
    duplicates_moved: int = 0
    noise_moved: int = 0
    topic_moves: int = 0
    errors: list[str] = Field(default_factory=list)
    proposed_moves: list[dict] = Field(default_factory=list)
```
Per D-03a, `PipelineReport` needs analogous per-phase counts instead (`entries_total`, `entries_processed`, `reduced`, `hubs_touched`, `reweave_edits`, `verify_failed`, `verify_requeued`, `status`, `mode`, `errors: list[str]`).

**Per-move error accumulation pattern** (repeated throughout `vault_sweeper.py`, e.g. `:287,377,521,559,582,618,650,713,715`):
```python
report.errors.append(f"topic_move {path}: {exc}")
```
Apply the same per-entry, per-phase granular error-string convention in the orchestrator loop (never let one entry's exception abort the whole run — catch per-entry, append to `report.errors`, continue).

**Status wrapper pattern** (`vault_sweeper.py:756-765`):
```python
def get_status() -> dict:
    return get_sweep_status()

def _set_status(report: SweepReport) -> None:
    set_sweep_status_from_report(report)

def reset_status_for_tests() -> None:
    reset_sweep_status()
```

**Function signature to mirror** (`vault_sweeper.py:412-421`):
```python
async def run_sweep(
    client, classifier, embedder, *,
    force_reclassify: bool = False,
    status_callback: Callable[[SweepReport], None] | None = None,
    dry_run: bool = False,
    source_folder: str = "",
    safe_to_mutate: "Callable[[], Awaitable[bool]] | None" = None,
) -> SweepReport: ...
```
`pipeline_orchestrator.run(vault, *, mode: str, status_callback=None, ...) -> PipelineReport` — `mode` replaces sweep's booleans/`source_folder` as the primary branch discriminator (ralph/pipeline/reweave/rethink).

---

### `sentinel-core/app/services/pipeline_status_store.py` (store, CRUD)

**Analog:** `sentinel-core/app/services/sweep_status_store.py` (whole file — copy near-verbatim)

```python
"""Operational sweep status store."""
from __future__ import annotations

_SWEEP_STATUS: dict[str, object] = {
    "sweep_id": None,
    "status": "idle",
    "files_processed": 0,
    "files_total": 0,
    "duplicates_moved": 0,
    "noise_moved": 0,
}

def get_sweep_status() -> dict:
    return dict(_SWEEP_STATUS)

def set_sweep_status_from_report(report) -> None:
    _SWEEP_STATUS.update(
        sweep_id=report.sweep_id, status=report.status,
        files_processed=report.files_processed, files_total=report.files_total,
        duplicates_moved=report.duplicates_moved, noise_moved=report.noise_moved,
    )

def patch_sweep_status(**kwargs) -> None:
    _SWEEP_STATUS.update(kwargs)

def reset_sweep_status() -> None:
    _SWEEP_STATUS.update(sweep_id=None, status="idle", files_processed=0,
                          files_total=0, duplicates_moved=0, noise_moved=0)
```
Rename to `_PIPELINE_STATUS` / `get_pipeline_status` / `set_pipeline_status_from_report` / `patch_pipeline_status` / `reset_pipeline_status`, with the `PipelineReport` field set (add `mode`, per-phase counts) substituted for the sweep fields. Do NOT unify into one generic store (RESEARCH explicitly recommends against; YAGNI).

---

### `sentinel-core/app/services/pipeline_runner.py` (or folded into orchestrator) — background-task wrapper

**Analog:** `sentinel-core/app/services/note_sweep_runner.py`

**Imports** (`note_sweep_runner.py:1-14`):
```python
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable
from app.errors import SweepInProgressError
from app.services.sweep_status_store import patch_sweep_status
from app.services.task_runner import AsyncioTaskRunner, TaskRunner
from app.services.vault_sweeper import _set_status, get_status, run_sweep
```

**Core `start_sweep` → `start_pipeline` template** (`note_sweep_runner.py:130-151`, this is the exact non-dry-run branch to clone; the dry-run branch is NOT needed for pipeline per D-03):
```python
async def start_pipeline(*, vault, mode: str, task_runner: TaskRunner | None = None) -> dict:
    pipeline_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    runner = task_runner or AsyncioTaskRunner()
    _set_pipeline_status(_new_status(pipeline_id, "running", mode))

    async def _runner():
        try:
            report = await pipeline_orchestrator.run(vault, mode=mode, status_callback=_set_pipeline_status)
            _set_pipeline_status(report)
        except SweepInProgressError:
            get_pipeline_status()["status"] = "blocked"
        except Exception as exc:
            logger.exception("pipeline crashed: %s", exc)
            get_pipeline_status()["status"] = "error"

    runner.schedule(_runner())
    return {"pipeline_id": pipeline_id, "status": "running", "mode": mode}
```
(RESEARCH.md's Pattern 2 section gives this exact snippet, verified against source.)

**Task-runner seam** (`sentinel-core/app/services/task_runner.py`, whole file, 16 lines):
```python
class TaskRunner(Protocol):
    def schedule(self, coro: Awaitable[object]) -> object: ...

class AsyncioTaskRunner:
    def schedule(self, coro: Awaitable[object]) -> object:
        return asyncio.create_task(coro)
```

---

### `sentinel-core/app/services/six_rs/reduce.py`, `reweave.py`, `verify.py` (claim-title assist), `rethink.py` (structured LLM completion, transform)

**Analog:** `sentinel-core/app/services/note_classifier.py`

**Model-resolution pattern to promote to a shared helper** (`note_classifier.py:190-246`, RESEARCH A2 recommends extracting this to e.g. `app/services/model_resolution.py` rather than duplicating 5x):
```python
async def _resolve_model_for_classification() -> tuple[str, object | None, str | None]:
    api_base = settings.lmstudio_base_url or "http://host.docker.internal:52415"
    api_base_v1 = f"{api_base.rstrip('/')}/v1" if not api_base.rstrip("/").endswith("/v1") else api_base
    try:
        loaded = await get_loaded_models(api_base_v1)
    except Exception as exc:
        logger.warning("...: get_loaded_models failed: %s", exc)
        loaded = []
    preferences: dict[str, str] = {}
    preferred = settings.model_preferred or settings.model_name
    if preferred:
        preferences["structured"] = preferred
    try:
        model_id = select_model("structured", loaded, preferences=preferences,
                                 default=settings.model_name or None)
    except Exception as exc:
        logger.warning("select_model failed (%s); falling back to configured MODEL_NAME", exc)
        model_id = settings.model_name or "openai/local-model"
    prefixed_model_id = ensure_litellm_prefix(model_id)
    bare_model_id = strip_litellm_prefix(prefixed_model_id)
    try:
        profile = await get_profile(bare_model_id, api_base=api_base)
    except Exception as exc:
        logger.warning("get_profile failed (%s); using None", exc)
        profile = None
    return prefixed_model_id, profile, api_base
```

**Structured JSON-mode completion call shape** (adapted per RESEARCH.md Code Examples, `reduce_entry` template, verified pattern from `classify_note`):
```python
class ReduceResult(BaseModel):
    claim_title: str
    body: str
    schema_type: str

async def reduce_entry(entry_text: str) -> ReduceResult:
    model_id, profile, api_base = await _resolve_model_for_classification()
    response = await acompletion_with_profile(
        model=model_id,
        messages=[
            {"role": "system", "content": _REDUCE_SYSTEM_PROMPT},
            {"role": "user", "content": entry_text},
        ],
        profile=profile, api_base=api_base, api_key="lmstudio",
        response_format={"type": "json_schema", "json_schema": _REDUCE_SCHEMA},
        temperature=0.0,
    )
    # extract content OR reasoning_content fallback (Qwen3 thinking-mode / LM Studio bug #1773)
    return ReduceResult.model_validate(parsed)
```

**Error-coercion pattern** (`note_classifier.classify_note`'s discipline — coerce to `unsure`/safe-default on any parse failure, never raise up into the orchestrator loop): every `six_rs/*` completion call must catch JSON-parse/schema-validation errors internally and return a safe/neutral result (mirrors `_coerce_topic`, `note_classifier.py:139-143`) so a single bad LLM output doesn't crash `pipeline_orchestrator.run()`.

**Six_rs/verify.py — pure-Python reuse, no re-implementation** (`note_schema.py:121-154`, `check_note_compliance`):
```python
def check_note_compliance(body: str, filename_slug: str) -> dict:
    result = {"has_schema": False, "has_type": False, "has_claim_title": False,
              "has_wikilink": False, "failures": []}
    try:
        schema = parse_schema_block(body)
        result["has_schema"] = schema is not None
        if not result["has_schema"]:
            result["failures"].append("missing _schema block")
        result["has_type"] = schema is not None and "type" in schema
        if result["has_schema"] and not result["has_type"]:
            result["failures"].append("missing type key in _schema block")
        result["has_claim_title"] = has_claim_title(body, filename_slug)
        if not result["has_claim_title"]:
            result["failures"].append("missing claim-style title")
        result["has_wikilink"] = has_wikilink(body)
        if not result["has_wikilink"]:
            result["failures"].append("missing wikilink")
    except Exception as exc:
        result["failures"].append(f"compliance check error: {exc}")
    return result
```
`six_rs/verify.py` calls this directly; per D-02a it only ADDS the optional claim-title NL assist on top — it must not re-implement `has_schema`/`has_wikilink` checks.

---

### `sentinel-core/app/services/six_rs/reflect.py` (embedding-first hub lookup + attach)

**Analog:** `sentinel-core/app/services/moc_maintenance.py`

**Embedding-first lookup, no fresh cosine implementation** (`moc_maintenance.py:83-118`):
```python
def find_hub_candidate(*, note_vector, hub_paths: set[str], index: dict, active_model: str) -> str | None:
    entries, _matched_model_count = eligible_entries(
        index, active_model=active_model, exclude_prefixes=(), query_dim=len(note_vector),
    )
    best_path: str | None = None
    best_sim = HUB_COSINE_FLOOR
    for entry in entries:
        if entry.path not in hub_paths:
            continue
        sim = float(cosine_similarity(note_vector, entry.vector))
        if sim >= best_sim:
            best_path, best_sim = entry.path, sim
    return best_path
```

**Idempotent append-under-marker write** (`moc_maintenance.py:136-178`, `attach_to_hub` — the exact D-01/D-03d idempotency precedent Reweave must also follow):
```python
def _insert_member_wikilink(pre_block_body: str, wikilink: str) -> str:
    if wikilink in pre_block_body:
        return pre_block_body  # idempotent: no duplicate insert
    stripped = pre_block_body.rstrip("\n")
    if HUB_MEMBER_MARKER not in stripped:
        stripped = f"{stripped}\n\n{HUB_MEMBER_MARKER}" if stripped else HUB_MEMBER_MARKER
    return f"{stripped}\n- {wikilink}\n"

async def attach_to_hub(vault, hub_path: str, member_slug: str) -> None:
    body = await vault.read_note(hub_path)
    pre_block_body, trailing_block = split_schema_block(body)
    wikilink = f"[[{_slug_to_display(member_slug)}]]"
    updated_pre_block = _insert_member_wikilink(pre_block_body, wikilink)
    merged = updated_pre_block if updated_pre_block.endswith("\n") else f"{updated_pre_block}\n"
    if trailing_block:
        if not merged.endswith("\n\n"):
            merged = f"{merged.rstrip(chr(10))}\n\n"
        merged = merged + trailing_block + "\n"
    await vault.write_note(hub_path, merged)
```
**Apply this exact shape to `six_rs/reweave.py`**: check for a `## Reweave — {date}` marker already present in the note body before appending (dedupe by dated section marker, D-01) — never call `vault.patch_append`; always full-body `read_note` → merge → single `write_note` (transaction-less REST vault constraint).

---

### `sentinel-core/app/routes/pipeline.py` (route, request-response, admin-gated)

**Analog:** `sentinel-core/app/routes/note.py:108-196`

**Admin gate helper** (`note.py:126-132`) — RESEARCH Open Question 3 recommends IMPORTING this, not duplicating:
```python
def _is_admin_route(user_id: str) -> bool:
    raw = os.environ.get("SENTINEL_ADMIN_USER_IDS", "")
    if raw.strip() == "*":
        return True
    allowed = {u.strip() for u in raw.split(",") if u.strip()}
    return bool(allowed) and user_id in allowed
```

**Start route** (`note.py:135-190`, `vault_sweep_start` — mirror shape, drop the `safe_to_mutate`/embedder-probe closure since the six_rs completions manage their own failure handling per-entry, not via a single upfront gate — confirm with planner but the shape below is the direct structural template):
```python
class PipelineStartRequest(BaseModel):
    user_id: str
    mode: str  # "ralph" | "pipeline" | "reweave" | "rethink"

@router.post("/vault/pipeline/start")
async def vault_pipeline_start(req: PipelineStartRequest, request: Request):
    if not _is_admin_route(req.user_id):
        raise HTTPException(status_code=403, detail="admin only")
    ctx = get_route_context(request)
    return await start_pipeline(vault=ctx.vault, mode=req.mode)

@router.get("/vault/pipeline/status")
async def vault_pipeline_status():
    return get_pipeline_status()
```
(Status route is ungated — matches `vault_sweep_status` at `note.py:193-195`, no admin check.)

---

### `sentinel-core/app/services/inbox.py` (MODIFIED — add `retry_count`)

**Analog:** itself. Modify these four existing functions in place (all four are pure, I/O-free — RESEARCH Pattern 5).

**`PendingEntry` model to extend** (`inbox.py:47-56`):
```python
class PendingEntry(BaseModel):
    entry_n: int
    timestamp: str = ""
    topic: str = "unsure"
    suggested: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    reasoning: str = ""
    candidate_text: str = ""
    # ADD: retry_count: int = 0
    # ADD: needs_attention: bool = False  (or similar, per D-02b)
```

**`_parse_entry_section` field-read pattern to mirror for `retry_count`** (`inbox.py:98-118`, exactly how `confidence` is parsed with a safe int/float coercion):
```python
try:
    confidence = float(fields.get("confidence", "0") or 0)
except ValueError:
    confidence = 0.0
# mirror this for retry_count:
# try:
#     retry_count = int(fields.get("retry_count", "0") or 0)
# except ValueError:
#     retry_count = 0
```
`_parse_entry_section` already defaults missing fields gracefully (`fields.get(key, default)`), so existing inbox entries with no `retry_count` line parse to `0` — no migration step needed (RESEARCH "Runtime State Inventory" confirms this).

**`_render_entry` line-emission pattern to extend** (`inbox.py:141-154`):
```python
def _render_entry(e: PendingEntry) -> str:
    suggested = ", ".join(e.suggested)
    quoted = "\n".join(f"> {ln}" if ln else ">" for ln in (e.candidate_text or "").splitlines())
    if not quoted:
        quoted = "> "
    return (
        f"- timestamp: {e.timestamp}\n"
        f"- topic: {e.topic}\n"
        f"- suggested: {suggested}\n"
        f"- confidence: {e.confidence}\n"
        f"- reasoning: {e.reasoning}\n"
        # ADD: f"- retry_count: {e.retry_count}\n"
        f"\n{quoted}\n"
    )
```

**`append_entry` pattern to extend (or add a `requeue_entry` twin)** (`inbox.py:170-198`):
```python
def append_entry(body, candidate_text, result, suggested=None, now=None) -> str:
    if not body or not body.strip():
        body = build_initial_inbox(now)
    fm, _ = split_frontmatter(body)
    if not fm:
        fm = {"type": "pending-classification-inbox"}
    fm["updated"] = _iso_utc(now)
    fm.setdefault("type", "pending-classification-inbox")
    entries = parse_inbox(body)
    next_n = (max((e.entry_n for e in entries), default=0)) + 1
    new_entry = PendingEntry(
        entry_n=next_n, timestamp=_iso_utc(now), topic=result.topic,
        suggested=list(suggested or []), confidence=float(result.confidence),
        reasoning=(result.reasoning or "")[:300], candidate_text=candidate_text or "",
        # ADD retry_count=... when requeuing a Verify-failed entry (increment prior value)
    )
    return _rebuild_body(fm, entries + [new_entry])
```
**Named-constant discipline (D-02b):** define `VERIFY_RETRY_CAP = 2` in `six_rs/verify.py` (or `pipeline_orchestrator.py`) — never a bare magic number at the call site.

---

### `interfaces/discord/command_router.py` (MODIFIED — add 5 explicit branches)

**Analog:** itself, the existing `vault-sweep` branch (`command_router.py:144-153`):
```python
if subcmd == "vault-sweep":
    if not is_admin(user_id):
        return "Admin only. Set SENTINEL_ADMIN_USER_IDS in your env to use this command."
    verb = (args.strip().split(maxsplit=1) or [""])[0]
    if verb == "status":
        return await call_core_sweep_status(user_id)
    if verb == "dry-run":
        return await call_core_sweep_start(user_id, force_reclassify=False, dry_run=True)
    force = verb == "force"
    return await call_core_sweep_start(user_id, force_reclassify=force)
```
New branches for `ralph`/`pipeline`/`reweave`/`rethink`/`refactor` follow this verb-parsing shape (`args.strip().split(maxsplit=1)` to detect `status` vs a start invocation), e.g.:
```python
if subcmd in ("ralph", "pipeline", "reweave", "rethink", "refactor"):
    verb = (args.strip().split(maxsplit=1) or [""])[0]
    mode = {"ralph": "ralph", "pipeline": "pipeline", "reweave": "reweave",
            "rethink": "rethink", "refactor": "rethink"}[subcmd]
    if verb == "status":
        return await call_core_pipeline_status(user_id)
    return await call_core_pipeline_start(user_id, mode=mode)
```
Also add `call_core_pipeline_start` / `call_core_pipeline_status` params to `handle_subcommand()`'s keyword-only signature (currently lists `call_core_sweep_start`, `call_core_sweep_status`, `call_core_graph`, etc. at `:52-56`) — must NOT gate these behind `is_admin` per D-04a (the concurrency message, not an admin check, is the refusal path); confirm against CONTEXT — vault-sweep IS admin-gated but pipeline commands are not called out as admin-only in CONTEXT.md, so mirror the shape but drop the `is_admin` check unless the planner decides otherwise.

**Note:** the tail-end dead-fallback these currently hit (`command_router.py:179-181`) is what gets bypassed once the explicit branches are added — this is the Phase-45-07 "drop dead prompts" precedent repeated.

---

### `interfaces/discord/core_gateway.py` (MODIFIED — add `call_core_pipeline_start/status`)

**Analog:** itself — `call_core_sweep_start` / `call_core_sweep_status` (`core_gateway.py:78-115`):
```python
async def call_core_sweep_start(*, user_id: str, force_reclassify: bool, dry_run: bool, sentinel_client) -> str:
    payload = {"user_id": user_id, "force_reclassify": force_reclassify, "dry_run": dry_run}
    try:
        async with httpx.AsyncClient(timeout=120.0) as http_client:
            data = await sentinel_client.post_to_module("vault/sweep/start", payload, http_client)
    except Exception as exc:
        logger.warning("vault sweep start failed: %s", exc)
        return f"Vault sweep failed to start: {exc}"
    sweep_id = data.get("sweep_id", "?")
    return f"Vault sweep started: `{sweep_id}`. Use `:vault-sweep status` to check progress."

async def call_core_sweep_status(*, user_id: str, core_url: str, api_key: str) -> str:
    try:
        async with httpx.AsyncClient() as http_client:
            resp = await http_client.get(
                f"{core_url.rstrip('/')}/vault/sweep/status",
                headers={"X-Sentinel-Key": api_key}, timeout=20.0,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("vault sweep status failed: %s", exc)
        return f"Vault sweep status fetch failed: {exc}"
    return (f"sweep `{data.get('sweep_id', '-')}`: status={data.get('status', '-')}, "
            f"processed={data.get('files_processed', 0)}/{data.get('files_total', 0)}, "
            f"duplicates_moved={data.get('duplicates_moved', 0)}")
```
`call_core_pipeline_start(*, user_id, mode, sentinel_client)` posts to `vault/pipeline/start` with `{"user_id": user_id, "mode": mode}`, same `timeout=120.0`, same try/except-log-and-return-string shape. `call_core_pipeline_status` mirrors the GET shape exactly, formatting the new `PipelineReport` per-phase counts instead of sweep's `duplicates_moved`.

---

### `interfaces/discord/bot.py` (MODIFIED — remove dead entries, add wrappers)

**Analog:** itself.

**Dead-prompt entries to REMOVE from `_SUBCOMMAND_PROMPTS`** (`bot.py:175-188`, confirmed verbatim):
```python
"ralph": "Process my inbox queue — work through items in inbox/ and move completed ones to notes/ following the 2nd brain pipeline.",
"pipeline": "Run the full 6 Rs pipeline on my inbox queue: Record → Reduce → Reflect → Reweave → Verify → Rethink.",
"reweave": "Run a reweave pass on my vault — identify notes that should be updated given recent additions. Update older notes with new context and connections.",
"rethink": "Review accumulated observations and tensions in ops/observations/ and ops/tensions/. Triage each: PROMOTE, IMPLEMENT, METHODOLOGY, ARCHIVE, or KEEP PENDING.",
"refactor": "Review vault organization and suggest restructuring improvements.",
```
(mirrors Phase 45-07's removal of `graph`/`stats`/`check` dead-prompt entries — same precedent, same file, same dict.)

**Wrapper functions to add** (`bot.py:259-275`, `_call_core_sweep_start`/`_call_core_sweep_status` — exact template):
```python
async def _call_core_sweep_start(user_id: str, force_reclassify: bool = False, dry_run: bool = False) -> str:
    return await core_gateway.call_core_sweep_start(
        user_id=user_id, force_reclassify=force_reclassify, dry_run=dry_run,
        sentinel_client=_sentinel_client,
    )

async def _call_core_sweep_status(user_id: str) -> str:
    return await core_gateway.call_core_sweep_status(
        user_id=user_id, core_url=SENTINEL_CORE_URL, api_key=SENTINEL_API_KEY,
    )
```
Add `_call_core_pipeline_start(user_id: str, mode: str)` / `_call_core_pipeline_status(user_id: str)` following this exact shape.

**kwargs dict wiring** (`bot.py:544-570`, the dict passed into `discord_router_bridge.handle_subcommand`) — add `"call_core_pipeline_start": _call_core_pipeline_start` and `"call_core_pipeline_status": _call_core_pipeline_status` alongside the existing `"call_core_sweep_start"` / `"call_core_sweep_status"` keys (`:559-560`).

---

### Tests (`tests/test_pipeline_orchestrator.py`, `tests/test_six_rs_*.py`)

**Analog:** `sentinel-core/tests/test_note_sweep_runner.py` (`:1-60`) + `sentinel-core/tests/fakes/vault.py` (`FakeVault`, `:28-203` — has `acquire_sweep_lock`/`release_sweep_lock` at `:199-203`, already delegates to the real `_ObsidianVault` lock methods for realistic lock-contention tests)

```python
from tests.fakes.vault import FakeVault

class _ImmediateTaskRunner:
    """Synchronous task runner — records coroutines, caller awaits run_all()."""
    def __init__(self): self._scheduled = []
    def schedule(self, coro): self._scheduled.append(coro)
    async def run_all(self):
        for coro in self._scheduled:
            await coro
        self._scheduled.clear()

def _make_vault():
    vault = FakeVault()
    vault.dirs[""] = []
    return vault
```
Pre-populate `inbox/_pending-classification.md` via `inbox.append_entry`; stub `acompletion_with_profile` per-`six_rs` module via `unittest.mock.patch` (mirrors how `test_note_sweep_runner.py` patches `probe_classifier_model_ready`/`probe_embedding_model_loaded`). For hub/embedding tests, reuse `tests/test_moc_maintenance.py`'s existing `find_hub_candidate`/`attach_to_hub` fixtures rather than rewriting them (Phase 45 already unit-tested this machinery against `FakeVault`).

**Required test per Pitfall 6:** feed Reduce a deliberately malformed completion and assert the note is still filed as `_schema.status: draft`, not dropped or retried indefinitely.

**Required test per Pitfall 8:** two concurrent `:ralph`/`:pipeline` invocations — assert the second's `pipeline_orchestrator.run()` raises `SweepInProgressError` BEFORE any `parse_inbox`/inbox read (lock acquired first, exactly as `run_sweep()` acquires before `walk_vault()` at `vault_sweeper.py:480-486`).

## Shared Patterns

### Concurrency lock (D-04)
**Source:** `sentinel-core/app/vault.py:692-720` (`acquire_sweep_lock`/`release_sweep_lock`, Protocol declared at `:163-165`)
**Apply to:** `pipeline_orchestrator.py` only (single call site) — reused verbatim, no new lock name/path.
```python
async def acquire_sweep_lock(self, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    existing = await self.read_note(_LOCKFILE_PATH)
    if existing.strip():
        fm, _ = split_frontmatter(existing)
        started = _parse_iso(str(fm.get("started_at", "")))
        if started is not None:
            age = (now - started).total_seconds()
            if age < _STALE_LOCK_SECONDS:
                return False
            logger.warning("acquire_sweep_lock: stale lockfile (age %.0fs) — taking over", age)
    fm = {"started_at": _iso_utc(now), "host": "sentinel-core"}
    body = join_frontmatter(fm, "# Sweep in progress\n")
    await self.write_note(_LOCKFILE_PATH, body)
    return True

async def release_sweep_lock(self) -> None:
    try:
        await self.delete_note(_LOCKFILE_PATH)
    except Exception as exc:
        logger.warning("release_sweep_lock: delete failed: %s", exc)
```

### Background task scheduling (D-06)
**Source:** `sentinel-core/app/services/task_runner.py` (whole file)
**Apply to:** `pipeline_runner.py`/`start_pipeline()` — `runner.schedule(_runner())` where `runner = task_runner or AsyncioTaskRunner()`.

### Error handling / never-crash-the-loop discipline
**Source:** `vault_sweeper.py`'s per-entry `report.errors.append(...)` convention (repeated 10+ times across the file) + `note_classifier.classify_note`'s coerce-to-safe-default-on-parse-failure discipline (`:139-143`, `_coerce_topic`)
**Apply to:** every phase in `pipeline_orchestrator.py`'s loop AND every `six_rs/*` completion call — catch per-entry/per-phase exceptions locally, append a string to `report.errors`, never let one bad entry abort the whole run.

### Admin gate
**Source:** `sentinel-core/app/routes/note.py:126-132` (`_is_admin_route`)
**Apply to:** `routes/pipeline.py`'s `POST /vault/pipeline/start` — import directly (`from app.routes.note import _is_admin_route`), do not duplicate (RESEARCH Open Question 3 — auth-gate logic must not have two independently-maintained copies).

### Idempotent append-only write (D-01, D-03d precedent)
**Source:** `sentinel-core/app/services/moc_maintenance.py:136-178` (`_insert_member_wikilink` + `attach_to_hub`)
**Apply to:** `six_rs/reweave.py`'s dated-section append — check for the `## Reweave — {date}` marker before appending; never `vault.patch_append`; always full read → merge → single `write_note`.

## No Analog Found

None. Every file in this phase has a direct or role-match analog already in the tree (this phase is explicitly "clone the sweep shape," per RESEARCH.md's own framing — the infrastructure precedent is complete).

## Metadata

**Analog search scope:** `sentinel-core/app/services/`, `sentinel-core/app/routes/`, `sentinel-core/app/`, `interfaces/discord/`, `sentinel-core/tests/`
**Files scanned (read in full or targeted sections):** `vault_sweeper.py`, `note_sweep_runner.py`, `sweep_status_store.py`, `task_runner.py`, `note_classifier.py`, `inbox.py`, `routes/note.py`, `core_gateway.py`, `command_router.py`, `bot.py` (targeted sections), `moc_maintenance.py` (targeted), `note_schema.py` (targeted), `vault.py` (targeted, lock methods), `tests/test_note_sweep_runner.py`, `tests/fakes/vault.py` (targeted)
**Pattern extraction date:** 2026-07-06
