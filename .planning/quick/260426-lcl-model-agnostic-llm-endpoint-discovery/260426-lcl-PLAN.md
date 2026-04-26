---
phase: lcl-260426
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - sentinel-core/app/config.py
  - sentinel-core/app/services/model_selector.py
  - sentinel-core/app/services/model_registry.py
  - sentinel-core/app/main.py
  - sentinel-core/tests/test_model_selector_discovery.py
  - sentinel-core/tests/test_model_registry.py
autonomous: true
requirements: [lcl-model-agnostic]

must_haves:
  truths:
    - "Sentinel-core discovers the active model name from /v1/models at startup instead of reading MODEL_NAME blindly"
    - "If MODEL_PREFERRED or MODEL_NAME matches a loaded model it is used; otherwise the best-scoring model for chat is selected"
    - "If /v1/models is unreachable or returns empty, startup continues and falls back to MODEL_NAME (non-fatal)"
    - "MODEL_AUTO_DISCOVER=false bypasses discovery and uses MODEL_NAME directly (backward-compat opt-out)"
    - "model_registry._fetch_lmstudio uses the discovered name, not settings.model_name, for the context-window fetch"
  artifacts:
    - path: "sentinel-core/app/services/model_selector.py"
      provides: "Model discovery + scoring logic for sentinel-core (copied from pathfinder)"
      exports: ["get_loaded_models", "select_model", "ModelSelectorError"]
    - path: "sentinel-core/app/config.py"
      provides: "New Settings fields for auto-discovery"
      contains: "model_auto_discover"
    - path: "sentinel-core/tests/test_model_selector_discovery.py"
      provides: "Tests for discover_active_model integration"
  key_links:
    - from: "sentinel-core/app/main.py lifespan"
      to: "sentinel-core/app/services/model_selector.py"
      via: "discover_active_model(settings, http_client)"
      pattern: "discover_active_model"
    - from: "sentinel-core/app/services/model_registry.py _fetch_lmstudio"
      to: "discovered model name"
      via: "parameter passed in from build_model_registry"
      pattern: "discovered_name"
---

<objective>
Replace sentinel-core's hardcoded MODEL_NAME startup binding with runtime model discovery.
At startup, query `/v1/models` on the configured provider endpoint; score and select the
best model for chat; use that name when constructing LiteLLMProvider and when fetching the
context window from LM Studio. Fallback chain: MODEL_PREFERRED → scored best → first loaded
→ MODEL_NAME. If discovery fails entirely, fall through to MODEL_NAME (non-fatal).

Purpose: The user loads whatever model they want in LM Studio (or Ollama) and sentinel-core
picks it up automatically on next restart — no env var editing required.

Output: model_selector.py in sentinel-core/app/services/, updated config.py, updated
main.py lifespan, updated model_registry._fetch_lmstudio, and tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
</context>

<interfaces>
<!-- Extracted from source files. Use these directly — no codebase exploration needed. -->

From sentinel-core/app/config.py (current Settings fields relevant here):
```python
class Settings(BaseSettings):
    lmstudio_base_url: str = "http://host.docker.internal:1234/v1"
    model_name: str = "local-model"          # static fallback / preferred hint
    ai_provider: str = "lmstudio"            # lmstudio | claude | ollama | llamacpp
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:14b"
    llamacpp_base_url: str = "http://localhost:8080"
    llamacpp_model: str = "local-model"
```

From sentinel-core/app/main.py lifespan (the two blocks to change):
```python
# Block 1 — active model name resolution (lines 67-76):
_active_model = (
    settings.model_name
    if settings.ai_provider == "lmstudio"
    else settings.claude_model
    if settings.ai_provider == "claude"
    else settings.ollama_model
    if settings.ai_provider == "ollama"
    else settings.llamacpp_model
)
_model_info = model_registry.get(_active_model)

# Block 2 — LiteLLMProvider construction (lines 88-106):
_provider_map = {
    "lmstudio": LiteLLMProvider(
        model_string=f"openai/{settings.model_name}",  # <-- hardcoded
        api_base=settings.lmstudio_base_url,
        api_key="lmstudio",
    ),
    "ollama": LiteLLMProvider(
        model_string=f"ollama/{settings.ollama_model}",  # <-- also discover
        api_base=settings.ollama_base_url,
    ),
    "llamacpp": LiteLLMProvider(
        model_string=f"openai/{settings.llamacpp_model}",  # <-- also discover
        api_base=settings.llamacpp_base_url,
    ),
}
```

From sentinel-core/app/services/model_registry.py (_fetch_lmstudio to update):
```python
async def _fetch_lmstudio(
    settings: Settings, client: httpx.AsyncClient
) -> dict[str, "ModelInfo"]:
    ctx = await get_context_window_from_lmstudio(
        client, settings.lmstudio_base_url, settings.model_name  # <-- use discovered name
    )
    ...
    return {
        settings.model_name: ModelInfo(...)  # <-- key by discovered name
    }

async def build_model_registry(
    settings: Settings, http_client: httpx.AsyncClient
) -> dict[str, ModelInfo]:
    ...
    if settings.ai_provider == "lmstudio":
        live = await _fetch_lmstudio(settings, http_client)  # needs discovered name passed in
```

From modules/pathfinder/app/model_selector.py (copy verbatim to sentinel-core):
```python
TaskKind = Literal["chat", "structured", "fast"]

async def get_loaded_models(api_base: str, *, force_refresh: bool = False) -> list[str]: ...
def select_model(task_kind, loaded, *, preferences=None, default=None) -> str: ...
class ModelSelectorError(RuntimeError): ...
def _reset_cache_for_tests() -> None: ...
```

From sentinel-core/tests/test_model_registry.py (fixture pattern to follow):
```python
@pytest.fixture
def lmstudio_settings(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "lmstudio")
    monkeypatch.setenv("MODEL_NAME", "test-model")
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://test-lmstudio/v1")
    from app.config import Settings
    return Settings()
```
</interfaces>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add model_selector.py to sentinel-core and extend config.py</name>
  <files>
    sentinel-core/app/services/model_selector.py
    sentinel-core/app/config.py
    sentinel-core/tests/test_model_selector_discovery.py
  </files>
  <behavior>
    - get_loaded_models("http://lmstudio/v1", force_refresh=False) returns cached list on second call without HTTP
    - get_loaded_models returns [] (not raises) when /v1/models is unreachable; logs warning
    - select_model("chat", ["ModelA"], default="fallback") returns "ModelA"
    - select_model("chat", [], default="fallback") returns "fallback"
    - select_model("chat", [], default=None) raises ModelSelectorError
    - discover_active_model with model_auto_discover=False returns f"openai/{settings.model_name}" without HTTP
    - discover_active_model with model_auto_discover=True, /v1/models returns ["Qwen2.5-14B"], model_preferred=None → returns "openai/Qwen2.5-14B"
    - discover_active_model with model_auto_discover=True, model_preferred="Qwen2.5-14B" in loaded list → returns "openai/Qwen2.5-14B" (honored)
    - discover_active_model with /v1/models unreachable → returns f"openai/{settings.model_name}" (non-fatal fallback)
    - discover_active_model with model_name already containing "/" → no double prefix ("openai/openai/X" must not occur)
    - discover_active_model for ai_provider="ollama" → returns "ollama/{name}"
  </behavior>
  <action>
1. Copy `modules/pathfinder/app/model_selector.py` verbatim to
   `sentinel-core/app/services/model_selector.py`. Do not modify the copied file.

2. Add `discover_active_model` function at the bottom of the new
   `sentinel-core/app/services/model_selector.py` (do NOT add it to pathfinder):

```python
async def discover_active_model(
    settings: "Settings",
    http_client: httpx.AsyncClient,
) -> str:
    """
    Returns a LiteLLM-compatible model string (e.g. "openai/Qwen2.5-14B-Instruct").
    Falls back to _with_provider_prefix(settings.model_name) on any failure.
    Never raises — startup must not fail due to discovery issues.
    """
    def _prefixed(name: str) -> str:
        if "/" in name:
            return name
        if settings.ai_provider == "ollama":
            return f"ollama/{name}"
        return f"openai/{name}"

    if not settings.model_auto_discover:
        return _prefixed(settings.model_name)

    # Resolve base URL for the active provider
    base_url = {
        "lmstudio": settings.lmstudio_base_url,
        "ollama": settings.ollama_base_url,
        "llamacpp": settings.llamacpp_base_url,
    }.get(settings.ai_provider, settings.lmstudio_base_url)

    # Reuse get_loaded_models (handles network errors, returns [] on failure)
    # Pass a fresh client reference — no extra HTTP context manager needed
    url = base_url.rstrip("/")
    try:
        resp = await http_client.get(f"{url}/models", timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        loaded = [e["id"] for e in data.get("data", []) if isinstance(e.get("id"), str)]
    except Exception as exc:
        logger.warning("Model discovery failed: %s — using MODEL_NAME=%s", exc, settings.model_name)
        return _prefixed(settings.model_name)

    if not loaded:
        logger.warning("No models loaded at %s — using MODEL_NAME=%s", url, settings.model_name)
        return _prefixed(settings.model_name)

    preferences = {}
    preferred = settings.model_preferred or settings.model_name
    if preferred:
        preferences["chat"] = preferred

    try:
        chosen = select_model("chat", loaded, preferences=preferences, default=settings.model_name)
    except ModelSelectorError:
        chosen = loaded[0]

    logger.info("Auto-selected model: %s", chosen)
    return _prefixed(chosen)
```

3. Extend `sentinel-core/app/config.py` Settings with (add after `lmstudio_api_key`):
```python
# Model auto-discovery (lcl-model-agnostic)
model_auto_discover: bool = True
model_preferred: str | None = None
model_task_chat: str | None = None
model_task_structured: str | None = None
model_task_fast: str | None = None
```
`model_name` is retained unchanged as static fallback.

4. Write `sentinel-core/tests/test_model_selector_discovery.py` with tests covering all
   behaviors listed above. Use `httpx.MockTransport` for network mocking (same pattern as
   test_model_registry.py). Import `discover_active_model` from
   `app.services.model_selector`. Use monkeypatch + `app.config.Settings` for settings
   fixture construction, not direct instantiation with keyword args (avoids sentinel_api_key
   requirement). Pattern from existing tests:
   ```python
   monkeypatch.setenv("SENTINEL_API_KEY", "test-key")
   monkeypatch.setenv("MODEL_AUTO_DISCOVER", "false")
   from app.config import Settings
   s = Settings()
   ```
  </action>
  <verify>
    <automated>cd /Users/trekkie/projects/sentinel-of-mnemosyne/sentinel-core && python -m pytest tests/test_model_selector_discovery.py -v 2>&1 | tail -30</automated>
  </verify>
  <done>All test_model_selector_discovery tests GREEN. model_selector.py present in sentinel-core/app/services/. config.py has model_auto_discover field.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Wire discover_active_model into main.py and model_registry.py</name>
  <files>
    sentinel-core/app/main.py
    sentinel-core/app/services/model_registry.py
    sentinel-core/tests/test_model_registry.py
  </files>
  <behavior>
    - build_model_registry with lmstudio provider and /v1/models returning ["discovered-model"] stores "discovered-model" key in registry (not "test-model" from MODEL_NAME)
    - build_model_registry with lmstudio provider and /v1/models unreachable still stores MODEL_NAME key in registry (graceful fallback path)
    - build_model_registry with model_auto_discover=false stores MODEL_NAME key in registry (no discovery attempt)
  </behavior>
  <action>
1. Update `sentinel-core/app/services/model_registry.py`:

   a. Add import at top: `from app.services.model_selector import discover_active_model`

   b. Change `_fetch_lmstudio` signature to accept an explicit `discovered_name: str` parameter:
   ```python
   async def _fetch_lmstudio(
       settings: Settings, client: httpx.AsyncClient, discovered_name: str
   ) -> dict[str, "ModelInfo"]:
       ctx = await get_context_window_from_lmstudio(
           client, settings.lmstudio_base_url, discovered_name
       )
       ...
       return {
           discovered_name: ModelInfo(
               id=discovered_name,
               provider="lmstudio",
               context_window=ctx,
               capabilities={"chat": True},
               notes="Fetched from LM Studio at startup",
           )
       }
   ```

   c. In `build_model_registry`, call `discover_active_model` before the provider if-chain
   to resolve the name, then pass it in:
   ```python
   # Discover active model name (non-fatal; falls back to settings.model_name)
   discovered_lmstudio_name = settings.model_name  # default
   if settings.ai_provider == "lmstudio":
       model_str = await discover_active_model(settings, http_client)
       # Strip provider prefix for registry key (e.g. "openai/Qwen2.5" → "Qwen2.5")
       discovered_lmstudio_name = model_str.split("/", 1)[-1]

   if settings.ai_provider == "lmstudio":
       live = await _fetch_lmstudio(settings, http_client, discovered_lmstudio_name)
       registry.update(live)
   ```

2. Update `sentinel-core/app/main.py` lifespan:

   a. Add import: `from app.services.model_selector import discover_active_model`

   b. After `build_model_registry` call, resolve discovered names per provider before
   the `_active_model` block and `_provider_map` construction:
   ```python
   # Discover active model per provider (non-fatal)
   _discovered_lmstudio = await discover_active_model(settings, http_client)
   _discovered_lmstudio_name = _discovered_lmstudio.split("/", 1)[-1]

   # For Ollama/llamacpp, attempt discovery if auto_discover enabled; else use static setting
   _discovered_ollama = await discover_active_model(
       _ollama_settings_view(settings), http_client
   ) if settings.model_auto_discover and settings.ai_provider in ("ollama",) else f"ollama/{settings.ollama_model}"
   _discovered_ollama_name = _discovered_ollama.split("/", 1)[-1]

   _discovered_llamacpp = f"openai/{settings.llamacpp_model}"  # no discovery for llamacpp
   ```

   IMPORTANT: Do not introduce a `_ollama_settings_view` helper. Instead, call
   `discover_active_model` with a modified settings only when ai_provider matches.
   Use the simpler approach below to avoid complexity:

   Replace the `_active_model` block and `_provider_map` block in lifespan with:
   ```python
   # Discover active model for the configured provider
   _lmstudio_model_str = await discover_active_model(settings, http_client)
   _lmstudio_model_name = _lmstudio_model_str.split("/", 1)[-1]

   # Determine active model for context window lookup
   _active_model = (
       _lmstudio_model_name
       if settings.ai_provider == "lmstudio"
       else settings.claude_model
       if settings.ai_provider == "claude"
       else settings.ollama_model
       if settings.ai_provider == "ollama"
       else settings.llamacpp_model
   )
   _model_info = model_registry.get(_active_model)
   context_window = _model_info.context_window if _model_info else 4096
   if not _model_info:
       logger.warning(
           f"Active model '{_active_model}' not found in registry — using 4096 token default"
       )
   else:
       logger.info(f"Context window: {context_window} tokens (model: {_active_model})")
   app.state.context_window = context_window

   # Build provider map with discovered model names
   _provider_map = {
       "lmstudio": LiteLLMProvider(
           model_string=_lmstudio_model_str,  # discovered, not hardcoded
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
       _provider_map["claude"] = LiteLLMProvider(
           model_string=settings.claude_model,
           api_key=settings.anthropic_api_key,
       )
   ```
   Keep Ollama and llamacpp using their static settings for now — they are stubs and
   the user's primary use case is LM Studio.

3. Extend `sentinel-core/tests/test_model_registry.py` with tests:
   - `test_lmstudio_registry_uses_discovered_model_name`: mock `/v1/models` to return
     `{"data": [{"id": "discovered-model"}]}` AND mock `/api/v0/models/discovered-model`
     to return `{"max_context_length": 65536}`. Settings: MODEL_AUTO_DISCOVER=true,
     MODEL_NAME="static-name". Assert registry key is "discovered-model" (not "static-name")
     and context_window is 65536.
   - `test_lmstudio_registry_fallback_when_discovery_fails`: `/v1/models` raises
     ConnectError. MODEL_NAME="static-name". Assert registry key is "static-name".
   - `test_lmstudio_registry_no_discovery_when_disabled`: MODEL_AUTO_DISCOVER=false.
     MODEL_NAME="static-name". Assert registry key is "static-name" (no discovery HTTP call).

   The mock transport handler must route by URL path:
   ```python
   def handler(request):
       if "/v1/models" in request.url.path:
           return httpx.Response(200, json={"data": [{"id": "discovered-model"}]})
       if "/api/v0/models" in request.url.path:
           return httpx.Response(200, json={"max_context_length": 65536, "id": "discovered-model"})
       return httpx.Response(404)
   ```
  </action>
  <verify>
    <automated>cd /Users/trekkie/projects/sentinel-of-mnemosyne/sentinel-core && python -m pytest tests/test_model_registry.py tests/test_model_selector_discovery.py -v 2>&1 | tail -40</automated>
  </verify>
  <done>All model_registry and model_selector_discovery tests GREEN. sentinel-core starts without error (docker compose build sentinel-core runs clean). discover_active_model is called in lifespan and the resolved model string drives LiteLLMProvider construction.</done>
</task>

<task type="auto">
  <name>Task 3: Full test suite green + smoke-test sentinel-core startup</name>
  <files></files>
  <action>
1. Run the full sentinel-core test suite and fix any failures introduced by Tasks 1-2.
   Common failure modes to watch for:
   - Tests that mock `build_model_registry` but now also need to handle the
     `discover_active_model` call inside it (add `/v1/models` route to mock transports)
   - Tests constructing `Settings()` directly that now fail because `model_auto_discover`
     default is `True` and the test makes HTTP calls unexpectedly — add
     `MODEL_AUTO_DISCOVER=false` to monkeypatch.setenv blocks in those tests
   - Import errors if `discover_active_model` import in model_registry.py creates a
     circular import — resolve by moving the import inside the function body if needed

2. Verify sentinel-core Docker image builds cleanly:
   ```bash
   docker compose build sentinel-core 2>&1 | tail -20
   ```
   If build fails due to a missing import or syntax error, fix it.

3. Log a note in the summary about the one-known limitation:
   "Model is resolved once at startup. If the user switches models in LM Studio
   mid-session, sentinel-core uses the old model until restarted. Hot-reload is a
   future improvement."
  </action>
  <verify>
    <automated>cd /Users/trekkie/projects/sentinel-of-mnemosyne/sentinel-core && python -m pytest tests/ -v --tb=short 2>&1 | tail -50</automated>
  </verify>
  <done>Full sentinel-core test suite GREEN (or same failures as before this task — no regressions introduced). Docker build completes without error.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| sentinel-core → LM Studio /v1/models | Outbound HTTP at startup; response is parsed for model IDs |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-lcl-01 | Tampering | discover_active_model JSON parse | mitigate | Only `entry["id"]` string values are extracted; non-string entries are silently skipped. No eval, no exec. |
| T-lcl-02 | Denial of Service | /v1/models discovery at startup | accept | 5-second timeout already in get_loaded_models; failure is non-fatal and falls back to MODEL_NAME. Startup cannot be blocked. |
| T-lcl-03 | Elevation of Privilege | model string injection via /v1/models | accept | Model string is used only as a LiteLLM model identifier, not executed or passed to shell. LiteLLM validates provider prefix. No PII in model names. |
</threat_model>

<verification>
```bash
# 1. All new and existing sentinel-core tests pass
cd /Users/trekkie/projects/sentinel-of-mnemosyne/sentinel-core
python -m pytest tests/ -v --tb=short

# 2. Docker build clean
docker compose build sentinel-core

# 3. Confirm model_selector.py exists in sentinel-core services
ls sentinel-core/app/services/model_selector.py

# 4. Confirm config.py has auto-discover fields
grep -n "model_auto_discover\|model_preferred" sentinel-core/app/config.py

# 5. Confirm main.py uses discover_active_model
grep -n "discover_active_model" sentinel-core/app/main.py
```
</verification>

<success_criteria>
- `sentinel-core/app/services/model_selector.py` exists and exports `discover_active_model`, `get_loaded_models`, `select_model`
- `config.py` has `model_auto_discover: bool = True` and `model_preferred: str | None = None`
- `main.py` lifespan calls `discover_active_model` and passes the result to `LiteLLMProvider(model_string=...)`
- `model_registry._fetch_lmstudio` uses the discovered name (not `settings.model_name`) for the context-window fetch
- `MODEL_AUTO_DISCOVER=false` preserves full backward-compat (uses MODEL_NAME directly)
- All sentinel-core tests GREEN, no regressions
- Docker build for sentinel-core succeeds
</success_criteria>

<output>
After completion, create `.planning/quick/260426-lcl-model-agnostic-llm-endpoint-discovery/260426-lcl-SUMMARY.md`
</output>
