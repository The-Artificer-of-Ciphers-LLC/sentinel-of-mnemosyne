---
phase: 43
slug: embeddings-through-sentinel
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-05
---

# Phase 43 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Synced from `43-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio (`asyncio_mode = "auto"`) |
| **Config file** | `sentinel-core/pyproject.toml` (`[tool.pytest.ini_options]`) + `modules/pathfinder/pyproject.toml` |
| **Quick run command** | `cd sentinel-core && pytest tests/test_embeddings.py tests/test_embedding_sidecar_index.py tests/test_vault_sweeper.py -x` · `cd modules/pathfinder && pytest tests/test_rule_query.py tests/test_rules_integration.py -x` |
| **Full suite command** | `cd sentinel-core && pytest` · `cd modules/pathfinder && pytest` |
| **Estimated runtime** | ~30–60 s per container (full suite) |

---

## Sampling Rate

- **After every task commit:** Run the relevant quick-run subset (embeddings/sidecar-index/vault-sweeper for core changes; rule_query/rules_integration for pf2e changes)
- **After every plan wave:** Run the full suite in both `sentinel-core` and `modules/pathfinder`
- **Before `/gsd-verify-work`:** Full suite green in both containers **plus** live confirmation of EMB-03 / EMB-04 (LM Studio reachable, `:pf rule` returns rules, `/health` `embedding_model_loaded: true`)
- **Max feedback latency:** ~60 seconds (unit subset)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 43-01-01 | 01 | 1 | EMB-02 | — | `embedding_base_url` defaults to LM Studio :1234, independent of `lmstudio_base_url`/`exo_base_url` | unit | `cd sentinel-core && pytest tests/test_embeddings.py -x` | ✅ extend | ⬜ pending |
| 43-01-02 | 01 | 1 | EMB-02, EMB-04 | — | `composition.py` wires `Embeddings(...)` **and** `probe_embedding_model_loaded(...)` off `embedding_base_url` (two-site fix) | unit | `cd sentinel-core && pytest tests/ -k composition -x` | ❌ W0 (verify/extend) | ⬜ pending |
| 43-01-03 | 01 | 1 | EMB-02 | — | Two exo-port-asserting tests corrected (no-defer) | unit | `cd sentinel-core && pytest tests/test_embeddings.py -x` | ✅ replace 2 | ⬜ pending |
| 43-02-01 | 02 | 1 | EMB-01 | T-43-02 ID/DoS | `POST /embeddings` texts-only schema, `_MAX_TEXTS` cap, typed error→503 non-leak | unit | `cd sentinel-core && pytest tests/ -k embeddings_route -x` | ❌ W0 (new) | ⬜ pending |
| 43-02-02 | 02 | 1 | EMB-01 | T-43-02 | `APIKeyMiddleware` covers new route; guardrail test passes with new `routes/embeddings.py` | unit | `cd sentinel-core && pytest tests/test_ai_agnostic_guardrail.py -x` | ✅ verify | ⬜ pending |
| 43-03-01 | 03 | 2 | EMB-01 | — | `SentinelCoreClient.embed()` exists; `embed_texts()` internals call it (signature preserved) | unit | `cd modules/pathfinder && pytest tests/test_rule_query.py -x` | ✅ extend | ⬜ pending |
| 43-03-02 | 03 | 2 | EMB-01, EMB-03 | — | `modules/pathfinder/app/llm.py` no longer references `litellm.aembedding` | unit | new guardrail-style test (mirror core `test_ai_agnostic_guardrail`) | ❌ W0 (new) | ⬜ pending |
| 43-04-01 | 04 | 2 | EMB-04 | — | Dimension-mismatch entries skipped, not errored (existing guard) | unit | `cd sentinel-core && pytest tests/test_embedding_sidecar_index.py::test_eligible_entries_skips_stale_model_and_dimension_mismatch -x` | ✅ exists | ⬜ pending |
| 43-04-02 | 04 | 2 | EMB-04 | — | Sweeper persists `embedding_dim` (backward-compatible) | unit | `cd sentinel-core && pytest tests/test_vault_sweeper.py -x` | ✅ extend | ⬜ pending |
| 43-05-01 | 05 | 3 | EMB-03, EMB-04 | — | Phase regression suites green in both containers | suite | full suite (both containers) | ✅ | ⬜ pending |
| 43-05-02 | 05 | 3 | EMB-03 | — | `:pf rule` returns non-empty ranked rules, no 503 (live) | manual | `LIVE_TEST=1 python scripts/uat_rules.py` | ✅ existing UAT | ⬜ pending |
| 43-05-03 | 05 | 3 | EMB-04 | — | Post-restart `/health` `embedding_model_loaded: true` + `/message` recall returns warm-tier hits (live) | manual | manual live check (see below) | ❌ live-only | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `sentinel-core/tests/test_embeddings.py` — replace `test_default_lmstudio_base_url_is_docker_reachable` and `test_embeddings_falls_back_to_default_base_url_when_falsy` (they currently assert the exo-port bug as correct)
- [ ] `sentinel-core/tests/` — new/extended composition-wiring test asserting `Embeddings(...)` and `probe_embedding_model_loaded(...)` read `embedding_base_url`, not `lmstudio_base_url` (check for an existing `test_composition.py` to extend first)
- [ ] `sentinel-core/tests/` — route test for the new `POST /embeddings` (texts cap, typed-error→503 non-leak)
- [ ] `modules/pathfinder/tests/` — new test asserting `embed_texts()` calls `_core_client.embed()` (mirror the Phase-42 pattern used to test `complete()` call sites) + a guardrail assertion that `llm.py` no longer references `litellm.aembedding`
- [ ] `scripts/uat_rules.py` — confirm `test_lm_studio_embeddings_reachable`'s probe path still matches post-cutover (targets LM Studio directly; expected no change, confirm no regression)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `:pf rule <query>` returns relevant ranked rules, no 503 | EMB-03 | Requires a live LM Studio serving nomic on :1234 + live sentinel-core + live pf2e | Operator loads `text-embedding-nomic-embed-text-v1.5` in LM Studio (:1234); restart the stack; run `LIVE_TEST=1 python scripts/uat_rules.py`; issue a `:pf rule` query and confirm non-empty ranked results |
| Core semantic recall returns hits post-cutover | EMB-04 | Sidecar index is rebuilt live against the new backend; inherently live-backend | Restart the sentinel-core container; confirm `/health` reports `embedding_model_loaded: true`; issue a `/message` whose answer depends on a vault note and confirm non-empty warm-tier recall |

*These two success criteria are inherently unautomatable without a live LM Studio instance — matching the operator-action-gated verification pattern documented in `.planning/debug/exo-model-notfound-502.md`.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (EMB-03/EMB-04 live checks are documented manual-only)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-05
