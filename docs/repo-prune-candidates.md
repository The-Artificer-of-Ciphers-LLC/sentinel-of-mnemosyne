# Repository Scan — Files Not Required for Application Runtime

Date: 2026-05-06

This is a **runtime-focused** audit (what the app needs to run in production), not a dev/audit/docs audit.

## Definitely not required for runtime (high confidence)

- `.DS_Store`
- `node_modules/` (root)
- `pi-harness/node_modules/`
- `scripts/__pycache__/`
- `security/__pycache__/`
- `shared/__pycache__/`
- `sentinel-core/.pytest_cache/`
- `sentinel-core/.ruff_cache/`
- `sentinel-core/.venv/`
- `shared/.pytest_cache/`
- `shared/.ruff_cache/`
- `.pytest_cache/`
- `.ruff_cache/`

## Local machine / operator-private artifacts (should not be in repo)

- `.env` (machine-local config)
- `.gsd-id`
- `.planning/` (all planning artifacts)
- `.claude/` (local agent state)
- `CLAUDE.md` (local AI instructions file)
- `GSD-WORKTREE-DELETION-BUG-REPORT.md`
- `V040-REFACTORING-DIRECTIVE.md`

## Secrets currently present in repo (critical cleanup candidates)

These are not needed in git and should be removed from repo history if possible:

- `secrets/alpaca_live_api_key`
- `secrets/alpaca_live_secret_key`
- `secrets/alpaca_paper_api_key`
- `secrets/alpaca_paper_secret_key`
- `secrets/anthropic_api_key`
- `secrets/discord_bot_token`
- `secrets/lmstudio_api_key`
- `secrets/obsidian_api_key`
- `secrets/sentinel_api_key`

Keep only:

- `secrets/.gitkeep`
- `secrets/README.md`

## Not needed for production runtime, but useful for development/operations

If you want a minimal deploy-only repo, these can be removed/moved:

- `.github/` (CI, templates, governance)
- `docs/` (all docs)
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`
- `sentinel-core/tests/`
- `shared/tests/`
- `scripts/uat_*.py`, `scripts/uat_*.sh`
- `security/pentest-agent/`
- `security/pentest/`
- `security/JAILBREAK-BASELINE.md`
- `security/owasp-llm-checklist.md`

## Likely optional depending on deployment profile

- `pi-harness/` (optional by your own architecture; only needed with `--pi` workflows)
- `interfaces/imessage/` (optional interface)
- `interfaces/messages/` (placeholder)
- `modules/pathfinder/` (optional unless you run Pathfinder)

## Core runtime set (keep)

For baseline Sentinel Core + Discord + optional modules:

- `docker-compose.yml`
- `sentinel.sh`
- `.env.example`
- `sentinel-core/` (app + compose + Dockerfile + pyproject + models)
- `shared/` (runtime shared package)
- `interfaces/discord/` (if using Discord)
- `modules/pathfinder/` (if using Pathfinder)
- `pi-harness/` (only if using `--pi`)

---

If you want, next step I can generate a **safe deletion plan** in phases:
1. immediate safe deletes,
2. security-critical secret purge,
3. optional slim-down profile (core-only vs full-stack).
