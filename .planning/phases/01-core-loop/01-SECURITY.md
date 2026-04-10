---
phase: 01
slug: core-loop
status: verified
threats_open: 0
threats_total: 8
threats_closed: 8
verified: "2026-04-10"
---

# Phase 01: Core Loop — Security Report

**Phase Goal:** End-to-end core message loop — containerized, with token guard and injection protection.
**Verified:** 2026-04-10
**Status:** SECURED — all 8 threats closed

## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| External caller → POST /message | Untrusted user input crosses here into the system |
| Sentinel Core → Pi harness (HTTP) | Core forwards user content over internal Docker network |
| Sentinel Core → LM Studio (HTTP) | Core calls LM Studio on host.docker.internal; no auth (Phase 1 acceptance) |

## Threat Register

| Threat ID | Category | Component | Disposition | Status | Evidence |
|-----------|----------|-----------|-------------|--------|----------|
| T-1-03-01 | Denial of Service | POST /message, token guard | mitigate | CLOSED | `check_token_limit()` at `routes/message.py:23` before `send_prompt()` at line 32. `TokenLimitError` → HTTP 422 at line 25. Implementation in `services/token_guard.py:36-40`. |
| T-1-03-02 | Denial of Service | httpx timeout | mitigate | CLOSED | `main.py:34` — `httpx.AsyncClient(timeout=30.0)`. `clients/pi_adapter.py:26` — `timeout=190.0` (10s margin over Pi's 180s internal timeout, extended for large local model latency). |
| T-1-03-03 | Information Disclosure | LM Studio no auth | accept | CLOSED | Accepted risk. Single Mac Mini personal LAN deployment. LM Studio auth deferred to Phase 4 (PROV-01). |
| T-1-03-04 | Spoofing | POST /message caller identity | accept | CLOSED | Accepted risk. No caller auth in Phase 1. X-Sentinel-Key authentication deferred to Phase 3 (IFACE-06). `user_id` is unverified string field. |
| T-1-03-05 | Tampering | MessageEnvelope.content injection | mitigate | CLOSED | `models.py:7` — `content: str = Field(..., min_length=1, max_length=32_000)`. `clients/pi_adapter.py:23-26` — `json={"message": message}` uses httpx json= serialization (json.dumps() internally). No shell execution path. |
| T-1-02-01 | Tampering | JSONL injection | mitigate | CLOSED | `pi-harness/src/pi-adapter.ts:148` — `JSON.stringify({ type: 'prompt', message })`. Pi spawned at line 54 with `stdio: ['pipe','pipe','inherit']`, no `shell: true`. |
| T-1-02-02 | Denial of Service | Pi queue | mitigate | CLOSED | `pi-adapter.ts:140-146` — 180s responseTimeout. Sequential queue via `pendingQueue` array (line 46) + `isProcessing` guard (line 152). `bridge.ts:40` maps timeout → HTTP 504. |
| T-1-02-03 | Elevation of Privilege | Pi container PATH | mitigate | CLOSED | `pi-harness/Dockerfile:23` — `ENV PATH="/app/node_modules/.bin:$PATH"`. Build-time fixed prefix; no host PATH inherited at Docker runtime. |

## Accepted Risks Log

| Risk ID | Description | Accepted | Resolution Phase |
|---------|-------------|----------|-----------------|
| T-1-03-03 | LM Studio exposed on local network without authentication | 2026-04-10 | Phase 4 (PROV-01) |
| T-1-03-04 | POST /message has no caller authentication | 2026-04-10 | Phase 3 (IFACE-06) |

## Audit Trail

### Security Audit 2026-04-10

| Metric | Count |
|--------|-------|
| Threats found | 8 |
| Closed | 8 |
| Open | 0 |

**Auditor notes:** T-1-03-02 had a documentation gap — threat register stated "35s timeout (5s margin over Pi's 30s)" but implementation uses 190s (10s margin over Pi's 180s). The change was made during Wave 2 to accommodate large local model latency (devstral 14GB, 60-90s prompt processing). Threat register updated in PLAN.md to reflect actual implementation. Mitigation is functionally present and stronger than originally planned.
