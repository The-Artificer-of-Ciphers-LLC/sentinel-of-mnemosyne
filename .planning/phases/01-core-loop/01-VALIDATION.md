---
phase: 01-core-loop
nyquist_compliant: true
wave_0_complete: true
status: verified
verified: 2026-04-10T00:00:00Z
nyquist_written: 2026-04-11T00:00:00Z
note: "Nyquist matrix written retroactively by Phase 22. Documentation-only."
---

# Phase 01: Core Loop — Validation

## Nyquist Test Matrix

| Requirement | Description | Test File | Test Function(s) | Automated? | Evidence |
|-------------|-------------|-----------|-----------------|------------|----------|
| CORE-01 | Pi harness accepts HTTP POST /prompt via Fastify bridge | test_pi_adapter.py | test_send_messages_success | Yes | PiAdapterClient POSTs to /prompt; 200 response asserted |
| CORE-02 | Adapter pattern isolates pi-mono; exact pin @0.66.1 | test_pi_adapter.py | test_send_messages_success | Partial | Adapter isolation tested; pin verified by code review (package.json exact 0.66.1, no caret) |
| CORE-03 | POST /message returns ResponseEnvelope (content, model) | test_message.py | test_post_message_returns_response_envelope, test_post_message_503_when_pi_and_ai_provider_unavailable | Yes | ResponseEnvelope shape asserted; 200 and 503 paths covered |
| CORE-04 | LM Studio async client fetches context window; falls back to 4096 | test_message.py | test_post_message_returns_response_envelope | Partial | Context window used in test; fallback to 4096 verified by code review |
| CORE-05 | Token guard rejects messages exceeding context window (HTTP 422) | test_token_guard.py | test_rejects_oversized, test_permits_normal, test_token_count_includes_message_overhead, test_check_token_limit_raises_on_exceeded, test_check_token_limit_passes_for_normal, test_multi_message_token_guard | Yes | 6 automated tests; test_post_message_422_when_message_too_long adds integration coverage |
| CORE-06 | Python project with FastAPI + pydantic-settings; startup fails fast on missing SENTINEL_API_KEY | (none) | (none) | Manual | docker-compose.yml include directive verified by code review; startup failure on missing SENTINEL_API_KEY verified per 01-VERIFICATION.md human_verification item 4 |
| CORE-07 | Docker Compose include directive pattern (never -f flag stacking) | (none) | (none) | Manual | docker-compose.yml uses include: only; -f prohibited by inline comment; verified per 01-VERIFICATION.md Key Link rows 5-6 |

## Nyquist Compliance Decision

All 7 CORE requirements are covered:

- **CORE-01, CORE-03, CORE-05** are fully automated: direct unit and integration tests exist in `test_pi_adapter.py`, `test_message.py`, and `test_token_guard.py` respectively. CORE-05 has 6 dedicated unit tests plus one integration test.
- **CORE-02, CORE-04** are partially automated: the adapter isolation contract (CORE-02) is exercised in `test_send_messages_success`, and the context window path (CORE-04) is exercised via `test_post_message_returns_response_envelope`. The pin verification and fallback behavior are additionally confirmed by code review of `package.json` and `lmstudio.py`.
- **CORE-06, CORE-07** are manual only: these are infrastructure-level constraints (pydantic-settings startup validation, Docker Compose structure) that cannot be verified without a live container environment. Evidence is documented in `01-VERIFICATION.md` human_verification items 1 and 4, and Key Link rows 5-6.

**nyquist_compliant: true** — all requirements have documented test coverage or manual verification evidence.

## Task Verification Summary

| Plan | Name | Status | Reference |
|------|------|--------|-----------|
| 01-01 | Core Scaffolding | VERIFIED | 01-VERIFICATION.md |
| 01-02 | Pi Harness Integration | VERIFIED | 01-VERIFICATION.md |
| 01-03 | Sentinel Core Message Loop | VERIFIED | 01-VERIFICATION.md |

Full verification detail, observable truths (7/7), required artifacts (15/15), key links (6/6), and behavioral spot-checks are documented in `.planning/phases/01-core-loop/01-VERIFICATION.md`.
