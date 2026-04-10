# Phase 02: Memory Layer - Research

**Researched:** 2026-04-10
**Domain:** Obsidian Local REST API, Pi RPC protocol, FastAPI async patterns, token budgeting
**Confidence:** HIGH (core stack), MEDIUM (Pi context injection workaround)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

1. **Prompt construction:** Prepend user context as a user/assistant turn pair before the actual
   message. Implementation:
   ```python
   messages = [
       {"role": "user", "content": f"Here is context about me:\n{user_context}"},
       {"role": "assistant", "content": "Understood."},
       {"role": "user", "content": envelope.content},
   ]
   ```
   Token budget note: token guard must count all messages, not just user content.

2. **Session summary write policy:** Always write — every completed exchange produces a session
   note at `/core/sessions/{YYYY-MM-DD}/{user_id}-{HH-MM-SS}.md`. If write fails, log warning,
   do NOT fail the HTTP response.

3. **Obsidian failure behavior:** Graceful degradation — proceed without memory when Obsidian
   is unavailable. Health endpoint reports Obsidian status as a non-blocking field.

4. **User context file:** Manual, free-form Markdown at `/core/users/{user_id}.md`. No schema
   enforcement. Read entire file verbatim. Missing file = skip injection silently.

### Claude's Discretion

- **Token budget ceiling (MEM-07):** 25% of context window reserved for injected context (user
  file + hot-tier sessions combined). Enforced by existing `check_token_limit()` on the full
  message array. No separate ceiling config needed in Phase 2.

- **Hot tier (MEM-05):** Last 3 session summaries for this user_id, always loaded if they exist.

- **Warm tier:** Vault keyword search — reserved for Phase 2 if time allows; not required for
  MVP cross-session memory demo.

### Deferred Ideas (OUT OF SCOPE)

- Vector search / semantic retrieval (VMEM-01)
- Entity graph for NPCs, people, projects
- User-facing command to query their own memory
- Auto-updating user context file (AI writes back what it learns)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MEM-01 | Obsidian REST API accessible from Core container; health check detects unavailability and degrades gracefully | ObsidianClient with 404/connection-error handling; health endpoint extended with `obsidian` field |
| MEM-02 | Core retrieves user context file before building Pi prompt | ObsidianClient.get_user_context() → GET /vault/core/users/{user_id}.md |
| MEM-03 | Core writes session summary after each interaction | ObsidianClient.write_session_summary() → PUT /vault/core/sessions/{date}/{user_id}-{time}.md |
| MEM-04 | Cross-session memory demo — second conversation references prior session detail | Hot tier (last 3 sessions) + context injection enables this |
| MEM-05 | Tiered retrieval architecture in place | Hot tier implemented; warm/cold tiers scaffolded but not active in MVP |
| MEM-06 | Write-selectivity policy defined and enforced | Policy = always write; documented in ObsidianClient docstring |
| MEM-07 | Token budget ceiling enforced for context injection | Existing check_token_limit() handles multi-message arrays correctly — see findings below |
| MEM-08 | Obsidian search abstracted behind a class | ObsidianClient.search_vault() method; keyword now, vector later |
</phase_requirements>

---

## Summary

Phase 2 adds an ObsidianClient to Sentinel Core and wires it into the POST /message flow.
Before each Pi call, the route retrieves user context and recent session summaries from the
Obsidian vault and serializes them into a single formatted string injected as the first
"prompt" to Pi. After the response arrives, a non-blocking background task writes a session
summary back to the vault.

The most important finding is about Pi RPC: the `prompt` command accepts only `message: string`
— not a messages array. The CONTEXT.md shows the desired 3-message structure (context user turn,
"Understood." assistant turn, actual user message), but this cannot be passed as an array through
the existing Pi bridge. The correct implementation serializes these three turns into a single
formatted string before calling `sendPrompt`. This requires modifying `bridge.ts` to accept
a `messages` array from Sentinel Core, then serializing it server-side before forwarding to Pi.

The Obsidian REST plugin runs HTTPS-only by default (port 27124 with self-signed cert), but
supports an optional HTTP mode on port 27123. The `.env` already uses
`http://host.docker.internal:27124` — this is a misconfiguration: HTTP on the HTTPS port will
be refused. The correct approach is either enable HTTP in Obsidian settings (port 27123) and
update the URL, or use the HTTPS port with `verify=False` in the httpx client.

**Primary recommendation:** Implement ObsidianClient following the LMStudioClient pattern.
Serialize the messages array to a flat string for Pi. Enable HTTP mode in Obsidian settings or
use `verify=False` with HTTPS. Use FastAPI BackgroundTasks for the best-effort summary write.

---

## Standard Stack

### Core (all already in pyproject.toml)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `httpx` | >=0.28.1 | ObsidianClient HTTP calls | Already in stack; `AsyncClient` for all outbound HTTP |
| `fastapi` | >=0.135.0 | BackgroundTasks for async write | Built-in; no new dependency |
| `tiktoken` | (pinned) | Token counting | Already used by token_guard.py |
| `pydantic-settings` | >=2.13.0 | New config fields | Already in stack |

No new dependencies required for Phase 2. [VERIFIED: pyproject.toml read]

### No New Packages
All Phase 2 work is pure code additions using existing stack libraries. The ObsidianClient,
context injection logic, and session write are all implementable with httpx + fastapi +
standard library datetime.

---

## Architecture Patterns

### New Component: ObsidianClient

Pattern: identical to `LMStudioClient` — a class wrapping the shared `httpx.AsyncClient`,
instantiated in lifespan, attached to `app.state.obsidian_client`.

```python
# Source: modeled on sentinel-core/app/clients/lmstudio.py
class ObsidianClient:
    def __init__(self, http_client: httpx.AsyncClient, base_url: str, api_key: str) -> None:
        self._client = http_client
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    async def get_user_context(self, user_id: str) -> str | None:
        """GET /vault/core/users/{user_id}.md — returns body or None if 404/unavailable."""
        try:
            resp = await self._client.get(
                f"{self._base_url}/vault/core/users/{user_id}.md",
                headers=self._headers,
                timeout=5.0,
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.text
        except Exception:
            return None  # graceful degradation

    async def get_recent_sessions(self, user_id: str, limit: int = 3) -> list[str]:
        """Search vault for recent session files for this user."""
        try:
            resp = await self._client.post(
                f"{self._base_url}/search/simple/?query={user_id}",
                headers={**self._headers, "Content-Type": "application/json"},
                timeout=5.0,
            )
            resp.raise_for_status()
            results = resp.json()
            # Filter to session files for this user_id, return content of last N
            # Results are filenames — need separate GET calls for content
            return []  # implementation detail — see Architecture Notes below
        except Exception:
            return []

    async def write_session_summary(self, path: str, content: str) -> None:
        """PUT /vault/{path} — best-effort write, caller catches all exceptions."""
        resp = await self._client.put(
            f"{self._base_url}/vault/{path}",
            headers={**self._headers, "Content-Type": "text/markdown"},
            content=content.encode("utf-8"),
            timeout=10.0,
        )
        resp.raise_for_status()

    async def search_vault(self, query: str) -> list[dict]:
        """POST /search/simple/ — keyword search. Warm tier, reserved for future."""
        try:
            resp = await self._client.post(
                f"{self._base_url}/search/simple/?query={query}",
                headers=self._headers,
                timeout=5.0,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return []
```

[VERIFIED: endpoint paths, auth header format from coddingtonbear/obsidian-local-rest-api README]
[VERIFIED: error handling pattern from sentinel-core/app/clients/lmstudio.py]

### CRITICAL: Pi RPC Context Injection Pattern

**Finding:** Pi RPC `prompt` only accepts `message: string`. No `messages` array, no history
injection, no system prompt. [VERIFIED: official pi-mono RPC docs at hochej.github.io/pi-mono/coding-agent/rpc/]

**Required change:** Bridge.ts must be modified to accept a `messages` array and serialize it
to a single string before forwarding to `sendPrompt`. Sentinel Core passes the 3-message
structure; the bridge does the serialization.

**Bridge.ts change** — update PromptBody interface:
```typescript
// Before (Phase 1):
interface PromptBody { message: string; }

// After (Phase 2):
interface PromptBody {
  message?: string;
  messages?: Array<{ role: string; content: string }>;
}

// Serialization function:
function serializeMessages(messages: Array<{ role: string; content: string }>): string {
  return messages
    .map(m => `[${m.role.toUpperCase()}]: ${m.content}`)
    .join('\n\n');
}
```

**Python side** — `PiAdapterClient.send_prompt` signature stays the same but caller passes the
full messages array. The Python adapter sends it to the bridge:

```python
# sentinel-core/app/clients/pi_adapter.py — updated method
async def send_messages(self, messages: list[dict]) -> str:
    """Send a message array to Pi harness POST /prompt. Bridge serializes to string."""
    resp = await self._client.post(
        f"{self._harness_url}/prompt",
        json={"messages": messages},
        timeout=190.0,
    )
    resp.raise_for_status()
    return resp.json()["content"]
```

**Why this approach:** Pi's `new_session` + sequential `prompt` calls is NOT viable for
per-request stateless pattern. The CONTEXT.md decision to use `new_session` per request (from
Phase 1) means each request starts fresh. Context must be serialized into the single string
message. [VERIFIED: pi-mono uses `--no-session` flag in spawnPi — confirmed stateless per request]

### Modified: POST /message Flow

```python
# sentinel-core/app/routes/message.py — Phase 2 changes
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
import asyncio
from datetime import datetime, timezone

@router.post("/message", response_model=ResponseEnvelope)
async def post_message(
    envelope: MessageEnvelope,
    request: Request,
    background_tasks: BackgroundTasks,
) -> ResponseEnvelope:
    obsidian = request.app.state.obsidian_client

    # 1. Retrieve user context (graceful skip on failure)
    user_context = await obsidian.get_user_context(envelope.user_id)

    # 2. Retrieve hot-tier sessions (last 3)
    recent_sessions = await obsidian.get_recent_sessions(envelope.user_id, limit=3)

    # 3. Build message array
    messages = []
    if user_context or recent_sessions:
        context_parts = []
        if user_context:
            context_parts.append(f"User profile:\n{user_context}")
        if recent_sessions:
            context_parts.append("Recent session history:\n" + "\n---\n".join(recent_sessions))
        messages.append({"role": "user", "content": "\n\n".join(context_parts)})
        messages.append({"role": "assistant", "content": "Understood."})
    messages.append({"role": "user", "content": envelope.content})

    # 4. Token guard on full message array
    try:
        check_token_limit(messages, request.app.state.context_window)
    except TokenLimitError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # 5. Forward to Pi harness
    pi_adapter = request.app.state.pi_adapter
    settings = request.app.state.settings
    try:
        content = await pi_adapter.send_messages(messages)
    except (httpx.ConnectError, httpx.RemoteProtocolError):
        raise HTTPException(status_code=503, detail="AI backend not ready")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (503, 504):
            raise HTTPException(status_code=503, detail="AI backend not ready")
        raise HTTPException(status_code=502, detail="Pi harness error")

    # 6. Best-effort session summary write (non-blocking)
    background_tasks.add_task(
        _write_session_summary,
        obsidian,
        envelope.user_id,
        envelope.content,
        content,
        settings.model_name,
    )

    return ResponseEnvelope(content=content, model=settings.model_name)


async def _write_session_summary(
    obsidian, user_id: str, user_msg: str, ai_msg: str, model: str
) -> None:
    """Best-effort session summary write. Failures are logged, not raised."""
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H-%M-%S")
    path = f"core/sessions/{date_str}/{user_id}-{time_str}.md"
    content = f"""---
timestamp: {now.isoformat()}
user_id: {user_id}
model: {model}
---

## User

{user_msg}

## Sentinel

{ai_msg}
"""
    try:
        await obsidian.write_session_summary(path, content)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(f"Session summary write failed: {exc}")
```

### BackgroundTasks vs asyncio.create_task

**Use FastAPI `BackgroundTasks`** for the session summary write.

- `BackgroundTasks` runs after the response is sent but BEFORE the connection is closed.
  Correct for best-effort writes that should not block the caller.
- `asyncio.create_task()` detaches completely — the task can outlive the request and even
  swallow errors silently if not tracked. Harder to test.
- `BackgroundTasks` is the FastAPI-idiomatic choice for this exact pattern.
  [VERIFIED: FastAPI docs recommend BackgroundTasks for post-response tasks]

### New Config Fields

Add to `sentinel-core/app/config.py`:
```python
obsidian_api_url: str = "http://host.docker.internal:27123"  # HTTP mode (see pitfall below)
obsidian_api_key: str = ""  # blank = no auth header
context_injection_budget_ratio: float = 0.25  # 25% of context window for injected context
```

Both `OBSIDIAN_API_URL` and `OBSIDIAN_API_KEY` already present in `.env`. [VERIFIED: .env read]

### Lifespan Addition

```python
# In lifespan() after existing client setup:
from app.clients.obsidian import ObsidianClient

obsidian_client = ObsidianClient(
    http_client,
    settings.obsidian_api_url,
    settings.obsidian_api_key,
)
app.state.obsidian_client = obsidian_client

# Health check at startup — log warning if unavailable, do not block
obsidian_ok = await obsidian_client.check_health()
if not obsidian_ok:
    logger.warning("Obsidian REST API unavailable at startup — memory features degraded.")
```

### GET /health Extension

```python
@app.get("/health")
async def health(request: Request) -> JSONResponse:
    obsidian_ok = False
    try:
        obsidian_ok = await request.app.state.obsidian_client.check_health()
    except Exception:
        pass
    return JSONResponse({
        "status": "ok",
        "obsidian": "ok" if obsidian_ok else "degraded",
    })
```

### Hot-Tier Session Retrieval Pattern

`get_recent_sessions()` cannot use the Obsidian search API efficiently for ordered file
retrieval (search returns relevance-ranked results, not chronological). The correct pattern:

1. Call `GET /vault/core/sessions/{YYYY-MM-DD}/` for today and yesterday to list files
2. Filter filenames matching `{user_id}-*.md`
3. Sort by filename (timestamp is in filename), take last N
4. `GET /vault/core/sessions/{date}/{filename}` for each — fetch content

This is 2-3 additional HTTP calls per request but all have 5s timeout and fail gracefully.

Alternative: maintain a per-user index file at `/core/users/{user_id}-sessions.json` that
gets appended after each write. Simpler reads, more complex writes. Defer to planner decision.

[ASSUMED] The listing endpoint `GET /vault/core/sessions/{date}/` returns a directory listing
with filenames. This is consistent with the Obsidian REST API directory listing pattern
(GET /vault/ returns listing) but not verified for subdirectory paths.

### Recommended Project Structure

```
sentinel-core/app/
├── clients/
│   ├── lmstudio.py       # existing
│   ├── pi_adapter.py     # existing — add send_messages()
│   └── obsidian.py       # NEW — ObsidianClient
├── routes/
│   └── message.py        # modified — context injection + BackgroundTasks
├── services/
│   └── token_guard.py    # no changes needed
├── models.py             # no changes needed
├── config.py             # add obsidian_api_url, obsidian_api_key
└── main.py               # lifespan: add obsidian_client; health: add obsidian field

pi-harness/src/
├── bridge.ts             # modified — accept messages array, serialize to string
└── pi-adapter.ts         # no changes needed
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| Async non-blocking write | Custom task queue | FastAPI `BackgroundTasks` |
| Token counting | Custom estimator | Existing `token_guard.count_tokens()` — already handles multi-message arrays |
| HTTP client | Custom requests wrapper | `httpx.AsyncClient` (shared instance from `app.state.http_client`) |
| Obsidian auth | Custom header logic | `"Authorization: Bearer {key}"` — standard Bearer pattern |

**Key insight:** `count_tokens()` in `token_guard.py` already iterates over `messages: list[dict]`
and counts all roles and content values. It handles 1-message or 3-message arrays identically.
No changes needed to token_guard for Phase 2. [VERIFIED: token_guard.py read, line 18-33]

---

## Common Pitfalls

### Pitfall 1: Obsidian HTTP vs HTTPS Port Mismatch
**What goes wrong:** The `.env` has `OBSIDIAN_API_URL=http://host.docker.internal:27124`. Port
27124 is the HTTPS port. Sending HTTP to an HTTPS port returns a connection error or an
SSL-related rejection, not a useful 4xx.
**Why it happens:** The Obsidian plugin default is HTTPS on 27124. HTTP mode runs on 27123 and
must be explicitly enabled in Obsidian settings.
**How to avoid:** Either:
  - Enable HTTP in Obsidian plugin settings and use `http://host.docker.internal:27123`
  - Or use `https://host.docker.internal:27124` with `verify=False` on the httpx client
  - Recommended: HTTP mode (27123) is simpler for local Docker use — no cert handling needed
**Warning signs:** `httpx.ConnectError` or `httpx.RemoteProtocolError` when Obsidian is running

[VERIFIED: Obsidian Local REST API README — HTTP port 27123, HTTPS port 27124, HTTP disabled by default]

### Pitfall 2: Pi RPC Has No Messages Array
**What goes wrong:** CONTEXT.md specifies a `messages` list structure for context injection.
Passing `{"messages": [...]}` to the Pi bridge's `/prompt` endpoint will cause the bridge to
fail because `message` field is missing, or the bridge passes `undefined` to `sendPrompt`.
**Why it happens:** Pi RPC `prompt` command only accepts `message: string`. There is no
`messages` field, no history injection API, and no system prompt.
**How to avoid:** Modify `bridge.ts` to accept a `messages` array and serialize it into a
formatted string before calling `sendPrompt`. Never pass raw arrays through to Pi.
**Warning signs:** 400 response from Pi bridge ("message field required"), or Pi receiving
a stringified `[object Object]`

[VERIFIED: pi-mono RPC docs — prompt command schema has no messages field]

### Pitfall 3: BackgroundTasks Blocks Response Until Complete
**What goes wrong:** A developer wraps a slow Obsidian write in BackgroundTasks expecting it
to be truly fire-and-forget, but the HTTP response is held until all background tasks finish.
**Why it happens:** FastAPI BackgroundTasks run after the response is SENT but within the same
request lifecycle. The response is streamed immediately; the task runs after. This is correct
behavior for best-effort writes — response is not delayed.
**How to avoid:** This is actually the correct behavior. The caller gets the response immediately;
the write happens concurrently. No action needed. Document this clearly.
**Warning signs:** Only a concern if the write is extremely slow (>10s). Timeout is set to 10s
on the Obsidian client, so worst case is 10s added to connection close time, not response time.

### Pitfall 4: Obsidian Search Results Are Relevance-Ranked, Not Chronological
**What goes wrong:** Using `/search/simple/?query={user_id}` to find recent sessions returns
results ranked by relevance, not by time. The "most recent" 3 sessions may not be the actually
most recent.
**Why it happens:** Obsidian's full-text search doesn't sort by file modification time.
**How to avoid:** Use directory listing (`GET /vault/core/sessions/{date}/`) and sort by
filename (which encodes the timestamp). See hot-tier retrieval pattern above.
**Warning signs:** Cross-session memory test fails because old session content is injected
instead of recent sessions.

### Pitfall 5: Token Guard Counts Context Budget Against Full Window
**What goes wrong:** The 25% context budget for injected context is described as a policy, but
if the full message array exceeds the total context window, the token guard raises 422 — which
is correct. However, a user with a very long profile file + 3 verbose session summaries could
be systematically blocked.
**Why it happens:** Token guard enforces absolute ceiling, not percentage-based ceiling on the
injected portion.
**How to avoid:** Apply a token ceiling to the injected context BEFORE building the final
messages array. Truncate user_context and session content if they would exceed 25% of
context_window. Log a warning when truncation occurs.
**Warning signs:** Users with large profile files getting systematic 422 errors.

---

## Code Examples

### Obsidian Auth Header
```python
# Source: coddingtonbear/obsidian-local-rest-api README
headers = {"Authorization": f"Bearer {api_key}"}
```

### Write a File via PUT
```python
# Source: Obsidian Local REST API README — PUT /vault/{path}
resp = await client.put(
    f"{base_url}/vault/core/sessions/2026-04-10/trekkie-14-30-00.md",
    headers={**auth_headers, "Content-Type": "text/markdown"},
    content=markdown_content.encode("utf-8"),
    timeout=10.0,
)
resp.raise_for_status()  # 200 or 204 on success
```

### Read a File via GET
```python
# Source: Obsidian Local REST API README — GET /vault/{path}
resp = await client.get(
    f"{base_url}/vault/core/users/trekkie.md",
    headers=auth_headers,
    timeout=5.0,
)
if resp.status_code == 404:
    return None  # file doesn't exist — new user
resp.raise_for_status()
return resp.text  # plain Markdown content
```

### Pi Bridge Serialization (bridge.ts)
```typescript
// Source: derived from pi-mono RPC docs — prompt only accepts message string
function serializeMessages(messages: Array<{role: string; content: string}>): string {
  return messages
    .map(m => `[${m.role.toUpperCase()}]: ${m.content}`)
    .join('\n\n');
}

// In route handler:
const messageStr = body.messages
  ? serializeMessages(body.messages)
  : body.message ?? '';
const content = await sendPrompt(messageStr);
```

### FastAPI BackgroundTasks Pattern
```python
# Source: FastAPI docs — BackgroundTasks for post-response work
from fastapi import BackgroundTasks

@router.post("/message")
async def post_message(
    envelope: MessageEnvelope,
    request: Request,
    background_tasks: BackgroundTasks,  # injected by FastAPI
) -> ResponseEnvelope:
    # ... main logic ...
    background_tasks.add_task(write_summary, obsidian, user_id, user_msg, ai_msg)
    return response  # sent immediately; write_summary runs after
```

### Token Budget Enforcement with Truncation
```python
# Source: derived from token_guard.py pattern
MAX_CONTEXT_RATIO = 0.25

def truncate_to_budget(text: str, budget_tokens: int) -> str:
    """Truncate text to fit within a token budget. Appends '[...truncated]' marker."""
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)
    if len(tokens) <= budget_tokens:
        return text
    truncated = enc.decode(tokens[:budget_tokens])
    return truncated + "\n\n[...context truncated to fit token budget]"
```

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|-----------------|--------|
| `@app.on_event("startup")` | `asynccontextmanager lifespan` | Already using modern pattern |
| Global httpx client per service | Shared `http_client` from `app.state` | Already using correct pattern |
| requests library | httpx AsyncClient | Already using correct library |
| Obsidian HTTPS + cert mgmt | HTTP mode on port 27123 | Simpler for local Docker deployment |

**No deprecated patterns to replace in Phase 2.** Phase 1 already established all correct patterns.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `GET /vault/core/sessions/{date}/` returns a directory listing with filenames | Architecture Patterns — hot-tier retrieval | If directory listing at subdirectory paths is not supported, must use search API with date filter instead |
| A2 | Pi bridge serialization of messages into `[ROLE]: content` format will produce valid context that the LLM understands | Architecture Patterns — Pi serialization | LLM may misinterpret the format; may need role prefixes like `Human:` / `Assistant:` instead |
| A3 | HTTP mode on port 27123 is stable across Obsidian plugin versions | Pitfall 1 | If HTTP mode was removed, must use HTTPS + verify=False or cert download |

---

## Open Questions

1. **Hot-tier session file listing**
   - What we know: Obsidian REST API supports `GET /vault/` for root listing; directory listing at subdirectory paths is documented but not tested
   - What's unclear: Whether `GET /vault/core/sessions/2026-04-10/` returns a JSON array of filenames or something else
   - Recommendation: Implement with `GET /vault/core/sessions/{date}/` pattern; add a fallback to search API if directory listing returns unexpected format. The Wave 0 integration test will confirm this.

2. **Pi context serialization format**
   - What we know: Pi only accepts a string; must serialize the 3-message structure to a flat string
   - What's unclear: Whether `[USER]: ... \n\n[ASSISTANT]: Understood.\n\n[USER]: actual message` is the optimal format for the model to understand context vs. actual question
   - Recommendation: Use `[USER]:` / `[ASSISTANT]:` prefixes. The cross-session memory demo (MEM-04) will validate whether the model correctly leverages injected context.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Obsidian + Local REST API plugin | MEM-01 through MEM-08 | ✓ (env shows keys present) | Plugin v3.6.1 [ASSUMED] | All memory features degrade gracefully |
| httpx | ObsidianClient | ✓ | >=0.28.1 (in pyproject.toml) | — |
| tiktoken | token_guard | ✓ | In pyproject.toml | — |
| FastAPI BackgroundTasks | Session write | ✓ | Built into fastapi>=0.135.0 | — |

**Missing dependencies with no fallback:** None.

**Note on Obsidian HTTP mode:** Must be enabled manually in Obsidian Settings → Local REST API →
enable non-encrypted server. The current `.env` `OBSIDIAN_API_URL=http://host.docker.internal:27124`
points HTTP at the HTTPS port — this will fail. Update to port 27123 after enabling HTTP mode.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio |
| Config file | `sentinel-core/pyproject.toml` (tool.pytest.ini_options) |
| Quick run command | `cd sentinel-core && python -m pytest tests/ -x -q` |
| Full suite command | `cd sentinel-core && python -m pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MEM-01 | Health endpoint reports `obsidian: "degraded"` when Obsidian down | unit (mock) | `pytest tests/test_obsidian_client.py::test_health_degraded_when_obsidian_down -x` | ❌ Wave 0 |
| MEM-01 | Health endpoint reports `obsidian: "ok"` when Obsidian up | unit (mock) | `pytest tests/test_obsidian_client.py::test_health_ok -x` | ❌ Wave 0 |
| MEM-02 | Context retrieved and injected when file exists | unit (mock) | `pytest tests/test_message.py::test_context_injected_when_file_exists -x` | ❌ Wave 0 |
| MEM-02 | No injection when user file missing (404) | unit (mock) | `pytest tests/test_message.py::test_no_injection_when_file_missing -x` | ❌ Wave 0 |
| MEM-02 | No injection when Obsidian unreachable | unit (mock) | `pytest tests/test_message.py::test_no_injection_when_obsidian_down -x` | ❌ Wave 0 |
| MEM-03 | Session summary written after response | unit (mock) | `pytest tests/test_message.py::test_session_summary_written -x` | ❌ Wave 0 |
| MEM-03 | Response not blocked when summary write fails | unit (mock) | `pytest tests/test_message.py::test_response_succeeds_when_write_fails -x` | ❌ Wave 0 |
| MEM-04 | Cross-session memory demo | manual | Manual: two curl calls, second references first | — |
| MEM-05 | Hot tier loads last 3 sessions | unit (mock) | `pytest tests/test_obsidian_client.py::test_get_recent_sessions -x` | ❌ Wave 0 |
| MEM-06 | Every completed exchange triggers write | unit (mock) | `pytest tests/test_message.py::test_write_called_every_exchange -x` | ❌ Wave 0 |
| MEM-07 | Token guard fires on 3-message array exceeding window | unit | `pytest tests/test_token_guard.py::test_multi_message_token_guard -x` | ❌ Wave 0 |
| MEM-07 | Context truncation when injection exceeds 25% budget | unit | `pytest tests/test_message.py::test_context_truncation -x` | ❌ Wave 0 |
| MEM-08 | ObsidianClient.search_vault abstraction | unit (mock) | `pytest tests/test_obsidian_client.py::test_search_vault -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd sentinel-core && python -m pytest tests/ -x -q`
- **Per wave merge:** `cd sentinel-core && python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `sentinel-core/tests/test_obsidian_client.py` — covers MEM-01, MEM-05, MEM-08
- [ ] `sentinel-core/tests/test_message.py` — extend existing file with MEM-02, MEM-03, MEM-06, MEM-07 tests
- [ ] `sentinel-core/tests/test_token_guard.py` — extend with multi-message array test for MEM-07

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | N/A — internal service-to-service |
| V3 Session Management | no | No sessions; stateless per-request |
| V4 Access Control | no | `X-Sentinel-Key` already enforced on all non-health routes (Phase 3) |
| V5 Input Validation | yes | Pydantic v2 validates `user_id` (max_length=64); file path constructed from user_id |
| V6 Cryptography | no | Bearer token for Obsidian auth; no custom crypto |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal via user_id | Tampering | Sanitize user_id — only allow alphanumeric + hyphens/underscores before constructing Obsidian path |
| Obsidian API key in logs | Info Disclosure | Never log `api_key` value; log warnings omit auth headers |

**Path traversal note:** `user_id` is used directly in the Obsidian file path
(`/core/users/{user_id}.md`). A user_id of `../../sensitive/file` would attempt to read
an arbitrary vault file. The existing Pydantic `max_length=64` is necessary but not sufficient.
Add a regex validator: `pattern=r'^[a-zA-Z0-9_-]+$'` to `MessageEnvelope.user_id`.
[ASSUMED — verify if Obsidian REST API performs its own path sanitization]

---

## Sources

### Primary (HIGH confidence)
- `sentinel-core/app/clients/pi_adapter.py` — current bridge protocol (read in session)
- `sentinel-core/app/clients/lmstudio.py` — pattern for ObsidianClient (read in session)
- `sentinel-core/app/services/token_guard.py` — confirms multi-message array support (read in session)
- `sentinel-core/pyproject.toml` — confirms no new deps needed (read in session)
- `pi-harness/src/pi-adapter.ts` — confirms `sendPrompt(message: string)` signature (read in session)
- `pi-harness/src/bridge.ts` — confirms current PromptBody interface (read in session)
- coddingtonbear/obsidian-local-rest-api README — endpoints, auth header, HTTP/HTTPS ports

### Secondary (MEDIUM confidence)
- hochej.github.io/pi-mono/coding-agent/rpc/ — Pi RPC full command list, prompt schema
- deepwiki.com Obsidian REST API SSL certificate management page — HTTP mode on port 27123

### Tertiary (LOW confidence)
- FastAPI BackgroundTasks community discussion (Reddit, Medium) — confirmed consistent with FastAPI docs behavior

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in pyproject.toml, verified
- Architecture: HIGH for Python side; MEDIUM for Pi serialization (protocol confirmed, format convention unverified)
- Obsidian HTTP mode: MEDIUM — documented but must be enabled manually
- Hot-tier directory listing: LOW — endpoint pattern assumed, not tested against running plugin

**Research date:** 2026-04-10
**Valid until:** 2026-05-10 (pi-mono is fast-moving; check for RPC changes before execution)
