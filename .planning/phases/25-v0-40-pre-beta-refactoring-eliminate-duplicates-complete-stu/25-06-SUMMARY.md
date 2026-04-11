---
phase: 25-v0-40-pre-beta-refactoring-eliminate-duplicates-complete-stu
plan: "06"
subsystem: security
tags: [security, pentest, injection-filter, tdd, sec-04]
dependency_graph:
  requires:
    - 25-04-PLAN.md (InjectionFilter service exists in sentinel-core)
  provides:
    - security/pentest/jailbreak_baseline.py (41-prompt parametrized baseline)
    - security/JAILBREAK-BASELINE.md (baseline results documentation)
    - SEC-04 checked in REQUIREMENTS.md
  affects:
    - sentinel-core/app/services/injection_filter.py (expanded to 27 patterns + normalization)
tech_stack:
  added: []
  patterns:
    - Parametrized pytest baseline as security evidence
    - Three-layer Unicode normalization pre-pass (NFKC + Cyrillic confusables + zero-width strip)
    - sys.path manipulation for cross-package test imports
key_files:
  created:
    - security/__init__.py
    - security/pentest/__init__.py
    - security/pentest/jailbreak_baseline.py
    - security/JAILBREAK-BASELINE.md
  modified:
    - sentinel-core/app/services/injection_filter.py
    - .planning/REQUIREMENTS.md
decisions:
  - "Cyrillic confusable map (22 entries) over Unicode confusables database — avoids external dependency, covers the high-risk visual lookalikes used in real attacks"
  - "Zero-width char stripping via regex pre-pass (16 codepoints) before pattern matching — simpler and more explicit than NFKC which doesn't strip them"
  - "Multi-language patterns (ES/FR/DE) added directly to _INJECTION_PATTERNS — consistent with existing corpus, no separate multilingual layer needed at this scale"
metrics:
  duration: "~12 min"
  completed_date: "2026-04-11"
  tasks_completed: 2
  files_changed: 6
---

# Phase 25 Plan 06: Jailbreak Resistance Baseline (SEC-04) Summary

**One-liner:** 41-prompt adversarial parametrized pytest baseline against real InjectionFilter, expanded from 19 to 27 patterns with Cyrillic confusable + zero-width normalization pre-pass — all GREEN, SEC-04 checked.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 25-06-01 | Write 30+ jailbreak prompts as pytest parametrize cases (RED → GREEN) | e156d7b | security/__init__.py, security/pentest/__init__.py, security/pentest/jailbreak_baseline.py, sentinel-core/app/services/injection_filter.py |
| 25-06-02 | Write JAILBREAK-BASELINE.md and check SEC-04 in REQUIREMENTS.md | d510d9d | security/JAILBREAK-BASELINE.md, .planning/REQUIREMENTS.md |

## Decisions Made

1. **Cyrillic confusable map (22 entries) rather than a Unicode confusables database** — The `confusables` PyPI package would add a dependency; a hand-curated 22-entry map covers the specific attack surface (visual ASCII lookalikes). Kept in-module as `_CYRILLIC_CONFUSABLES`.

2. **Zero-width char stripping via regex (16 codepoints) rather than NFKC** — NFKC does not remove zero-width spaces (U+200B) or soft hyphens (U+00AD); they are not compatibility equivalents in Unicode. Explicit regex strip is the correct approach.

3. **Multi-language patterns added to `_INJECTION_PATTERNS` directly** — No separate multilingual layer. The existing pattern list is the single source of truth; Spanish/French/German patterns are added there.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] InjectionFilter missing 10 patterns required by the baseline**
- **Found during:** Task 1 (RED phase — 27 of 41 tests failed)
- **Issue:** Filter had 19 patterns but was missing: `ignore all instructions` (no qualifier), `disregard all instructions`, `forget all instructions`, `override previous instructions`, `pretend you have no restrictions`, `bypass your safety guidelines`, `dan mode`, `system prompt:`, `your real instructions are`, `your true instructions are`, plus OWASP multi-language variants
- **Fix:** Expanded `_INJECTION_PATTERNS` from 19 to 27 patterns; added `_normalize_text()` pre-pass function with three normalization steps
- **Files modified:** `sentinel-core/app/services/injection_filter.py`
- **Commit:** e156d7b

**2. [Rule 2 - Missing Critical Functionality] Cyrillic homoglyph and zero-width bypass not handled**
- **Found during:** Task 1 (RED phase — all 4 homoglyph tests and 3 of 4 unicode tests failed)
- **Issue:** NFKC normalization does not normalize Cyrillic confusables to ASCII, and does not strip zero-width spaces/soft hyphens — both are known bypass techniques
- **Fix:** Added `_CYRILLIC_CONFUSABLES` translation table (22 Cyrillic visual lookalikes → ASCII) and `_ZERO_WIDTH_CHARS_PATTERN` (16 invisible codepoints) applied in `_normalize_text()` before pattern matching
- **Files modified:** `sentinel-core/app/services/injection_filter.py`
- **Commit:** e156d7b

## TDD Gate Compliance

- RED gate: Tests written first, 27 of 41 failed before InjectionFilter expansion (confirmed)
- GREEN gate: InjectionFilter expanded, all 41 tests pass (commit e156d7b)

## Known Stubs

None — all tests use the real InjectionFilter; no mock or stub implementations present.

## Threat Flags

None — no new network endpoints, auth paths, or file access patterns introduced. The `security/` package is test-only and does not run in production.

## Self-Check: PASSED

- `security/__init__.py` — FOUND
- `security/pentest/__init__.py` — FOUND
- `security/pentest/jailbreak_baseline.py` — FOUND (41 parametrized test cases, 5 test functions)
- `security/JAILBREAK-BASELINE.md` — FOUND (41/41 caught, 0 passed through)
- `sentinel-core/app/services/injection_filter.py` — FOUND (27 patterns, `_normalize_text()` pre-pass)
- `.planning/REQUIREMENTS.md` SEC-04 checkbox — `[x]` CONFIRMED
- Commit e156d7b — FOUND (feat(25-06): jailbreak resistance baseline)
- Commit d510d9d — FOUND (feat(25-06): JAILBREAK-BASELINE.md and SEC-04)
- 16 existing sentinel-core injection_filter tests — ALL PASS (no regressions)
