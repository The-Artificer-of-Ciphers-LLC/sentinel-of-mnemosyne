# Sentinel of Mnemosyne — Domain Context

Domain glossary for Sentinel Core. Shared vocabulary for code, planning artifacts, and architecture
discussions. Architectural terms (module, seam, depth, adapter) live in
`improve-codebase-architecture/LANGUAGE.md` — this file is project-domain only.

## Language

**Sentinel**:
The AI assistant the user talks to. Single-process FastAPI service (`sentinel-core/`) that takes
a message in and returns an AI response that knows the user's history.
_Avoid_: bot, agent, assistant.

**Sentinel persona**:
The system-prompt content that defines how the Sentinel responds — tone, scope, what it should and
should not do. Sourced at request time from `sentinel/persona.md` in the **Vault**, with a
hardcoded fallback when the Vault is unreachable. Distinct from the user's identity, which the
Sentinel reads from the **Self namespace**.
_Avoid_: system prompt (use only when describing the LLM mechanism), personality, character.

**Vault**:
The Obsidian vault that serves as the Sentinel's persistent memory. Both a domain concept
and a code module (`app/vault.py`) — the `Vault` Protocol is the single seam through which
Sentinel Core reads and writes persistent state. The current concrete adapter `ObsidianVault`
implements the Protocol over the Obsidian Local REST API; tests use `FakeVault`. Contains the
**Self**, **Sentinel**, **Ops**, and **Trash** namespaces.
_Avoid_: database, store, knowledge base, ObsidianClient (legacy name — superseded by `Vault`).

**Self namespace** (`self/`):
Vault path holding the **user's** identity, methodology, goals, and relationships. Read by the
Sentinel into the **Hot tier** on every message. Operator-curated, not Sentinel-written.
_Avoid_: user profile, user data.

**Sentinel namespace** (`sentinel/`):
Vault path holding the **Sentinel's** own self-definition. Currently holds `sentinel/persona.md`.
Parallel to **Self namespace** but for the Sentinel rather than the user. Operator-curated.
_Avoid_: prompts/, system/.

**Ops namespace** (`ops/`):
Vault path holding operational state the Sentinel writes to: **Session summaries**
(`ops/sessions/`), reminders (`ops/reminders.md`), sweeper output (`ops/sweeps/`).
_Avoid_: logs, history.

**Trash namespace** (`_trash/`):
Vault path holding files relocated by the **vault sweeper** rather than deleted. Sweep
operations are non-destructive: every relocation places the source under `_trash/{date}/`
so an operator can restore. Operator-curated cleanup; never read by the Sentinel during
message processing.
_Avoid_: deleted/, archive/.

**Hot tier**:
Context loaded into every message: **Sentinel persona** (system role), **Self namespace** files
(user role), recent **Session summaries**. Read in parallel via `asyncio.gather`.

**Warm tier**:
Context loaded conditionally: vault search results scored above a relevance threshold.

**Session**:
One user message + one Sentinel response. Bounded by a single `POST /message` request.

**Session summary**:
A markdown file written to `ops/sessions/{date}/` after every Session. Holds the user message and
the Sentinel response. Best-effort — write failure does not fail the response.

**Module** (Sentinel sense):
A pluggable container that attaches to Sentinel Core to add capabilities (Discord interface,
finance tracker, trading module). Distinct from the architectural sense — see Flagged ambiguities.
_Avoid_: plugin, extension, service.

## Relationships

- A **Sentinel** owns one **Vault**.
- A **Vault** contains the **Self namespace**, the **Sentinel namespace**, the **Ops namespace**,
  and the **Trash namespace**.
- A **Session** writes one **Session summary** into `ops/sessions/`.
- The **Sentinel persona** is read from the **Sentinel namespace** at the start of every **Session**.
- The **Hot tier** combines the **Sentinel persona**, the **Self namespace**, and recent
  **Session summaries**. The **Warm tier** is sourced from **Vault** search.
- The **vault sweeper** never deletes — it relocates source files into the **Trash namespace**.

## Example dialogue

> **Operator:** "I want to soften the Sentinel's tone — fewer questions, more acknowledgement."
> **Dev:** "Edit `sentinel/persona.md` in the Vault. The change takes effect on the next message —
> the Sentinel persona is read every Session, not pinned at startup."

> **Operator:** "What writes into `ops/sessions/`?"
> **Dev:** "Every Session writes one Session summary there. The Sentinel never writes to the Self
> namespace or the Sentinel namespace — those are operator-curated."

## Flagged ambiguities

- **"Module"** is overloaded. Sentinel-domain module = pluggable container (Discord, finance,
  trading). Architectural module = interface + implementation (any function/class/package). When
  the context isn't obvious, qualify: "Sentinel module" vs "architectural module".
- **"Self"** in `self/identity.md` refers to the **user's** self, not the Sentinel's self. The
  Sentinel's self lives under `sentinel/`. Resolved via the **Sentinel namespace**.

## Architecture memory for future agents (sentinel-core, machine-oriented)

### Canonical seams
- `app/state.py`
  - `RouteContext` is REQUIRED route dependency carrier.
  - `get_route_context(request)` strict: missing `route_ctx` => runtime error.
- `app/composition.py`
  - `initialize_startup(app, settings, http_client)` is startup orchestrator.
  - Performs state pinning + persona startup policy.
- `app/vault.py`
  - `Vault` protocol is sole persistence interface.

### Runtime state contract
- Lifespan pins:
  - `app.state.route_ctx` (primary)
  - `app.state.settings` (minimal non-route use)
  - `app.state.vault` (minimal non-route use)
- Do not reintroduce scattered `app.state.*` dependencies in routes.

### Adapter map
- `app/main.py` => `/health`
- `app/routes/message.py` => `/message`
- `app/routes/status.py` => `/status`, `/context/{user_id}`
- `app/routes/modules.py` => register/list/proxy
- `app/routes/note.py` => note/inbox/sweep endpoints

Adapters should do only translation/auth/delegation.

### Deep module map
- Startup: `app/composition.py`
- Runtime config view: `app/runtime_config.py`
- Runtime probe: `app/services/runtime_probe.py`
- Health payload: `app/services/health_response.py`
- Message request build: `app/services/message_request_factory.py`
- Message exception mapping: `app/services/message_http_mapping.py`
- Module forwarding: `app/services/module_gateway.py`
- Module registry ops: `app/services/module_registry.py`
- Sweep orchestration: `app/services/note_sweep_runner.py`
- Sweep engine: `app/services/vault_sweeper.py`
- Sweep status store: `app/services/sweep_status_store.py`
- Background scheduling seam: `app/services/task_runner.py`
- PF2e Foundry NeDB chat import: `modules/pathfinder/app/foundry_chat_import.py`

### Authoritative flows
- Message flow:
  1) route -> `get_route_context`
  2) `message_request_factory.build_message_request`
  3) `MessageProcessor.process`
  4) map exception via `message_http_mapping`
  5) schedule session summary write via `ctx.vault`

- Sweep flow:
  1) route admin check
  2) `note_sweep_runner.start_sweep`
  3) schedule background task via `task_runner`
  4) core execution in `vault_sweeper.run_sweep`
  5) status via `sweep_status_store` wrappers

- Health/status flow:
  - `runtime_probe.probe_runtime` drives runtime snapshot
  - `/health` additionally probes embedding model and formats through `health_response`

- PF2e Foundry NeDB chat import flow:
  1) Foundry/ops copies `messages.db` into inbox folder (`/vault/inbox/messages.db` default)
  2) PF2e route `POST /foundry/messages/import` validates `X-Sentinel-Key`
  3) `import_nedb_chatlogs_from_inbox(...)` parses line-delimited NeDB JSON
  4) each message classified to `ic|roll|ooc|system` from `type` + normalized content
  5) result persisted as markdown report note under `mnemosyne/pf2e/sessions/foundry-chat/YYYY-MM-DD/`
  6) response returns summary counts (`imported_count`, `invalid_count`, `class_counts`, `note_path`)

### Policy invariants
- Startup persona policy:
  - persona missing + reachable vault => hard fail
  - vault unreachable => warning + degraded startup
- Sweeper is non-destructive (`_trash/*` moves only).
- Pi harness probe is non-fatal.
- `/health` always returns 200 with degraded fields when needed.

### Validation baseline
- Unit/integration tests: 279 passed, 12 skipped.
- Live smoke validated: `/health`, `/status` (auth+unauth), `/modules`, `/note/classify`, `/message`.
