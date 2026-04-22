# Phase 29: NPC CRUD + Obsidian Persistence — Pattern Map

**Mapped:** 2026-04-22
**Files analyzed:** 10 (6 modified + 4 new)
**Analogs found:** 10 / 10

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `interfaces/discord/bot.py` | controller | request-response | `interfaces/discord/bot.py` (self) | exact |
| `shared/sentinel_client.py` | utility | request-response | `shared/sentinel_client.py` (self) | exact |
| `modules/pathfinder/app/main.py` | config + app bootstrap | request-response | `modules/pathfinder/app/main.py` (self) | exact |
| `modules/pathfinder/app/config.py` | config | — | `sentinel-core/app/config.py` | role-match |
| `modules/pathfinder/app/obsidian.py` | service | CRUD | `sentinel-core/app/clients/obsidian.py` | exact |
| `modules/pathfinder/app/llm.py` | service | request-response | `sentinel-core/app/clients/litellm_provider.py` | exact |
| `modules/pathfinder/app/routes/npc.py` | controller | CRUD | `sentinel-core/app/routes/modules.py` | role-match |
| `modules/pathfinder/tests/test_npc.py` | test | — | `modules/pathfinder/tests/test_healthz.py` | role-match |
| `modules/pathfinder/compose.yml` | config | — | `modules/pathfinder/compose.yml` (self) | exact |
| `.env.example` | config | — | `.env.example` (self) | exact |

---

## Pattern Assignments

### `interfaces/discord/bot.py` — add `_pf_dispatch()` + `elif subcmd == "pf"` branch

**Analog:** `interfaces/discord/bot.py` (self, lines 206–282)

**Subcommand routing pattern** (lines 206–212 and 229–239 as representative):
```python
async def handle_sentask_subcommand(subcmd: str, args: str, user_id: str) -> str:
    if subcmd == "help":
        return SUBCOMMAND_HELP

    # plugin: prefix routing — check BEFORE dict lookup
    if subcmd.startswith("plugin:"):
        ...

    # Arg-taking standard commands
    if subcmd == "capture":
        if not args.strip():
            return "Usage: `:capture <text>` — provide something to capture."
        return await _call_core(user_id, f"Capture this insight...")
```

**Insertion point for `_pf_dispatch`:** Add `elif subcmd == "pf":` as the first branch in `handle_sentask_subcommand`, before the `plugin:` check (lines 211–228). Pattern:
```python
    if subcmd == "pf":
        return await _pf_dispatch(args, user_id, attachments=attachments)
```

**`_call_core` pattern for module calls** (lines 169–175) — `_pf_dispatch` follows same async-with-client structure:
```python
async def _call_core(user_id: str, message: str) -> str:
    async with httpx.AsyncClient() as http_client:
        return await _sentinel_client.send_message(user_id, message, http_client)
```

**Signature extension needed:** `_route_message` (line 181) and `handle_sentask_subcommand` (line 206) must each gain `attachments: list | None = None` parameter. The `on_message` handler (line 382) passes `message.attachments` down this chain. Discord thread reply flow (`message.channel` is a `discord.Thread`) already exposes `message.attachments`.

**`_pf_dispatch` internal dispatch pattern** — mirrors the existing `if subcmd == "capture"` pattern but parses `<noun> <verb> <rest>`:
```python
async def _pf_dispatch(args: str, user_id: str, attachments: list | None = None) -> str:
    """Route :pf <noun> <verb> <rest> to pathfinder module endpoints."""
    parts = args.strip().split(" ", 2)
    if len(parts) < 2:
        return "Usage: `:pf npc <create|update|show|relate|import> ...`"
    noun, verb = parts[0].lower(), parts[1].lower()
    rest = parts[2] if len(parts) > 2 else ""

    if noun == "npc":
        async with httpx.AsyncClient() as http_client:
            if verb == "create":
                # split name | description on first pipe
                name, _, description = rest.partition("|")
                payload = {"name": name.strip(), "description": description.strip(), "user_id": user_id}
                result = await _sentinel_client.post_to_module("modules/pathfinder/npc/create", payload, http_client)
                return _format_npc_response(result)
            ...
    return f"Unknown pf command `{noun} {verb}`. Try `:help`."
```

---

### `shared/sentinel_client.py` — add `post_to_module()` method

**Analog:** `shared/sentinel_client.py` (self, lines 15–43)

**Existing `send_message` pattern** (lines 15–43) — `post_to_module` is a slimmer version of this:
```python
async def send_message(self, user_id: str, content: str, client: httpx.AsyncClient) -> str:
    try:
        resp = await client.post(
            f"{self._base_url}/message",
            json={"content": content, "user_id": user_id},
            headers={"X-Sentinel-Key": self._api_key},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return resp.json()["content"]
    except httpx.TimeoutException:
        logger.error("Core request timed out after %ss", self._timeout)
        return "The Sentinel took too long to respond. Try again."
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        ...
    except httpx.ConnectError:
        logger.error("Cannot reach Sentinel Core at %s", self._base_url)
        return "Cannot reach the Sentinel. Is sentinel-core running?"
    except Exception as exc:
        logger.exception("Unexpected error calling Core: %s", exc)
        return "An unexpected error occurred."
```

**New method to add** — returns `dict` not `str`; raises on error (caller in `_pf_dispatch` catches):
```python
async def post_to_module(self, path: str, payload: dict, client: httpx.AsyncClient) -> dict:
    """POST to a module proxy path (e.g., 'modules/pathfinder/npc/create').
    
    Raises httpx.HTTPStatusError on 4xx/5xx so callers can format error embeds.
    Raises httpx.ConnectError if sentinel-core is unreachable.
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

---

### `modules/pathfinder/app/config.py` — NEW pydantic-settings config

**Analog:** `sentinel-core/app/config.py` (lines 1–90)

**Imports pattern** (lines 1–12):
```python
from pydantic_settings import BaseSettings
```

**Settings class pattern** (lines 26–87):
```python
class Settings(BaseSettings):
    lmstudio_base_url: str = "http://host.docker.internal:1234/v1"
    sentinel_api_key: str  # Required — no default. Startup fails fast if missing.
    obsidian_api_url: str = "http://host.docker.internal:27123"
    obsidian_api_key: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

settings = Settings()
```

**Pathfinder-specific adaptation** — add OBSIDIAN_BASE_URL, OBSIDIAN_API_KEY, LITELLM_MODEL:
```python
class Settings(BaseSettings):
    sentinel_core_url: str = "http://sentinel-core:8000"
    sentinel_api_key: str  # Required — startup fails fast if missing
    obsidian_base_url: str = "http://host.docker.internal:27123"
    obsidian_api_key: str = ""
    litellm_model: str = "openai/local-model"
    litellm_api_base: str = "http://host.docker.internal:1234/v1"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

settings = Settings()
```

Note: `main.py` currently reads env vars via `os.getenv()` directly (line 26). Moving to a `Settings` class in `config.py` requires updating `main.py` to import from `app.config`. Add `config.py` as a new file; update `main.py` to use `from app.config import settings` where `SENTINEL_CORE_URL` and `SENTINEL_API_KEY` are referenced (lines 26, 49).

---

### `modules/pathfinder/app/obsidian.py` — NEW ObsidianClient for pathfinder

**Analog:** `sentinel-core/app/clients/obsidian.py` (lines 1–183)

**Constructor pattern** (lines 22–29):
```python
class ObsidianClient:
    def __init__(self, http_client: httpx.AsyncClient, base_url: str, api_key: str) -> None:
        self._client = http_client
        self._base_url = base_url.rstrip("/")
        self._headers: dict[str, str] = (
            {"Authorization": f"Bearer {api_key}"} if api_key else {}
        )
```

**`_safe_request` wrapper** (lines 31–38) — use for GET/collision check:
```python
async def _safe_request(self, coro, default, operation: str, silent: bool = False):
    """Execute a coroutine, returning default on any failure."""
    try:
        return await coro
    except Exception as exc:
        if not silent:
            logger.warning("%s failed: %s", operation, exc)
        return default
```

**GET pattern — collision check / note read** (lines 53–71, `get_user_context`):
```python
async def _inner():
    resp = await self._client.get(
        f"{self._base_url}/vault/{path}",
        headers=self._headers,
        timeout=5.0,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.text
return await self._safe_request(_inner(), None, "get_note")
```

**PUT pattern — write/overwrite note** (lines 152–164, `write_session_summary`):
```python
resp = await self._client.put(
    f"{self._base_url}/vault/{path}",
    headers={**self._headers, "Content-Type": "text/markdown"},
    content=content.encode("utf-8"),
    timeout=10.0,
)
resp.raise_for_status()
```

**PATCH pattern — single-field frontmatter update** (new for Phase 29; follows same httpx style):
```python
async def patch_frontmatter_field(self, path: str, field: str, value) -> None:
    """PATCH one frontmatter field. Value is the complete new value for that field."""
    import json
    resp = await self._client.patch(
        f"{self._base_url}/vault/{path}",
        headers={
            **self._headers,
            "Content-Type": "application/json",
            "Target-Type": "frontmatter",
            "Target": field,
            "Operation": "replace",
        },
        content=json.dumps(value).encode("utf-8"),
        timeout=10.0,
    )
    resp.raise_for_status()
```

**Critical:** Do NOT send a multi-key JSON dict as the body — the Obsidian v3 PATCH API treats the entire body as the value for the single field named in the `Target` header (RESEARCH.md Pattern 2). For multi-field NPC updates, use GET-then-PUT (read full note, modify frontmatter in memory, PUT back).

---

### `modules/pathfinder/app/llm.py` — NEW LiteLLM wrapper for pathfinder

**Analog:** `sentinel-core/app/clients/litellm_provider.py` (lines 1–99)

**Import pattern** (lines 1–20):
```python
import logging
import litellm
```

**Core call pattern** (lines 60–78):
```python
async def complete(self, messages: list[dict]) -> str:
    kwargs: dict = {
        "model": self._model_string,
        "messages": messages,
        "timeout": 120.0,
    }
    if self._api_base:
        kwargs["api_base"] = self._api_base
    if self._api_key:
        kwargs["api_key"] = self._api_key
    response = await litellm.acompletion(**kwargs)
    return response.choices[0].message.content
```

**Pathfinder-specific adaptation** — NPC field extraction function (wraps litellm directly, not behind Protocol):
```python
import json
import litellm

async def extract_npc_fields(name: str, description: str, model: str, api_base: str | None) -> dict:
    system_prompt = (
        "You are a PF2e Remaster NPC generator. "
        "Extract or infer NPC fields from the description. "
        "Return ONLY a JSON object with these exact keys: "
        "name, level (int, default 1), ancestry, class, traits (list), "
        "personality, backstory, mood (default 'neutral'). "
        "For unspecified fields, randomly select a valid PF2e Remaster option. "
        "Return nothing except the JSON object."
    )
    response = await litellm.acompletion(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Name: {name}\nDescription: {description}"},
        ],
        timeout=60.0,
        **({"api_base": api_base} if api_base else {}),
    )
    content = response.choices[0].message.content
    # Strip markdown code fences — LMs often wrap JSON in triple backticks
    content = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(content)
```

---

### `modules/pathfinder/app/routes/npc.py` — NEW FastAPI NPC router

**Analog:** `sentinel-core/app/routes/modules.py` (lines 1–117)

**Router declaration pattern** (line 15):
```python
router = APIRouter()
```

**Pathfinder adaptation** — use prefix:
```python
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/npc")
```

**Pydantic request model pattern** (lines 18–26):
```python
class ModuleRoute(BaseModel):
    path: str
    description: str
```

**Pathfinder NPC request models:**
```python
class NPCCreateRequest(BaseModel):
    name: str
    description: str = ""
    user_id: str

class NPCUpdateRequest(BaseModel):
    name: str
    correction: str
    user_id: str

class NPCShowRequest(BaseModel):
    name: str

class NPCRelateRequest(BaseModel):
    name: str
    relation: str
    target: str

class NPCImportRequest(BaseModel):
    actors_json: str  # raw JSON string fetched from attachment URL
    user_id: str
```

**Route + error handling pattern** (lines 85–117, `proxy_module`):
```python
@router.post("/modules/{name}/{path:path}")
async def proxy_module(name: str, path: str, request: Request) -> JSONResponse:
    registry = request.app.state.module_registry
    if name not in registry:
        raise HTTPException(status_code=404, detail=f"Module '{name}' not registered")
    ...
    try:
        resp = await request.app.state.http_client.post(...)
        try:
            content = resp.json()
        except ValueError:
            content = {"body": resp.text}
        return JSONResponse(content=content, status_code=resp.status_code)
    except httpx.TransportError:
        raise HTTPException(status_code=503, detail={"error": "module unavailable"})
```

**Pathfinder NPC create endpoint adaptation:**
```python
VALID_RELATIONS = {"knows", "trusts", "hostile-to", "allied-with", "fears", "owes-debt"}

@router.post("/create")
async def create_npc(req: NPCCreateRequest) -> JSONResponse:
    slug = slugify(req.name)
    # 1. Collision check — GET-before-write (D-19)
    existing = await obsidian.get_note(f"mnemosyne/pf2e/npcs/{slug}.md")
    if existing is not None:
        raise HTTPException(status_code=409, detail={
            "error": "NPC already exists",
            "path": f"mnemosyne/pf2e/npcs/{slug}.md"
        })
    # 2. LLM extraction
    fields = await extract_npc_fields(req.name, req.description, settings.litellm_model, settings.litellm_api_base)
    fields["relationships"] = []
    fields["imported_from"] = None
    # 3. Build markdown + PUT
    content = build_npc_markdown(fields)
    await obsidian.put_note(f"mnemosyne/pf2e/npcs/{slug}.md", content)
    return JSONResponse({"status": "created", "slug": slug, "path": f"mnemosyne/pf2e/npcs/{slug}.md", **fields})
```

**Slug helper** — no external dependency:
```python
import re

def slugify(name: str) -> str:
    """'Baron Aldric' → 'baron-aldric'"""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
```

**NPC markdown builder:**
```python
import yaml

def build_npc_markdown(fields: dict, stats: dict | None = None) -> str:
    frontmatter = yaml.dump(fields, default_flow_style=False, allow_unicode=True)
    body = f"---\n{frontmatter}---\n"
    if stats:
        stats_yaml = yaml.dump(stats, default_flow_style=False, allow_unicode=True)
        body += f"\n## Stats\n```yaml\n{stats_yaml}```\n"
    return body
```

---

### `modules/pathfinder/app/main.py` — add NPC router + config import

**Analog:** `modules/pathfinder/app/main.py` (self, lines 1–87)

**Router include pattern** — add after existing `app = FastAPI(...)` declaration (lines 72–77):
```python
from modules.pathfinder.app.routes import npc as npc_router
app.include_router(npc_router.router)
```

**REGISTRATION_PAYLOAD update** (lines 31–35) — add NPC routes:
```python
REGISTRATION_PAYLOAD = {
    "name": "pathfinder",
    "base_url": "http://pf2e-module:8000",
    "routes": [
        {"path": "healthz", "description": "pf2e module health check"},
        {"path": "npc/create", "description": "Create NPC in Obsidian"},
        {"path": "npc/update", "description": "Update NPC fields"},
        {"path": "npc/show", "description": "Show NPC summary"},
        {"path": "npc/relate", "description": "Add NPC relationship"},
        {"path": "npc/import", "description": "Bulk import NPCs from Foundry JSON"},
    ],
}
```

**Lifespan pattern** (lines 63–69) — add persistent httpx.AsyncClient for Obsidian (mirrors sentinel-core pattern):
```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    async with httpx.AsyncClient() as client:
        await _register_with_retry(client)
    # Phase 29: persistent client for Obsidian calls
    async with httpx.AsyncClient() as obsidian_http_client:
        app.state.obsidian_client = ObsidianClient(
            obsidian_http_client, settings.obsidian_base_url, settings.obsidian_api_key
        )
        yield
```

---

### `modules/pathfinder/compose.yml` — add OBSIDIAN env vars

**Analog:** `modules/pathfinder/compose.yml` (self, lines 1–37)

**Environment block pattern** (lines 21–23):
```yaml
    environment:
      - SENTINEL_CORE_URL=http://sentinel-core:8000
```

**Addition** — append to `environment` block:
```yaml
    environment:
      - SENTINEL_CORE_URL=http://sentinel-core:8000
      - OBSIDIAN_BASE_URL=http://host.docker.internal:27123
      - OBSIDIAN_API_KEY=  # blank; real key goes in secrets/ if needed
      - LITELLM_MODEL=openai/local-model
      - LITELLM_API_BASE=http://host.docker.internal:1234/v1
```

**Secrets pattern** (lines 34–37) — if `obsidian_api_key` is moved to a secret file, follow the same pattern as `sentinel_api_key`:
```yaml
secrets:
  sentinel_api_key:
    file: ../../secrets/sentinel_api_key
  obsidian_api_key:
    file: ../../secrets/obsidian_api_key
```

---

### `.env.example` — add OBSIDIAN_BASE_URL, OBSIDIAN_API_KEY

**Analog:** `.env.example` (self, lines 1–77)

**Existing Obsidian block pattern** (lines 32–39):
```bash
# Obsidian — Mnemosyne Vault
# ...
OBSIDIAN_API_URL=http://host.docker.internal:27124
```

**Addition** — append a pathfinder module Obsidian block (distinct from the sentinel-core `OBSIDIAN_API_URL`):
```bash
# ------------------------------------------------------------
# Pathfinder Module — Obsidian direct access
# The pathfinder module calls Obsidian directly (D-27).
# OBSIDIAN_BASE_URL: HTTP port 27123 (non-encrypted) for Docker→Mac host.
# OBSIDIAN_API_KEY: blank if Obsidian REST API auth is disabled.
# ------------------------------------------------------------
OBSIDIAN_BASE_URL=http://host.docker.internal:27123
OBSIDIAN_API_KEY=
```

---

### `modules/pathfinder/tests/test_npc.py` — NEW test file

**Analog:** `modules/pathfinder/tests/test_healthz.py` (lines 1–18) and `test_registration.py` (lines 1–85)

**File header pattern** (lines 1–7 of test_healthz.py):
```python
"""Tests for pf2e-module /healthz endpoint."""
import os
os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("SENTINEL_CORE_URL", "http://sentinel-core:8000")

from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch
```

**ASGI test client pattern** (lines 13–18 of test_healthz.py):
```python
with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)):
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/healthz")
    assert resp.status_code == 200
```

**Mock patch pattern** (lines 36–42 of test_registration.py):
```python
mock_client = AsyncMock()
mock_client.post = AsyncMock(
    side_effect=[
        httpx.ConnectError("refused"),
        httpx.ConnectError("refused"),
        success_resp,
    ]
)
```

**NPC test adaptation:**
```python
"""Tests for pf2e-module NPC CRUD endpoints."""
import os
os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("SENTINEL_CORE_URL", "http://sentinel-core:8000")
os.environ.setdefault("OBSIDIAN_BASE_URL", "http://localhost:27123")

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch

async def test_npc_create_success():
    """POST /npc/create returns 200 + slug when NPC does not exist."""
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian.get_note", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.extract_npc_fields", new=AsyncMock(return_value={...})), \
         patch("app.routes.npc.obsidian.put_note", new=AsyncMock(return_value=None)):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/create", json={"name": "Varek", "description": "gnome rogue", "user_id": "u1"})
        assert resp.status_code == 200
        assert resp.json()["slug"] == "varek"
```

---

## Shared Patterns

### Authentication (X-Sentinel-Key)
**Source:** `sentinel-core/app/routes/modules.py` lines 98–108
**Apply to:** `modules/pathfinder/app/routes/npc.py` — pathfinder module must verify the X-Sentinel-Key on incoming requests from sentinel-core's proxy. Existing APIKeyMiddleware pattern in sentinel-core covers the sentinel-core→module hop automatically (sentinel-core forwards the key per lines 98–108).
```python
sentinel_key = request.headers.get("X-Sentinel-Key", "")
# forwarded verbatim to module:
headers={"Content-Type": "application/json", "X-Sentinel-Key": sentinel_key}
```

### Obsidian `_safe_request` Error Wrapper
**Source:** `sentinel-core/app/clients/obsidian.py` lines 31–38
**Apply to:** `modules/pathfinder/app/obsidian.py` — copy verbatim. All GET calls (collision check, note read for GET-then-PUT) use this wrapper. PUT and PATCH calls raise directly (callers in npc.py catch and return HTTPException).
```python
async def _safe_request(self, coro, default, operation: str, silent: bool = False):
    try:
        return await coro
    except Exception as exc:
        if not silent:
            logger.warning("%s failed: %s", operation, exc)
        return default
```

### httpx Bearer Auth Header
**Source:** `sentinel-core/app/clients/obsidian.py` lines 27–29
**Apply to:** `modules/pathfinder/app/obsidian.py`
```python
self._headers: dict[str, str] = (
    {"Authorization": f"Bearer {api_key}"} if api_key else {}
)
```

### pydantic-settings `model_config`
**Source:** `sentinel-core/app/config.py` line 87
**Apply to:** `modules/pathfinder/app/config.py`
```python
model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}
```

### FastAPI `JSONResponse` return type
**Source:** `sentinel-core/app/routes/modules.py` — all route handlers return `JSONResponse`
**Apply to:** `modules/pathfinder/app/routes/npc.py` — use `JSONResponse(content=..., status_code=...)` not bare `dict` returns for explicit status code control.

### `litellm.acompletion` kwargs pattern
**Source:** `sentinel-core/app/clients/litellm_provider.py` lines 66–78
**Apply to:** `modules/pathfinder/app/llm.py`
```python
kwargs: dict = {"model": ..., "messages": ..., "timeout": 120.0}
if self._api_base:
    kwargs["api_base"] = self._api_base
if self._api_key:
    kwargs["api_key"] = self._api_key
response = await litellm.acompletion(**kwargs)
return response.choices[0].message.content
```

### Test env-var-before-import guard
**Source:** `modules/pathfinder/tests/test_healthz.py` lines 1–7
**Apply to:** `modules/pathfinder/tests/test_npc.py` — env vars must be set via `os.environ.setdefault()` before any `from app...` import to avoid Settings validation failure at import time.

---

## No Analog Found

All files have close analogs. No entries in this section.

---

## Metadata

**Analog search scope:** `sentinel-core/`, `interfaces/discord/`, `modules/pathfinder/`, `shared/`
**Files read:** 10
**Pattern extraction date:** 2026-04-22
