# Phase 1 Discussion Log

**Date:** 2026-04-10
**Phase:** 1 — Core Loop

---

## Gray Areas Discussed

### Node.js Version (Clarification)

**Question:** Research recommended Node 22 LTS; user note suggested Node 24. Node 24 is currently the "Current" release (not LTS) — will reach LTS in October 2026.

**Answer:** Node 22 LTS confirmed.

---

### Pi Process Model

**Question:** Long-lived persistent subprocess vs. spawn-per-request for the Pi harness inside the container.

**Answer:** Long-lived subprocess.
- Rationale: lower latency, native multi-turn session state, simpler conversation management
- Bridge queues requests; crash recovery via stdout-close detection + respawn

---

### Deployment Topology

**Question:** Everything on one Mac Mini vs. Docker + Obsidian on Mac Mini with LM Studio on separate machine. (.env.example showed a LAN IP for LM Studio suggesting possible split.)

**Answer:** Everything on one Mac Mini.
- All inter-service calls via `host.docker.internal`
- .env.example LAN IP for LM Studio was legacy scaffolding — update to `host.docker.internal`

---

### Startup Resilience

**Question:** Graceful degradation (Core starts immediately, returns 503 when AI backend unavailable) vs. fail-fast (Core blocks until all dependencies are healthy).

**Answer:** Graceful degradation.
- Core starts in ~2 seconds regardless of LM Studio/Obsidian state
- POST /message returns 503 with clear error when LM Studio is not ready
- Phase 1 does not use Obsidian — vault degradation is a Phase 2 concern
