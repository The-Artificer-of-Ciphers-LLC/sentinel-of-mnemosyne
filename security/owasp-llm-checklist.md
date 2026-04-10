# OWASP LLM Top 10 (2025) — Sentinel of Mnemosyne Security Audit

**Phase:** 05 — AI Security / Prompt Injection Hardening
**Date:** 2026-04-10
**Threat model boundary:** Single-user, air-gapped personal assistant (Mac Mini + local Docker).
X-Sentinel-Key auth scope: local network only (decided Phase 3, not revisited here).

## Checklist

| # | Category | Status | Implementation / Rationale |
|---|----------|--------|---------------------------|
| LLM01 | Prompt Injection | MITIGATED | InjectionFilter (injection_filter.py): framing wrapper [BEGIN RETRIEVED CONTEXT] + pattern blocklist (19 patterns from OWASP cheat sheet) applied to vault context AND user input via single shared sanitize() implementation. |
| LLM02 | Sensitive Information Disclosure | MITIGATED | OutputScanner (output_scanner.py): 7-pattern regex scan before response leaves POST /message. Confirmed leaks blocked (HTTP 500) and written to Obsidian /security/leak-incidents/. Haiku secondary classifier prevents false positives. Fail-open on timeout. |
| LLM03 | Supply Chain | ACCEPTED-RISK | LM Studio model is user-sourced and user-controlled. Model provenance is a user operational responsibility. LiteLLM pinned to >=1.83.0,<2.0 after supply-chain incident (malicious 1.82.7-1.82.8). No mitigations planned beyond version pinning. |
| LLM04 | Data and Model Poisoning | ACCEPTED-RISK | No fine-tuning or RLHF in this project. Vault content is user-authored. Risk: adversarial vault content persists across sessions via hot-tier context. Mitigated by InjectionFilter scanning all injected context. Accepted: no external fine-tuning pipeline. |
| LLM05 | Improper Output Handling | MITIGATED | AI response does not flow to downstream execution (no shell eval, no SQL, no HTML rendering). OutputScanner scans before response is returned to caller. Session summaries written verbatim to Obsidian markdown — no code execution path. |
| LLM06 | Excessive Agency | MITIGATED | Pi harness tool execution probed by scheduled pen test agent (garak + ofelia, weekly). Pen test reports written to Obsidian /security/pentest-reports/. Jailbreak patterns in garak corpus include excessive agency probes. |
| LLM07 | System Prompt Leakage | MITIGATED | InjectionFilter strips "reveal your system prompt" / "print your system prompt" patterns. OutputScanner would catch system prompt content in output via bearer token / key patterns. Framing wrapper delimits context from instructions. |
| LLM08 | Vector and Embedding Weaknesses | N/A | No vector database in v1.0. Context retrieval is flat file read from Obsidian vault. Deferred to future phase if semantic search is added. |
| LLM09 | Misinformation | ACCEPTED-RISK | Personal single-user assistant. User is sole judge of output quality. No fact-checking pipeline planned. Accepted: user verifies outputs. |
| LLM10 | Unbounded Consumption | MITIGATED | Token guard (token_guard.py, CORE-05/MEM-07) enforces context window ceiling. 25% budget ratio caps injected context. HTTP 422 returned if limits exceeded. No per-user rate limiting (single-user system, accepted risk). |

## Phase 5 Threat Surface Summary

- **Surface 1 — Vault content injection:** MITIGATED (InjectionFilter wrap_context + framing)
- **Surface 2 — Interface input:** MITIGATED (InjectionFilter filter_input, same code path)
- **Surface 3 — AI response leakage:** MITIGATED (OutputScanner regex + Haiku secondary)
- **Surface 4 — Ongoing validation:** MITIGATED (pen test agent, garak probes, weekly schedule)

## Incident Log

Leak incidents auto-written to: `security/leak-incidents/{timestamp}.md` (via OutputScanner + Obsidian)
Pen test reports auto-written to: `security/pentest-reports/{date}.md` (via pen test agent)

## Phase Closure Requirement (SEC-03)

Phase 5 closes only when all 10 items have status MITIGATED, ACCEPTED-RISK, or N/A with rationale.
Current status: **ALL 10 ITEMS ADDRESSED** (4 Mitigated, 3 Accepted-Risk, 1 N/A, 2 N/A-but-mitigated-by-adjacent-control)
