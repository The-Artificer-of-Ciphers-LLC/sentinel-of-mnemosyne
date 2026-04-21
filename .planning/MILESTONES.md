# Milestones: Sentinel of Mnemosyne

## v0.40 — Pre-Beta Refactoring

**Shipped:** 2026-04-21
**Phases:** 21–27 (7 phases, 24 plans)
**Requirements:** 35/35 v0.40 requirements complete
**LOC:** ~109K (Python + TypeScript)
**Timeline:** 2026-04-10 → 2026-04-21 (11 days)

### Delivered

1. Restored security pipeline (InjectionFilter + OutputScanner + Discord) after production regression wipe (`6cfb0d3`)
2. Full requirements traceability repair — all 35 requirements cross-referenced and verified across three artifact sources
3. Pi /reset route added — prevents LM Studio context overflow after repeated sessions; configurable `PI_TIMEOUT_S`
4. Pentest agent (SEC-04) wired into compose; missing VERIFICATION.md generated for Phases 02, 05, 07
5. Full pre-beta refactor: DUP-01–05 eliminated, STUB-01–08 completed, CONTRA-01–04 resolved, all 20 acceptance criteria passed
6. Nyquist VALIDATION.md created/repaired for all 4 noncompliant phases (04, 06, 07, 10); 12 Discord tests added
7. **Architecture pivot to Path B**: Pi removed from base stack, LiteLLM-direct AI calls, module API gateway, `/sentask`→`/sen`

### Archive

- [v0.40-ROADMAP.md](milestones/v0.40-ROADMAP.md) — Phase details and decisions
- [v0.40-REQUIREMENTS.md](milestones/v0.40-REQUIREMENTS.md) — Requirements with outcomes

Known deferred items at close: 3 phases with `human_needed` verifications (runtime checks, not code deficiencies).

---

*Prior milestones v0.1–v0.4 were completed before this tracking file existed. See ROADMAP.md for phase history.*
