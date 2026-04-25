---
plan: 35-02
phase: 35-foundry-vtt-event-ingest
status: complete
completed: 2026-04-25
self_check: PASSED
---

# Plan 35-02 Summary — Python Backend: foundry.py + POST /foundry/event

## What Was Built

- **`modules/pathfinder/app/foundry.py`** — LLM narration helper (`generate_foundry_narrative`) using LiteLLM, plain-text fallback (`build_narrative_fallback`, D-13), and Discord notify dispatch (`notify_discord_bot` via httpx, D-14). Never raises on LLM or HTTP failure.
- **`modules/pathfinder/app/routes/foundry.py`** — FastAPI router `POST /foundry/event`. Pydantic discriminated union (`FoundryRollEvent` / `FoundryChatEvent`), `X-Sentinel-Key` auth (401 on mismatch), 422 on schema validation failure. Dispatches to `app.foundry` helpers via module reference (`import app.foundry as _foundry`) so test patches on `app.foundry.*` intercept correctly.
- **`app/config.py`** — `foundry_narration_model` (str | None, falls back to `litellm_model`) and `discord_bot_internal_url` added to `Settings`.

## Key Decisions / Deviations

- **Deviation (Rule 1):** Route file originally used `from app.foundry import generate_foundry_narrative, notify_discord_bot` (direct name binding). Patching `app.foundry.*` did not intercept — 3 tests failed. Corrected to `import app.foundry as _foundry` with `_foundry.generate_foundry_narrative(...)` call pattern so patches work. This matches the test contract written in Wave 0.
- **Deviation (Rule 1):** Plan 35-02 executor added `app.include_router(foundry_router)` to `main.py` without the import — caused `NameError` on test runs. Fixed by adding `from app.routes.foundry import router as foundry_router` to `main.py` imports. Full main.py wiring (REGISTRATION_PAYLOAD, StaticFiles) remains for plan 35-04.

## Test Results

- 5/6 `test_foundry.py` tests GREEN (test_roll_event_accepted, test_auth_rejected, test_invalid_payload, test_notify_dispatched, test_llm_fallback)
- `test_registration_payload` intentionally deferred — requires REGISTRATION_PAYLOAD update in plan 35-04
- Existing pathfinder suite: unaffected

## Key Files Created/Modified

- `modules/pathfinder/app/foundry.py` (new, 120 lines)
- `modules/pathfinder/app/routes/foundry.py` (new, ~155 lines)
- `modules/pathfinder/app/config.py` (2 fields added)
- `modules/pathfinder/app/main.py` (import added; include_router added)

## Commits

- `70f60d9` feat(35-02): extend config.py with foundry_narration_model + discord_bot_internal_url
- `87cdf8c` feat(35-02): create app/foundry.py — LLM narration + fallback + Discord notify
- `510e293` fix(35-02): use module-ref for _foundry calls; add missing foundry_router import to main.py
