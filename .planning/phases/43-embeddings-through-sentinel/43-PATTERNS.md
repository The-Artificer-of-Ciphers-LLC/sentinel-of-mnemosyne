# Phase 43: Embeddings Through Sentinel - Pattern Map

**Mapped:** 2026-07-05
**Files analyzed:** 8
**Analogs found:** 8 / 8 (RESEARCH.md absent — file list taken from 43-CONTEXT.md `<code_context>` / `<canonical_refs>`)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `sentinel-core/app/main.py` (NEW `POST /embeddings` route — likely as `sentinel-core/app/routes/embeddings.py` + `include_router`) | route/controller | request-response | `sentinel-core/app/routes/provider.py` (`POST /provider/complete`) | exact |
| `modules/pathfinder/app/llm.py::SentinelCoreClient.embed()` — actually lands on `shared/sentinel_client.py::SentinelCoreClient` | service/client | request-response | `shared/sentinel_client.py::SentinelCoreClient.complete()` | exact |
| `sentinel-core/app/config.py::Settings` (add `embedding_base_url`/`embedding_model` reuse/`embedding_api_key`) | config | CRUD (settings fields) | existing `exo_base_url`/`exo_model`/`exo_api_key` triplet, same file | exact |
| `sentinel-core/app/clients/embeddings.py` (fix `DEFAULT_LMSTUDIO_BASE_URL`; wire injected base_url) | service/client | request-response | itself — `Embeddings.__init__` already accepts `base_url`; the bug is the caller in `composition.py`, not the class | exact (self-modify) |
| `sentinel-core/app/composition.py` (construction site of `Embeddings(...)`, lines 393-401) | config/wiring (compose root) | CRUD (object construction) | `build_provider_router()` per-provider wiring pattern (exo entry, lines 259-269), same file | role-match |
| `sentinel-core/app/services/recall.py::SemanticRecall` (dimension-mismatch guard) | service | CRUD/transform | existing MEM-05 `embedding_model` mismatch skip — already implemented one layer down in `embedding_sidecar_index.py::eligible_entries` (lines 191-222) | exact (extend existing) |
| `sentinel-core/app/services/vault_sweeper.py::rebuild_embedding_index` (re-sweep trigger + dim in index) | service | batch/event-driven | itself, `_emit_embedding_index` / `eligible_entries` codec helpers | exact (self-modify) |
| `modules/pathfinder/app/llm.py::embed_texts` (swap litellm for `SentinelCoreClient.embed()`) | service/transform | request-response | `modules/pathfinder/app/llm.py`'s own already-migrated chat call sites (`_core_client.complete(...)`) — see llm.py lines 1-49 | exact (in-file precedent) |

## Pattern Assignments

### `sentinel-core/app/routes/embeddings.py` (NEW route, request-response)

**Analog:** `sentinel-core/app/routes/provider.py` (full file, 78 lines — the `POST /provider/complete` narrow passthrough)

**Imports pattern** (provider.py lines 16-24):
```python
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.errors import ProviderUnavailableError
from app.state import get_route_context

logger = logging.getLogger(__name__)

router = APIRouter()
```

**Request/response model pattern** (provider.py lines 37-50):
```python
class ProviderMessage(BaseModel):
    role: str
    content: str = Field(max_length=_MAX_CONTENT_LENGTH)


class ProviderCompleteRequest(BaseModel):
    messages: list[ProviderMessage] = Field(min_length=1, max_length=_MAX_MESSAGES)
    stop: list[str] | None = None
    temperature: float | None = None


class ProviderCompleteResponse(BaseModel):
    content: str
    model: str
```
For `/embeddings`, mirror this shape: `EmbeddingsRequest(texts: list[str] = Field(min_length=1, max_length=<cap>))` / `EmbeddingsResponse(vectors: list[list[float]], model: str)`. Add a DoS-guard cap constant analogous to `_MAX_MESSAGES` / `_MAX_CONTENT_LENGTH` (provider.py lines 28-34).

**RouteContext usage + core pattern** (provider.py lines 53-77):
```python
@router.post("/provider/complete", response_model=ProviderCompleteResponse)
async def post_provider_complete(
    body: ProviderCompleteRequest, request: Request
) -> ProviderCompleteResponse:
    ctx = get_route_context(request)
    if ctx.ai_provider is None:
        raise HTTPException(status_code=500, detail="ai_provider not configured")

    messages = [m.model_dump() for m in body.messages]
    try:
        content = await ctx.ai_provider.complete(
            messages, stop=body.stop, temperature=body.temperature
        )
    except ProviderUnavailableError:
        raise HTTPException(status_code=503, detail="AI provider unavailable")

    return ProviderCompleteResponse(content=content, model=ctx.ai_provider_name or "")
```
For `/embeddings`: use `ctx.embedder` (already exists on `RouteContext`, `app/state.py` line 58 — `embedder: Callable[[list[str]], Awaitable[list[float]]] = _missing_embedder`), call `await ctx.embedder(body.texts)`, wrap in try/except analogous to `ProviderUnavailableError` → 503 (check `app/errors.py` for an `EmbeddingModelUnavailable` equivalent — it already exists, imported in `clients/embeddings.py` line 12).

**Auth pattern:** None needed in the route itself — `APIKeyMiddleware` (main.py lines 44-53) covers every non-`/health` route globally, including the new one. Do not add per-route auth.

**Router registration pattern** (main.py lines 30-34, 98-102):
```python
from app.routes.provider import router as provider_router
...
app.include_router(provider_router)
```
Add `from app.routes.embeddings import router as embeddings_router` and `app.include_router(embeddings_router)` alongside the existing includes.

---

### `shared/sentinel_client.py::SentinelCoreClient.embed()` (NEW method, request-response)

**Analog:** `SentinelCoreClient.complete()` in the same file (lines 74-108)

```python
    async def complete(
        self,
        messages: list[dict],
        client: httpx.AsyncClient,
        stop: list[str] | None = None,
        temperature: float | None = None,
    ) -> dict:
        """POST /provider/complete — thin chat/completion passthrough to core.

        Mirrors post_to_module()'s raise-on-error posture EXACTLY (NOT
        send_message()'s swallow-to-string posture) so pf2e call sites get
        real exceptions to react to.
        """
        resp = await client.post(
            f"{self._base_url}/provider/complete",
            json={"messages": messages, "stop": stop, "temperature": temperature},
            headers={"X-Sentinel-Key": self._api_key},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return resp.json()
```
`embed()` is the direct mirror: `POST {base_url}/embeddings`, body `{"texts": texts}`, same header/timeout/raise-for-status posture (raise-on-error, NOT `send_message()`'s swallow-to-string posture — pf2e's `embed_texts` caller needs real exceptions to decide retry/503-degrade, matching D-07's `_build_rules_index_safely()` contract).

---

### `sentinel-core/app/config.py::Settings` (config, CRUD fields)

**Analog:** existing `exo_*` triplet (lines 71-80) and `ollama_*` (lines 60-62) / `llamacpp_*` (lines 64-66) triplets in the same class

```python
    # exo (D-03) — dedicated config, independent of lmstudio_*. exo and LM Studio
    # can be configured simultaneously; ai_provider selects which is active.
    exo_base_url: str = "http://host.docker.internal:52415/v1"
    exo_model: str = ""
    exo_api_key: str = ""
```
Add a new `embedding_*` triplet (D-03 of Phase 43): `embedding_base_url: str = "http://host.docker.internal:1234/v1"` (LM Studio port 1234, NOT exo's 52415), reuse the existing `embedding_model: str = "text-embedding-nomic-embed-text-v1.5"` field (line 47 — already present, do not duplicate), add `embedding_api_key: str = ""` (defaults to `"lm-studio"` sentinel at the call site per `Embeddings.__init__`'s existing `api_key or "lm-studio"` fallback, embeddings.py line 114 — mirrors `lmstudio_api_key`, line 69).

If `embedding_api_key` needs Docker-secret support, add it to the `secret_map` dict in `load_secrets` (lines 100-110), following the `"exo_api_key": "exo_api_key"` entry pattern (line 104).

---

### `sentinel-core/app/clients/embeddings.py` (MODIFY — bug fix, request-response)

**Root-cause line** (embeddings.py line 14):
```python
DEFAULT_LMSTUDIO_BASE_URL = "http://host.docker.internal:52415"
```
This is exo's port and is only used as the fallback when `base_url` is falsy in `Embeddings.__init__` (line 107: `normalised = base_url.rstrip("/") if base_url else DEFAULT_LMSTUDIO_BASE_URL`). The class itself is NOT broken — it already accepts an injected `base_url`. **The actual fix is at the call site in `composition.py`** (see next section), not in this file. This file only needs the constant renamed/repointed to LM Studio's port 1234 as the SAFE fallback default (`http://host.docker.internal:1234`), so a missing/blank `embedding_base_url` degrades to LM Studio, not exo.

**Existing degrade pattern to preserve** (embeddings.py lines 60-71):
```python
    except litellm.BadRequestError as exc:
        if "no models loaded" in str(exc).lower():
            raise EmbeddingModelUnavailable(
                f"No embedding model loaded on LM Studio. Configured: "
                f"{resolved_model}. Load via `lms load {resolved_model}` "
                f"or LM Studio UI."
            ) from exc
        raise
```
Keep this untouched — it is the typed-exception seam the new `/embeddings` route and `SemanticRecall` both rely on for graceful degrade.

---

### `sentinel-core/app/composition.py` (MODIFY — compose-root wiring, lines 393-401)

**Current (buggy) construction:**
```python
    if embeddings is None:
        embeddings = Embeddings(
            http_client,
            settings.lmstudio_base_url or DEFAULT_LMSTUDIO_BASE_URL,
            settings.embedding_model,
            api_key=settings.lmstudio_api_key or "lm-studio",
        )
```
This is THE bug (D-02): it wires the embeddings client off `settings.lmstudio_base_url` (chat's base URL, defaulting to exo's 52415) instead of an independent embeddings base URL. **Fix:** repoint to the new `settings.embedding_base_url` / `settings.embedding_api_key` fields (D-03/D-04) — do NOT let embeddings inherit `lmstudio_base_url` or any chat-provider base_url:
```python
    if embeddings is None:
        embeddings = Embeddings(
            http_client,
            settings.embedding_base_url or DEFAULT_LMSTUDIO_BASE_URL,
            settings.embedding_model,
            api_key=settings.embedding_api_key or "lm-studio",
        )
```

**Sibling per-provider wiring analog** (`build_provider_router`, lines 259-278) — shows the established "each backend gets its own dedicated settings fields, independently constructed" convention this change follows:
```python
    provider_map = {
        "lmstudio": LiteLLMProvider(
            model_string=lmstudio_model_str,
            api_base=settings.lmstudio_base_url,
            api_key="lmstudio",
        ),
        "exo": LiteLLMProvider(
            model_string=f"openai/{resolved_exo_model}",
            api_base=settings.exo_base_url,
            api_key=settings.exo_api_key or None,
        ),
        ...
    }
```
D-05 explicitly rejects retrofitting this `provider_map`/`ProviderRouter` shape onto embeddings — do not generalize `Embeddings` into a routed multi-backend abstraction; keep it a single injected client.

---

### `sentinel-core/app/services/recall.py::SemanticRecall` (MODIFY — add dimension guard, CRUD/transform)

**Important finding:** a dimension check ALREADY EXISTS one layer down, in `sentinel-core/app/services/embedding_sidecar_index.py::eligible_entries()` (lines 173-229), called from `SemanticRecall.search()`-equivalent (recall.py lines 562-567):
```python
        decoded_entries, matched_model_count = eligible_entries(
            self._index,
            active_model=self._active_model,
            exclude_prefixes=self._config.exclude_prefixes,
            query_dim=len(qv),
        )
```
And inside `eligible_entries` (embedding_sidecar_index.py lines 215-222):
```python
            if len(raw) != query_dim:
                logger.warning(
                    "Embedding sidecar index: dimension mismatch for %r (%d vs query %d), skipping",
                    path,
                    len(raw),
                    query_dim,
                )
                continue
```
This already hard-skips per-entry on dimension mismatch against the live query vector's dimension — it is the mechanism D-08 asks for, just not badged as "D-08" in comments yet and not driven by a persisted `embedding_dim` field (it derives dimension from `len(raw)` decoded at read time, comparing against the query vector's dimension rather than a stored per-entry dim). Planner should treat this as "verify/extend/document" rather than "build from scratch" — decide (per Claude's Discretion in CONTEXT.md) whether to also persist `embedding_dim` in the index for cheaper skip-before-decode, following the adjacent `entry_model = entry.get("embedding_model", "")` read-and-compare pattern (line 191) as the template for a new `entry.get("embedding_dim")` read-and-compare.

**Existing MEM-05 model-mismatch skip this pattern mirrors** (embedding_sidecar_index.py lines 191-194):
```python
        entry_model = entry.get("embedding_model", "")
        if not entry_model or entry_model != active_model:
            continue
        matched_model_count += 1
```

**All-mismatch degrade pattern** (recall.py lines 577-585):
```python
        if matched_model_count == 0 and self._index:
            logger.warning(
                "SemanticRecall: all %d index entries mismatch active model %r"
                " — degrading to keyword-only",
                len(self._index),
                self._active_model,
            )
            return []
```

---

### `sentinel-core/app/services/vault_sweeper.py::rebuild_embedding_index` (MODIFY — re-sweep trigger, batch/event-driven)

**Analog:** itself — `rebuild_embedding_index` (lines 265-354) and its helper `_emit_embedding_index` / `eligible_entries` codec

**Existing structure** (lines 265-346, full function): walk vault → build survivor tuples → embed bodies via injected `embedder` callable → `_emit_embedding_index` writes the sidecar with `content_hash` + `embedding_model` per entry (embedding_sidecar_index.py lines 150-151, 164-168). To add `embedding_dim`, follow the same call shape used for `active_model` (vault_sweeper.py line 244: `active_model=_embedding_model_id()`) — thread a resolved dimension value (e.g. `len(embeddings[0])` post-embed, or a `_embedding_dim()` helper mirroring `_embedding_model_id()` at line 97) into `fresh_entry(...)`/`stale_entry(...)` in `embedding_sidecar_index.py`.

**`model_loaded` gate pattern to reuse for the forced re-sweep trigger** (lines 301-307):
```python
        if not model_loaded:
            logger.warning(
                "rebuild_embedding_index: embedding model unavailable — index refresh skipped"
            )
            report.status = "skipped"
            return report
```
The re-sweep trigger mechanism (startup hook vs CLI vs one-shot ops route — Claude's Discretion per D-09) should call this existing function; no new embed/walk logic is needed, only a new caller.

**Test analog:** `sentinel-core/tests/test_vault_sweeper.py::test_rebuild_embedding_index_writes_index_with_all_fields` — extend this test's assertions to also check the new `embedding_dim` field once added.

---

### `modules/pathfinder/app/llm.py::embed_texts` (MODIFY — swap litellm for core client, request-response)

**Analog:** the file's OWN already-migrated chat call sites — this file's module docstring (lines 1-21) and `_core_client` singleton (lines 34-45) show the exact precedent to replicate for embeddings:
```python
from sentinel_client import SentinelCoreClient
...
_core_client = SentinelCoreClient(
    base_url=settings.sentinel_core_url,
    api_key=settings.sentinel_api_key,
)
```
The current `embed_texts` (lines 410-489) calls `litellm.aembedding` directly (line 460) — this is the drift D-06/D-07 corrects. Replace the internal `litellm.aembedding(**kwargs)` call with `await _core_client.embed(texts, client=<httpx.AsyncClient>)` (mirroring `SentinelCoreClient.complete()`'s signature — client is caller-owned per the file's own convention, see docstring lines 34-41: "each call site below opens its own short-lived httpx.AsyncClient... since none of these functions have a caller-owned client in scope today"). Preserve `embed_texts`'s existing validation block (lines 435-444, input-shape checks) and its output-shape validation (lines 471-489) — only the internal HTTP call changes; the function signature/contract to its callers (`RulesIndex`, `_build_rules_index_safely`) stays identical.

**Do NOT touch:** `modules/pathfinder/app/main.py::_build_rules_index_safely()` — its graceful-503-degrade wrapper is preserved as-is (D-07); only the embed call underneath (inside `embed_texts`) changes.

---

## Shared Patterns

### Authentication (all new/modified core routes)
**Source:** `sentinel-core/app/main.py` lines 44-53 (`APIKeyMiddleware`)
**Apply to:** the new `POST /embeddings` route — no per-route auth code needed, global middleware already covers every non-`/health` path.
```python
class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next) -> Response:
        if request.url.path == "/health":
            return await call_next(request)
        key = request.headers.get("X-Sentinel-Key", "")
        if key != settings.sentinel_api_key:
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)
```

### Provider-unavailable → 503 error contract
**Source:** `sentinel-core/app/routes/provider.py` lines 71-75; typed exception `EmbeddingModelUnavailable` in `sentinel-core/app/clients/embeddings.py` line 12 / `app/errors.py`
**Apply to:** `/embeddings` route (core side) and `SentinelCoreClient.embed()` (pf2e side) — never echo underlying provider exception text (may embed api_base/api_key), same posture as the chat route's `ProviderUnavailableError` → generic 503 detail.

### Per-provider settings triplet
**Source:** `sentinel-core/app/config.py` lines 71-80 (`exo_*`) — pattern also present for `ollama_*` / `llamacpp_*`
**Apply to:** new `embedding_base_url` / `embedding_api_key` fields (D-03) — independent of `ai_provider`/`lmstudio_base_url` (D-04).

### RouteContext embedder seam (already exists, do not rebuild)
**Source:** `sentinel-core/app/state.py` lines 43-44, 58
```python
async def _missing_embedder(*_args: Any, **_kwargs: Any) -> list[float]:
    raise RuntimeError("note embedder not configured on app state")
...
    embedder: Callable[[list[str]], Awaitable[list[float]]] = _missing_embedder
```
The new `/embeddings` route should consume `ctx.embedder` — this field and its safe-default already exist on `RouteContext`; only the underlying `Embeddings` construction in `composition.py` needs its base_url fixed.

## No Analog Found

None — every file in CONTEXT.md's code_context/canonical_refs has either an exact same-file precedent (self-modify) or a structurally identical Phase 42 sibling (`/provider/complete` ↔ `/embeddings`, `SentinelCoreClient.complete()` ↔ `.embed()`).

## Metadata

**Analog search scope:** `sentinel-core/app/` (routes, services, clients, config, composition, state, main), `modules/pathfinder/app/llm.py`, `shared/sentinel_client.py`
**Files scanned:** `sentinel-core/app/main.py`, `sentinel-core/app/config.py`, `sentinel-core/app/routes/provider.py`, `sentinel-core/app/clients/embeddings.py`, `sentinel-core/app/composition.py`, `sentinel-core/app/services/recall.py`, `sentinel-core/app/services/vault_sweeper.py`, `sentinel-core/app/services/embedding_sidecar_index.py`, `sentinel-core/app/state.py`, `modules/pathfinder/app/llm.py`, `shared/sentinel_client.py`
**Pattern extraction date:** 2026-07-05
**Note:** Memtrace MCP tools were not available in this agent's toolset (Read/Bash/Write only); analog discovery used direct grep + Read against the live dev repo (`/Users/trekkie/projects/sentinel-of-mnemosyne`), per the fallback instruction in the task brief.
