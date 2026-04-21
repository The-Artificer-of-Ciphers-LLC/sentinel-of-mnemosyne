# Phase 26: Nyquist Validation Cleanup — Context

**Gathered:** 2026-04-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Retroactive Nyquist compliance for the four phases that shipped without it: create VALIDATION.md for Phases 04 and 06, repair the non-compliant VALIDATION.md files for Phases 07 and 10, and expand the Phase 10 Discord bot test stubs into real integration tests. This closes all remaining LOW-severity tech debt from the v0.1–v0.4 audit.

No new features. No changes to production code paths. Work is documentation + tests only.

</domain>

<decisions>
## Implementation Decisions

### Test Stubs — Phase 10 (item 5)

- **D-01:** The test files already exist at `interfaces/discord/tests/test_subcommands.py` and `interfaces/discord/tests/test_thread_persistence.py` (created by Phase 25/RD-09). Phase 26 does NOT create new files — it verifies these files pass, then expands them.
- **D-02:** Expand with real sample Discord commands: `:seed`, `:check`, `:pipeline`, and `plugin:` prefix routing. These are the representative subcommands from the 27-command system (2B-01) and plugin routing (bot.py lines 189–202).
- **D-03:** Tests are integration-level — they call the live Obsidian REST API (not mocked). Tests require a running Obsidian instance with the Local REST API plugin active.
- **D-04:** Cleanup strategy: `pytest` autouse fixture performs teardown via `DELETE /vault/{path}` for any test-specific paths written during the run. Tests write under a test-prefixed path (e.g., `ops/test-threads.md`) to avoid colliding with live data. No manual cleanup required.
- **D-05:** After tests pass and are expanded, update Phase 10's VALIDATION.md to reference the correct `interfaces/discord/tests/` paths (currently references stale `sentinel-core/tests/` paths).

### Repair Scope — Phases 07 and 10

- **D-06:** Full repair for both phases — not just metadata. Each must receive a complete Per-Task Verification Map with actual test commands, not just a frontmatter flip.
- **D-07:** Reconstruction approach: read each phase's PLAN.md and SUMMARY.md to determine what tasks were actually executed and what tests were written. The verification map should reflect historical intent, not just current test coverage.
- **D-08:** Phase 07 specifically needs: Per-Task Verification Map added (it has a Dimension Coverage table but no task-level map), frontmatter updated to `nyquist_compliant: true`, `status: complete`, `wave_0_complete: true`.
- **D-09:** Phase 10 specifically needs: all `sentinel-core/tests/` path references updated to `interfaces/discord/tests/`, sign-off checklist updated, frontmatter updated to `nyquist_compliant: true`, `status: complete`, `wave_0_complete: true`.

### VALIDATION.md Creation — Phases 04 and 06

- **D-10:** Reconstruct from source artifacts — read each phase's PLAN.md and SUMMARY.md to determine what was planned and what shipped. The Nyquist matrix should document historical intent, not just current test coverage.
- **D-11:** Phase 04 scope: multi-provider support, retry logic, LiteLLM provider — requirements PROV-01–PROV-05, CORE-07 (retry/timeout). Reference `sentinel-core/tests/test_litellm_provider.py` and `test_pi_adapter.py` for current test evidence.
- **D-12:** Phase 06 scope: Discord regression fix — requirements IFACE-02, IFACE-03, IFACE-04. Reference `interfaces/discord/tests/` for current test evidence. Phase 06 completed with `06-VERIFICATION.md` and `06-UAT.md` — read both for historical context.

### Claude's Discretion

- The exact structure of the Nyquist matrix tables (column layout, status values) should follow the pattern established in `25-VALIDATION.md` — use that as the authoritative template.
- For Phase 04 and 06, if some tasks have no automated test equivalent today, document them as `manual` type with the acceptance criteria from their VERIFICATION.md as the test instruction.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Nyquist Template (authoritative format)
- `.planning/phases/25-v0-40-pre-beta-refactoring-eliminate-duplicates-complete-stu/25-VALIDATION.md` — The only currently nyquist_compliant: true VALIDATION.md in this codebase. Use as structural template for all four phases.
- `.planning/phases/27-architecture-pivot/27-VALIDATION.md` — Second compliant reference if format comparison is needed.

### Phase 04 source artifacts
- `.planning/phases/04-ai-provider-multi-provider-support-retry-logic-fallback/04-CONTEXT.md` — Decisions made during Phase 04
- `.planning/phases/04-ai-provider-multi-provider-support-retry-logic-fallback/04-VERIFICATION.md` — What was verified at completion
- `.planning/phases/04-ai-provider-multi-provider-support-retry-logic-fallback/04-02-PLAN.md` — Plan details
- `.planning/phases/04-ai-provider-multi-provider-support-retry-logic-fallback/04-02-SUMMARY.md` — What was built

### Phase 06 source artifacts
- `.planning/phases/06-discord-regression-fix/06-CONTEXT.md` — Decisions made during Phase 06
- `.planning/phases/06-discord-regression-fix/06-VERIFICATION.md` — What was verified
- `.planning/phases/06-discord-regression-fix/06-UAT.md` — User acceptance testing record

### Phase 07 source artifacts
- `.planning/phases/07-phase-2-verification-mem-08/07-VALIDATION.md` — Existing (partial) VALIDATION.md to repair
- All `07-*-PLAN.md` and `07-*-SUMMARY.md` files in the Phase 07 directory — task reconstruction source

### Phase 10 source artifacts
- `.planning/phases/10-knowledge-migration-tool-import-from-existing-second-brain/10-VALIDATION.md` — Existing VALIDATION.md to repair
- `.planning/phases/10-knowledge-migration-tool-import-from-existing-second-brain/10-VERIFICATION.md` — Verified completion record (gaps_found status)
- All `10-*-PLAN.md` and `10-*-SUMMARY.md` files in the Phase 10 directory — task reconstruction source

### Discord test files (to expand)
- `interfaces/discord/tests/test_subcommands.py` — Existing file to verify + expand (2B-01 coverage)
- `interfaces/discord/tests/test_thread_persistence.py` — Existing file to verify + expand (2B-03 coverage)
- `interfaces/discord/bot.py` — Production bot code; lines 189–202 (plugin: routing), lines 253–269 (_persist_thread_id), lines 281–301 (setup_hook)

### Requirements traceability
- `.planning/REQUIREMENTS.md` — Full requirements list; Phase 04 covers PROV-01–05, Phase 06 covers IFACE-02–04, Phase 10 covers 2B-01, 2B-03, 2B-04

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `interfaces/discord/tests/conftest.py` — Existing conftest; expand with Obsidian integration fixture + teardown autouse fixture
- `sentinel-core/tests/` — The original test suite; useful for understanding what tests covered phase 04/06/07 requirements
- `interfaces/discord/bot.py` — `_SUBCOMMAND_PROMPTS` dict and `_PLUGIN_PROMPTS` dict are the routing tables under test

### Established Patterns
- Test isolation: existing discord tests stub out the `discord` library entirely (no live Discord needed) — keep this pattern, only add live Obsidian calls
- The autouse teardown fixture pattern is established in `sentinel-core/tests/conftest.py` — apply same pattern for Obsidian cleanup

### Integration Points
- Obsidian REST API available at `OBSIDIAN_BASE_URL` env var (default: `http://host.docker.internal:27124`) with `Authorization: Bearer {OBSIDIAN_API_KEY}`
- Phase 26 does not modify any production code — all changes are in `.planning/phases/` VALIDATION.md files and `interfaces/discord/tests/`

</code_context>

<specifics>
## Specific Ideas

- Test cleanup should use `ops/test-run-{uuid}/` as the write prefix so teardown is a single recursive delete rather than per-file DELETEs
- The integration tests should be marked with `@pytest.mark.integration` so they can be skipped in environments without live Obsidian: `pytest -m "not integration"` runs the fast suite, `pytest` runs everything
- Phase 26 success criteria item 5 says "all tests pass" — the integration marker ensures CI can run the full suite when Obsidian is available and the fast suite otherwise

</specifics>

<deferred>
## Deferred Ideas

### Phase 28 (proposed) — LLM Health & Startup Validation
The following ideas came up during this discussion but are outside Phase 26's scope. They are required for a complete v0.40 release — the system cannot function without a loaded LLM — and should be addressed in a new Phase 28:

1. **LLM availability check at startup** — Validate that LM Studio (or configured provider) is reachable and has a model loaded before the Sentinel accepts traffic. Currently the system fails at request time rather than startup time.
2. **LLM performance/hardware baseline** — Validate that the configured LLM is appropriate for the host hardware platform (e.g., warn if a 70B model is configured on hardware with insufficient VRAM).

These should be Phase 28: "LLM Health & Startup Validation" as part of completing the v0.40 milestone.

</deferred>

---

*Phase: 26-nyquist-validation-cleanup*
*Context gathered: 2026-04-21*
