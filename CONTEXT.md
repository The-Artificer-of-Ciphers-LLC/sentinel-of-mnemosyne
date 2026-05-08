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

**Module version**:
A version number owned by an individual Sentinel module and released independently from Sentinel Core.
Example: Sentinel Core `v0.50` and Pathfinder module `v1.0` can ship on different cadences.
_Avoid_: assuming one global version implies all module versions.

## Relationships

- A **Sentinel** owns one **Vault**.
- A **Vault** contains the **Self namespace**, the **Sentinel namespace**, the **Ops namespace**,
  and the **Trash namespace**.
- A **Session** writes one **Session summary** into `ops/sessions/`.
- The **Sentinel persona** is read from the **Sentinel namespace** at the start of every **Session**.
- The **Hot tier** combines the **Sentinel persona**, the **Self namespace**, and recent
  **Session summaries**. The **Warm tier** is sourced from **Vault** search.
- The **vault sweeper** never deletes — it relocates source files into the **Trash namespace**.
- A **Sentinel module** has its own **Module version** lifecycle independent of Sentinel Core.

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

---

## session_issues
<!-- AI-readable. Compact YAML. Append-only. Each entry: stable ref → fact → mitigation → status. -->

```yaml
repo_state:
  - ref: GIT-001
    fact: ".planning/, .claude/, .agents/, CLAUDE.md, .gitignore are intentionally untracked"
    evidence: "commits 2eec6d2 (remove .gitignore from repo) and dc2a2f1 (untrack local agent/planning artifacts); .gitignore in .git/info/exclude"
    implication: "worktree-isolated agents cannot read .planning/* — fail at <files_to_read>"
    mitigation: "git.branching_strategy=none, workflow.use_worktrees=false; sequential execution on main tree"
    status: applied_for_phase_37
  - ref: GIT-002
    fact: ".gitignore extended locally for secrets/, mnemosyne/, node_modules/, __pycache__/, .env, .DS_Store, .pi/, .claude/settings.local.json, GSD-WORKTREE-DELETION-BUG-REPORT.md, V040-REFACTORING-DIRECTIVE.md"
    persistence: local-only (file is in .git/info/exclude, never tracked)
    note: "extensions survive across sessions on this machine; do not assume gitignore semantics from upstream main"

phase_37_contract_drift:
  - ref: PHASE37-A
    fact: "PlayerStartCommand shipped with payload {user_id} only; /player/onboard requires character_name, preferred_name, style_preset → 422"
    why_missed_by_verifier: "adapter unit tests mocked post_to_module without validating payload against route Pydantic model"
    mitigation_commit: "fix(discord): :pf player start parses pipe-separated onboard args (mitigation for Phase 38)"
    new_contract: "rest=`<character_name> | <preferred_name> | <style_preset>`; empty rest → usage hint, no POST"
    status: deployed
  - ref: PHASE37-B
    fact: "verb name asymmetry — ROADMAP success criterion #1 says 'onboard', dispatcher registers 'start'"
    canonical: "37-CONTEXT.md line 129 — verb is 'start' (start/style allowed pre-onboarding)"
    status: design_lock_honored_no_change_needed
  - ref: PHASE37-C
    fact: "PlayerStateCommand does not exist; GET /player/state is HTTP-only (no Discord verb)"
    intent: by_design
    consumers: orchestrator_gate_logic, foundry_projection_lookups
    status: not_a_bug
  - ref: PHASE37-D
    fact: "routes/foundry._identity_resolver typed for record dict but called with speaker-token string; every Foundry import silently classified speakers as 'unknown'"
    caught_by: "plan 37-14 closeout E2E test (test_phase37_integration.py)"
    fix_commit: 8aee784
    lesson: "wave-7 unit tests passed because they injected their own resolver callable; only route-stack E2E exercised the real wrapper"
    status: fixed_in_phase
  - ref: PHASE37-E
    fact: "PlayerAskCommand posted {user_id, question} but PlayerAskRequest schema requires {user_id, text}; every live :pf player ask 422'd"
    caught_by: "scripts/uat_phase37.py UAT-18 (adapter contract drift regression guard)"
    why_missed_by_verifier: "same blind spot as PHASE37-A — adapter unit test mocked post_to_module without validating against the route's Pydantic model"
    secondary_fix: "PlayerAskCommand response no longer fabricates question_id — route returns {ok, slug, path}, no id is generated; questions.md is a free-form append and the operator picks a question_id when canonizing"
    status: fixed
  - ref: PHASE37-F
    fact: "shipped Phase 37 USER-GUIDE.md described 6 wrong example responses + wrong canonize signature ('<question_id> <green|red> [reason]' instead of '<outcome> <question_id> <rule_text>' with yellow/green/red)"
    caught_by: "manual reconciliation against scripts/uat_phase37.py output"
    lesson: "doc examples must be copy-pasted from real adapter output, not transcribed from intent; verifier should diff doc claims against UAT output"
    status: fixed

doc_audit_findings:
  - ref: DOC-001
    fact: "README.md (3x) + ARCHITECTURE-Core.md (5x) prescribed --pathfinder flag, but shipped sentinel.sh only recognises --pf2e; new-user install instructions silently broke at the up step"
    canonical: "docker profile name = pf2e (compose.yml), module registry name = pathfinder (REGISTRATION_PAYLOAD); intentional split per CLAUDE.md D-12"
    caught_by: "audit triggered by /technical-writer 'confirm all verbs and commands'"
    status: fixed
  - ref: DOC-002
    fact: "README.md /sen subcommand table is correct but incomplete — 12 listed, ~25 shipped (missing :seed, :connect, :review, :graph, :learn, :remember, :note, :tasks, :stats, :vault-sweep, :inbox, plus all 10 :plugin:* commands)"
    impact: "completeness, not correctness — every listed entry verified accurate"
    canonical: "interfaces/discord/command_router.py + bot.py _SUBCOMMAND_PROMPTS / _PLUGIN_PROMPTS"
    status: noted_not_fixed (out of audit scope; expansion is a separate writing task)
  - ref: DOC-003
    fact: "USER-GUIDE.md only documents :pf player verbs; :pf rule/session/npc/foundry/cartosia/ingest noun namespaces ship without user-facing docs"
    impact: "user-facing reference incomplete for non-player :pf verbs"
    canonical_source: "interfaces/discord/pathfinder_dispatch.py COMMANDS dict"
    status: noted_not_fixed (expansion task)

verifier_blind_spots:
  - "adapter→route contract drift invisible when adapter tests mock the HTTP boundary"
  - "verifier PASS requires goal-backward trace from success criterion to behavioral test that exercises the production seam, not the mocked seam"
  - "trust-but-verify must pull at least one E2E curl through the real container before accepting verifier PASS for shipped HTTP features"

deferred_pre_existing:
  - ref: DEFER-001
    file: modules/pathfinder/app/routes/foundry.py:110
    fact: "get_profile NameError"
    introduced_by: "Phase 35 commit ea7da29 (2026-04-26)"
    failing_tests: "test_foundry.py::{test_roll_event_accepted, test_notify_dispatched, test_llm_fallback}"
    status: tracked_in_deferred-items.md
  - ref: DEFER-002
    file: modules/pathfinder/tests/test_registration.py
    fact: "test_registration_payload_has_16_routes stale — payload now has 29 routes"
    rule: "Test-Rewrite Ban — operator decides whether to retire or update"
    status: tracked_in_deferred-items.md

infra_quirks:
  - ref: INFRA-001
    fact: "sentinel-core /modules/{name}/{path} proxy returns 405 for GET-with-query-string"
    repro: "curl -G --data-urlencode 'user_id=X' http://localhost:8000/modules/pathfinder/player/state → 405; same hit direct on pf2e-module:8000 → 200"
    impact_on_discord: "none — Discord adapter uses POST routes; only HTTP debug/curl affected"
    status: out_of_scope_unfiled

phase_38_queued:
  ref: PHASE38
  goal: "multi-step Discord onboarding dialog replacing one-shot pipe args"
  driver: "37-CONTEXT.md line 129 unimplemented in Phase 37"
  preserves: "v0.5 pipe-separated one-shot syntax (regression coverage required)"
  next_action: "/gsd-spec-phase 38"
  status: queued_in_ROADMAP

dockerfile_dep_check_phase_37:
  fact: "no new Python deps introduced in Phase 37"
  imports: stdlib + fastapi + pydantic + yaml (all pre-existing)
  dual_ship_required: false
```
