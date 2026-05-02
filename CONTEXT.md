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
The Obsidian vault that serves as the Sentinel's persistent memory. Accessed exclusively through
the Obsidian Local REST API. Contains the **Self**, **Sentinel**, and **Ops** namespaces.
_Avoid_: database, store, knowledge base.

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
- A **Vault** contains the **Self namespace**, the **Sentinel namespace**, and the **Ops namespace**.
- A **Session** writes one **Session summary** into `ops/sessions/`.
- The **Sentinel persona** is read from the **Sentinel namespace** at the start of every **Session**.
- The **Hot tier** combines the **Sentinel persona**, the **Self namespace**, and recent
  **Session summaries**. The **Warm tier** is sourced from **Vault** search.

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
