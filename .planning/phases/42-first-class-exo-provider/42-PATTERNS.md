# Phase 42: First-Class exo Provider - Pattern Map

**Mapped:** 2026-07-05
**Files analyzed:** 11 (modified) + 3 (new)
**Analogs found:** 14 / 14

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|---------------|
| `sentinel-core/app/config.py` (+ `exo_base_url`/`exo_model`/`exo_api_key`) | config | CRUD (settings load) | same file — `ollama_base_url`/`ollama_model`/`llamacpp_*` triplets | exact |
| `sentinel-core/app/composition.py` (`build_provider_router()`) | service (composition root) | request-response (startup wiring) | same file — existing `lmstudio`/`ollama`/`llamacpp` `LiteLLMProvider` instantiation in `provider_map` | exact |
| `sentinel-core/app/composition.py` (`active_model` ternary, lines 143-151) | service | transform | same file — the ternary chain itself (being generalized to dict lookup) | exact |
| `sentinel-core/app/composition.py` (stop-sequence fetch, lines 161-183) | service | request-response | same file — `get_profile(lmstudio_model_name, api_base=lmstudio_api_base)` block | exact |
| `sentinel-core/app/services/provider_router.py` (`_FALLBACK_TRIGGERS`, fallback selection) | service | event-driven (exception-triggered fallback) | same file — current `(httpx.ConnectError, httpx.TimeoutException)` tuple + `ai_fallback_provider == "claude"` branch in `composition.py` | exact |
| `sentinel-core/app/services/model_selector.py` (`discover_via_exo_state()` — NEW function) | service | request-response (HTTP GET + parse) | same file — `get_loaded_models()` (existing `/v1/models` GET+parse) | role-match (different endpoint shape: tagged-union vs flat list) |
| `sentinel-core/app/services/model_selector.py` (`discover_active_model()` base_url dict, lines 247-251) | service | transform | same file — the dict-lookup itself (being generalized) | exact |
| `sentinel-core/app/services/model_registry.py` (`build_model_registry()` — exo branch) | service | CRUD (registry build) | same file — `_fetch_lmstudio()` / the `elif settings.ai_provider == "ollama":` stub branches | role-match |
| `sentinel-core/app/routes/provider.py` (NEW — `POST /provider/complete`) | route/controller | request-response | `sentinel-core/app/routes/message.py` (`POST /message`) — simpler shape closer to `modules.py`'s `proxy_module` | role-match (message.py for RouteContext/error-mapping pattern; modules.py for "thin passthrough, no pipeline" shape) |
| `sentinel-core/app/state.py` (`RouteContext` + `ai_provider` field) | model/config (dataclass) | CRUD | same file — existing `ai_provider_name: str \| None = None` field pattern | exact |
| `sentinel-core/tests/test_provider_router.py` (extend with `NotFoundError` case) | test | event-driven | same file — `test_falls_back_on_connect_error` / `test_falls_back_on_timeout` | exact |
| `sentinel-core/tests/test_composition.py` (extend with exo + LM Studio regression pin) | test | request-response | same file — `test_build_provider_router_picks_primary_from_settings` | exact |
| `sentinel-core/tests/test_model_selector_discovery.py` (new exo `/state` tests) | test | request-response | same file — existing `get_loaded_models`/`discover_active_model` mock-transport tests | role-match |
| `sentinel-core/tests/test_provider_route.py` (NEW FILE) | test | request-response | `sentinel-core/tests/test_message_route.py` (if present) or `app/routes/modules.py`'s proxy tests — TestClient + RouteContext seeding pattern | role-match |
| `modules/pathfinder/app/config.py` (remove `litellm_model`/`litellm_api_base` chat fields) | config | CRUD | same file — remove pattern precedent: none needed, straightforward field deletion | n/a (deletion, not analog-based) |
| `modules/pathfinder/app/llm.py` (~13 call sites migrate to core client) | service | request-response | same file's own `acompletion_with_profile()` call sites — replaced by `SentinelCoreClient.complete()` calls | exact (self-analog: same call shape, different callee) |
| `shared/sentinel_client.py` (`SentinelCoreClient.complete()` — NEW method) | service (shared client) | request-response | same file — `post_to_module()` (raise-on-error shape) vs `send_message()` (swallow-to-string shape) | exact — copy `post_to_module()`'s error-propagation posture, not `send_message()`'s |

## Pattern Assignments

### `sentinel-core/app/config.py` — new `exo_*` fields (config)

**Analog:** same file, `ollama_base_url`/`ollama_model` (lines 60-62) and `llamacpp_base_url`/`llamacpp_model` (lines 64-66)

**Pattern to copy** (lines 60-69):
```python
# Ollama (stub — Linux workstation LAN)
ollama_base_url: str = "http://localhost:11434"
ollama_model: str = "qwen2.5:14b"

# llama.cpp (stub — OpenAI-compatible server)
llamacpp_base_url: str = "http://localhost:8080"
llamacpp_model: str = "local-model"

# LM Studio API key (optional — only if LM Studio auth is enabled)
lmstudio_api_key: str = ""
```
New fields follow this exact triplet shape:
```python
exo_base_url: str = "http://host.docker.internal:52415/v1"
exo_model: str = ""  # blank = auto-discover via GET /state (D-07); never a hardcoded model default (removes the debug-time default)
exo_api_key: str = ""
```
`ai_provider` field (line 53) gets `exo` added to its comment enum; `ai_fallback_provider` (line 54) comment changes from `"claude | none"` to reflect D-05 (any configured provider name).

If `exo_api_key` should be Docker-secret-backed, add `"exo_api_key": "exo_api_key"` to the `secret_map` dict in `load_secrets()` (lines 89-98) — same as `lmstudio_api_key`/`anthropic_api_key` today.

---

### `sentinel-core/app/composition.py` — `build_provider_router()` (controller/service, request-response)

**Analog:** the file's own existing per-provider branches (this is a generalize-in-place, not a copy-from-elsewhere task)

**Current provider_map construction to extend** (lines 186-205):
```python
provider_map = {
    "lmstudio": LiteLLMProvider(
        model_string=lmstudio_model_str,  # discovered, not hardcoded
        api_base=settings.lmstudio_base_url,
        api_key="lmstudio",
    ),
    "ollama": LiteLLMProvider(
        model_string=f"ollama/{settings.ollama_model}",
        api_base=settings.ollama_base_url,
    ),
    "llamacpp": LiteLLMProvider(
        model_string=f"openai/{settings.llamacpp_model}",
        api_base=settings.llamacpp_base_url,
    ),
}
if settings.anthropic_api_key:
    provider_map["claude"] = LiteLLMProvider(
        model_string=settings.claude_model,
        api_key=settings.anthropic_api_key,
    )
```
New `exo` entry follows the exact `lmstudio` shape (both become `openai_compatible` table entries per RESEARCH Pattern 1):
```python
"exo": LiteLLMProvider(
    model_string=f"openai/{exo_model_str}",  # exo_model_str from discover_via_exo_state() or settings.exo_model
    api_base=settings.exo_base_url,
    api_key=settings.exo_api_key or None,
),
```

**Fallback selection to generalize** (lines 216-224 — currently hardcoded to `claude` only):
```python
# Select fallback provider
fallback = None
if settings.ai_fallback_provider == "claude":
    fallback = provider_map.get("claude")
    if fallback is None:
        logger.warning(
            "AI_FALLBACK_PROVIDER=claude but ANTHROPIC_API_KEY not set — no fallback available"
        )
```
Generalize to (D-05):
```python
fallback = provider_map.get(settings.ai_fallback_provider)
if settings.ai_fallback_provider != "none" and fallback is None:
    logger.warning(
        f"AI_FALLBACK_PROVIDER={settings.ai_fallback_provider!r} but provider "
        "could not be instantiated — no fallback available"
    )
```

**`active_model` ternary to replace with dict lookup** (Pitfall 1, lines 143-151):
```python
active_model = (
    lmstudio_model_name
    if settings.ai_provider == "lmstudio"
    else settings.claude_model
    if settings.ai_provider == "claude"
    else settings.ollama_model
    if settings.ai_provider == "ollama"
    else settings.llamacpp_model
)
```
Replace with a dict + `.get(provider, <safe default>)` per the table-driven pattern (RESEARCH Pattern 1); add `"exo": exo_model_str` entry; log WARNING (not silent fallback) if `ai_provider` key is missing.

**Stop-sequence/model-profile fetch to generalize** (Pitfall 3, lines 161-183) — currently unconditionally uses `settings.lmstudio_base_url` regardless of active provider; must resolve `api_base` from the SAME table-driven lookup used above, keyed by `settings.ai_provider`.

---

### `sentinel-core/app/services/provider_router.py` — add `NotFoundError` trigger (D-06)

**Analog:** same file's current `_FALLBACK_TRIGGERS` tuple

**Current** (lines 14-21):
```python
import httpx

from app.errors import ContextLengthError, ProviderUnavailableError

# Errors that trigger fallback (connectivity failures only)
_FALLBACK_TRIGGERS = (httpx.ConnectError, httpx.TimeoutException)
```

**Change to** (per RESEARCH Code Example §1):
```python
import httpx
import litellm

from app.errors import ContextLengthError, ProviderUnavailableError

# Errors that trigger fallback (connectivity failures + model-not-served)
_FALLBACK_TRIGGERS = (
    httpx.ConnectError,
    httpx.TimeoutException,
    litellm.NotFoundError,   # D-06: exo's real failure mode is a 404
)
```
No other change needed in this file — `complete()`'s `except _FALLBACK_TRIGGERS as primary_exc:` block (lines 60-71) already handles any tuple member identically; module docstring (lines 1-13) should be updated to mention the new trigger.

---

### `sentinel-core/app/services/model_selector.py` — `discover_via_exo_state()` (NEW function, service, request-response)

**Analog:** same file's `get_loaded_models()` (lines 98-126) for the HTTP-GET-and-cache shape; `discover_active_model()`'s base_url dict (lines 247-251) for the provider-keyed-lookup generalization

**Reference implementation** (from RESEARCH Code Examples §2 — already codebase-appropriate, use verbatim as starting point):
```python
async def discover_via_exo_state(base_url: str, http_client: httpx.AsyncClient) -> list[str]:
    """Return the list of currently-loaded exo model ids via GET /state.

    Unlike /v1/models (a ~120-entry static catalog of servable-but-not-necessarily-
    running models), /state.instances reflects ONLY models with an active running
    instance. Each instance value is a tagged union — {"MlxRingInstance": {...}}
    or {"MlxJacclInstance": {...}} — with the model id at
    <tag-value>.shardAssignments.modelId (camelCase on the wire).

    Zero running instances → "instances": {} → returns [] (caller feeds this into
    select_model(), which raises ModelSelectorError rather than guessing when
    `loaded` is empty and no default is configured — D-08).
    """
    resp = await http_client.get(f"{base_url.rstrip('/')}/state", timeout=5.0)
    resp.raise_for_status()
    data = resp.json()
    instances = data.get("instances", {})
    model_ids: list[str] = []
    for instance_value in instances.values():
        for tagged_body in instance_value.values():
            model_id = tagged_body.get("shardAssignments", {}).get("modelId")
            if isinstance(model_id, str) and model_id:
                model_ids.append(model_id)
    return model_ids
```
NOTE (MEDIUM confidence, A1 in RESEARCH Assumptions Log): consider defensively also checking snake_case (`shard_assignments`/`model_id`) as a fallback since the camelCase wire format was not live-curl-confirmed.

**`discover_active_model()` base_url dict to generalize** (Pitfall 2, lines 247-251):
```python
base_url = {
    "lmstudio": settings.lmstudio_base_url,
    "ollama": settings.ollama_base_url,
    "llamacpp": settings.llamacpp_base_url,
}.get(settings.ai_provider, settings.lmstudio_base_url)
```
Add `"exo": settings.exo_base_url` and route exo through `discover_via_exo_state()` instead of the generic `/models` GET this function currently does for all providers — exo needs its own branch here (or a `discover_fn` in the table-driven registry per RESEARCH Pattern 1), since `/state` has a completely different response shape than `/v1/models`.

**D-08 "never guess" contract to preserve:** `select_model()` (lines 129-190) is UNCHANGED — feed `discover_via_exo_state()`'s `[]` result into it exactly as `get_loaded_models()`'s `[]` result is fed today; `ModelSelectorError` propagation on empty+no-default is already correct and must not be special-cased for exo.

---

### `sentinel-core/app/services/model_registry.py` — exo branch in `build_model_registry()`

**Analog:** the `elif settings.ai_provider == "ollama": logger.info(...)` stub branch (lines 180-181) — exo should get a similarly light branch since it has no `/api/v0/models/{id}`-equivalent (Pitfall 4/Assumption A2):
```python
elif settings.ai_provider == "ollama":
    logger.info("Ollama registry fetch: stub only — using seed data")
elif settings.ai_provider == "llamacpp":
    logger.info("llama.cpp registry fetch: stub only — using seed data")
```
New exo branch: skip the LM-Studio-only `/api/v0/models/{id}` call entirely (do NOT reuse `_fetch_lmstudio`), fall to `model_profiles` family-based inference the same way `_fetch_lmstudio`'s OWN 4096-fallback path already does (lines 84-117) — i.e. call `get_profile(discovered_name, api_base=settings.exo_base_url)` directly rather than routing through `_fetch_lmstudio`.

---

### `sentinel-core/app/state.py` — `RouteContext.ai_provider` field (model/config)

**Analog:** same file, existing `ai_provider_name: str | None = None` field (line 59)

**Pattern** (lines 46-63, add one field):
```python
@dataclass(frozen=True)
class RouteContext:
    """Single object route handlers use instead of scattered app.state fields."""

    vault: "Vault"
    processor: "MessageProcessor | None" = None
    settings: "Settings | None" = None
    http_client: "httpx.AsyncClient | None" = None
    context_window: int = 4096
    lmstudio_stop_sequences: list[str] = field(default_factory=list)
    classify: Callable[[str], Awaitable[Any]] = _missing_classifier
    embedder: Callable[[list[str]], Awaitable[list[float]]] = _missing_embedder
    module_registry: dict[str, Any] = field(default_factory=dict)
    ai_provider_name: str | None = None
    recall: "Recall | None" = None
    # NEW — the ProviderRouter itself, for the narrow /provider/complete route
    ai_provider: "ProviderRouter | None" = None
```
Pin it in `initialize_startup()` (`composition.py` lines 401-413) alongside the other fields — value comes from `graph.ai_provider` (already constructed at `composition.py:381`).

---

### `sentinel-core/app/routes/provider.py` (NEW) — `POST /provider/complete` (route/controller, request-response)

**Analog:** `sentinel-core/app/routes/message.py` for the `RouteContext`/error-mapping/router-registration shape; `sentinel-core/app/routes/modules.py`'s `proxy_module` for the "thin passthrough, no pipeline" shape (no background tasks, no note filing, no recall)

**Imports pattern to copy** (from `message.py` lines 1-13, trimmed to what's actually needed):
```python
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.state import get_route_context

logger = logging.getLogger(__name__)

router = APIRouter()
```

**Core request/response shape** (per RESEARCH Pattern 2 — thin passthrough):
```python
class ProviderCompleteRequest(BaseModel):
    messages: list[dict]
    stop: list[str] | None = None
    temperature: float | None = None
    # V5 input-validation note (RESEARCH Security Domain): add a list-size cap
    # on `messages`, mirroring MessageEnvelope.content's max_length=32_000 pattern —
    # no existing message-count cap exists anywhere in the codebase; this endpoint
    # is the first to need one.


class ProviderCompleteResponse(BaseModel):
    content: str
    model: str


@router.post("/provider/complete", response_model=ProviderCompleteResponse)
async def post_provider_complete(
    body: ProviderCompleteRequest, request: Request
) -> ProviderCompleteResponse:
    ctx = get_route_context(request)
    if ctx.ai_provider is None:
        raise HTTPException(status_code=500, detail="ai_provider not configured")
    try:
        content = await ctx.ai_provider.complete(
            body.messages, stop=body.stop, temperature=body.temperature
        )
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return ProviderCompleteResponse(content=content, model=ctx.ai_provider_name or "")
```
Auth: NO new code needed — `APIKeyMiddleware` (global, `app/main.py`) already covers every non-`/health` route including this new one (confirmed in RESEARCH Security Domain V2).

**Error handling pattern:** follow `message.py`'s `map_message_exception()` idea loosely, but this endpoint is intentionally NARROWER — only `ProviderUnavailableError` → 503 needs mapping (no `ContextLengthError`/injection-filter/recall errors are reachable from a bare `ctx.ai_provider.complete()` call, unlike `/message`'s full pipeline).

---

### `shared/sentinel_client.py` — `SentinelCoreClient.complete()` (NEW method, service, request-response)

**Analog:** same file's `post_to_module()` (raise-on-error shape) — explicitly NOT `send_message()` (swallow-to-string shape), per RESEARCH Pattern 2 and Security Domain "Spoofing" row.

**Pattern to copy** (lines matching `post_to_module()`):
```python
async def post_to_module(self, path: str, payload: dict, client: httpx.AsyncClient) -> dict:
    """POST to a sentinel-core module proxy path.

    Unlike send_message(), this method raises on error so callers can
    format domain-specific error messages (e.g., 409 NPC collision).
    ...
    Raises:
        httpx.HTTPStatusError: On 4xx/5xx responses.
        httpx.ConnectError: If sentinel-core is unreachable.
        httpx.TimeoutException: If request exceeds self._timeout.
    """
    resp = await client.post(
        f"{self._base_url}/{path.lstrip('/')}",
        json=payload,
        headers={"X-Sentinel-Key": self._api_key},
        timeout=self._timeout,
    )
    resp.raise_for_status()
    return resp.json()
```
New `complete()` method mirrors this exactly, hardcoded to the new path and typed request/response:
```python
async def complete(
    self,
    messages: list[dict],
    client: httpx.AsyncClient,
    stop: list[str] | None = None,
    temperature: float | None = None,
) -> dict:
    """POST /provider/complete — thin chat/completion passthrough to core.

    Raises (same posture as post_to_module(), NOT send_message()):
        httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException.
    """
    resp = await client.post(
        f"{self._base_url}/provider/complete",
        json={"messages": messages, "stop": stop, "temperature": temperature},
        headers={"X-Sentinel-Key": self._api_key},
        timeout=self._timeout,
    )
    resp.raise_for_status()
    return resp.json()  # {"content": str, "model": str}
```

---

### `modules/pathfinder/app/llm.py` — ~13 call sites migrate from direct litellm to `SentinelCoreClient.complete()`

**Analog:** the file's own current call shape (self-analog — same call site, different callee)

**Current pattern** (repeated ~13x, e.g. lines 83, 113, 165, 227, 305, 527, 697, 809, 867, 937 — via `sentinel_shared.llm_call.acompletion_with_profile`):
```python
from sentinel_shared.llm_call import acompletion_with_profile
from sentinel_shared.model_profiles import ModelProfile
...
response = await acompletion_with_profile(
    model=settings.litellm_model,
    api_base=settings.litellm_api_base,
    messages=[...],
    ...
)
```
Migration target per call site:
```python
from shared.sentinel_client import SentinelCoreClient  # or wherever pf2e imports the shared client from
...
result = await core_client.complete(messages=[...], client=http_client, stop=..., temperature=...)
content = result["content"]
```
Each of the ~13 sites' surrounding JSON-parse/salvage logic (e.g. `generate_npc_reply`'s `{reply, mood_delta}` parse) is UNCHANGED — only the LLM-invocation line changes. `pf2e's config.py` loses `litellm_model`/`litellm_api_base` (chat-only fields); `rules_embedding_model` and embedding config are untouched (Phase 43).

**Pf2e currently has no `SentinelCoreClient` import anywhere** (RESEARCH-confirmed) — the migration must ADD the import + a constructed client instance (likely at module/app-state level, consistent with how `sentinel_core_url`/`sentinel_api_key` are already read in `modules/pathfinder/app/config.py`).

---

### Tests

#### `sentinel-core/tests/test_provider_router.py` — extend for D-06

**Analog:** same file's `test_falls_back_on_connect_error` / `test_falls_back_on_timeout` (lines 33-50)

**Pattern to copy** (from RESEARCH Code Example §3, matches existing file structure exactly):
```python
async def test_falls_back_on_not_found_error(primary, fallback):
    primary.complete.side_effect = litellm.NotFoundError(
        "no instance found", llm_provider="openai", model="mlx-community/x"
    )
    router = ProviderRouter(primary, fallback)
    result = await router.complete([{"role": "user", "content": "hi"}])
    assert result == "fallback response"
    fallback.complete.assert_awaited_once()
```
Also add a "no fallback configured, NotFoundError raised" case mirroring `test_raises_unavailable_with_no_fallback` (lines 72-76).

#### `sentinel-core/tests/test_composition.py` — extend for SC-2 (exo selection) + SC-6 (LM Studio regression pin)

**Analog:** existing `test_build_provider_router_picks_primary_from_settings` (per RESEARCH Pitfall 5 citation) — extend, don't replace; add an assertion that PINS the exact `LiteLLMProvider(model_string=..., api_base=..., api_key=...)` construction args for `ai_provider="lmstudio"` both pre- and post-refactor (assert equality of constructor args, not just "returns a provider").

#### `sentinel-core/tests/test_model_selector_discovery.py` — new exo `/state` tests

**Analog:** existing `get_loaded_models`/`discover_active_model` tests in the same file, which use `httpx.MockTransport` (confirmed pattern per RESEARCH Environment Availability table — "Tests use `httpx.MockTransport`/`patch("litellm.acompletion", ...)`, no live exo dependency needed").

Test cases to add: (1) zero instances → `[]`; (2) single `MlxRingInstance` → one model id extracted via tagged-union unwrap; (3) single `MlxJacclInstance` → same; (4) malformed/missing `shardAssignments` → skipped gracefully, not raised.

#### `sentinel-core/tests/test_provider_route.py` (NEW FILE)

**Analog:** whatever existing route test uses FastAPI `TestClient` + seeds `RouteContext` directly (check `test_message_route.py` if present, else follow `modules.py`'s route + `get_route_context` seeding convention used across the route test suite). Cover: success (200, `{content, model}`), auth via existing global `X-Sentinel-Key` middleware (no new auth code, but confirm 401 without header), 503 mapping when `ProviderUnavailableError` is raised.

#### pf2e-side tests (new, exact file(s) TBD per Open Question §1 scoping)

**Analog:** whichever existing `modules/pathfinder/tests/test_llm.py`-equivalent file already patches `acompletion_with_profile` — same mocking shape, but patch the new `SentinelCoreClient.complete()` call instead.

## Shared Patterns

### Table-driven provider registry (cross-cutting — composition.py + model_selector.py + model_registry.py)
**Source:** RESEARCH.md Architecture Patterns §Pattern 1 (illustrative sketch, not yet in codebase — this phase INTRODUCES it)
**Apply to:** `composition.py` (`active_model` lookup, `provider_map` construction, stop-sequence api_base resolution), `model_selector.py` (`discover_active_model()`'s base_url lookup + exo's `discover_via_exo_state()` wiring), `model_registry.py` (exo branch in `build_model_registry()`)
```python
_OPENAI_COMPATIBLE_BACKENDS: dict[str, "BackendSpec"] = {
    "lmstudio": BackendSpec(
        base_url_field="lmstudio_base_url",
        model_field="model_name",
        api_key_field="lmstudio_api_key",
        discover=discover_via_v1_models,
    ),
    "exo": BackendSpec(
        base_url_field="exo_base_url",
        model_field="exo_model",
        api_key_field="exo_api_key",
        discover=discover_via_exo_state,
    ),
}
```
This is the SINGLE fix for Pitfalls 1, 2, and 3 — do not patch the three branch points independently with `if ai_provider == "exo":` conditionals (that shape is exactly what caused `exo-model-notfound-502`).

### Auth (unchanged, applies to new route)
**Source:** `app/main.py` — global `APIKeyMiddleware` (`X-Sentinel-Key` exact-match against `settings.sentinel_api_key`)
**Apply to:** `sentinel-core/app/routes/provider.py` — no new auth code required; the new route is covered automatically since the middleware applies before route dispatch to all non-`/health` paths.

### Error-propagation posture: raise vs swallow (cross-cutting — shared client)
**Source:** `shared/sentinel_client.py` — `post_to_module()` raises (`httpx.HTTPStatusError`/`ConnectError`/`TimeoutException`); `send_message()` swallows into user-facing strings.
**Apply to:** the new `SentinelCoreClient.complete()` method MUST follow `post_to_module()`'s raise-on-error posture, since pf2e's internal call sites (llm.py) already have their own JSON-parse-failure salvage/error handling and need real exceptions to react to — NOT the string-swallowing shape.

### `litellm.NotFoundError` as vendor-normalized 404 signal
**Source:** RESEARCH Don't-Hand-Roll table — `litellm.NotFoundError` is already importable/raised generically for ANY provider's 404 via `exception_mapping_utils.py`.
**Apply to:** `provider_router.py`'s `_FALLBACK_TRIGGERS` only. Do NOT add it to `litellm_provider.py`'s `_RETRYABLE` tuple (line 28-33) — it is a fallback trigger, not a transient/retryable error; tenacity retry logic in `LiteLLMProvider.complete()` is unchanged this phase.

## No Analog Found

None — every file in scope has a codebase-verified analog (either a sibling provider's existing branch being generalized, or an existing test/route/client file whose shape is directly reusable). The `openai_compatible` unification itself has no prior analog as a *named concept* in this codebase, but its constituent pieces (`LiteLLMProvider`, `provider_map`, per-provider Settings triplets) are all established patterns being extended, not invented from scratch.

## Metadata

**Analog search scope:** `sentinel-core/app/{config.py,composition.py,state.py}`, `sentinel-core/app/services/{provider_router.py,model_selector.py,model_registry.py}`, `sentinel-core/app/clients/litellm_provider.py`, `sentinel-core/app/routes/{message.py,modules.py}`, `sentinel-core/tests/test_provider_router.py`, `shared/sentinel_client.py`, `modules/pathfinder/app/{config.py,llm.py}`
**Files scanned:** 14 read in full (all ≤ 500 lines; no large-file grep-first strategy needed)
**Pattern extraction date:** 2026-07-05
