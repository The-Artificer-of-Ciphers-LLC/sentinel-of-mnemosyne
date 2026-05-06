# V0.40 REFACTORING DIRECTIVE — IMMUTABLE

> **Status:** AUTHORITATIVE — This document governs all refactoring for Sentinel of Mnemosyne pre-beta milestone v0.40.
> **Created:** 2026-04-11
> **Scope:** Complete codebase consolidation, duplicate elimination, stub completion, and best-practices enforcement.
> **Rule:** No item in this directive may be deferred, stubbed, TODO'd, FIXME'd, or marked "future work." Every item ships or the milestone does not ship.

---

## Table of Contents

1. [Codebase Inventory Summary](#1-codebase-inventory-summary)
2. [Duplicates Registry](#2-duplicates-registry)
3. [Stubs and Incomplete Code Registry](#3-stubs-and-incomplete-code-registry)
4. [Architecture Contradictions Registry](#4-architecture-contradictions-registry)
5. [Refactoring Directives](#5-refactoring-directives)
6. [Container Engine Contracts](#6-container-engine-contracts)
7. [REST API Route Registry](#7-rest-api-route-registry)
8. [Function Design Registry](#8-function-design-registry)
9. [Test Coverage Requirements](#9-test-coverage-requirements)
10. [Acceptance Criteria](#10-acceptance-criteria)

---

## 1. Codebase Inventory Summary

### Containers

| Container | Language | Framework | Port | Source Files | Engine File |
|-----------|----------|-----------|------|-------------|-------------|
| sentinel-core | Python 3.12 | FastAPI | 8000 | 14 app modules + 13 test files | `app/main.py` |
| pi-harness | Node.js 22 | Fastify 5 | 3000 | 2 source + 1 test | `src/bridge.ts` |
| discord | Python 3.12 | discord.py | none | 1 source | `bot.py` |
| imessage | Python 3.12 | none (polling) | none | 1 source | `bridge.py` |

### Source File Count (excluding tests, venv, node_modules)

- sentinel-core/app/: 14 .py files
- pi-harness/src/: 2 .ts files
- interfaces/discord/: 1 .py file
- interfaces/imessage/: 1 .py file
- Root config: 1 docker-compose.yml, 1 sentinel.sh, 1 .env.example

**Total production source files: 19**

### Current REST API Routes

| Container | Method | Path | Handler |
|-----------|--------|------|---------|
| sentinel-core | POST | /message | `post_message()` in routes/message.py |
| sentinel-core | GET | /health | `health()` in main.py |
| pi-harness | POST | /prompt | anonymous handler in bridge.ts |
| pi-harness | GET | /health | anonymous handler in bridge.ts |
| pi-harness | POST | /reset | anonymous handler in bridge.ts |

**Missing from implementation (documented in ARCHITECTURE-Core.md but never built):**

| Container | Method | Path | Status |
|-----------|--------|------|--------|
| sentinel-core | GET | /status | NOT IMPLEMENTED |
| sentinel-core | GET | /context/{user_id} | NOT IMPLEMENTED |

---

## 2. Duplicates Registry

Every duplicate listed below must be resolved. Resolution means one canonical implementation exists and all consumers use it.

### DUP-01: `call_core()` — Interface → Core HTTP Client

**Locations:**
- `interfaces/discord/bot.py` lines ~200–230: `call_core(user_id, message)`
- `interfaces/imessage/bridge.py` lines ~90–120: `call_core(client, user_id, content)`

**What's duplicated:** Both implement the same pattern — POST to `SENTINEL_CORE_URL/message` with `X-Sentinel-Key` header, 200s timeout, identical error handling for 401, 422, timeout, and connection errors. Both return user-facing error strings.

**Resolution:** Extract to a shared module `shared/sentinel_client.py` that both interfaces import. The module provides a single `SentinelCoreClient` class with one `async def send_message(user_id: str, content: str) -> str` method containing the canonical implementation.

**File to create:** `shared/sentinel_client.py`
**Files to modify:** `interfaces/discord/bot.py`, `interfaces/imessage/bridge.py`

---

### DUP-02: ObsidianClient Graceful Error Handling

**Location:** `sentinel-core/app/clients/obsidian.py` — 5 methods repeat identical try/except patterns:

| Method | Default Return on Error |
|--------|------------------------|
| `check_health()` | `False` |
| `get_user_context()` | `None` |
| `read_self_context()` | `""` |
| `get_recent_sessions()` | `[]` |
| `search_vault()` | `[]` |

**What's duplicated:** Every method wraps its HTTP call in a try/except that catches `Exception`, logs a warning, and returns a type-specific default value.

**Resolution:** Extract a private helper method `_safe_request()` that accepts a coroutine, a default return value, and an operation name for logging. All 5 methods delegate to it.

```python
async def _safe_request(self, coro, default, operation: str):
    try:
        return await coro
    except Exception as exc:
        logger.warning("%s failed: %s", operation, exc)
        return default
```

**File to modify:** `sentinel-core/app/clients/obsidian.py`

---

### DUP-03: Retry Strategy Configuration

**Locations:**
- `sentinel-core/app/clients/pi_adapter.py`: `@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=4), retry=...)`
- `sentinel-core/app/clients/litellm_provider.py`: `@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=4), retry=...)`

**What's duplicated:** Identical retry parameters (3 attempts, 1s–4s exponential backoff) applied to different error sets.

**Resolution:** Define a shared retry configuration in `sentinel-core/app/clients/retry_config.py`:

```python
STANDARD_RETRY_STOP = stop_after_attempt(3)
STANDARD_RETRY_WAIT = wait_exponential(multiplier=1, min=1, max=4)
HARD_TIMEOUT_SECONDS = 30
```

Both `pi_adapter.py` and `litellm_provider.py` import from this module. The retry error sets remain different per client (that is correct — they handle different exceptions). Only the timing parameters are unified.

**File to create:** `sentinel-core/app/clients/retry_config.py`
**Files to modify:** `sentinel-core/app/clients/pi_adapter.py`, `sentinel-core/app/clients/litellm_provider.py`

---

### DUP-04: Stub Provider Implementations

**Locations:**
- `sentinel-core/app/clients/ollama_provider.py`: `OllamaProvider.complete()` raises `NotImplementedError`
- `sentinel-core/app/clients/llamacpp_provider.py`: `LlamaCppProvider.complete()` raises `NotImplementedError`

**What's duplicated:** Both are identical stub patterns. Both providers can use LiteLLM's unified interface (Ollama via `ollama/<model>`, llama.cpp via `openai/<model>`). There is no reason for separate provider classes.

**Resolution:** Delete both files. Route Ollama and llama.cpp through `LiteLLMProvider` with different model strings, which is how the architecture already handles LM Studio and Claude. Update `main.py` lifespan to instantiate `LiteLLMProvider` for all four backends:

| ai_provider | LiteLLM model_string | api_base |
|-------------|---------------------|----------|
| lmstudio | `openai/{model_name}` | `settings.lmstudio_base_url` |
| claude | `{settings.claude_model}` | None (uses ANTHROPIC_API_KEY) |
| ollama | `ollama/{settings.ollama_model}` | `settings.ollama_base_url` |
| llamacpp | `openai/{settings.llamacpp_model}` | `settings.llamacpp_base_url` |

**Files to delete:** `sentinel-core/app/clients/ollama_provider.py`, `sentinel-core/app/clients/llamacpp_provider.py`
**Files to modify:** `sentinel-core/app/main.py`, `sentinel-core/app/clients/__init__.py`

---

### DUP-05: Docker Compose Orchestration Strategy Contradiction

**Locations:**
- `docker-compose.yml` (root): Uses `include` directive (Compose v2.20+) — correct per project decisions
- `sentinel.sh`: Uses `-f` flag stacking — directly contradicts the project decision "never use -f stacking; use include only"

**What's duplicated/contradicted:** Two conflicting composition strategies. The root `docker-compose.yml` includes `sentinel-core/compose.yml`, `pi-harness/compose.yml`, and `interfaces/discord/compose.yml` via `include`. Meanwhile `sentinel.sh` stacks `-f` flags for override files that don't exist yet.

**Resolution:** Rewrite `sentinel.sh` to work with the `include` directive by writing a temporary override compose file that includes only the requested modules, or — simpler — convert to Docker Compose profiles. Each optional service (discord, imessage, pathfinder, music, finance, trader, coder) gets a `profiles: [discord]` key in the compose file, and `sentinel.sh` translates flags to `--profile` arguments.

**Files to modify:** `docker-compose.yml`, `sentinel.sh`
**Files to modify in each interface/module:** Add `profiles:` key to compose.yml

---

## 3. Stubs and Incomplete Code Registry

Every item below must be completed (implemented, tested, wired) or explicitly removed with justification. No `NotImplementedError`, no `pass`, no `# TODO`, no `# FIXME`.

### STUB-01: OllamaProvider (NotImplementedError)

**File:** `sentinel-core/app/clients/ollama_provider.py`
**Resolution:** Eliminated by DUP-04 (routed through LiteLLMProvider).

---

### STUB-02: LlamaCppProvider (NotImplementedError)

**File:** `sentinel-core/app/clients/llamacpp_provider.py`
**Resolution:** Eliminated by DUP-04 (routed through LiteLLMProvider).

---

### STUB-03: SEC-04 — Jailbreak Resistance Baseline

**Requirement:** SEC-04 in REQUIREMENTS.md — "Jailbreak resistance baseline documented"
**Status:** Unchecked. Automated pen test agent not wired.
**Resolution:** Implement SEC-04 fully. This means:
1. Create `security/pentest/jailbreak_baseline.py` — a test suite that sends known jailbreak prompts through POST /message and asserts that InjectionFilter catches them
2. Document baseline results in `security/JAILBREAK-BASELINE.md`
3. Add `pentest` service to docker-compose.yml (or as a pytest fixture)
4. Check the SEC-04 box in REQUIREMENTS.md

---

### STUB-04: Discord Bot Thread Persistence Tests (RED)

**File:** `sentinel-core/tests/test_bot_thread_persistence.py`
**Status:** All 3 tests are RED stubs expecting functionality from Plan 10-02.
**Resolution:** The implementation exists in `interfaces/discord/bot.py` (`_persist_thread_id`, `setup_hook` thread loading). These tests stub discord.py but never actually test the implemented code. Fix the tests to cover the real implementation, or if the implementation is incomplete, complete it. Zero RED tests at v0.40.

---

### STUB-05: iMessage attributedBody Decoding (Ventura+)

**File:** `interfaces/imessage/bridge.py` line ~70
**Status:** `poll_new_messages()` skips messages that have `attributedBody` but no `text` field (macOS Ventura+ changed where message body lives). This silently drops messages.
**Resolution:** Implement attributedBody extraction. The `imessage_reader` library handles Ventura+ `attributedBody` parsing. Add it as a dependency and decode `attributedBody` when `text` is NULL.

---

### STUB-06: Missing REST Endpoints (Documented but Not Implemented)

**Architecture doc** (`docs/ARCHITECTURE-Core.md`) specifies:
- `GET /status` — system status (Pi? Obsidian? LM Studio reachable?)
- `GET /context/{user_id}` — retrieve recent context for debugging

**Neither endpoint exists in code.**

**Resolution:** Implement both endpoints in `sentinel-core/app/routes/`:
1. `GET /status` — returns JSON with reachability status of Pi harness, Obsidian, and the configured AI provider. Requires X-Sentinel-Key.
2. `GET /context/{user_id}` — returns the current context that would be built for a given user_id (self/ files, recent sessions, search results). Requires X-Sentinel-Key. Useful for debugging.

---

### STUB-07: Empty Directories (security/, modules/)

**Locations:**
- `security/` — contains only `__pycache__`, no source files
- `modules/` — contains only `.gitkeep`

**Resolution:**
- `security/` → This is where SEC-04 jailbreak baseline lands (STUB-03). Create proper package structure: `security/__init__.py`, `security/pentest/jailbreak_baseline.py`, `security/JAILBREAK-BASELINE.md`.
- `modules/` → This directory is the future home for Phase 11+ modules (Pathfinder, Music, etc.). These are **not v0.40 scope**. Keep `.gitkeep`. Add a `modules/README.md` explaining the module contract and referencing `docs/MODULE-SPEC.md`.

---

### STUB-08: sentinel.sh References to Non-Existent Module Overrides

**File:** `sentinel.sh`
**Status:** References 5 override files that don't exist:
- `interfaces/messages/docker-compose.override.yml`
- `modules/music/docker-compose.override.yml`
- `modules/finance/docker-compose.override.yml`
- `modules/trader/docker-compose.override.yml`
- `modules/pathfinder/docker-compose.override.yml`
- `modules/coder/docker-compose.override.yml`

**Resolution:** Resolved by DUP-05 (rewrite sentinel.sh to use profiles). Flags for modules that don't exist yet should print a warning and exit, not silently proceed.

---

## 4. Architecture Contradictions Registry

### CONTRA-01: Message Envelope Mismatch

**In code** (`sentinel-core/app/models.py`):
```python
class MessageEnvelope(BaseModel):
    content: str
    user_id: str = "default"
```

**In architecture doc** (`docs/ARCHITECTURE-Core.md`):
```json
{
  "id": "uuid-v4",
  "source": "discord",
  "user_id": "user-identifier",
  "channel_id": "channel-identifier",
  "timestamp": "2026-04-06T12:00:00Z",
  "content": "user message text",
  "attachments": [],
  "metadata": {}
}
```

**The code envelope has 2 fields. The documented envelope has 8 fields.**

**Resolution:** Pick one and make them match. For v0.40 pre-beta, the minimal envelope (content + user_id) is sufficient. Update the architecture doc to reflect reality, or expand the Pydantic model to match the doc. Recommendation: expand the model to include `source` and `channel_id` as optional fields (useful for multi-interface routing). Leave `id`, `timestamp`, `attachments`, `metadata` as optional fields that interfaces may provide. The ResponseEnvelope should similarly be expanded or the doc updated.

---

### CONTRA-02: Pi Harness Port Mismatch

**In code** (`pi-harness/compose.yml`): Port 3000
**In architecture doc** (`docs/ARCHITECTURE-Core.md`): Port 8765

**Resolution:** Code is authoritative. Port is 3000. Update the architecture doc to say 3000.

---

### CONTRA-03: Context Read Paths Mismatch

**In code** (`sentinel-core/app/routes/message.py`):
```python
_SELF_PATHS = [
    "self/identity.md",
    "self/methodology.md",
    "self/goals.md",
    "self/relationships.md",
    "ops/reminders.md",
]
```
Reads 5 files in parallel.

**In architecture doc** (`docs/obsidian-lifebook-design.md`):
```
get_self_context() concatenates 3 files:
1. self/identity.md
2. self/goals.md
3. self/relationships.md
```
Says 3 files.

**Resolution:** Code is authoritative (5 files is correct — methodology and reminders were added later). Update the design doc.

---

### CONTRA-04: Session Summary Path Mismatch

**In code** (`sentinel-core/app/routes/message.py`):
```python
path = f"ops/sessions/{date_str}/{user_id}-{time_str}.md"
```

**In architecture doc** (`docs/ARCHITECTURE-Core.md`):
```
/core/sessions/{YYYY-MM-DD}/{user_id}-{HH-MM-SS}.md
```

**Resolution:** Code is authoritative (`ops/sessions/` not `core/sessions/`). Update the architecture doc.

---

## 5. Refactoring Directives

### RD-01: Create Shared Interface Client Library

**Goal:** Eliminate DUP-01 and establish the canonical way interfaces talk to Sentinel Core.

**Create:** `shared/sentinel_client.py`

```python
"""Canonical HTTP client for Sentinel Core — used by all interfaces."""

import httpx
import logging

logger = logging.getLogger(__name__)

class SentinelCoreClient:
    """Single interface for all interface containers to call Sentinel Core."""

    def __init__(self, base_url: str, api_key: str, timeout: float = 200.0):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    async def send_message(
        self,
        user_id: str,
        content: str,
        client: httpx.AsyncClient,
    ) -> str:
        """Send a message to Sentinel Core and return the AI response text.
        
        Returns a user-facing error string on failure (never raises).
        """
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
            if status == 401:
                logger.error("Auth mismatch — check SENTINEL_API_KEY")
                return "Authentication error. Check configuration."
            if status == 422:
                logger.warning("Context too long for model window")
                return "Your message plus context is too long. Try a shorter message."
            logger.error("Core returned HTTP %d: %s", status, exc.response.text)
            return f"Something went wrong (HTTP {status})."
        except httpx.ConnectError:
            logger.error("Cannot reach Sentinel Core at %s", self._base_url)
            return "Cannot reach the Sentinel. Is sentinel-core running?"
        except Exception as exc:
            logger.exception("Unexpected error calling Core: %s", exc)
            return "An unexpected error occurred."
```

**Modify:** `interfaces/discord/bot.py` — replace inline `call_core()` with `SentinelCoreClient.send_message()`
**Modify:** `interfaces/imessage/bridge.py` — replace inline `call_core()` with `SentinelCoreClient.send_message()`

---

### RD-02: Consolidate AI Providers to LiteLLM Only

**Goal:** Eliminate DUP-04 (stub providers). One provider class handles all backends.

**Delete:** `sentinel-core/app/clients/ollama_provider.py`
**Delete:** `sentinel-core/app/clients/llamacpp_provider.py`

**Modify:** `sentinel-core/app/main.py` lifespan — build provider map using only `LiteLLMProvider`:

```python
_provider_map = {
    "lmstudio": LiteLLMProvider(
        model_string=f"openai/{settings.model_name}",
        api_base=settings.lmstudio_base_url,
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

**Modify:** `sentinel-core/app/clients/__init__.py` — remove imports for deleted modules.

---

### RD-03: Extract Retry Configuration

**Goal:** Eliminate DUP-03. Single source of truth for retry timing.

**Create:** `sentinel-core/app/clients/retry_config.py`

```python
"""Shared retry configuration for all HTTP clients (PROV-03)."""

from tenacity import stop_after_attempt, wait_exponential

RETRY_ATTEMPTS = 3
RETRY_STOP = stop_after_attempt(RETRY_ATTEMPTS)
RETRY_WAIT = wait_exponential(multiplier=1, min=1, max=4)
HARD_TIMEOUT_SECONDS = 30
```

**Modify:** `sentinel-core/app/clients/pi_adapter.py` — import from retry_config
**Modify:** `sentinel-core/app/clients/litellm_provider.py` — import from retry_config

---

### RD-04: Extract ObsidianClient Error Helper

**Goal:** Eliminate DUP-02. One error-handling pattern for all vault calls.

**Modify:** `sentinel-core/app/clients/obsidian.py` — add `_safe_request()`:

```python
async def _safe_request(self, coro, default, operation: str):
    """Execute a coroutine, returning default on any failure."""
    try:
        return await coro
    except Exception as exc:
        if not isinstance(default, bool):  # Don't log 404s for check_health
            logger.warning("%s failed: %s", operation, exc)
        return default
```

Refactor all 5 methods to use `_safe_request()` while preserving the specific behavior of each (e.g., `read_self_context` returns `""` silently on 404, `get_user_context` logs on non-404 errors).

---

### RD-05: Implement Missing REST Endpoints

**Goal:** Eliminate STUB-06. Code matches architecture doc.

**Create:** `sentinel-core/app/routes/status.py`

```python
"""System status and debug endpoints."""

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

router = APIRouter()

@router.get("/status")
async def system_status(request: Request) -> JSONResponse:
    """Report reachability of all backend services."""
    obsidian = request.app.state.obsidian
    pi = request.app.state.pi_adapter
    
    obsidian_ok = await obsidian.check_health()
    # Pi health: try GET /health
    pi_ok = False
    try:
        resp = await request.app.state.http_client.get(
            f"{request.app.state.pi_url}/health", timeout=5.0
        )
        pi_ok = resp.status_code == 200
    except Exception:
        pass

    return JSONResponse({
        "status": "ok" if (obsidian_ok and pi_ok) else "degraded",
        "obsidian": "ok" if obsidian_ok else "unreachable",
        "pi_harness": "ok" if pi_ok else "unreachable",
        "ai_provider": request.app.state.ai_provider_name,
    })

@router.get("/context/{user_id}")
async def debug_context(request: Request, user_id: str) -> JSONResponse:
    """Return the context that would be built for a user (debug endpoint)."""
    obsidian = request.app.state.obsidian
    self_paths = [
        "self/identity.md", "self/methodology.md",
        "self/goals.md", "self/relationships.md", "ops/reminders.md",
    ]
    import asyncio
    results = await asyncio.gather(
        *[obsidian.read_self_context(p) for p in self_paths],
        return_exceptions=True,
    )
    context_files = {
        path: text for path, text in zip(self_paths, results)
        if isinstance(text, str) and text
    }
    sessions = await obsidian.get_recent_sessions(user_id)
    
    return JSONResponse({
        "user_id": user_id,
        "context_files": context_files,
        "recent_sessions_count": len(sessions),
    })
```

**Modify:** `sentinel-core/app/main.py` — include status router, protect both with APIKeyMiddleware.

---

### RD-06: Rewrite sentinel.sh to Use Docker Compose Profiles

**Goal:** Eliminate DUP-05 and STUB-08. One composition strategy (include + profiles).

**Modify:** Each optional service's compose.yml adds a `profiles` key:

```yaml
# interfaces/discord/compose.yml
services:
  discord:
    profiles: ["discord"]
    # ... rest of service config
```

**Rewrite:** `sentinel.sh`:

```bash
#!/bin/bash
# Sentinel of Mnemosyne — Docker Compose wrapper
set -euo pipefail

PROFILES=()
ARGS=()

for arg in "$@"; do
  case "$arg" in
    --discord)    PROFILES+=("discord") ;;
    --imessage)   echo "iMessage runs natively on Mac, not in Docker." && exit 1 ;;
    --pathfinder) PROFILES+=("pathfinder") ;;
    --music)      PROFILES+=("music") ;;
    --finance)    PROFILES+=("finance") ;;
    --trader)     PROFILES+=("trader") ;;
    --coder)      PROFILES+=("coder") ;;
    *)            ARGS+=("$arg") ;;
  esac
done

PROFILE_FLAGS=""
for p in "${PROFILES[@]}"; do
  PROFILE_FLAGS="$PROFILE_FLAGS --profile $p"
done

docker compose $PROFILE_FLAGS "${ARGS[@]}"
```

---

### RD-07: Implement SEC-04 Jailbreak Baseline

**Goal:** Eliminate STUB-03. Complete all security requirements.

**Create:** `security/__init__.py`
**Create:** `security/pentest/__init__.py`
**Create:** `security/pentest/jailbreak_baseline.py` — pytest suite that sends known jailbreak prompts through InjectionFilter and asserts they're caught. Include at minimum:
- The 19 patterns already in `_INJECTION_PATTERNS`
- 10 additional adversarial prompts from OWASP LLM Top 10
- Homoglyph variants (Cyrillic lookalikes)
- Unicode normalization bypass attempts
- Multi-language injection attempts

**Create:** `security/JAILBREAK-BASELINE.md` — documents the baseline results, what's caught, what's not, and the plan for what's not caught.

**Modify:** `.planning/REQUIREMENTS.md` — check the SEC-04 box after implementation passes.

---

### RD-08: Fix iMessage attributedBody Decoding

**Goal:** Eliminate STUB-05. No silently dropped messages.

**Modify:** `interfaces/imessage/bridge.py`

Add `imessage_reader` as a dependency. When `text` is NULL but `attributedBody` is present, decode using `imessage_reader`'s Ventura+ parser:

```python
from imessage_reader.fetch_data import FetchData

def _decode_attributed_body(blob: bytes) -> str | None:
    """Decode macOS Ventura+ attributedBody blob to plain text."""
    try:
        # attributedBody is a NSKeyedArchiver plist with the text buried inside
        import plistlib
        plist = plistlib.loads(blob)
        # The text is in the NS.string key of the root object
        return plist.get("NS.string", None)
    except Exception:
        return None
```

Update `poll_new_messages()` to attempt attributedBody decoding before skipping.

---

### RD-09: Fix Discord Thread Persistence Tests

**Goal:** Eliminate STUB-04. Zero RED tests.

**File:** `sentinel-core/tests/test_bot_thread_persistence.py`

The implementation already exists in `interfaces/discord/bot.py`. The test file is in the wrong directory (sentinel-core/tests/ instead of interfaces/discord/tests/) and uses incorrect mocking. Resolution:

1. Move tests to `interfaces/discord/tests/test_thread_persistence.py`
2. Update mocks to match the actual `_persist_thread_id()` and `setup_hook()` implementations
3. All 3 tests must be GREEN

---

### RD-10: Synchronize Architecture Docs with Code

**Goal:** Eliminate CONTRA-01 through CONTRA-04. Documentation matches implementation exactly.

**Modify:** `docs/ARCHITECTURE-Core.md`:
- Update Message Envelope spec to match `models.py` (add note about optional fields)
- Change Pi harness port from 8765 to 3000
- Change session path from `/core/sessions/` to `/ops/sessions/`
- Update endpoints list to include /status and /context/{user_id}

**Modify:** `docs/obsidian-lifebook-design.md`:
- Update get_self_context to show 5 files (add methodology.md and reminders.md)

**Modify:** `sentinel-core/app/models.py`:
- Add optional fields to MessageEnvelope: `source`, `channel_id`

---

## 6. Container Engine Contracts

Each container has exactly one engine — the single entry point that owns the event loop, wires dependencies, and exposes the API surface.

### Sentinel Core Engine: `app/main.py`

**Responsibilities:**
1. Create shared httpx.AsyncClient (singleton, connection pooling)
2. Build model registry (live fetch + seed fallback)
3. Instantiate all AI providers via LiteLLMProvider (no stubs)
4. Wire ProviderRouter (primary + optional fallback)
5. Create PiAdapterClient
6. Create ObsidianClient
7. Instantiate security services (InjectionFilter, OutputScanner)
8. Register all route modules (/message, /health, /status, /context)
9. Register APIKeyMiddleware
10. Graceful shutdown (close httpx client)

**Must not contain:** Business logic, direct HTTP calls, AI inference calls.

### Pi Harness Engine: `src/bridge.ts`

**Responsibilities:**
1. Spawn Pi subprocess via `pi-adapter.ts`
2. Create Fastify instance with routes (/prompt, /health, /reset)
3. Health monitoring of Pi subprocess
4. Message serialization (JSONL, manual \n splitting)

**Must not contain:** AI provider logic, Obsidian logic, user identity logic.

### Discord Interface Engine: `bot.py`

**Responsibilities:**
1. Initialize discord.Client with intents
2. Register slash commands (/sentask)
3. Load persisted thread IDs from Obsidian on startup
4. Route subcommands to prompt templates
5. Call Sentinel Core via `SentinelCoreClient` (from shared/)
6. Manage thread lifecycle (create, persist, respond)

**Must not contain:** AI inference, vault reads/writes (beyond thread persistence), token counting.

### iMessage Interface Engine: `bridge.py`

**Responsibilities:**
1. Poll chat.db for new incoming messages
2. Decode message text (including Ventura+ attributedBody)
3. Call Sentinel Core via `SentinelCoreClient` (from shared/)
4. Send replies via macpymessenger
5. Feature flag guard (IMESSAGE_ENABLED)

**Must not contain:** AI inference, vault reads/writes, Discord logic.

---

## 7. REST API Route Registry

The complete, authoritative list of REST API routes across all containers. No route exists outside this table. No route appears twice.

### Sentinel Core (port 8000)

| Method | Path | Auth Required | Handler Module | Purpose |
|--------|------|---------------|----------------|---------|
| POST | /message | Yes (X-Sentinel-Key) | routes/message.py | Accept message, return AI response |
| GET | /health | No | main.py | Container health check |
| GET | /status | Yes (X-Sentinel-Key) | routes/status.py | System-wide service reachability |
| GET | /context/{user_id} | Yes (X-Sentinel-Key) | routes/status.py | Debug: show context for user |

### Pi Harness (port 3000, internal only)

| Method | Path | Auth Required | Handler Module | Purpose |
|--------|------|---------------|----------------|---------|
| POST | /prompt | No (internal network) | bridge.ts | Forward message to Pi subprocess |
| GET | /health | No (internal network) | bridge.ts | Pi subprocess health |
| POST | /reset | No (internal network) | bridge.ts | Reset Pi session |

### Discord Interface (no exposed port)

No HTTP routes. Uses Discord WebSocket gateway + slash commands.

### iMessage Interface (no exposed port)

No HTTP routes. Polls SQLite database.

---

## 8. Function Design Registry

Every public function in the codebase, its canonical location, and its contract. If a function appears in this table, it exists exactly once. If a function does not appear in this table, it does not exist in the codebase.

### Sentinel Core — Routes

| Function | Module | Signature | Returns | Side Effects |
|----------|--------|-----------|---------|--------------|
| `post_message` | routes/message.py | `(envelope: MessageEnvelope, request: Request, background_tasks: BackgroundTasks) -> ResponseEnvelope` | ResponseEnvelope | Writes session summary (background) |
| `health` | main.py | `(request: Request) -> JSONResponse` | `{"status": "ok", "obsidian": ...}` | None |
| `system_status` | routes/status.py | `(request: Request) -> JSONResponse` | `{"status": ..., "obsidian": ..., "pi_harness": ..., "ai_provider": ...}` | None |
| `debug_context` | routes/status.py | `(request: Request, user_id: str) -> JSONResponse` | `{"user_id": ..., "context_files": ..., "recent_sessions_count": ...}` | None |

### Sentinel Core — Services

| Function/Method | Module | Signature | Returns | Raises |
|----------------|--------|-----------|---------|--------|
| `InjectionFilter.sanitize` | services/injection_filter.py | `(text: str) -> tuple[str, bool]` | (sanitized_text, was_modified) | Never |
| `InjectionFilter.wrap_context` | services/injection_filter.py | `(context: str) -> str` | Framed + sanitized context | Never |
| `InjectionFilter.filter_input` | services/injection_filter.py | `(user_input: str) -> tuple[str, bool]` | (sanitized_input, was_modified) | Never |
| `OutputScanner.scan` | services/output_scanner.py | `(response: str) -> tuple[bool, str \| None]` | (is_safe, reason) | Never (fail-open) |
| `ProviderRouter.complete` | services/provider_router.py | `(messages: list[dict]) -> str` | AI response text | ProviderUnavailableError |
| `build_model_registry` | services/model_registry.py | `(settings, http_client) -> dict[str, ModelInfo]` | Model registry dict | Never (non-fatal) |
| `count_tokens` | services/token_guard.py | `(messages: list[dict]) -> int` | Token count | Never |
| `check_token_limit` | services/token_guard.py | `(messages: list[dict], context_window: int) -> None` | None | TokenLimitError |

### Sentinel Core — Clients

| Function/Method | Module | Signature | Returns | Raises |
|----------------|--------|-----------|---------|--------|
| `LiteLLMProvider.complete` | clients/litellm_provider.py | `(messages: list[dict]) -> str` | AI response text | litellm errors (after 3 retries) |
| `get_context_window_from_lmstudio` | clients/litellm_provider.py | `(client, base_url, model_name) -> int` | Context window int | Never (returns 4096 default) |
| `fetch_anthropic_models` | clients/anthropic_registry.py | `(api_key: str) -> dict` | Model info dict | Never (returns {}) |
| `PiAdapterClient.send_messages` | clients/pi_adapter.py | `(messages: list[dict]) -> str` | AI response text | httpx errors (after 3 retries) |
| `PiAdapterClient.reset_session` | clients/pi_adapter.py | `() -> None` | None | Never |
| `ObsidianClient.check_health` | clients/obsidian.py | `() -> bool` | True/False | Never |
| `ObsidianClient.read_self_context` | clients/obsidian.py | `(path: str) -> str` | File content or "" | Never |
| `ObsidianClient.get_user_context` | clients/obsidian.py | `(user_id: str) -> str \| None` | File content or None | Never |
| `ObsidianClient.get_recent_sessions` | clients/obsidian.py | `(user_id: str, limit: int) -> list[str]` | List of session texts | Never |
| `ObsidianClient.write_session_summary` | clients/obsidian.py | `(path: str, content: str) -> None` | None | httpx errors (caller catches) |
| `ObsidianClient.search_vault` | clients/obsidian.py | `(query: str) -> list[dict]` | Search results or [] | Never |

### Sentinel Core — Private Helpers (not part of public API but must exist exactly once)

| Function | Module | Purpose |
|----------|--------|---------|
| `_truncate_to_tokens` | routes/message.py | Truncate text to token budget |
| `_format_search_results` | routes/message.py | Format vault search results as markdown |
| `_write_session_summary` | routes/message.py | Background task: write session to Obsidian |
| `_log_leak_incident` | routes/message.py | Background task: log security incident |
| `_safe_request` | clients/obsidian.py | Graceful error wrapper for vault calls |

### Pi Harness

| Function | Module | Purpose |
|----------|--------|---------|
| `buildApp` | bridge.ts | Create Fastify instance with routes |
| `start` | bridge.ts | Spawn Pi, start Fastify server |
| `serializeMessages` | bridge.ts | Convert message array to JSONL for Pi RPC |
| `spawnPi` | pi-adapter.ts | Spawn pi binary in RPC mode |
| `sendPrompt` | pi-adapter.ts | Send message to Pi, return response |
| `getPiHealth` | pi-adapter.ts | Return Pi subprocess status |
| `sendReset` | pi-adapter.ts | Send new_session command to Pi |
| `extractText` | pi-adapter.ts | Handle dual-format Pi content |
| `handleEvent` | pi-adapter.ts | Process Pi RPC events |
| `drainQueue` | pi-adapter.ts | FIFO queue processor |

### Shared Library

| Function/Method | Module | Purpose |
|----------------|--------|---------|
| `SentinelCoreClient.send_message` | shared/sentinel_client.py | Canonical HTTP call to POST /message |

### Discord Interface

| Function/Method | Module | Purpose |
|----------------|--------|---------|
| `SentinelBot.__init__` | bot.py | Initialize Discord client |
| `SentinelBot.setup_hook` | bot.py | Sync commands, load thread IDs |
| `SentinelBot.on_ready` | bot.py | Log ready state |
| `SentinelBot.on_message` | bot.py | Handle messages in tracked threads |
| `sentask` | bot.py | Slash command handler |
| `handle_sentask_subcommand` | bot.py | Route subcommands to prompts |
| `_persist_thread_id` | bot.py | Write thread ID to Obsidian |

### iMessage Interface

| Function | Module | Purpose |
|----------|--------|---------|
| `sanitize_imessage_handle` | bridge.py | Convert phone/email to user_id |
| `poll_new_messages` | bridge.py | Query chat.db for new messages |
| `send_imessage_reply` | bridge.py | Send reply via macpymessenger |
| `run_bridge` | bridge.py | Main polling loop |
| `_decode_attributed_body` | bridge.py | Ventura+ attributedBody parser |

---

## 9. Test Coverage Requirements

Every module listed in Section 8 must have corresponding tests. No test may be RED at v0.40.

### Required Test Files

| Test File | Tests Module | Minimum Coverage |
|-----------|-------------|-----------------|
| sentinel-core/tests/test_message.py | routes/message.py | POST /message success, 401, 422, 502, 503; background tasks |
| sentinel-core/tests/test_auth.py | main.py (middleware) | Missing key, wrong key, health bypass, valid key |
| sentinel-core/tests/test_status.py | routes/status.py | GET /status with all-up, degraded; GET /context/{user_id} |
| sentinel-core/tests/test_provider_router.py | services/provider_router.py | Primary success, fallback on ConnectError, both fail |
| sentinel-core/tests/test_litellm_provider.py | clients/litellm_provider.py | Success, retries, no-retry on auth error, context window fetch |
| sentinel-core/tests/test_pi_adapter.py | clients/pi_adapter.py | Success, retries, timeout, HTTP error passthrough |
| sentinel-core/tests/test_obsidian_client.py | clients/obsidian.py | All 6 public methods, graceful degradation |
| sentinel-core/tests/test_injection_filter.py | services/injection_filter.py | All 19 patterns, homoglyphs, wrap_context, filter_input |
| sentinel-core/tests/test_output_scanner.py | services/output_scanner.py | All 7 secret patterns, fail-open, excerpt extraction |
| sentinel-core/tests/test_token_guard.py | services/token_guard.py | Limit exceeded, normal pass, multi-message |
| sentinel-core/tests/test_model_registry.py | services/model_registry.py | Live fetch, seed fallback, missing provider |
| sentinel-core/tests/test_ai_agnostic_guardrail.py | (meta) | No vendor imports in app/ |
| interfaces/discord/tests/test_thread_persistence.py | bot.py | Load on startup, 404 graceful, persist on creation |
| interfaces/discord/tests/test_subcommands.py | bot.py | Subcommand routing, unknown command handling |
| interfaces/imessage/tests/test_bridge.py | bridge.py | Poll messages, attributedBody decode, sanitize handle |
| shared/tests/test_sentinel_client.py | sentinel_client.py | Success, timeout, 401, 422, connection error |
| security/pentest/jailbreak_baseline.py | injection_filter.py | 30+ jailbreak prompts tested against filter |
| pi-harness/src/bridge.test.ts | bridge.ts | /prompt, /health, /reset |

---

## 10. Acceptance Criteria

v0.40 pre-beta ships when ALL of the following are true:

1. **Zero duplicates:** Every item in Section 2 is resolved. `grep -rn "def call_core"` returns exactly 0 results in interfaces/. `grep -rn "NotImplementedError"` returns exactly 0 results in app/.
2. **Zero stubs:** Every item in Section 3 is resolved. No `NotImplementedError`, no `pass`-as-placeholder, no `# TODO`, no `# FIXME` in any production source file.
3. **Zero RED tests:** `pytest` in sentinel-core exits 0. `vitest run` in pi-harness exits 0. All test files listed in Section 9 exist and pass.
4. **Zero architecture contradictions:** Every item in Section 4 is resolved. Documentation matches code.
5. **Route registry match:** `grep -rn "@router\|@app\." sentinel-core/app/` produces exactly the 4 routes in Section 7. Pi-harness has exactly 3 routes.
6. **Engine contract:** Each container has exactly one engine file as defined in Section 6. No container has two entry points.
7. **Shared library:** `shared/sentinel_client.py` exists and is imported by both interfaces. No inline `call_core()` remains.
8. **SEC-04 complete:** `security/pentest/jailbreak_baseline.py` passes. `security/JAILBREAK-BASELINE.md` exists. SEC-04 checkbox checked in REQUIREMENTS.md.
9. **Docker Compose clean:** `docker compose config` succeeds with no warnings. `sentinel.sh --discord up -d` starts exactly sentinel-core + pi-harness + discord.
10. **Function registry match:** Every public function in Section 8 exists in exactly the listed module. No public function exists outside this registry.

---

## Execution Order

This is the recommended order for implementing the directives. Dependencies flow downward.

| Order | Directive | Depends On | Estimated Effort |
|-------|-----------|-----------|------------------|
| 1 | RD-03: Extract retry config | Nothing | Small |
| 2 | RD-04: Extract ObsidianClient error helper | Nothing | Small |
| 3 | RD-02: Consolidate providers to LiteLLM | RD-03 | Medium |
| 4 | RD-01: Create shared interface client | Nothing | Medium |
| 5 | RD-05: Implement /status and /context endpoints | Nothing | Medium |
| 6 | RD-06: Rewrite sentinel.sh to profiles | Nothing | Small |
| 7 | RD-08: Fix iMessage attributedBody | Nothing | Small |
| 8 | RD-09: Fix thread persistence tests | Nothing | Small |
| 9 | RD-07: Implement SEC-04 jailbreak baseline | Nothing | Medium |
| 10 | RD-10: Synchronize architecture docs | RD-02, RD-05 | Medium |

**Total items: 10 directives, 5 duplicates to resolve, 8 stubs to complete, 4 contradictions to fix.**

---

*This directive is immutable. Changes require a new version of this document with a new date and a changelog entry explaining what changed and why.*
