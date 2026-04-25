#!/bin/bash
# Phase 33 Rules Engine — live-stack UAT orchestrator.
#
# Rebuilds pf2e-module + discord containers (picks up Phase 33 source changes),
# waits for healthy, confirms pathfinder module registered with 14 routes,
# then runs scripts/uat_rules.py against the live stack.
#
# Safe to re-run. No-op if nothing changed in the images.
#
# Usage: ./scripts/uat_phase33.sh
# Prereqs:
#   - .env populated with SENTINEL_API_KEY, OBSIDIAN_API_KEY, OBSIDIAN_API_URL
#   - LM Studio running on host with text-embedding-nomic-embed-text-v1.5 loaded
#     (for RAG retrieval — L-10 pre-check in uat_rules.py catches misconfiguration)
#   - Obsidian running with Local REST API plugin
#   - Docker Desktop running

set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$PROJECT_ROOT"

echo "── Phase 33 UAT: rebuild + test ──"
echo "Project: $PROJECT_ROOT"

# Source .env so SENTINEL_API_KEY / OBSIDIAN_* / DISCORD_ALLOWED_CHANNELS land
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
else
  echo "ERROR: .env not found at $PROJECT_ROOT/.env"
  exit 1
fi

echo ""
echo "── Step 1: Rebuild pf2e-module + discord containers ──"
./sentinel.sh --pf2e --discord up -d --build

echo ""
echo "── Step 2: Wait for healthy (up to 90s) ──"
DEADLINE=$(( $(date +%s) + 90 ))
while [ $(date +%s) -lt $DEADLINE ]; do
  sentinel_ok=false
  pf_ok=false

  if curl -sf "${UAT_SENTINEL_URL:-http://localhost:8000}/health" > /dev/null 2>&1; then
    sentinel_ok=true
  fi

  if docker ps --format '{{.Names}}: {{.Status}}' | grep -qE 'pf2e-module.*\(healthy\)'; then
    pf_ok=true
  fi

  if $sentinel_ok && $pf_ok; then
    echo "✓ Stack healthy (sentinel-core + pf2e-module)"
    break
  fi
  sleep 3
done

if [ $(date +%s) -ge $DEADLINE ]; then
  echo "✗ Timeout waiting for healthy stack — check: docker ps"
  docker ps --format '{{.Names}}: {{.Status}}'
  exit 1
fi

echo ""
echo "── Step 3: Confirm pf2e-module registered with 14 routes ──"
# Phase 33 adds the 14th route (rule). This check fails fast if the container
# came up with a stale build (old REGISTRATION_PAYLOAD) — catches the Phase 32
# G-1 regression class where Dockerfile deps didn't dual-ship.
REG_RETRIES=20
ROUTES="0"
while [ $REG_RETRIES -gt 0 ]; do
  ROUTES=$(curl -sf -H "X-Sentinel-Key: $SENTINEL_API_KEY" \
      "${UAT_SENTINEL_URL:-http://localhost:8000}/modules" 2>/dev/null \
      | python3 -c "import json, sys
try:
    d = json.load(sys.stdin)
    for m in d:
        if m.get('name') == 'pathfinder':
            print(len(m.get('routes', [])))
            sys.exit(0)
    print(0)
except Exception:
    print(0)" 2>/dev/null || echo "0")
  if [ "$ROUTES" = "14" ]; then
    echo "✓ 14 routes registered"
    break
  fi
  REG_RETRIES=$((REG_RETRIES - 1))
  sleep 2
done
if [ "$ROUTES" != "14" ]; then
  echo "ERROR: expected 14 routes, got $ROUTES"
  exit 1
fi

echo ""
echo "── Step 4: Confirm LM Studio embeddings reachable from inside pf2e-module ──"
# L-10 in-container smoke — proves embed_texts works from the module's own
# Docker network namespace (host.docker.internal resolution + LM Studio
# embeddings model loaded). Failure here = lifespan would have crashed at
# startup; if we got past Step 2 healthy this should always pass, but the
# explicit check makes the failure mode visible at the orchestrator level.
if ! docker compose exec -T pf2e-module python -c "
import asyncio, sys
from app.llm import embed_texts
from app.config import settings
async def main():
    try:
        v = await embed_texts(
            ['healthy?'],
            model=settings.rules_embedding_model,
            api_base=settings.litellm_api_base or None,
        )
        print(f'OK — embed returned {len(v)} vector(s) of dim {len(v[0])}')
    except Exception as e:
        print(f'FAIL: {e}', file=sys.stderr)
        sys.exit(1)
asyncio.run(main())
"; then
  echo "ERROR: embed_texts from inside pf2e-module failed — LM Studio embedding model likely not loaded"
  exit 1
fi

echo ""
echo "── Step 5: Run rules UAT against live stack ──"

# Run inside interfaces/discord venv (has httpx + discord.py).
# OBSIDIAN_API_URL in .env is `host.docker.internal:27123` (container perspective);
# the host must use localhost:27123 instead — host.docker.internal doesn't resolve
# from macOS shells.
HOST_OBSIDIAN_URL="${OBSIDIAN_API_URL//host.docker.internal/localhost}"

cd "$PROJECT_ROOT/interfaces/discord"
# `set -e` would kill the script on a non-zero uv-run exit before we could
# capture UAT_EXIT — disable it for this single command so we can report
# the UAT result cleanly.
set +e
LIVE_TEST=1 \
  UAT_SENTINEL_URL="${UAT_SENTINEL_URL:-http://localhost:8000}" \
  UAT_SENTINEL_KEY="$SENTINEL_API_KEY" \
  UAT_OBSIDIAN_URL="${HOST_OBSIDIAN_URL:-http://localhost:27123}" \
  UAT_OBSIDIAN_KEY="$OBSIDIAN_API_KEY" \
  UAT_LMSTUDIO_URL="${UAT_LMSTUDIO_URL:-http://localhost:1234/v1}" \
  uv run --no-sync python "$PROJECT_ROOT/scripts/uat_rules.py"

UAT_EXIT=$?
set -e

echo ""
if [ $UAT_EXIT -eq 0 ]; then
  echo "✓ Phase 33 live UAT passed"
else
  echo "✗ Phase 33 live UAT failed (exit $UAT_EXIT)"
fi

exit $UAT_EXIT
