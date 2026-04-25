---
phase: 35-foundry-vtt-event-ingest
plan: "06"
subsystem: foundry-vtt
tags: [javascript, foundry-vtt, discord, cors, pna, webhook]
dependency_graph:
  requires: [35-05]
  provides: [FVT-01, FVT-02, FVT-03 gap-closure]
  affects:
    - modules/pathfinder/foundry-client/sentinel-connector.js
    - modules/pathfinder/app/main.py
    - .env.example
tech_stack:
  added: []
  patterns:
    - PNACORSMiddleware subclassing Starlette CORSMiddleware
    - Webhook-first hybrid with AbortController 3s timeout
    - Discord webhook no-cors fire-and-forget embed delivery
key_files:
  created: []
  modified:
    - modules/pathfinder/foundry-client/sentinel-connector.js
    - modules/pathfinder/app/main.py
    - .env.example
decisions:
  - "sentinelBaseUrl default is empty string — webhook-only mode works out of the box for all Forge players"
  - "PNACORSMiddleware adds Access-Control-Allow-Private-Network header via simple_headers dict"
  - "Discord webhook uses mode: no-cors — opaque response is acceptable for fire-and-forget delivery"
  - "3s AbortController timeout prevents Foundry chat delays when Sentinel is unreachable"
metrics:
  duration: ~12m
  completed: 2026-04-25
  tasks_completed: 2
  tasks_total: 2
  files_modified: 3
---

# Phase 35 Plan 06: Forge Connectivity Gap Closure Summary

Webhook-first hybrid delivery in sentinel-connector.js with PNACORSMiddleware for Tailscale HTTPS browser-origin requests.

## What Was Built

**Task A: sentinel-connector.js rewrite**

Replaced the single-path Sentinel-only `_postRollEvent`/`_postChatEvent` helper functions with a single `async function postEvent()` implementing a webhook-first hybrid pattern:

- `sentinelBaseUrl` setting renamed from `baseUrl` and defaulted to empty string — webhook-only mode works for all Forge players on day one with no infrastructure
- New `discordWebhookUrl` world setting (config: true) for direct Discord webhook delivery
- `postEvent()` attempts Sentinel first with a 3-second `AbortController` timeout; if the request fails (AbortError = timeout, TypeError = mixed content/CORS block) it falls back to the Discord webhook
- Webhook path uses `mode: 'no-cors'` with an `embeds` array payload (title/description/footer/color) built from local roll data
- All CR-01/CR-03 invariants preserved: `config: false` on `apiKey`, `dc_hidden` assigned before first `return true`, `postEvent()` called fire-and-forget (no `await`) so `preCreateChatMessage` hook remains synchronous

**Task B: PNACORSMiddleware + .env.example documentation**

Added `PNACORSMiddleware` to `modules/pathfinder/app/main.py`:

- Subclasses Starlette's `CORSMiddleware` — extends `simple_headers` dict with `Access-Control-Allow-Private-Network: true` when `allow_private_network=True`
- Registered via `app.add_middleware()` before the `StaticFiles` mount with origins including `https://forge-vtt.com`, `https://*.forge-vtt.com`, and localhost variants
- `allow_headers=["Content-Type", "X-Sentinel-Key"]` — required for CORS preflight to pass the non-standard auth header
- Extended `.env.example` Foundry section with `DISCORD_WEBHOOK_URL` reference comment and Tailscale HTTPS cert setup guidance

## Verification

All 178 pathfinder tests pass with no regression.

```
modules/pathfinder $ uv run python -m pytest tests/ --no-header
============================= 178 passed in 1.67s ==============================
```

Import check:
```
modules/pathfinder $ uv run python -c "from app.main import app, PNACORSMiddleware; print('ok')"
PNACORSMiddleware imported ok
```

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. All settings wired directly to `game.settings.get()` and `game.settings.register()` calls. The `postEvent()` function makes real fetch calls to real URLs when both are configured; neither path is stubbed.

## Threat Flags

No new threat surface beyond what the plan's `<threat_model>` already covers. `PNACORSMiddleware` only adds the PNA response header — it does not expand the set of trusted origins beyond what was registered.

## Self-Check: PASSED

| Item | Status |
|------|--------|
| `modules/pathfinder/foundry-client/sentinel-connector.js` | FOUND |
| `modules/pathfinder/app/main.py` | FOUND |
| `.env.example` | FOUND |
| `.planning/phases/35-foundry-vtt-event-ingest/35-06-SUMMARY.md` | FOUND |
| Task A commit `0e5b5a5` | FOUND |
| Task B commit `371ea7b` | FOUND |
