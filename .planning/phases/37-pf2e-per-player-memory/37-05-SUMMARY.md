---
phase: 37-pf2e-per-player-memory
plan: "05"
subsystem: pathfinder/obsidian-client-probe
tags: [probe, wave-0, obsidian, alias-path, research-resolution]
type: auto
wave: 0
requires:
  - modules/pathfinder/app/obsidian.py (ObsidianClient — thin REST wrapper)
provides:
  - Empirical confirmation that ObsidianClient accepts mnemosyne/pf2e/players/_aliases.json
  - Locked-in alias map path string for Wave 1 plan 37-06 (player_identity_resolver)
  - Resolution of RESEARCH.md Open Question #5 / Assumption A1
affects:
  - .planning/phases/37-pf2e-per-player-memory/37-06-PLAN.md (alias map path now locked)
tech-stack:
  added: []
  patterns:
    - httpx.MockTransport for behavioral capture of outgoing HTTP requests
    - Pair-of-paths probe (primary + fallback) to lock both options before Wave 1
key-files:
  created:
    - modules/pathfinder/tests/test_aliases_path_probe.py
  modified: []
decisions:
  - "ALIAS_MAP_PATH = mnemosyne/pf2e/players/_aliases.json (underscore prefix) — confirmed accepted by ObsidianClient"
  - "Fallback mnemosyne/pf2e/players/aliases.json also confirmed accepted (locked as fallback if Obsidian's *vault listing* later excludes underscore-prefixed files; not relevant for direct GET/PUT)"
  - "ObsidianClient does no path validation — it string-concatenates {base_url}/vault/{path} and lets httpx URL-encode segments. Underscore is a valid URL char so no encoding artifacts"
metrics:
  duration: ~3 min
  completed: 2026-05-07
  tests_added: 4
---

# Phase 37 Plan 05: Obsidian Client Underscore-Path Probe Summary

**One-liner:** Empirical probe of `ObsidianClient` confirms `mnemosyne/pf2e/players/_aliases.json` round-trips verbatim through `get_note()` and `put_note()`, locking the Wave 1 alias map path with no client-side rejection risk.

## Empirical Result

All 4 behavioral tests pass. The pytest output:

```
============================= test session starts ==============================
platform darwin -- Python 3.14.4, pytest-9.0.2, pluggy-1.6.0
rootdir: /Users/trekkie/projects/sentinel-of-mnemosyne/modules/pathfinder
configfile: pyproject.toml
plugins: mock-3.15.1, asyncio-1.3.0, cov-7.0.0, anyio-4.13.0
asyncio: mode=Mode.AUTO

tests/test_aliases_path_probe.py::test_obsidian_client_accepts_underscore_prefixed_path_get PASSED [ 25%]
tests/test_aliases_path_probe.py::test_obsidian_client_accepts_underscore_prefixed_path_put PASSED [ 50%]
tests/test_aliases_path_probe.py::test_obsidian_client_accepts_plain_aliases_json_path_get PASSED [ 75%]
tests/test_aliases_path_probe.py::test_obsidian_client_accepts_plain_aliases_json_path_put PASSED [100%]

============================== 4 passed in 0.06s ===============================
```

### What the probe asserts behaviorally

For each path variant the test installs an `httpx.MockTransport` that records every request the client emits, then:

1. Calls `await client.get_note(path)` — asserts `req.method == "GET"`, `req.url.path == f"/vault/{path}"`, and `Authorization: Bearer <key>` header present.
2. Calls `await client.put_note(path, body)` — asserts `req.method == "PUT"`, `req.url.path == f"/vault/{path}"`, `Content-Type: text/markdown`, and `req.content == body.encode("utf-8")`.

Both the underscore-prefixed `mnemosyne/pf2e/players/_aliases.json` and the plain `mnemosyne/pf2e/players/aliases.json` round-trip verbatim. **No client-side path validation rejects either variant.**

## Why This Resolves Open Question #5 / Assumption A1

`RESEARCH.md` flagged uncertainty about whether the project's Obsidian wrapper (or its underlying httpx layer) would mangle underscore-prefixed filenames before the HTTP call reached Obsidian. Inspection of `modules/pathfinder/app/obsidian.py` shows the client is a thin wrapper:

```python
async def get_note(self, path: str) -> str | None:
    resp = await self._client.get(
        f"{self._base_url}/vault/{path}", headers=self._headers, timeout=5.0,
    )
```

No validation, no `path.startswith("_")` rejection, no encoding transformation specific to leading underscores. `httpx` URL-encodes path segments by RFC 3986 rules; underscore is in the unreserved set, so it is never percent-encoded. The probe confirms both ends of this chain.

## Implication for Plan 37-06 (Wave 1 player_identity_resolver)

**Locked path string:** `mnemosyne/pf2e/players/_aliases.json`

Plan 37-06's `player_identity_resolver` should use this exact path constant. The underscore prefix keeps the alias map sorted to the top of the `players/` directory listing in the Obsidian UI (cosmetic) and signals "system file" to a human browsing the vault — both desirable. There is no functional cost.

If a later phase needs to enumerate player vaults via `list_directory("mnemosyne/pf2e/players/")`, the resolver should explicitly skip files whose basename starts with `_` (the alias map and any future system files). That filter belongs in plan 37-06 or wherever directory enumeration lives — flag for the planner.

## Deviations from Plan

None — plan executed exactly as written. The plan's "most likely outcome" (both variants pass, underscore variant locked in) matched reality.

## Self-Check: PASSED

- modules/pathfinder/tests/test_aliases_path_probe.py — FOUND
- Commit 5161ba2 — FOUND in git log
- 4/4 tests pass with the test runner used by the rest of the pathfinder suite
