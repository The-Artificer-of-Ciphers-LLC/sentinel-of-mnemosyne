---
phase: 30-npc-outputs
plan: "02"
subsystem: pathfinder-module
tags: [endpoints, foundry, midjourney, pdf, embed, wave-2, green]
dependency_graph:
  requires:
    - 30-01 (provides build_npc_pdf, generate_mj_description, build_mj_prompt)
  provides:
    - "POST /npc/export-foundry (OUT-01)"
    - "POST /npc/token (OUT-02)"
    - "POST /npc/stat (OUT-03)"
    - "POST /npc/pdf (OUT-04)"
    - REGISTRATION_PAYLOAD now lists 10 routes
  affects:
    - Plan 30-03 — Discord bot can now call all 4 new module endpoints via post_to_module
tech_stack:
  added: []
  patterns:
    - "All 4 handlers follow the slugify → get_note → 404-if-None → parse_frontmatter → parse_stats_block → transform pipeline; only the transform step differs between endpoints"
    - "PF2e Remaster Foundry actor: uses uuid.uuid4().hex[:16] for _id (Pitfall 4); does NOT include system.details.alignment (removed in 2023 Remaster)"
    - "Binary-via-JSON-proxy: PDF bytes returned as base64-encoded data_b64 inside JSONResponse — sentinel-core proxy always calls resp.json() so raw binary cannot pass through (RESEARCH.md Pattern 1)"
    - "Hybrid LLM/template prompt assembly for token: LLM produces visual description slot, build_mj_prompt anchors --ar 1:1 / --no text outside the LLM (D-09)"
    - "stats={} fallback: stat_block returns empty dict instead of None when no ## Stats block present (D-16) — bot layer can rely on .get() patterns"
key_files:
  created: []
  modified:
    - modules/pathfinder/app/routes/npc.py
    - modules/pathfinder/app/main.py
decisions:
  - "_build_foundry_actor lives in npc.py, not pdf.py — it's domain logic for the Foundry schema, not PDF rendering. Keeps module concerns separated"
  - "NPCOutputRequest is a separate model from NPCShowRequest because OUT endpoints don't need user_id (no audit logging requirement); shared sanitize_name validator via _validate_npc_name"
  - "Imports consolidated into single `from app.llm import (...)` block instead of two lines (minor style improvement over plan's literal text — same import, cleaner code)"
metrics:
  completed: "2026-04-23"
  tasks_completed: 2
  files_modified: 2
---

# Phase 30 Plan 02: NPC Output Endpoints + Module Registration

Plan 30-02 implements the 4 NPC output endpoints that turn the Plan 30-01 RED test stubs GREEN. Each endpoint reads the existing NPC Obsidian note and transforms it into a different output format — Foundry actor JSON, Midjourney prompt text, structured stat data, or PDF bytes.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add 4 route handlers + NPCOutputRequest + _build_foundry_actor | 16596e0 | app/routes/npc.py |
| 2 | Extend REGISTRATION_PAYLOAD + docstring | c7536a7 | app/main.py |

## Verification Results

**Module test suite (18 tests — 9 NPC CRUD from Phase 29 + 9 OUT from Plan 30-01):**
```
$ uv run pytest tests/test_npc.py -q
..................                                                       [100%]
18 passed in 1.20s
```

**REGISTRATION_PAYLOAD invariant:**
```
$ SENTINEL_API_KEY=test uv run python -c "from app.main import REGISTRATION_PAYLOAD; routes = [r['path'] for r in REGISTRATION_PAYLOAD['routes']]; assert 'npc/export-foundry' in routes; assert 'npc/token' in routes; assert 'npc/stat' in routes; assert 'npc/pdf' in routes; assert len(routes) == 10"
REGISTRATION_PAYLOAD OK — 10 routes
```

## Endpoint Behaviors

| Endpoint | Request | 200 Response | 404 |
|----------|---------|--------------|-----|
| POST /npc/export-foundry | {"name": "..."} | `{"actor": {...}, "filename": "<slug>.json", "slug": "..."}` | NPC not found |
| POST /npc/token | {"name": "..."} | `{"prompt": "<MJ prompt>", "slug": "..."}` | NPC not found |
| POST /npc/stat | {"name": "..."} | `{"fields": {...}, "stats": {...} or {}, "slug": "...", "path": "..."}` | NPC not found |
| POST /npc/pdf | {"name": "..."} | `{"data_b64": "<base64>", "filename": "<slug>-stat-card.pdf", "slug": "..."}` | NPC not found |

## Pitfalls Avoided

| Pitfall | How avoided |
|---------|-------------|
| Pitfall 4: Foundry _id format | `uuid.uuid4().hex[:16]` produces 16 hex chars (not full UUID with dashes) |
| Pitfall 6: io.BytesIO.read() returns empty | `build_npc_pdf` (Plan 01) uses `.getvalue()` — verified via `assert pdf_bytes[:4] == b"%PDF"` |
| Pitfall 7: Heterogeneous skills | `build_npc_pdf` handles dict OR string (Plan 01) — pdf endpoint passes through whatever stats dict comes back from parse |
| 2023 Remaster: alignment removed | `_build_foundry_actor` does NOT include `system.details.alignment` — `grep -c "alignment" modules/pathfinder/app/routes/npc.py` returns 0 |
| Binary transport via JSON proxy | PDF endpoint returns `data_b64` (base64-encoded) inside JSONResponse, not raw bytes — bot layer (Plan 03) decodes |

## Threat-Model Status

| Threat ID | Mitigation Implemented | Evidence |
|-----------|------------------------|----------|
| T-30-02-01 (Path traversal via name) | NPCOutputRequest applies `_validate_npc_name` validator; `slugify()` strips path separators | `grep -c "sanitize_name" app/routes/npc.py` shows the validator is wired |
| T-30-02-02 (LLM prompt injection) | `generate_mj_description` truncates personality+backstory to 200 chars and strips newlines (Plan 01 mitigation, called from /token) | `app/llm.py:90-91` |
| T-30-02-03 (PDF size bomb) | Accepted — single-user personal tool, ReportLab page size + Discord 8MB limit act as backstops | n/a |
| T-30-02-04 (Foundry JSON exposure) | Accepted — single-user personal tool, data is user's own content | n/a |

## Deviations from Plan

1. **Imports consolidated**: Plan 30-02 said to "Add new imports to npc.py (after existing imports)" with two separate `from app.llm import` lines (one existing, one new). I extended the existing `from app.llm import (...)` tuple instead — same module imports, cleaner Python. Functionally identical.
2. **Mid-edit ruff F401 race**: PostToolUse formatter (ruff with `--fix`) ran after my first import-add edit and stripped the new imports as "unused" because the references didn't exist yet. Re-added them after the references were in place; the second time they stuck. Recoverable, no impact on final state.

## Self-Check: PASSED

- 4 new POST routes registered: `grep -c "@router.post(\"/export-foundry\"\\|@router.post(\"/token\"\\|@router.post(\"/stat\"\\|@router.post(\"/pdf\")" app/routes/npc.py` returns 4
- `_build_foundry_actor` defined and called: 2 references
- `uuid.uuid4().hex[:16]` present (Pitfall 4)
- `base64.b64encode` present (pdf endpoint)
- Imports correct: `from app.pdf import build_npc_pdf` AND `from app.llm import build_mj_prompt, ..., generate_mj_description, ...`
- No `alignment` references (Remaster compliance)
- `len(REGISTRATION_PAYLOAD["routes"]) == 10`
- All 18 tests pass; 9 OUT tests now GREEN
- Commits `16596e0` and `c7536a7`: present on main
