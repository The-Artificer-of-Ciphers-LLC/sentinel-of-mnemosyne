# Phase 1 Context: Core Loop

**Phase:** 1 — Core Loop
**Created:** 2026-04-10
**Status:** Discussion complete — ready for research and planning

---

## Locked Decisions

### Node.js Version: 22 LTS

**Decision:** Node 22 LTS for the Pi harness container.

- pi-mono requires >=20.6.0; Node 22 is the active LTS line (until April 2027)
- Node 24 is the Current (not LTS) release — will become LTS in October 2026
- Lock: pin `node:22-alpine` in the Pi Dockerfile; do not drift to 24 until it reaches LTS

---

### Pi Process Model: Long-Lived Subprocess

**Decision:** One Pi subprocess runs for the lifetime of the Pi harness container. The Fastify HTTP bridge queues requests and routes them via stdin/stdout JSONL. Bridge detects stdout close and respawns Pi on crash.

Architecture:
```
Container start:
  Fastify bridge starts
  └── spawns Pi subprocess (once)
        stdin/stdout JSONL

Per request:
  POST /prompt → internal queue → write to Pi stdin
                                ← read from Pi stdout

Crash recovery:
  Bridge detects stdout close → respawn Pi subprocess
```

Implications for implementation:
- Request queue must be sequential (pi-mono is not concurrent per process)
- Bridge must expose a `/health` endpoint that reflects whether Pi is alive
- Restart count should be logged; alert if Pi respawns more than N times in a window
- Pi adapter wraps all bridge calls — callers never import pi-mono directly

---

### Deployment Topology: Single Mac Mini

**Decision:** Docker (Sentinel Core + Pi harness), LM Studio, and Obsidian all run on the same Mac Mini. All inter-service calls use `host.docker.internal`.

Environment variable defaults:
```
LMSTUDIO_BASE_URL=http://host.docker.internal:1234/v1
OBSIDIAN_API_URL=http://host.docker.internal:27124
```

Note: `.env.example` currently shows a LAN IP for LM Studio — this will be updated to `host.docker.internal` to match the single-machine topology. Users who want a split deployment can still override via env vars.

---

### Startup Resilience: Graceful Degradation

**Decision:** Core starts and begins serving requests immediately. Unavailable dependencies produce degraded (not crashed) behavior.

Behavior per dependency:
- **LM Studio unavailable**: POST /message returns HTTP 503 with `{"error": "AI backend not ready"}` — no crash, no hang
- **Pi subprocess crash on startup**: Bridge attempts respawn with backoff; /health returns degraded until Pi is alive
- **Obsidian unavailable**: Phase 1 does not yet use Obsidian — degradation for vault is a Phase 2 concern

Docker Compose health checks surface dependency status but do NOT block Core from starting.

---

## Constraints Confirmed

| Constraint | Value |
|-----------|-------|
| Node.js version | 22 LTS (`node:22-alpine`) |
| Pi process lifecycle | Long-lived, single subprocess per container |
| Docker host | Single Mac Mini — all services on `host.docker.internal` |
| Startup behavior | Graceful degradation — no hard dependency on LM Studio or Obsidian at boot |
| Pi version pin | Exact version required (semver `x.y.z`) — see PITFALLS.md |
| Fastify bridge | Developer-written (~50-100 lines) — NOT provided by pi-mono |
| Docker Compose | `include` directive (v2.20+) — no `-f` stacking |

---

## Open Questions for Research Phase

1. What is the exact pi-mono npm package name and version to pin? (`@mariozechner/pi-coding-agent` or `@badlogic/pi-mono`?)
2. What is the exact JSONL framing for a pi-mono request/response? (U+2028/U+2029 edge cases noted in ROADMAP research flags)
3. Does the Fastify bridge need to handle streaming responses from Pi, or is request/response sufficient for Phase 1?

---

## Deferred Ideas

- Multi-process Pi pool for concurrent requests — deferred to post-Phase 4 if throughput becomes a bottleneck
- Split deployment (Docker on separate machine from LM Studio) — env-var driven, can be done by user without code changes

---

*Discussed: 2026-04-10*
*Participants: Tom Boucher*
