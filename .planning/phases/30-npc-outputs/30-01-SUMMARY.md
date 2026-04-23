---
phase: 30-npc-outputs
plan: "01"
subsystem: pathfinder-module
tags: [helper-modules, reportlab, litellm, tdd, wave-1]
dependency_graph:
  requires: []
  provides:
    - modules/pathfinder/app/pdf.py
    - modules/pathfinder/app/llm.py (extended — generate_mj_description, build_mj_prompt)
    - modules/pathfinder/tests/test_npc.py (extended — 9 OUT-01..04 stubs)
    - reportlab>=4.4.0 dependency
  affects:
    - Plan 30-02 — endpoints can now import build_npc_pdf, generate_mj_description, build_mj_prompt
    - Plan 30-03 — bot tests not affected (bot.py is module-internal only at this point)
tech_stack:
  added:
    - "reportlab 4.4.10 (declared >=4.4.0 — Platypus PDF generation)"
  patterns:
    - "Module split: pdf.py is ReportLab-only, llm.py owns all LiteLLM calls (generate_mj_description sits alongside extract_npc_fields and update_npc_fields)"
    - "Constrained LLM call: max_tokens=40 enforces output ceiling instead of post-hoc truncation (D-10)"
    - "Prompt-injection mitigation: personality and backstory truncated to 200 chars and newlines stripped before LLM interpolation (D-11)"
    - "Hybrid prompt assembly: LLM produces only the visual-description slot; build_mj_prompt anchors style/framing/MJ params via fixed template (D-09)"
    - "Local-binding patch path: token tests patch `app.routes.npc.generate_mj_description` (the import binding inside npc.py), not `app.llm.generate_mj_description` — Python `unittest.mock.patch` resolves against the importing module's namespace"
key_files:
  created:
    - modules/pathfinder/app/pdf.py
  modified:
    - modules/pathfinder/app/llm.py
    - modules/pathfinder/pyproject.toml
    - modules/pathfinder/Dockerfile
    - modules/pathfinder/tests/test_npc.py
decisions:
  - "pdf.py kept ReportLab-only — no LLM imports — to keep module concerns separated and to make the test surface for PDF generation independent of LLM mocking"
  - "build_mj_prompt is sync (not async) — pure string assembly, no I/O; only generate_mj_description is async because it calls litellm.acompletion()"
  - "buffer.getvalue() not buffer.read() — Pitfall 6: io.BytesIO.read() returns empty after write because the cursor is at end-of-stream; getvalue() returns the full buffer regardless of cursor position"
  - "Style sheet keys: Title / Heading2 / Normal — exact case as defined in ReportLab getSampleStyleSheet (Pitfall 3)"
  - "Skills handled as dict OR string in PDF (Pitfall 7) — vault data is heterogeneous; defensive isinstance check prevents AttributeError on string-form skill lists"
metrics:
  completed: "2026-04-23"
  tasks_completed: 2
  files_modified: 5
  files_created: 1
---

# Phase 30 Plan 01: Helper Modules + RED Test Stubs

Plan 30-01 establishes the foundation for Phase 30: a ReportLab-only PDF builder, two new LLM helpers in the established `app/llm.py` location, the `reportlab>=4.4.0` dependency, and 9 RED-phase test stubs that prove the four new endpoints don't exist yet. Plan 30-02 turns the stubs GREEN by adding the endpoints.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create app/pdf.py + extend app/llm.py with MJ helpers | ce9a5f7 | app/pdf.py (new), app/llm.py |
| 2 | Add reportlab dep + 9 RED test stubs | fc8ec6d | pyproject.toml, Dockerfile, tests/test_npc.py |

## Verification Results

**Imports (after `uv sync` installed reportlab 4.4.10):**
```
$ uv run python -c "from app.pdf import build_npc_pdf; from app.llm import generate_mj_description, build_mj_prompt; print('imports ok')"
imports ok
```

**Existing test suite (Phase 29 NPC CRUD — must remain green):**
```
$ uv run pytest tests/test_npc.py -k "not (export_foundry or npc_token or npc_stat or npc_pdf)" -q
.........                                                                [100%]
9 passed, 9 deselected in 1.09s
```

**New OUT test stubs (must fail RED):**
```
$ uv run pytest tests/test_npc.py -k "export_foundry or npc_token or npc_stat or npc_pdf" -q
8 failed, 1 passed, 9 deselected in 1.05s
```

**Aggregate (full module):** 18 tests, 10 passing, 8 failing RED.

The single GREEN OUT stub is `test_npc_export_foundry_not_found` — it asserts `resp.status_code == 404`, and FastAPI returns 404 by default for any undefined route. Plan 30-02 keeps this test green via explicit 404 for unknown NPC, exercising the same outcome through the implemented code path.

## Test Coverage Added

| Test | Requirement | Behavior Covered | Status |
|------|-------------|------------------|--------|
| test_npc_export_foundry_success | OUT-01 | 200 + actor dict + filename slug.json | RED |
| test_npc_export_foundry_not_found | OUT-01 | 404 for unknown NPC | GREEN (incidental — FastAPI default) |
| test_npc_export_foundry_no_stats | OUT-01, D-05 | actor system.attributes.{ac,hp}.value == 0 with no stats block | RED |
| test_npc_token_success | OUT-02 | 200 + prompt key in response | RED |
| test_npc_token_template_structure | OUT-02, D-09 | prompt contains --ar 1:1 and --no text | RED |
| test_npc_stat_success | OUT-03 | 200 + fields + stats keys; stats.ac == 18 | RED |
| test_npc_stat_no_stats | OUT-03, D-16 | stats == {} when no ## Stats block present | RED |
| test_npc_pdf_success | OUT-04 | 200 + data_b64; decoded bytes start with %PDF | RED |
| test_npc_pdf_no_stats | OUT-04, D-20 | header-only PDF when no stats block | RED |

## Helper Functions Added

| Function | Module | Signature | Purpose |
|----------|--------|-----------|---------|
| build_npc_pdf | app/pdf.py | `(fields: dict, stats: dict) -> bytes` | One-page PF2e stat card via ReportLab Platypus |
| generate_mj_description | app/llm.py | `async (fields, model, api_base) -> str` | Constrained LLM call (max_tokens=40) for token visual description |
| build_mj_prompt | app/llm.py | `(fields, description) -> str` | Assemble full Midjourney prompt from description + fixed template |

## Deviations from Plan

None — both tasks executed as specified. Two minor notes:

1. **`generate_mj_description` and `build_mj_prompt` placed between `extract_npc_fields` and `update_npc_fields` in `app/llm.py`** rather than literally appended at the end of the file. The plan said "after the last existing function"; the chosen position keeps all four LLM-call functions grouped contiguously (LLM helpers grouped together, `_strip_code_fences` private helper at top). Functionally identical — Python doesn't care about module-level function order.
2. **Per-test-function `import base64`** preserved as written in the plan stub code, instead of moving to top-of-file imports. The plan text mentioned both options; following the literal stub code is consistent with the rest of the test file's pattern of late imports inside test bodies.

## Threat-Model Status

| Threat ID | Mitigation Implemented | Evidence |
|-----------|------------------------|----------|
| T-30-01-01 (NPCOutputRequest tampering) | Plan 30-02 will wire `_validate_npc_name()` to NPCOutputRequest field validator | Pending — Plan 02 |
| T-30-01-02 (LLM prompt injection) | `[:200].replace("\n", " ")` applied to personality and backstory in generate_mj_description | `app/llm.py:90-91` |

## Self-Check: PASSED

- `modules/pathfinder/app/pdf.py`: created with `build_npc_pdf` (no LLM imports — `grep -c "litellm\|generate_mj" app/pdf.py` returns 0)
- `modules/pathfinder/app/llm.py`: extended with `generate_mj_description` and `build_mj_prompt` (existing `extract_npc_fields` and `update_npc_fields` unchanged)
- `reportlab>=4.4.0` present in `pyproject.toml` AND `Dockerfile`
- 9 OUT test functions exist in `tests/test_npc.py`
- Token test patch path is `app.routes.npc.generate_mj_description` ×2 (local binding rule)
- `buffer.getvalue()` used in PDF code (not `buffer.read()`)
- Pre-existing test suite (9 NPC CRUD tests) still green
- Commits `ce9a5f7` and `fc8ec6d`: present on main
