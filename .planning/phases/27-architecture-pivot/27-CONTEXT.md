# Phase 27: Architecture Pivot (Path B) — Context

**Gathered:** 2026-04-20
**Status:** Ready for planning
**Source:** Direct capture — decisions made in prior session after architecture crisis declared

<domain>
## Phase Boundary

This phase realigns the entire Sentinel architecture to Path B, then prepares v0.5+ to build on the new contract. It does NOT implement any module — it defines and scaffolds the contract that every future module will follow.

**What this phase delivers:**
1. ARCHITECTURE-Core.md rewritten to Path B — canonical design doc going forward
2. `POST /modules/register` + proxy routing in sentinel-core — the new module contract
3. Pi harness removed from base docker-compose.yml — moved to opt-in via `--pi` flag in sentinel.sh
4. ROADMAP.md updated — Pi scoped to v0.7, v0.5 Pathfinder replanned under Path B
5. Discord bot `/sentask` renamed to `/sen`

**What this phase explicitly does NOT do:**
- Implement any module (Pathfinder, Music, Finance, etc.) — those come after
- Remove Pi harness container code or pi-adapter — just remove it from base compose; code stays
- Change the LiteLLM-direct chat pipeline — it stays exactly as Phase 25 left it

</domain>

<decisions>
## Implementation Decisions

### Architecture: Path B (LOCKED)

- **Chat route stays LiteLLM-direct.** `routes/message.py` calls LiteLLM → LM Studio. Pi is NOT in the message route. This is permanent, not a temporary workaround.
- **Modules expose HTTP API endpoints.** Each module runs as a Docker container with its own FastAPI (or similar) service. It registers its endpoint(s) with sentinel-core on startup.
- **Sentinel-core acts as the API gateway.** It maintains a module registry and proxies requests to the correct module endpoint.
- **Pi harness is demoted to optional power tool.** It is removed from `docker-compose.yml` base stack. A `--pi` flag in `sentinel.sh` re-adds it for advanced/coder use cases. Its eventual home is v0.7 scope.
- **Discord bot routes module requests by slash command.** `/sen` (renamed from `/sentask`) handles chat. Future module slash commands (e.g., `/npc`, `/log`) call specific module endpoints via sentinel-core proxy.

### Module Registration Contract (LOCKED)

- **Endpoint:** `POST /modules/register`
- **Payload:** `{ "name": str, "base_url": str, "routes": [{ "path": str, "description": str }] }`
- **Behavior:** sentinel-core stores the registration in-memory (no persistence required in Phase 27). Returns `{ "status": "registered" }`.
- **Proxy:** `POST /modules/{name}/{path}` — sentinel-core forwards the request body to the registered module's `base_url + path`, streams the response back.
- **Health:** If a module's base_url is unreachable, sentinel-core returns 503 with `{ "error": "module unavailable" }`.

### Pi Harness Removal from Base Compose (LOCKED)

- Remove the `pi-harness` service from `docker-compose.yml` (or comment with clear `# opt-in via --pi flag`).
- `sentinel.sh` gets a `--pi` flag: `if [[ "$*" == *"--pi"* ]]; then docker compose ... -f pi-harness/compose.yml ...; fi`
- Pi harness container code, Dockerfile, pi-adapter.ts — all stay intact. Just not in the default stack.
- `sentinel-core` must degrade gracefully when Pi is absent — no startup errors, no health-check failures from missing Pi service.

### Discord Command Rename (LOCKED)

- `/sentask` → `/sen`
- Same behavior, same parameters. Pure rename.
- Update `bot.py` slash command definition and any user-facing help text.

### ARCHITECTURE-Core.md Rewrite (LOCKED)

- Document the actual runtime: LiteLLM-direct chat, module API gateway pattern, Pi as optional.
- Include a diagram description (ASCII or mermaid) showing: User → Interface → sentinel-core → LiteLLM → LM Studio, with a separate branch: Interface → sentinel-core → Module Registry → Module Container.
- Remove all language about Pi being the "brain" or primary AI layer.
- PRD §3 (AI layer description) must be updated to match.

### ROADMAP Updates (LOCKED)

- Phase 11 (Pathfinder) replanned: goal becomes "Deliver the first module under the Path B contract — a FastAPI container that registers with sentinel-core, exposes NPC/session endpoints, and is added via `docker compose --include`."
- Pi harness feature work (skill dispatch, tool-use loop) moved to a new phase in v0.7 scope.
- Phase 26 (Nyquist Validation Cleanup) remains in backlog — it is housekeeping and not blocking Path B work.

### Claude's Discretion

- How to store module registry in sentinel-core (dict, Pydantic model, simple list — any is fine for Phase 27)
- Whether to add a `GET /modules` endpoint for inspection (nice to have, not required)
- Exact sentinel.sh flag syntax — `--pi` is the locked name, implementation details flexible
- PRD §3 update scope — update only the AI layer section, not the full PRD

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture & Design
- `ARCHITECTURE-Core.md` — current (Path A) doc; this phase rewrites it to Path B
- `.planning/PROJECT.md` — project decisions log; update Key Decisions table after pivot
- `.planning/ROADMAP.md` — update Phase 11 goal and add Pi-to-v0.7 note

### Current Implementation (understand before changing)
- `sentinel-core/app/routes/message.py` — LiteLLM-direct route (DO NOT change)
- `docker-compose.yml` — root compose; remove pi-harness service entry
- `sentinel.sh` — startup script; add --pi flag here
- `interfaces/discord/app/bot.py` — rename /sentask → /sen here

### Phase 25 Output (what was built — don't regress)
- `.planning/phases/25-v0-40-pre-beta-refactoring-eliminate-duplicates-complete-stu/` — SUMMARY.md and VERIFICATION.md show what Phase 25 shipped

</canonical_refs>

<specifics>
## Specific Ideas

- The module registry can be as simple as `module_registry: dict[str, ModuleRegistration] = {}` in `main.py` lifespan state, accessed via `request.app.state.module_registry`.
- Proxy implementation: `httpx.AsyncClient` (already a dependency) forwarding to `module.base_url + path` with the original request body. Stream response back.
- `sentinel.sh` already exists (or should) as the user-facing startup script. If it doesn't exist, create it as a thin wrapper around `docker compose up`.
- The `/sen` rename is a one-line change in bot.py (`@app.slash_command(name="sen")`).

</specifics>

<deferred>
## Deferred Ideas

- Pi harness skill dispatch and tool-use loop — moved to v0.7 scope
- Module persistence (registry survives restart) — not needed until multiple modules ship
- Module authentication (modules authenticating to sentinel-core) — deferred to Phase 17 (Community & Polish)
- `GET /modules` inspection endpoint — nice to have, not required for Phase 27
- Phase 26 (Nyquist Validation Cleanup) — remains in backlog, not blocking

</deferred>

<gaps_required>
## Gap Items — MUST BE PLANNED (LOCKED)

These items have been surfaced repeatedly in research, review, and UAT but were never generated into plans. They are **mandatory gap-closure work** for Phase 27. The planner MUST create plans for all four.

### GAP-A: asyncio_mode missing — all async tests are false-positives (CR-01, CRITICAL)

- **D-GA-01:** Add `asyncio_mode = "auto"` to `[tool.pytest.ini_options]` in `sentinel-core/pyproject.toml`.
- **D-GA-02:** After fixing, run the full pytest suite and confirm tests actually execute (not just collect and return truthy coroutine objects).
- **Affects:** `sentinel-core/tests/test_modules.py`, `interfaces/discord/tests/test_subcommands.py`, `interfaces/discord/tests/test_thread_persistence.py` — all Phase 27 async tests have been false-positives since they were written.
- **Why mandatory:** The Phase 27 test suite has never actually run. Every "green" test result is a lie until this is fixed.

### GAP-B: Module proxy does not forward X-Sentinel-Key to modules (WR-01)

- **D-GB-01:** `sentinel-core/app/routes/modules.py` proxy handler must forward `X-Sentinel-Key` header when calling module containers.
- **D-GB-02:** The forwarded value must be the same key the caller used to authenticate with sentinel-core (available via `request.headers.get("X-Sentinel-Key")`).
- **Why mandatory:** Per the architecture spec (ARCHITECTURE-Core.md §3.4), all modules receive SENTINEL_API_KEY. Without forwarding it, any module that checks auth will reject every request from sentinel-core with 401, silently surfacing as a 503 to the caller.

### GAP-C: Discord slash commands not confirmed registered

- **D-GC-01:** The `/sen` slash command (and any subcommands) must be confirmed as actually registered with Discord — not just defined in bot.py, but synced to the Discord API and visible in the slash command picker.
- **D-GC-02:** A plan must include a verification step that confirms the bot's command tree is registered: `bot.tree.sync()` must have been called and completed without errors.
- **D-GC-03:** Any subcommands that the architecture specifies but are not yet registered (e.g., `/sen ask`, `/sen help`, or module-specific commands) must be listed and either implemented or explicitly deferred with a reason.
- **Why mandatory:** "Not a single Discord command is created" — the rename happened in code but Discord slash commands require an explicit sync to Discord's servers. Code presence ≠ registration.

### GAP-D: No LLM↔Obsidian integration validation

- **D-GD-01:** There must be at least one integration test (or validated manual test) that confirms the full pipeline works: user message → sentinel-core → LiteLLM provider → response that demonstrably includes context read from Obsidian.
- **D-GD-02:** The test must verify that Obsidian context (self-context files, recent sessions) is injected into the LiteLLM prompt — not just that the LiteLLM call succeeds.
- **D-GD-03:** Acceptable form: a pytest integration test with a real httpx call to a running sentinel-core, OR a documented manual UAT step with expected output that references actual vault content.
- **Why mandatory:** "There is no validation the LLM talks to Obsidian." The system's core value proposition is AI + memory. Without this validation, there is no evidence the two halves are connected.

</gaps_required>

---

*Phase: 27-architecture-pivot*
*Context gathered: 2026-04-20 via direct capture (prior session discussion)*
*Updated: 2026-04-21 — added GAP-A through GAP-D from repeated review/UAT findings*
