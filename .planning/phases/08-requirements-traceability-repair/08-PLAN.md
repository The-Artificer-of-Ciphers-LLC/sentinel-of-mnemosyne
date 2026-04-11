---
phase: 08-requirements-traceability-repair
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - .planning/REQUIREMENTS.md
  - .planning/PROJECT.md
  - .planning/STATE.md
  - .planning/phases/01-core-loop/01-VALIDATION.md
  - .planning/phases/03-interfaces/03-VALIDATION.md
autonomous: true
requirements:
  - DOCS-REPAIR
must_haves:
  truths:
    - "REQUIREMENTS.md checkboxes match actual shipped state through Phase 7"
    - "Traceability table shows Complete for CORE-01..07, IFACE-01..06, PROV-01..05, MEM-05, MEM-08"
    - "PROJECT.md checkboxes match the same shipped scope"
    - "STATE.md completed_phases reads 7 (not 4 or 5)"
    - "01-VALIDATION.md has a Nyquist Test Matrix and nyquist_compliant: true"
    - "03-VALIDATION.md has a Nyquist Test Matrix and nyquist_compliant: true"
  artifacts:
    - path: ".planning/REQUIREMENTS.md"
      provides: "Accurate v1 requirement status"
      contains: "[x] **CORE-01**"
    - path: ".planning/PROJECT.md"
      provides: "Accurate project checklist"
      contains: "[x] Pi harness runs in Docker"
    - path: ".planning/STATE.md"
      provides: "Accurate execution state"
      contains: "completed_phases: 7"
    - path: ".planning/phases/01-core-loop/01-VALIDATION.md"
      provides: "Nyquist compliance record for Phase 1"
      contains: "nyquist_compliant: true"
    - path: ".planning/phases/03-interfaces/03-VALIDATION.md"
      provides: "Nyquist compliance record for Phase 3"
      contains: "nyquist_compliant: true"
  key_links:
    - from: "REQUIREMENTS.md traceability table"
      to: "checkbox state"
      via: "consistent status across both representations"
---

<objective>
Repair all stale documentation artifacts so that REQUIREMENTS.md, PROJECT.md, per-phase VALIDATION.md files, and STATE.md accurately reflect what has been shipped through Phase 7.

Purpose: The milestone audit (2026-04-10) identified that checkboxes, traceability tables, and VALIDATION.md Nyquist flags were never updated after Phases 1, 3, 4, 6, and 7 completed. This creates false negatives in planning tooling and confusing audit trails.

Output: Five updated files — all documentation, no code changes.
</objective>

<execution_context>
@/Users/trekkie/.claude/get-shit-done/workflows/execute-plan.md
@/Users/trekkie/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/STATE.md
@.planning/REQUIREMENTS.md
@.planning/phases/08-requirements-traceability-repair/08-CONTEXT.md
@.planning/phases/01-core-loop/01-VALIDATION.md
@.planning/phases/01-core-loop/01-VERIFICATION.md
@.planning/phases/03-interfaces/03-VALIDATION.md
@.planning/phases/03-interfaces/03-VERIFICATION.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Update REQUIREMENTS.md — checkboxes and traceability table (D-01)</name>
  <files>.planning/REQUIREMENTS.md</files>
  <action>
Read REQUIREMENTS.md in full, then make the following targeted edits:

**CHECKBOX FLIPS — change `[ ]` to `[x]` for these requirements only:**

Core Infrastructure (all 7, Phase 1 complete):
- CORE-01, CORE-02, CORE-03, CORE-04, CORE-05, CORE-06, CORE-07

Interfaces (all 6, Phases 3 + 6 complete):
- IFACE-01, IFACE-02, IFACE-03, IFACE-04, IFACE-05, IFACE-06

AI Provider (all 5, Phase 4 complete):
- PROV-01, PROV-02, PROV-03, PROV-04, PROV-05

Memory Layer (2 specific items, Phase 7 Plan 2 complete):
- MEM-05, MEM-08

**TRACEABILITY TABLE — change "Pending" to "Complete" for these rows:**
- CORE-01 through CORE-07 → "Complete"
- IFACE-01 through IFACE-06 → "Complete"
- PROV-01 through PROV-05 → "Complete"
- MEM-05 → "Complete"
- MEM-08 → "Complete"

**DO NOT CHANGE:**
- MEM-01..04, MEM-06..07 (already [x] and already "Complete" — do not touch)
- SEC-01..03 (already [x] and already "Complete" — do not touch)
- SEC-04 (remains [ ] and "Pending" — pen test baseline report not yet produced)
- All PF2E, MUSIC, CODER, FIN, TRADE, COMM requirements (future phases — untouched)
- v2 requirements section (untouched)
- Out of Scope section (untouched)
- Coverage summary line at bottom (untouched — count is still correct at 62)

After edits, verify: grep for `[ ] **CORE` should return 0 matches; grep for `[ ] **IFACE` should return 0 matches; grep for `[ ] **PROV` should return 0 matches.
  </action>
  <verify>
    <automated>grep -c '\[x\] \*\*CORE' /Users/trekkie/projects/sentinel-of-mnemosyne/.planning/REQUIREMENTS.md && grep -c '\[x\] \*\*IFACE' /Users/trekkie/projects/sentinel-of-mnemosyne/.planning/REQUIREMENTS.md && grep -c '\[x\] \*\*PROV' /Users/trekkie/projects/sentinel-of-mnemosyne/.planning/REQUIREMENTS.md</automated>
  </verify>
  <done>
All 7 CORE, 6 IFACE, and 5 PROV checkboxes show [x]. MEM-05 and MEM-08 show [x]. Traceability table shows "Complete" for all those groups. SEC-04 and future-phase requirements unchanged.
  </done>
</task>

<task type="auto">
  <name>Task 2: Update PROJECT.md — checkboxes for delivered items (D-02)</name>
  <files>.planning/PROJECT.md</files>
  <action>
Read PROJECT.md in full. The "Active" section has informal checklist items grouped by subsystem. Flip `[ ]` to `[x]` for all items that were delivered through Phase 7. Use the REQUIREMENTS.md scope as the guide — same delivered set.

**Core Infrastructure group — flip all 5 items:**
- `[ ] Pi harness runs in Docker, accepts prompts via RPC (stdin/stdout JSONL), returns structured responses`
- `[ ] Sentinel Core container (FastAPI/Python) receives message envelopes, routes to Pi, returns responses`
- `[ ] LM Studio on Mac Mini confirmed as AI backend via OpenAI-compatible API`
- `[ ] Docker Compose base structure established with override file pattern`
- `[ ] Sentinel can receive a message and return an AI response end-to-end (v0.1)`

**Memory Layer group — flip all 4 items:**
- `[ ] Obsidian Local REST API plugin installed and accessible from Core container`
- `[ ] Core retrieves relevant user context from vault before building Pi prompt`
- `[ ] Core writes session summaries to vault after each interaction`
- `[ ] System demonstrates cross-session memory (references a prior conversation) (v0.2)`

**Interfaces group — flip all 4 items:**
- `[ ] Standard Message Envelope format defined and stable`
- `[ ] Discord bot interface container operational — sends envelopes, posts responses`
- `[ ] Apple Messages bridge (Mac-side component + HTTP bridge to Core)`
- `[ ] Docker Compose override pattern validated with first real interface (v0.3)`

**AI Layer Polish group — flip all 4 items (Phase 4 delivered PROV-01..05):**
- `[ ] Provider configuration via environment variables (no hardcoding)`
- `[ ] At least two providers testable (LM Studio + one other)`
- `[ ] Error handling, retry logic, and timeout management in Pi client`
- `[ ] Pi harness wrapper API finalized — clean contract rest of system depends on (v0.4)`

**DO NOT CHANGE:** Pathfinder 2e, Music, Coder, Finance, Trading, Live Trading, Polish & Community groups — all remain `[ ]`.

Also update the Key Decisions table: change all "— Pending" outcome cells to "— Implemented" for the decisions that cover the completed phases (Pi harness, Obsidian Local REST API, LM Studio, FastAPI, Docker Compose include, Pi HTTP bridge). Leave Alpaca and ofxtools as "— Pending" (trading module not yet built).

Update the last line: change `*Last updated: 2026-04-10 after initialization*` to `*Last updated: 2026-04-11 — Phase 7 complete; checkboxes updated*`.
  </action>
  <verify>
    <automated>grep -c '\[x\]' /Users/trekkie/projects/sentinel-of-mnemosyne/.planning/PROJECT.md</automated>
  </verify>
  <done>
All 17 items in Core Infrastructure, Memory Layer, Interfaces, and AI Layer Polish groups are [x]. Future-phase groups remain [ ]. Key Decisions updated where applicable. At least 17 [x] items present.
  </done>
</task>

<task type="auto">
  <name>Task 3: Update STATE.md — completed_phases count and position fields (D-04)</name>
  <files>.planning/STATE.md</files>
  <action>
Read STATE.md in full. Make these targeted changes to the frontmatter:

1. Change `completed_phases: 4` to `completed_phases: 7`
2. Change `stopped_at: Completed 02-memory-layer 02-02-PLAN.md — UAT passed, Phase 2 complete` to `stopped_at: Completed 07-phase-2-verification-mem-08 07-02-PLAN.md — MEM-08 warm tier wired, Phase 7 complete`
3. Change `last_activity: 2026-04-11 -- Phase 07 execution started` to `last_activity: 2026-04-11 -- Phase 07 complete; Phase 08 documentation repair starting`
4. In the "Current Position" prose section, update:
   - `Phase: 07 (phase-2-verification-mem-08) — EXECUTING` to `Phase: 08 (requirements-traceability-repair) — EXECUTING`
   - `Plan: 1 of 2` to `Plan: 1 of 1`
   - `Status: Executing Phase 07` to `Status: Executing Phase 08`
   - `Last activity: 2026-04-11 -- Phase 07 execution started` to `Last activity: 2026-04-11 -- Phase 08 documentation repair`

Do not change any other content — velocity metrics, decisions, blockers, quick tasks, or session continuity are untouched.
  </action>
  <verify>
    <automated>grep 'completed_phases' /Users/trekkie/projects/sentinel-of-mnemosyne/.planning/STATE.md</automated>
  </verify>
  <done>
STATE.md frontmatter shows `completed_phases: 7`. stopped_at and last_activity reflect Phase 7 completion. Current Position section shows Phase 08.
  </done>
</task>

<task type="auto">
  <name>Task 4: Add Nyquist Test Matrix to Phase 1 VALIDATION.md (D-03)</name>
  <files>.planning/phases/01-core-loop/01-VALIDATION.md</files>
  <action>
Read 01-VALIDATION.md in full. Read 01-VERIFICATION.md to confirm which tests exist. The goal is to add a Nyquist Test Matrix section and flip the frontmatter flag.

**Step 1 — Update frontmatter:**
Change `nyquist_compliant: false` to `nyquist_compliant: true`.

**Step 2 — Add section after the Per-Task Verification Map table (before "## Wave 0 Requirements"):**

Insert the following new section:

```markdown
## Nyquist Test Matrix

> Added retroactively (Phase 08 docs repair). All tests confirmed present in codebase as of 2026-04-11.
> Manual verifications reference evidence from 01-VERIFICATION.md (verified 2026-04-10).

| Requirement | Description | Test Type | Test File / Command | Status |
|-------------|-------------|-----------|---------------------|--------|
| CORE-01 | Pi harness accepts HTTP POST /prompt via Fastify bridge | manual | `curl -X POST http://localhost:3000/prompt` — see 01-VERIFICATION.md §Human Verification #2 | ✅ manual-verified |
| CORE-02 | Adapter pattern established, exact pin @0.66.1 | file assert | `grep '"@mariozechner/pi-coding-agent": "0.66.1"' pi-harness/package.json` | ✅ automated |
| CORE-03 | POST /message returns ResponseEnvelope | unit | `sentinel-core/tests/test_message.py::test_post_message_returns_response_envelope` | ✅ automated |
| CORE-04 | LM Studio async client, context window fetch, 4096 fallback | unit | `sentinel-core/tests/test_message.py` (mock_ai_provider fixture path) | ✅ automated |
| CORE-05 | Token guard rejects oversized messages (422) | unit | `sentinel-core/tests/test_token_guard.py::test_rejects_oversized`, `::test_check_token_limit_raises_on_exceeded` | ✅ automated |
| CORE-06 | `docker compose up` starts both services | manual | `docker compose up -d && docker compose ps` — see 01-VERIFICATION.md §Human Verification #2 | ✅ manual-verified |
| CORE-07 | Docker Compose `include` directive, no `-f` stacking | file assert | `grep -q "^include:" docker-compose.yml` | ✅ automated |

**Test count:** 7 requirements → 5 automated (unit + file assert) + 2 manual-verified
**Suite command:** `pytest sentinel-core/tests/test_message.py sentinel-core/tests/test_token_guard.py -x -q`
```

**Step 3 — Update Validation Sign-Off checklist:**
Change all `- [ ]` items in the "## Validation Sign-Off" section to `- [x]`, including the final `nyquist_compliant: true` item. Change `**Approval:** pending` to `**Approval:** retroactive — 2026-04-11 (Phase 08 docs repair)`.
  </action>
  <verify>
    <automated>grep 'nyquist_compliant' /Users/trekkie/projects/sentinel-of-mnemosyne/.planning/phases/01-core-loop/01-VALIDATION.md</automated>
  </verify>
  <done>
01-VALIDATION.md has `nyquist_compliant: true` in frontmatter, a "## Nyquist Test Matrix" section mapping all 7 CORE requirements to tests or manual verification evidence, and a completed Validation Sign-Off checklist.
  </done>
</task>

<task type="auto">
  <name>Task 5: Add Nyquist Test Matrix to Phase 3 VALIDATION.md (D-03)</name>
  <files>.planning/phases/03-interfaces/03-VALIDATION.md</files>
  <action>
Read 03-VALIDATION.md in full. Read 03-VERIFICATION.md to confirm which tests exist. The Per-Task Verification Map in the existing VALIDATION.md has a subtle error: task 03-01-01/02 maps to "IFACE-04" but those tasks actually implement IFACE-06 (auth middleware). The VERIFICATION.md correctly maps IFACE-06 to auth. Add the Nyquist matrix using the VERIFICATION.md as ground truth — do not propagate the mapping error.

**Step 1 — Update frontmatter:**
Change `nyquist_compliant: false` to `nyquist_compliant: true`.

**Step 2 — Add section after the Per-Task Verification Map table (before "## Wave 0 Requirements"):**

Insert the following new section:

```markdown
## Nyquist Test Matrix

> Added retroactively (Phase 08 docs repair). All tests confirmed present in codebase as of 2026-04-11.
> Manual verifications reference evidence from 03-VERIFICATION.md (verified 2026-04-10).
> Note: Per-Task Verification Map above has a mapping error (03-01-01/02 labels say IFACE-04 but
> implement IFACE-06 auth). This matrix uses 03-VERIFICATION.md as ground truth.

| Requirement | Description | Test Type | Test File / Command | Status |
|-------------|-------------|-----------|---------------------|--------|
| IFACE-01 | Standard Message Envelope defined as Pydantic v2 model | unit | `sentinel-core/tests/test_message.py` (envelope shape asserted in `test_post_message_returns_response_envelope`) | ✅ automated |
| IFACE-02 | Discord bot container operational, discord.py v2.7.x | manual | `docker compose up discord && /sentask hello` — see 03-VERIFICATION.md §Human Verification #1 | ✅ manual-verified |
| IFACE-03 | Discord slash commands use deferred responses (3s SLA) | manual | `interaction.response.defer(thinking=True)` confirmed in bot.py line 77; timing SLA requires live Discord — see 03-VERIFICATION.md §Human Verification #1 | ✅ manual-verified |
| IFACE-04 | Discord multi-turn conversations use threads | manual | `channel.create_thread()` confirmed in bot.py line 84; requires live Discord — see 03-VERIFICATION.md §Human Verification #1 | ✅ manual-verified |
| IFACE-05 | Apple Messages bridge operational as feature-flagged tier-2 | manual | IMESSAGE_ENABLED=false exit confirmed by live execution; full path requires macOS — see 03-VERIFICATION.md §Human Verification #2 | ✅ manual-verified |
| IFACE-06 | All non-health Core endpoints require X-Sentinel-Key | unit | `sentinel-core/tests/test_auth.py::test_auth_rejects_missing_key`, `::test_auth_rejects_wrong_key`, `::test_health_bypasses_auth`, `::test_auth_accepts_valid_key` | ✅ automated |

**Test count:** 6 requirements → 2 automated (unit) + 4 manual-verified (live hardware required)
**Suite command:** `pytest sentinel-core/tests/test_auth.py -x -q`
```

**Step 3 — Update Validation Sign-Off checklist:**
Change all `- [ ]` items in the "## Validation Sign-Off" section to `- [x]`, including the final `nyquist_compliant: true` item. Change `**Approval:** pending` to `**Approval:** retroactive — 2026-04-11 (Phase 08 docs repair)`.
  </action>
  <verify>
    <automated>grep 'nyquist_compliant' /Users/trekkie/projects/sentinel-of-mnemosyne/.planning/phases/03-interfaces/03-VALIDATION.md</automated>
  </verify>
  <done>
03-VALIDATION.md has `nyquist_compliant: true` in frontmatter, a "## Nyquist Test Matrix" section mapping all 6 IFACE requirements to tests or manual verification evidence (with the mapping error noted), and a completed Validation Sign-Off checklist.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| planner → docs | Executor edits markdown files in the repo — no external services, no user input, no data crossing a trust boundary |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-08-01 | Tampering | .planning/REQUIREMENTS.md | accept | Documentation-only edit; git history provides full audit trail; no secrets or executable code in scope |
| T-08-02 | Tampering | .planning/STATE.md | accept | State file is planning metadata, not auth or config; no security-sensitive fields in scope |
| T-08-03 | Information Disclosure | 01-VALIDATION.md / 03-VALIDATION.md | accept | Nyquist matrices document test file paths and commands — all already visible in the repo; no new disclosure surface |
| T-08-04 | Repudiation | All five files | accept | All changes committed to git with attribution; no repudiation risk beyond normal commit history |
</threat_model>

<verification>
After all five tasks complete, verify the overall repair is self-consistent:

1. REQUIREMENTS.md checkbox count: `grep -c '\[x\]' .planning/REQUIREMENTS.md` — expect 21+ (7 CORE + 6 IFACE + 5 PROV + 3 SEC already done + MEM-01..07 already done + MEM-08 newly flipped)
2. No CORE/IFACE/PROV/MEM-05/MEM-08 lines remain as `[ ]`: `grep '^\- \[ \] \*\*\(CORE\|IFACE\|PROV\|MEM-05\|MEM-08\)' .planning/REQUIREMENTS.md` — expect 0 matches
3. STATE.md completed_phases: `grep 'completed_phases' .planning/STATE.md` — expect `completed_phases: 7`
4. Both VALIDATION.md files: `grep 'nyquist_compliant' .planning/phases/01-core-loop/01-VALIDATION.md .planning/phases/03-interfaces/03-VALIDATION.md` — expect `true` in both
5. PROJECT.md has Core Infrastructure items checked: `grep '\[x\] Pi harness' .planning/PROJECT.md` — expect 1 match
</verification>

<success_criteria>
- REQUIREMENTS.md: 21 checkboxes show [x] for requirements delivered through Phase 7 (7 CORE + 6 IFACE + 5 PROV + MEM-01..07 already done + MEM-08). SEC-04 and all future-phase requirements remain [ ].
- REQUIREMENTS.md traceability table: CORE-01..07, IFACE-01..06, PROV-01..05, MEM-05, MEM-08 all show "Complete".
- PROJECT.md: All items in Core Infrastructure, Memory Layer, Interfaces, and AI Layer Polish groups are [x]. Future-phase groups remain [ ].
- STATE.md: `completed_phases: 7`. stopped_at and last_activity reflect Phase 7 completion.
- 01-VALIDATION.md: `nyquist_compliant: true` in frontmatter. Nyquist Test Matrix section present with all 7 CORE requirements mapped.
- 03-VALIDATION.md: `nyquist_compliant: true` in frontmatter. Nyquist Test Matrix section present with all 6 IFACE requirements mapped.
- No new code, no new tests, no new files created.
</success_criteria>

<output>
After completion, create `.planning/phases/08-requirements-traceability-repair/08-01-SUMMARY.md` using the standard summary template.
</output>
