---
phase: 34
reviewers: [lm_studio]
reviewed_at: 2026-04-25T19:15:41Z
plans_reviewed: [34-01-PLAN.md, 34-02-PLAN.md, 34-03-PLAN.md, 34-04-PLAN.md, 34-05-PLAN.md]
lm_studio_model: qwen3.6-35b-a3b
notes: claude skipped (self — running inside Claude Code CLI); opencode skipped (ProviderModelNotFoundError — model qwen3.5-27b-unsloth-mlx not loaded in LM Studio)
---

# Cross-AI Plan Review — Phase 34: Session Notes

## LM Studio Review (qwen3.6-35b-a3b)

### Plan 34-01: Wave 0 RED Test Scaffolding

**Summary:** A disciplined TDD-first approach that correctly prioritizes test stubs over implementation. The plan maps cleanly to SES-01/02/03 and covers the pure helpers, integration paths, Discord UI stubs, and UAT skeleton. It establishes a clear RED state before any production code lands.

**Strengths:**
- Strict adherence to TDD principles (RED → GREEN) prevents premature implementation bias.
- Explicit coverage of pure helpers, integration paths, and Discord UI components ensures early validation of cross-boundary contracts.
- `StatefulMockVault` correctly simulates Obsidian's PATCH semantics (append/replace) without requiring a live vault.
- UAT runner skeleton enables automated validation of the full session lifecycle before Wave 1 lands.

**Concerns:**
- **HIGH:** Function-scope imports inside tests are a pytest collection workaround that can cause flaky test discovery or mask missing dependencies. Consider lazy imports via `conftest.py` or pytest fixtures instead.
- **MEDIUM:** Missing explicit stubs for flag parsing (`--force`, `--retry-recap`) and collision policy (D-06) in the unit test matrix.
- **LOW:** No stubs for timezone handling (D-13) or error paths (LLM failure, Obsidian down).

**Suggestions:**
- Replace function-scope imports with `conftest.py` lazy-loading or `pytest.importorskip()` to avoid collection-time side effects.
- Add explicit test cases for `--force` and `--retry-recap` flag parsing in `parse_session_verb_args`.
- Include stubs for D-06 collision checks and D-13 timezone rendering to ensure full requirement coverage before Wave 1.

**Risk Assessment:** `MEDIUM`
The TDD approach is sound, but the import workaround and missing flag/error stubs introduce collection fragility. Addressing these before Wave 1 lands will prevent test suite rot during implementation.

---

### Plan 34-02: Wave 1 Pure Helpers + ObsidianClient.patch_heading + Config

**Summary:** Solid implementation of pure logic and Obsidian API differentiation. Correctly enforces the critical constraint that `patch_heading` uses different headers than `patch_frontmatter_field`, and covers all 10 required helpers with proper timezone handling.

**Strengths:**
- Explicit separation of pure logic from I/O aligns with clean architecture principles.
- `zoneinfo.ZoneInfo` usage respects D-13 without legacy pytz dependencies.
- Correct header differentiation for Obsidian PATCH operations prevents API misrouting.
- Covers all 10 helpers specified in the roadmap, including dual-pass NPC linking and location stub generation.

**Concerns:**
- **HIGH:** No error handling or retry logic for `patch_heading`. Obsidian REST API is local/networked and prone to transient 429/5xx errors. Without retries, session logs will fail silently or crash the bot.
- **MEDIUM:** `build_npc_link_pattern` compiles a regex per session with "sorted longest-first, IGNORECASE". This is inefficient for large rosters and should be cached or precompiled.
- **LOW:** `detect_npc_slug_collision` purpose is unclear in context (location vs NPC slug conflicts?).

**Suggestions:**
- Add exponential backoff retry logic (3 attempts, 1s/2s/4s delays) for `patch_heading` to handle Obsidian rate limits or temporary unavailability.
- Cache compiled regex patterns in a module-level `functools.lru_cache` or compile once at startup.
- Clarify collision detection scope and add unit tests for edge cases (e.g., "Drake" vs "Drakes").

**Risk Assessment:** `MEDIUM`
Core logic is sound, but missing retry logic and regex inefficiency will cause production failures under load or with large NPC rosters. Add retries and caching before Wave 2.

---

### Plan 34-03: Wave 2 FastAPI Route + LLM Functions

**Summary:** Comprehensive route implementation that correctly handles the 5-verb contract, dual-pass NPC linking, skeleton notes on failure (D-31), and `--retry-recap` (D-32). The LLM helpers correctly handle markdown fence stripping and JSON parsing.

**Strengths:**
- Clear route contract with explicit verb routing (`start`, `log`, `end`, `show`, `undo`).
- Correctly implements D-06 collision policy and D-31 skeleton fallback.
- Dual-pass NPC linking (fast-pass + LLM end) matches D-21 and reduces false positives.
- `generate_session_recap` correctly handles LLM markdown fence stripping and JSON parsing.

**Concerns:**
- **HIGH:** Module-level singletons (`obsidian = None`, `npc_roster_cache = None`) violate FastAPI best practices. They leak state across requests, break dependency injection, and make testing harder.
- **HIGH:** No explicit handling of D-07 (Obsidian-down at start). The route will crash or return 500 if Obsidian is unreachable, violating the hard requirement.
- **MEDIUM:** `generate_session_recap` JSON parse fallback isn't defined. If the LLM returns malformed JSON, the route should fall back to a skeleton note (D-31) rather than crashing.
- **LOW:** `show` verb patches "Story So Far" but doesn't clarify overwrite vs. append behavior (D-19).

**Suggestions:**
- Replace module-level singletons with FastAPI `Depends()` or lifespan-scoped state objects.
- Add explicit Obsidian connectivity check at route startup (D-07) and return 503 with clear error message if unreachable.
- Implement JSON parse fallback: on failure, trigger skeleton note creation (D-31) and log warning.
- Clarify "Story So Far" patch behavior: should overwrite the section or append? Recommend overwrite for consistency.

**Risk Assessment:** `HIGH`
Module-level state and missing D-07 handling are critical architectural flaws that will cause state leaks, test failures, and production crashes. Refactoring to DI and adding connectivity checks are mandatory before Wave 3.

---

### Plan 34-04: Main.py Wiring + Compose Env Vars

**Summary:** Correctly registers the session route and adds required environment variables. The lifespan pattern attempts to wire dependencies, but uses anti-pattern module assignment instead of FastAPI's native dependency injection.

**Strengths:**
- Explicit 15-route registration payload matches architecture expectations.
- Clear env var additions (`SESSION_AUTO_RECAP`, `SESSION_TZ`, `SESSION_RECAP_MODEL`) align with D-13/D-24.
- Lifespan shutdown cleanup prevents resource leaks.

**Concerns:**
- **HIGH:** `_session_module.obsidian = obsidian_client` bypasses FastAPI's DI system. It creates hidden coupling, makes unit testing harder, and risks state leakage if the module is reloaded or imported multiple times.
- **MEDIUM:** `build_npc_roster_cache` runs at lifespan startup, but D-22 states it should be "refreshed on session start". This creates a mismatch between startup caching and runtime refresh requirements.
- **LOW:** No validation for missing/invalid env vars (e.g., invalid timezone string).

**Suggestions:**
- Replace module assignment with FastAPI `Depends()` or lifespan-scoped state (`app.state`).
- Move NPC cache refresh to session `start` verb (per D-22) or add a configurable TTL/refresh trigger.
- Add startup validation for env vars with clear error messages (e.g., `python -c "zoneinfo.ZoneInfo('Invalid/Zone')"`).

**Risk Assessment:** `MEDIUM`
The wiring is functionally correct but architecturally fragile. Replacing module assignment with DI and aligning cache refresh timing will significantly improve maintainability and testability.

---

### Plan 34-05: Discord Bot Wiring

**Summary:** Correctly extends the bot with session command surface, implements the 180s timeout RecapView, and uses the placeholder→edit pattern for slow queries. Payload formatting aligns with module expectations.

**Strengths:**
- `RecapView` correctly implements 180s timeout with graceful fallback to plain text.
- Placeholder→edit pattern for `show`/`end` verbs improves UX by avoiding long wait times.
- Correctly formats payload to module (`{verb, args, flags}`).

**Concerns:**
- **HIGH:** Payload lacks session/channel context (`guild_id`, `channel_id`). The module cannot determine which session to log to or where to post responses.
- **HIGH:** No error handling for module failures. If `/modules/pathfinder/session` returns 4xx/5xx, the bot will crash or leave stale placeholders.
- **MEDIUM:** `RecapView` timeout handling doesn't specify behavior for successful recap vs. timeout edit race conditions (Discord API rate limits).
- **LOW:** No mention of D-06 collision policy or D-07 Obsidian-down handling at the bot level.

**Suggestions:**
- Include `guild_id` and `channel_id` in the payload to the module for session routing.
- Add error handling: if module returns failure, edit placeholder to error message and log warning.
- Implement Discord API rate limit handling for `RecapView` timeout vs success edits (use `try/except discord.HTTPException`).
- Propagate D-06/D-07 errors from module to bot UI (e.g., "Session already exists" or "Vault unreachable").

**Risk Assessment:** `HIGH`
Missing session context and error handling will cause silent failures, stale placeholders, and broken UX. Adding payload context and robust error handling is mandatory before deployment.

---

### Overall Risk Assessment

**Overall Risk Level:** `HIGH`

**Justification:**
While individual plans are well-structured and cover requirements thoroughly, cross-cutting architectural flaws create significant production risk:
1. **State Management:** Module-level singletons (34-03, 34-04) violate FastAPI patterns and will cause state leakage, test brittleness, and deployment fragility.
2. **Error Handling & Retries:** Missing Obsidian connectivity checks (D-07), LLM JSON parse fallbacks, and Discord API error handling will cause silent failures or crashes under real-world conditions.
3. **Payload Context:** Discord bot payload lacks session/channel routing context, breaking multi-session support.
4. **Caching/Performance:** Regex compilation per session and startup-only NPC caching conflict with D-22 refresh requirements.

**Critical Path Recommendations:**
- Replace module-level singletons with FastAPI `Depends()` or lifespan-scoped state across 34-03/04.
- Add exponential backoff retries to `patch_heading` and JSON parse fallbacks to LLM helpers (34-02/03).
- Include `guild_id`/`channel_id` in Discord→module payloads and add error propagation to bot UI (34-05).
- Align NPC cache refresh with D-22 (session start, not just lifespan) and add startup env var validation (34-04).
- Address TDD import workarounds and add missing flag/collision stubs before Wave 1 (34-01).

Once these cross-cutting issues are resolved, the phase risk drops to `LOW`. The plans demonstrate strong requirement coverage and architectural awareness; tightening error handling, state management, and payload routing will ensure production readiness.

---

## Consensus Summary

Only one reviewer contributed to this cycle (LM Studio / qwen3.6-35b-a3b). The review flags several cross-cutting concerns that apply across all five plans.

### Agreed Strengths

- Strong TDD discipline: Wave 0 RED scaffolding before any production code is a solid practice.
- Clean separation of pure helpers (session.py) from I/O (route, Obsidian client) is well-designed.
- The dual-pass NPC linking strategy (log-time fast-pass + session-end LLM) is pragmatic.
- `StatefulMockVault` test fixture is correctly designed for integration testing without a live vault.
- `RecapView` 180s timeout with graceful degradation is the right UX approach.

### Agreed Concerns

- **HIGH — Module-level singletons:** The `obsidian = None` / `npc_roster_cache = None` pattern in routes/session.py and its assignment in main.py lifespan is a known anti-pattern in FastAPI. All prior phases used it (it's the established project pattern), but the reviewer flags it as fragile. **Context: this pattern is consistent with Phases 29–33 in this codebase. It is the established project pattern, not a deviation. Flagged here for awareness; not a blocker.**
- **HIGH — D-07 Obsidian-down handling:** D-07 is a stated requirement (refuse at start if Obsidian unreachable) but the plan doesn't explicitly detail the connectivity check implementation. This should be verified in 34-03 execution.
- **HIGH — Discord bot error handling:** No explicit error handling when the module returns 4xx/5xx. The placeholder→edit pattern should include an error branch.
- **HIGH — Discord payload missing user_id context:** The `user_id` field IS included in `SessionRequest` per 34-03, but guild_id/channel_id for routing is not addressed. However, because session state is per-date in Obsidian (not per-user/channel), this is lower actual risk than the reviewer assessed.

### Divergent Views

- **Function-scope imports (34-01):** Reviewer flags as HIGH but this is the deliberate project pattern from Phase 33 (test_rules.py). It prevents collection-time ImportError during RED phase. The pattern is intentional, not a defect.
- **Module-level singletons (34-03/04):** Reviewer flags as HIGH architectural flaw. In practice, all prior phases (29–33) use this exact pattern successfully. FastAPI `Depends()` would require refactoring all modules. Not a per-phase regression.
- **`guild_id`/`channel_id` in payload:** Session state in Obsidian is date-scoped, not channel-scoped. The concern about "routing context" is partially moot — the module already knows the session date from the server clock.

### Reviewer Notes on False Positives

The reviewer (qwen3.6-35b-a3b) applied generic FastAPI best practices that don't account for this project's established patterns. The following concerns are noted but assessed as **non-blocking** for this phase:
- Function-scope imports (established TDD pattern, Phases 29–33)
- Module-level singletons (consistent across all 5 prior modules)
- guild_id/channel_id payload (session is date-scoped, not channel-scoped)

The following concerns ARE actionable:
- D-07 Obsidian-down check implementation detail (verify in 34-03 execution)
- Discord bot error handling for module failures (34-05)
- JSON parse fallback definition for `generate_session_recap` (34-03)
