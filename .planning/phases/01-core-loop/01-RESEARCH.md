# Phase 1: Core Loop - Research

**Researched:** 2026-04-10
**Domain:** FastAPI + Pi harness subprocess bridge + LM Studio OpenAI-compatible API + Docker Compose
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **Node.js version:** 22 LTS (`node:22-alpine`) — pi-mono requires >=20.6.0; Node 22 is active LTS until April 2027
- **Pi process model:** Long-lived subprocess per container — Fastify HTTP bridge queues requests via stdin/stdout JSONL; bridge detects stdout close and respawns Pi on crash
- **Deployment topology:** Single Mac Mini — all services use `host.docker.internal`; `LMSTUDIO_BASE_URL=http://host.docker.internal:1234/v1`, `OBSIDIAN_API_URL=http://host.docker.internal:27124`
- **Startup resilience:** Graceful degradation — Core starts immediately; LM Studio unavailable returns 503; Pi crash triggers respawn with backoff
- **Pi version pin:** Exact version required (no range); pin `@mariozechner/pi-coding-agent@0.66.1`
- **Fastify bridge:** Developer-written (~50-100 lines) — NOT provided by pi-mono
- **Docker Compose:** `include` directive (v2.20+) — no `-f` flag stacking

### Claude's Discretion

(None specified in CONTEXT.md)

### Deferred Ideas (OUT OF SCOPE)

- Multi-process Pi pool for concurrent requests — deferred to post-Phase 4
- Split deployment (Docker on separate machine from LM Studio) — user can override via env vars without code changes
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CORE-01 | Pi harness container starts and accepts HTTP POST requests via a Fastify bridge server wrapping the stdin/stdout JSONL subprocess | Pi RPC protocol fully documented: exact JSONL schemas, `agent_end` event signals completion, `\n`-only line splitting required |
| CORE-02 | Pi adapter pattern established — single point of contact with pi-mono, version pinned to exact release, with documented upgrade procedure | `@mariozechner/pi-coding-agent@0.66.1` confirmed latest; releases every 2-4 days require exact pin strategy |
| CORE-03 | Sentinel Core (FastAPI) receives a Message Envelope via POST /message and returns an AI response envelope | FastAPI + Pydantic v2 model pattern documented; httpx AsyncClient for LM Studio calls |
| CORE-04 | LM Studio on Mac Mini confirmed as AI backend — Core can call it and receive a completion response | LM Studio OpenAI-compatible API at `/v1/chat/completions`; models endpoint at `/api/v0/models` with `max_context_length` field |
| CORE-05 | Token count calculated before every LM Studio call; calls rejected if they would exceed context window | tiktoken `cl100k_base` encoding for approximate counts; LM Studio `/api/v0/models/{model}` returns `max_context_length` |
| CORE-06 | `docker compose up` starts the full core system (Core + Pi harness) in a single command | Docker Compose v2 `docker compose up` syntax confirmed; node version and Fastify v5.8.4 verified |
| CORE-07 | Docker Compose `include` directive pattern established in base compose — no module or interface uses `-f` flag stacking | `include` directive introduced in Compose v2.20.0 (Aug 2023); Docker Desktop 4.22; exact YAML syntax documented |
</phase_requirements>

---

## Summary

Phase 1 establishes the end-to-end message path: POST /message → FastAPI Core → Pi harness (Fastify bridge + subprocess) → LM Studio → response. All five research questions are now resolved. The Pi RPC protocol is well-documented with known JSONL framing requirements. The Fastify bridge is a developer-written ~50-100 line Node.js file — not a library — and the design pattern is straightforward: long-lived subprocess, sequential request queue, `agent_end` event as completion signal.

The most critical implementation detail is the **JSONL line splitter**: Node's `readline` must NOT be used because it splits on U+2028 and U+2029 (Unicode line separators that are valid inside JSON strings). Manual `\n`-only splitting is required. The second critical detail is that `@mariozechner/pi-coding-agent` releases 3-4 times per week; the version must be pinned exactly (`0.66.1`) and the adapter layer isolates the rest of the system from any future upgrade changes.

Token counting for LM Studio uses tiktoken with `cl100k_base` encoding (an approximation; the correct tokenizer varies per model, but cl100k_base is the universal safe choice for local models). The `/api/v0/models/{model}` endpoint returns `max_context_length` — fetch this at startup and cache it; do not hardcode context window sizes.

**Primary recommendation:** Build in this order: (1) docker-compose.yml with `include` skeleton, (2) Pi harness container with Fastify bridge, (3) FastAPI Core with `/message` endpoint and LM Studio client, (4) token count guard. Test end-to-end with `curl` before adding health checks or crash recovery.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | >=0.135.0 | HTTP API framework for Sentinel Core | Async-native, Pydantic v2 integration; no alternative for this use case per project constraints |
| Pydantic | >=2.7.0 | Message Envelope models, settings validation | Required by FastAPI; v2 syntax mandatory (`model_config`, not `class Config`) |
| pydantic-settings | >=2.13.0 | Environment variable loading + validation | Loads `.env`, validates at startup, type-safe; replaces `os.getenv()` |
| uvicorn[standard] | >=0.44.0 | ASGI server | `[standard]` extra installs uvloop + httptools for production performance |
| httpx | >=0.28.1 | Async HTTP client for LM Studio calls | Do NOT use `requests` (blocks event loop); httpx is FastAPI's recommended test client too |
| Fastify | 5.8.4 | HTTP bridge server in Pi harness container | Faster than Express, better TypeScript support; per project STACK.md |
| @mariozechner/pi-coding-agent | **0.66.1 (exact pin)** | Pi AI execution layer | Pin exactly — releases every 2-4 days; adapter layer isolates rest of system |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tiktoken | latest stable | Token counting before LM Studio calls | Required for CORE-05; use `cl100k_base` encoding for local model approximation |
| pytest + pytest-asyncio | latest | Test FastAPI async endpoints | Required for all `async def test_*` functions |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| tiktoken (approximation) | transformers AutoTokenizer | AutoTokenizer is exact for each model but requires downloading model files; tiktoken cl100k_base is a safe over-estimate, which is the safer failure mode |
| Fastify | Express | Express works; Fastify is faster and is the project's stated preference |

**Installation (Sentinel Core Python):**
```bash
pip install "fastapi>=0.135.0" "uvicorn[standard]>=0.44.0" "pydantic>=2.7.0" "pydantic-settings>=2.13.0" "httpx>=0.28.1" tiktoken
```

**Installation (Pi harness Node.js):**
```bash
npm install fastify@5.8.4
npm install --save-exact @mariozechner/pi-coding-agent@0.66.1
```

**Version verification:** [VERIFIED: npm registry]
- `@mariozechner/pi-coding-agent@0.66.1` — latest as of 2026-04-08; dist-tags.latest confirmed
- `fastify@5.8.4` — released 2026-03-23; confirmed via `npm view fastify version`

---

## Architecture Patterns

### Recommended Project Structure
```
sentinel-core/
├── app/
│   ├── main.py              # FastAPI app init, lifespan, health
│   ├── config.py            # pydantic-settings Settings class
│   ├── models.py            # MessageEnvelope, ResponseEnvelope (Pydantic v2)
│   ├── routes/
│   │   └── message.py       # POST /message handler
│   ├── clients/
│   │   ├── lmstudio.py      # httpx AsyncClient wrapper for LM Studio
│   │   └── pi_adapter.py    # HTTP client to Pi harness (the adapter layer)
│   └── services/
│       └── token_guard.py   # tiktoken count + context window check
├── tests/
│   ├── conftest.py
│   ├── test_message.py
│   └── test_token_guard.py
├── Dockerfile
├── pyproject.toml
└── .env.example

pi-harness/
├── src/
│   ├── bridge.ts            # Fastify server + Pi subprocess management
│   └── pi-adapter.ts        # All pi-mono imports isolated here
├── package.json             # pin @mariozechner/pi-coding-agent@0.66.1
├── tsconfig.json
└── Dockerfile

docker-compose.yml           # base compose with `include` skeleton
```

### Pattern 1: Pi Subprocess Bridge (Long-Lived Process)

**What:** Fastify HTTP server spawns Pi as a child process at startup. Requests are serialized through a promise queue — Pi processes one prompt at a time. Bridge listens for `agent_end` event on stdout to know the response is complete.

**When to use:** The only pattern for Phase 1. Pi is not concurrent per process.

**Example:**
```typescript
// Source: pi-mono rpc.md + Node.js child_process docs [VERIFIED: rpc.md via WebFetch]
import { spawn, ChildProcess } from 'child_process';

let piProcess: ChildProcess | null = null;
let requestQueue: Array<() => void> = [];
let isProcessing = false;

function spawnPi() {
  piProcess = spawn('pi', ['--mode', 'rpc', '--no-session'], {
    stdio: ['pipe', 'pipe', 'inherit']
  });

  // CRITICAL: do NOT use readline — it splits on U+2028 and U+2029
  // Manual \n splitting only
  let buffer = '';
  piProcess.stdout!.on('data', (chunk: Buffer) => {
    buffer += chunk.toString('utf8');
    const lines = buffer.split('\n');
    buffer = lines.pop()!; // keep incomplete last line
    for (const line of lines) {
      if (line.trim()) handleEvent(JSON.parse(line));
    }
  });

  piProcess.stdout!.on('close', () => {
    // respawn with backoff
    setTimeout(spawnPi, 1000);
  });
}

function sendPrompt(message: string): Promise<string> {
  return new Promise((resolve) => {
    const cmd = JSON.stringify({ type: 'prompt', message }) + '\n';
    piProcess!.stdin!.write(cmd);

    function handleEvent(event: any) {
      if (event.type === 'agent_end') {
        // extract final assistant text from event.messages
        resolve(extractAssistantText(event.messages));
      }
    }
  });
}
```

### Pattern 2: FastAPI Lifespan for Shared HTTP Client

**What:** Use FastAPI's `lifespan` context manager to create a single `httpx.AsyncClient` at startup and close it at shutdown. Attach it to `app.state` so routes can access it.

**When to use:** Any FastAPI app making outbound HTTP calls (LM Studio, later Obsidian).

**Example:**
```python
# Source: FastAPI docs [CITED: fastapi.tiangolo.com/advanced/events/]
from contextlib import asynccontextmanager
from fastapi import FastAPI
import httpx

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(timeout=30.0)
    yield
    await app.state.http_client.aclose()

app = FastAPI(lifespan=lifespan)
```

### Pattern 3: Pydantic v2 Settings

**What:** All configuration from environment variables via `pydantic-settings`. Single `Settings` instance created at import time.

**When to use:** All config — never call `os.getenv()` directly.

**Example:**
```python
# Source: pydantic-settings docs [CITED: docs.pydantic.dev/latest/concepts/pydantic_settings/]
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    lmstudio_base_url: str = "http://host.docker.internal:1234/v1"
    obsidian_api_url: str = "http://host.docker.internal:27124"
    pi_harness_url: str = "http://pi-harness:3000"
    sentinel_key: str  # required, no default — fails fast if missing
    model_name: str = "local-model"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

settings = Settings()
```

### Pattern 4: Docker Compose `include` Directive

**What:** Base `docker-compose.yml` uses `include` to pull in service definitions from module subdirectories. Each included file resolves paths relative to its own location.

**When to use:** Required by CORE-07. All future modules and interfaces use this pattern.

**Example:**
```yaml
# Source: Docker Compose docs [VERIFIED: docs.docker.com/compose/how-tos/multiple-compose-files/include/]
# docker-compose.yml (base)
include:
  - path: sentinel-core/compose.yml
  - path: pi-harness/compose.yml

# For modules in future phases:
# include:
#   - path: interfaces/discord/compose.yml
#   - path: modules/pathfinder/compose.yml
```

### Anti-Patterns to Avoid

- **Using Node `readline` for JSONL parsing:** readline splits on U+2028/U+2029 (valid JSON string chars). Use manual `\n`-only splitting.
- **Importing pi-mono directly from Core:** Pi adapter must be the single point of contact. Never add `@mariozechner/pi-coding-agent` as a dependency of anything except `pi-harness/`.
- **Hardcoding context window size:** Fetch `max_context_length` from `/api/v0/models/{model}` at startup and cache it. Models change.
- **Using `requests` library:** Blocks the async event loop. httpx only.
- **Pydantic v1 syntax:** `class Config: orm_mode = True` will break. Use `model_config = {"from_attributes": True}`.
- **`docker-compose` (hyphen):** Use `docker compose` (space, v2 CLI).
- **Spawning a new Pi process per request:** Pi is a long-lived process; spawning per request wastes ~2-5 seconds startup time and breaks session continuity.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Environment variable loading + validation | `os.getenv()` scattered across codebase | `pydantic-settings` | Silent failures on missing vars; no type safety |
| HTTP client connection pooling | Manual connection management | `httpx.AsyncClient()` as context manager | Connection reuse, timeouts, async-native |
| Token counting for OpenAI-format messages | BPE tokenizer from scratch | `tiktoken` with `cl100k_base` | Handles message format overhead (3 tokens/message + role tokens) |
| JSONL framing | Custom delimiter handling | Manual `\n` split (not readline) | readline breaks on Unicode line separators |
| Request serialization queue | Manual async lock | asyncio.Queue or a simple promise queue | Race conditions are subtle in async code |

**Key insight:** The Fastify bridge is genuinely ~50-100 lines because the hard parts (Pi execution, JSONL framing, session management) are inside pi-mono. The bridge's only job is: receive HTTP → write to Pi stdin → wait for `agent_end` → return HTTP response.

---

## Common Pitfalls

### Pitfall 1: readline() Breaks JSONL Protocol
**What goes wrong:** Using Node's `readline` module to parse Pi stdout produces garbled JSON when assistant responses contain U+2028 (line separator) or U+2029 (paragraph separator), which are valid inside JSON strings.
**Why it happens:** readline treats U+2028 and U+2029 as line boundaries per the ECMAScript spec, even though JSONL uses only `\n`.
**How to avoid:** Buffer stdout manually and split only on `\n`. See code example in Pattern 1 above.
**Warning signs:** JSON parse errors in bridge logs with valid-looking JSON from Pi.

### Pitfall 2: Pi Version Drift
**What goes wrong:** `@mariozechner/pi-coding-agent` releases 3-4 times per week. Without an exact pin, `npm install` will upgrade Pi, breaking the RPC protocol or changing behavior silently.
**Why it happens:** Active development; no semver stability guarantees in 0.x.
**How to avoid:** Pin exactly in `package.json`: `"@mariozechner/pi-coding-agent": "0.66.1"` and commit `package-lock.json`. Upgrade procedure: read release notes, update pin, test bridge contract, commit.
**Warning signs:** `npm install` changes `package-lock.json` Pi version without an explicit version bump in `package.json`.

### Pitfall 3: LM Studio `max_context_length` Not Fetched at Runtime
**What goes wrong:** Hardcoding context window size (e.g., `8192`) works until the user loads a different model. Token guard rejects valid requests or permits oversized ones.
**Why it happens:** LM Studio context length is model-dependent and set in the LM Studio UI, not in code.
**How to avoid:** Fetch `GET /api/v0/models/{model_name}` at Core startup, cache `max_context_length`. If LM Studio is unavailable at startup (graceful degradation), use a conservative default (4096) and log a warning.
**Warning signs:** Token guard rejects short messages, or oversized messages reach the model and fail with a cryptic error.

### Pitfall 4: Pi Process Starts Before Pi Binary Is Installed
**What goes wrong:** Dockerfile runs `npm install` but Pi binary (`pi`) is not on PATH because `npx` or `node_modules/.bin` wasn't added to PATH.
**Why it happens:** `@mariozechner/pi-coding-agent` installs the `pi` binary to `node_modules/.bin/pi`. Docker's default PATH doesn't include this.
**How to avoid:** In Dockerfile: `ENV PATH="/app/node_modules/.bin:$PATH"`. Alternatively use `npx pi --mode rpc --no-session` in the spawn call.
**Warning signs:** `ENOENT: no such file or directory` error when bridge tries to spawn `pi`.

### Pitfall 5: FastAPI `startup` Event vs `lifespan`
**What goes wrong:** Using deprecated `@app.on_event("startup")` decorator causes deprecation warnings in FastAPI >= 0.93 and will be removed in a future version.
**Why it happens:** Older tutorials still show the event decorator pattern.
**How to avoid:** Use `lifespan` context manager (see Pattern 2 above). It's the current standard.
**Warning signs:** `DeprecationWarning` in server logs on startup.

### Pitfall 6: Pi `agent_end` vs `turn_end` — Which Signals Completion?
**What goes wrong:** Resolving the promise on `turn_end` instead of `agent_end` causes premature response when Pi is doing multi-turn reasoning (tool calls, thinking steps). The response arrives before Pi is done.
**Why it happens:** `turn_end` fires per reasoning cycle. `agent_end` fires when all processing is complete.
**How to avoid:** Wait for `agent_end` to resolve the HTTP response. `agent_end.messages` contains all conversation messages including the final assistant text.
**Warning signs:** Truncated or incomplete responses; tool call results not included in response.

### Pitfall 7: Synchronous Requests to Pi Harness From Core
**What goes wrong:** If FastAPI sends a fire-and-forget HTTP request to the Pi harness (not awaiting the response), the Core endpoint returns before the AI response is ready.
**Why it happens:** Accidental non-awaited httpx call.
**How to avoid:** Always `await client.post(...)` for the Pi harness call. Set a 30-second timeout on the httpx client used for Pi calls.
**Warning signs:** POST /message returns 200 immediately with an empty response body.

---

## Code Examples

### Token Counting for OpenAI-Compatible Messages
```python
# Source: OpenAI cookbook [CITED: github.com/openai/openai-cookbook]
# Using cl100k_base as universal approximation for local models
import tiktoken

def count_tokens(messages: list[dict]) -> int:
    """Approximate token count for a messages array."""
    enc = tiktoken.get_encoding("cl100k_base")
    num_tokens = 0
    for message in messages:
        num_tokens += 3  # role, content, separator overhead per message
        for key, value in message.items():
            num_tokens += len(enc.encode(str(value)))
    num_tokens += 3  # reply priming tokens
    return num_tokens
```

### LM Studio Model Info Fetch
```python
# Source: LM Studio REST API docs [VERIFIED: lmstudio.ai/docs/developer/rest/endpoints]
async def get_context_window(client: httpx.AsyncClient, base_url: str, model_name: str) -> int:
    """Fetch max_context_length from LM Studio. Returns conservative default if unavailable."""
    try:
        resp = await client.get(f"{base_url.replace('/v1', '')}/api/v0/models/{model_name}")
        resp.raise_for_status()
        return resp.json().get("max_context_length", 4096)
    except Exception:
        return 4096  # conservative default; log this
```

### Docker Compose `include` Skeleton
```yaml
# docker-compose.yml
# Source: Docker Compose docs [VERIFIED: docs.docker.com/compose/how-tos/multiple-compose-files/include/]
# Requires Compose v2.20+ (Docker Desktop 4.22+, released Aug 2023)
include:
  - path: sentinel-core/compose.yml
  - path: pi-harness/compose.yml
```

### Pi Harness Dockerfile (Node 22 Alpine)
```dockerfile
# Source: CONTEXT.md locked decision [VERIFIED]
FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --production
# Add node_modules/.bin to PATH so 'pi' binary is found
ENV PATH="/app/node_modules/.bin:$PATH"
COPY src/ ./src/
EXPOSE 3000
CMD ["node", "src/bridge.js"]
```

### POST /message Handler (FastAPI)
```python
# Source: FastAPI docs [CITED: fastapi.tiangolo.com]
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel

class MessageEnvelope(BaseModel):
    content: str
    user_id: str = "default"

class ResponseEnvelope(BaseModel):
    content: str
    model: str

@app.post("/message", response_model=ResponseEnvelope)
async def post_message(envelope: MessageEnvelope, request: Request):
    client: httpx.AsyncClient = request.app.state.http_client
    settings: Settings = request.app.state.settings

    # 1. Token guard
    messages = [{"role": "user", "content": envelope.content}]
    token_count = count_tokens(messages)
    if token_count > request.app.state.context_window:
        raise HTTPException(status_code=422, detail=f"Message too long: {token_count} tokens exceeds {request.app.state.context_window} limit")

    # 2. Forward to Pi harness
    try:
        resp = await client.post(f"{settings.pi_harness_url}/prompt",
                                  json={"message": envelope.content},
                                  timeout=30.0)
        resp.raise_for_status()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="AI backend not ready")

    return ResponseEnvelope(content=resp.json()["content"], model=settings.model_name)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `@app.on_event("startup")` | `lifespan` context manager | FastAPI 0.93 (2023) | Old pattern deprecated; use lifespan |
| `docker-compose` (v1, hyphen) | `docker compose` (v2, space) | Docker CLI integration 2022 | v1 is unmaintained; v2 is the standard |
| Pydantic `class Config: orm_mode` | `model_config = {"from_attributes": True}` | Pydantic v2 (2023) | v1 syntax breaks in FastAPI >=0.100 |
| `requests` library | `httpx.AsyncClient` | FastAPI ecosystem shift 2021 | `requests` blocks the event loop |
| Multiple `-f` compose flags | `include` directive | Compose v2.20 (Aug 2023) | `include` resolves paths relative to each file; `-f` does not |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `cl100k_base` tiktoken encoding provides a safe over-estimate for local models hosted in LM Studio | Standard Stack, Code Examples | Token guard may reject valid messages (false positives) or miss oversized ones — depends on the loaded model's actual tokenizer. Acceptable risk: false positives fail safely, false negatives are bounded by LM Studio's own rejection. |
| A2 | Pi harness Fastify bridge needs to expose an HTTP endpoint at port 3000 for Core to call | Architecture Patterns | Port 3000 is conventional and not specified in pi-mono docs. If the bridge port needs to change, it's a single env var. |

---

## Open Questions

1. **Does `pi --mode rpc --no-session` need any additional flags (working directory, config file)?**
   - What we know: `pi --mode rpc --no-session` is the documented invocation from rpc.md
   - What's unclear: Whether the bridge needs to pass `--cwd` or a model config to Pi at startup for the LM Studio provider
   - Recommendation: Test `pi --mode rpc --no-session --help` in the Pi harness container during Wave 0 to see available flags; document in pi-adapter.ts

2. **Does LM Studio return `max_context_length` via `/api/v0/models/{model}` when accessed via `host.docker.internal`?**
   - What we know: The endpoint is documented and returns this field [VERIFIED: lmstudio.ai/docs]
   - What's unclear: Whether Docker networking `host.docker.internal` resolves correctly on macOS when LM Studio is host-bound
   - Recommendation: Smoke test with `curl` from inside a Docker container during Wave 0 before relying on it

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker Compose v2 | CORE-06, CORE-07 | Yes | v24.14.0 (includes Compose v2) | — |
| Node.js | Pi harness build | Yes | (via Docker; `node:22-alpine` image) | — |
| Python 3.12 | Sentinel Core build | Yes (Python 3.14 on host; 3.12 in Docker image) | 3.14.4 host / `python:3.12` Docker | Use Docker image |
| LM Studio | CORE-04 | ASSUMED running on Mac Mini | — | 503 response (graceful degradation per locked decision) |
| `pi` binary | CORE-01 | Installed via `npm ci` in Dockerfile | 0.66.1 | No fallback — Pi is core |

**Missing dependencies with no fallback:**
- LM Studio model loaded: operational requirement, not a code dependency. Core degrades to 503 when unavailable (locked decision).

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (latest) |
| Config file | `sentinel-core/pyproject.toml` (`[tool.pytest.ini_options]`) — Wave 0 gap |
| Quick run command | `pytest sentinel-core/tests/ -x -q` |
| Full suite command | `pytest sentinel-core/tests/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CORE-01 | Pi harness returns response to HTTP POST | integration (curl smoke) | `curl -s -X POST http://localhost:3000/prompt -d '{"message":"hello"}'` | Wave 0 gap |
| CORE-02 | Pi version pinned exactly in package.json | unit (file assertion) | `grep '"@mariozechner/pi-coding-agent": "0.66.1"' pi-harness/package.json` | Wave 0 gap |
| CORE-03 | POST /message returns ResponseEnvelope | unit | `pytest sentinel-core/tests/test_message.py -x` | Wave 0 gap |
| CORE-04 | Core calls LM Studio and receives response | integration | `pytest sentinel-core/tests/test_lmstudio_client.py -x` | Wave 0 gap |
| CORE-05 | Token guard rejects oversized message with 422 | unit | `pytest sentinel-core/tests/test_token_guard.py::test_rejects_oversized -x` | Wave 0 gap |
| CORE-05 | Token guard permits message within context window | unit | `pytest sentinel-core/tests/test_token_guard.py::test_permits_normal -x` | Wave 0 gap |
| CORE-06 | `docker compose up` starts both services | smoke (manual) | `docker compose up -d && docker compose ps` | Wave 0 gap |
| CORE-07 | `include` directive present in base compose | unit (file assertion) | `grep -q "^include:" docker-compose.yml` | Wave 0 gap |

### Sampling Rate
- **Per task commit:** `pytest sentinel-core/tests/ -x -q`
- **Per wave merge:** `pytest sentinel-core/tests/ -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `sentinel-core/tests/conftest.py` — shared fixtures (TestClient, mock LM Studio)
- [ ] `sentinel-core/tests/test_message.py` — covers CORE-03
- [ ] `sentinel-core/tests/test_token_guard.py` — covers CORE-05
- [ ] `sentinel-core/tests/test_lmstudio_client.py` — covers CORE-04 (mocked)
- [ ] `sentinel-core/pyproject.toml` — pytest + pytest-asyncio config
- [ ] Framework install: `pip install pytest pytest-asyncio httpx`

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No (Phase 1 — no auth yet; IFACE-06 is Phase 3) | — |
| V3 Session Management | No | — |
| V4 Access Control | No | — |
| V5 Input Validation | Yes | Pydantic v2 model on MessageEnvelope; token guard rejects oversized input |
| V6 Cryptography | No | — |

### Known Threat Patterns for Phase 1 Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Oversized message causes OOM in LM Studio | Denial of Service | Token guard (CORE-05) rejects before sending |
| Pi subprocess injection via message content | Tampering | Pi treats stdin as JSONL commands, not shell; message content goes in `"message"` field value — not interpreted as a command |
| LM Studio accessible without auth on local network | Information Disclosure | Phase 1 is local-network only; auth added in Phase 3 (IFACE-06) |

---

## Sources

### Primary (HIGH confidence)
- [VERIFIED: npm registry — `@mariozechner/pi-coding-agent@0.66.1`] — confirmed latest via `npm view`, release date 2026-04-08
- [VERIFIED: npm registry — `fastify@5.8.4`] — confirmed via `npm view`, release date 2026-03-23
- [CITED: github.com/badlogic/pi-mono rpc.md] — complete JSONL RPC protocol specification, all command/event types, framing rules
- [CITED: github.com/badlogic/pi-mono sdk.md] — `agent_end` as completion signal, sequential request model
- [CITED: lmstudio.ai/docs/developer/rest/endpoints] — `/api/v0/models` response format, `max_context_length` field
- [CITED: docs.docker.com/compose/how-tos/multiple-compose-files/include/] — `include` directive YAML syntax, path resolution behavior

### Secondary (MEDIUM confidence)
- Docker Compose v2.20.0 introduced `include` directive — confirmed via web search (Docker blog Aug 2023, multiple sources agree) [VERIFIED: multiple sources]
- tiktoken `cl100k_base` as universal approximation for local models — confirmed via OpenAI cookbook and community patterns [CITED: github.com/openai/openai-cookbook]

### Tertiary (LOW confidence)
- `pi --mode rpc --no-session` invocation flags — extracted from sdk.md fetch; exact flags for LM Studio provider configuration need verification during implementation

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions verified against npm registry and official docs
- Architecture: HIGH — Pi RPC protocol fully documented, FastAPI patterns are stable and well-established
- Pitfalls: HIGH — JSONL/readline issue is documented in project STACK.md; Pi version velocity confirmed via release history
- Token counting: MEDIUM — cl100k_base approximation is documented community practice, not an official LM Studio recommendation

**Research date:** 2026-04-10
**Valid until:** 2026-04-17 (7 days — pi-mono is fast-moving; re-verify latest version before implementation)
