---
phase: 04
slug: ai-provider-multi-provider-support-retry-logic-fallback
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-10
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Reconstructed 2026-04-21 from 04-VERIFICATION.md and 04-01 through 04-04 SUMMARY.md artifacts.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio |
| **Config file** | `sentinel-core/pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `cd sentinel-core && python3 -m pytest tests/test_litellm_provider.py tests/test_model_registry.py tests/test_provider_router.py -x -q` |
| **Full suite command** | `cd sentinel-core && python3 -m pytest -v` |
| **Estimated runtime** | ~30 seconds (62 tests) |

---

## Sampling Rate

- **After every task commit:** Run quick run command
- **After every plan wave:** Run `cd sentinel-core && python3 -m pytest -v`
- **Before `/gsd-verify-work`:** Full suite must be green (62/62)
- **Max feedback latency:** ~30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | PROV-01 | — | N/A | smoke | `cd sentinel-core && python3 -m pytest -v --co -q \| grep -c test` — verify test suite loads without import errors | ✅ | ✅ green |
| 04-01-02 | 01 | 1 | PROV-04 | — | N/A | manual | Read `sentinel-core/models-seed.json` — verify 5 model entries with context_window fields present | ✅ | ✅ green |
| 04-02-01 | 02 | 2 | PROV-02 | — | N/A | unit | `cd sentinel-core && python3 -m pytest tests/test_litellm_provider.py -v` | ✅ | ✅ green |
| 04-02-02 | 02 | 2 | PROV-03 | — | N/A | unit | `cd sentinel-core && python3 -m pytest tests/test_litellm_provider.py -v -k "retry"` | ✅ | ✅ green |
| 04-03-01 | 03 | 3 | PROV-04 | — | N/A | unit | `cd sentinel-core && python3 -m pytest tests/test_model_registry.py -v` | ✅ | ✅ green |
| 04-03-02 | 03 | 3 | PROV-05 | — | N/A | unit | `cd sentinel-core && python3 -m pytest tests/test_provider_router.py -v` | ✅ | ✅ green |
| 04-04-01 | 04 | 4 | PROV-01-05 | — | N/A | integration | `cd sentinel-core && python3 -m pytest -v` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `sentinel-core/tests/test_litellm_provider.py` — 9 TDD tests written in RED phase before LiteLLMProvider implementation (Plan 02)
- [x] `sentinel-core/tests/test_model_registry.py` — 5 TDD tests written in RED phase before ModelRegistry implementation (Plan 03)
- [x] `sentinel-core/tests/test_provider_router.py` — 7 TDD tests written in RED phase before ProviderRouter implementation (Plan 03)

*All Wave 0 test stubs were created before implementation. Phase 04 shipped with 62/62 tests green.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Switch from LM Studio to Claude API by changing only env vars | PROV-01, PROV-02 | Requires live LM Studio and Anthropic API key | Set `AI_PROVIDER=claude`, `ANTHROPIC_API_KEY=<key>`, `CLAUDE_MODEL=<model>` in `.env`. Start sentinel-core. Send a message. Verify response comes from Claude (check logs for LiteLLM routing). |
| Fallback triggers when LM Studio is unreachable | PROV-05 | Requires live provider fault injection | Stop LM Studio, set `AI_FALLBACK_PROVIDER=claude`. Send a message. Verify ProviderRouter catches ConnectError and routes to Claude fallback. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (TDD RED phase before each implementation plan)
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** complete — Phase 04 shipped 2026-04-10, re-verified 2026-04-10 after PROV-03 gap closed by quick task 260410-p7o. Final score: 4/4 truths, 62/62 tests green.
