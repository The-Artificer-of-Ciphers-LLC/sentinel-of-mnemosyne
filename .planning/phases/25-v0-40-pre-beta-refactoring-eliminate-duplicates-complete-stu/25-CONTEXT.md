# Phase 25: v0.40 Pre-Beta Refactoring — Context

**Gathered:** 2026-04-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Codebase consolidation before the v0.40 pre-beta milestone. This phase eliminates all known duplicates (DUP-01–05), completes all stubs (STUB-01–08), resolves architecture contradictions (CONTRA-01–04), and implements all 10 refactoring directives (RD-01–RD-10) as defined in `V040-REFACTORING-DIRECTIVE.md`.

Phase 24 work (pentest-agent compose wiring + missing VERIFICATION artifacts) is folded into this phase — the Phase 24 plans execute first as the opening block, then RD directives follow.

No new features. No scope beyond what `V040-REFACTORING-DIRECTIVE.md` specifies.

</domain>

<decisions>
## Implementation Decisions

### Phase 24 Integration

- **D-01:** Phase 24 (pentest-agent wire + VERIFICATION artifacts for phases 02, 05, 07) is folded into Phase 25. The planner should treat Phase 24's 3 existing plans as Phase 25's opening block. Phase 25 plans are numbered starting from plan 04 (after the 3 Phase 24 plans). Phase 25 SEC-04 work (RD-07) depends on Phase 24's D-01 completing first.

### Plan Breakdown Strategy

- **D-02:** Group by dependency cluster — approximately 4–5 plans total (not counting the 3 folded Phase 24 plans):
  - **Cluster A — Small refactors (independent):** RD-03 (retry config), RD-04 (ObsidianClient helper), RD-08 (iMessage attributedBody), RD-09 (thread persistence tests). All small, no mutual dependencies.
  - **Cluster B — Core features:** RD-01 (shared sentinel_client), RD-02 (consolidate providers to LiteLLM only), RD-05 (implement /status and /context/{user_id} endpoints), RD-06 (rewrite sentinel.sh to profiles). RD-02 depends on RD-03.
  - **Cluster C — Security baseline:** RD-07 (SEC-04 jailbreak baseline). Depends on Phase 24's D-01 (pentest-agent compose wiring).
  - **Cluster D — Doc sync:** RD-10 (architecture doc synchronization). Depends on RD-02 (provider consolidation) and RD-05 (new endpoints) being complete.

### MessageEnvelope Expansion (CONTRA-01)

- **D-03:** Expand the Pydantic model, not trim the doc. Add two optional fields to `MessageEnvelope` in `sentinel-core/app/models.py`:
  ```python
  source: str | None = None
  channel_id: str | None = None
  ```
  All existing interfaces continue to work without changes (optional fields default to None). Update `docs/ARCHITECTURE-Core.md` to document these as optional fields. Leave `id`, `timestamp`, `attachments`, `metadata` (the remaining doc-only fields) documented as "reserved for future interface expansion — not currently in use."

### iMessage attributedBody Decoding (RD-08)

- **D-04:** Use `plistlib` (Python stdlib, no new dependency). The directive's code snippet is authoritative:
  ```python
  def _decode_attributed_body(blob: bytes) -> str | None:
      try:
          import plistlib
          plist = plistlib.loads(blob)
          return plist.get("NS.string", None)
      except Exception:
          return None
  ```
  Do NOT add `imessage_reader` as a dependency — the directive's text mentioning it is superseded by the code snippet.

- **D-05:** Full Disk Access detection and messaging. macOS cannot programmatically trigger the Full Disk Access permission dialog (unlike camera/microphone). At `bridge.py` startup, before the polling loop begins:
  1. Attempt to open `~/Library/Messages/chat.db` in read mode.
  2. If `PermissionError` is raised, print a clear message to stderr explaining:
     - Why Full Disk Access is required (chat.db is protected by macOS SIP)
     - Step-by-step instructions: System Settings → Privacy & Security → Full Disk Access → enable for Terminal (or whichever process runs the bridge)
  3. Exit with code 1 so Docker / the process manager can surface the failure.
  This replaces silently failing or dropping messages.

### iMessage Interface Scope Clarification

- **D-06:** The existing chat.db polling + osascript approach is the authoritative implementation strategy. There is no Apple-certified personal-use iMessage API. Apple Messages for Business is for business-to-customer messaging and is not applicable to a personal AI assistant. The current bridge approach is documented, feature-flagged, and approved for v0.40.

### Claude's Discretion

- Exact cluster boundaries and plan counts within "Group by dependency cluster" — the planner may refine this based on actual file count and test coverage requirements.
- Retry config import style in `pi_adapter.py` and `litellm_provider.py` — wildcard import vs. explicit named imports from `retry_config.py`.
- Whether `GET /status` shares the router with `GET /context/{user_id}` in one `routes/status.py` file or splits into two files (directive recommends one file).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Primary Directive (authoritative — immutable)
- `V040-REFACTORING-DIRECTIVE.md` — All DUP, STUB, CONTRA, RD definitions. Sections 2–10 define every item in scope. Section 10 acceptance criteria are the phase exit condition.

### Requirements
- `.planning/REQUIREMENTS.md` — SEC-04 checkbox must be checked after RD-07 completes. All other requirements referenced by Phase 25 are already checked.

### Architecture Docs (targets for RD-10 updates)
- `docs/ARCHITECTURE-Core.md` — Update for CONTRA-01 (envelope fields), CONTRA-02 (port 3000), CONTRA-04 (session path), new routes /status and /context/{user_id}.
- `docs/obsidian-lifebook-design.md` — Update for CONTRA-03 (5 self/ files, not 3).

### Phase 24 Plans (execute first, in order)
- `.planning/phases/24-pentest-agent-wire-and-verification-artifacts/24-01-PLAN.md`
- `.planning/phases/24-pentest-agent-wire-and-verification-artifacts/24-02-PLAN.md`
- `.planning/phases/24-pentest-agent-wire-and-verification-artifacts/24-03-PLAN.md`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `sentinel-core/app/clients/pi_adapter.py`: Has `@retry` decorator with the exact parameters that `retry_config.py` will centralize. Import pattern to replicate.
- `sentinel-core/app/clients/litellm_provider.py`: Same retry decorator pattern. Also has `get_context_window_from_lmstudio()` that RD-10 docs need to reference.
- `sentinel-core/app/clients/obsidian.py`: 5 methods with identical try/except patterns — the extraction target for `_safe_request()`.
- `sentinel-core/app/routes/message.py`: Model for how new routes (status.py) should integrate with `request.app.state.*` for dependency access.
- `sentinel-core/tests/`: 12 test files already exist covering most modules. Missing: `test_status.py`. Misplaced: `test_bot_thread_persistence.py` (belongs in `interfaces/discord/tests/`).

### Established Patterns
- All route handlers access dependencies via `request.app.state.*` (no FastAPI `Depends()` — consistent with existing message.py pattern).
- `@retry` decorator from tenacity wraps async methods directly (not via middleware).
- Test files use `pytest-asyncio` with `AsyncClient(app=app, base_url="http://test")` pattern.

### Integration Points
- `sentinel-core/app/main.py` lifespan: where provider map is built — RD-02 modifies this.
- `sentinel-core/app/main.py` router registration: where `status.py` router gets included — RD-05 adds here.
- `interfaces/discord/bot.py` and `interfaces/imessage/bridge.py`: both import the inline `call_core()` function that RD-01 replaces with `SentinelCoreClient`.
- `docker-compose.yml` includes block: where Phase 24 pentest-agent include goes (D-01).
- `interfaces/discord/compose.yml`, `pi-harness/compose.yml`, `sentinel-core/compose.yml`: each needs a `profiles:` key added for RD-06.

### Files to Create (net new)
- `shared/sentinel_client.py`
- `shared/__init__.py`
- `shared/tests/test_sentinel_client.py`
- `sentinel-core/app/clients/retry_config.py`
- `sentinel-core/app/routes/status.py`
- `sentinel-core/tests/test_status.py`
- `interfaces/discord/tests/test_thread_persistence.py`
- `interfaces/discord/tests/test_subcommands.py`
- `interfaces/imessage/tests/test_bridge.py`
- `security/__init__.py`
- `security/pentest/__init__.py`
- `security/pentest/jailbreak_baseline.py`
- `security/JAILBREAK-BASELINE.md`
- `modules/README.md`

### Files to Delete
- `sentinel-core/app/clients/ollama_provider.py`
- `sentinel-core/app/clients/llamacpp_provider.py`
- `sentinel-core/tests/test_bot_thread_persistence.py` (moved to discord/tests/)
</code_context>
