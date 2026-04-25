#!/bin/bash
# Phase 34 Session Notes — live-stack UAT orchestrator.
#
# Rebuilds pf2e-module + discord containers (picks up Phase 34 source changes),
# waits for healthy, confirms pathfinder module registered with 15 routes,
# then runs scripts/uat_session.py against the live stack.
#
# Safe to re-run. No-op if nothing changed in the images.
#
# Usage: ./scripts/uat_phase34.sh
# Prereqs:
#   - .env populated with SENTINEL_API_KEY, OBSIDIAN_API_KEY, OBSIDIAN_API_URL
#   - LM Studio running on host with a chat model loaded
#   - Obsidian running with Local REST API plugin
#   - Docker Desktop running

set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$PROJECT_ROOT"

echo "── Phase 34 UAT: rebuild + test ──"
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
echo "── Step 3: Confirm pf2e-module registered with 15 routes ──"
# Phase 34 adds the 15th route (session). This check fails fast if the container
# came up with a stale build (old REGISTRATION_PAYLOAD).
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
  if [ "$ROUTES" = "15" ]; then
    echo "✓ 15 routes registered"
    break
  fi
  REG_RETRIES=$((REG_RETRIES - 1))
  sleep 2
done
if [ "$ROUTES" != "15" ]; then
  echo "ERROR: expected 15 routes, got $ROUTES"
  exit 1
fi

echo ""
echo "── Step 4: Run session UAT against live stack ──"

HOST_OBSIDIAN_URL="${OBSIDIAN_API_URL//host.docker.internal/localhost}"

cd "$PROJECT_ROOT/interfaces/discord"
set +e
LIVE_TEST=1 \
  UAT_SENTINEL_URL="${UAT_SENTINEL_URL:-http://localhost:8000}" \
  UAT_SENTINEL_KEY="$SENTINEL_API_KEY" \
  UAT_OBSIDIAN_URL="${HOST_OBSIDIAN_URL:-http://localhost:27123}" \
  UAT_OBSIDIAN_KEY="$OBSIDIAN_API_KEY" \
  uv run --no-sync python "$PROJECT_ROOT/scripts/uat_session.py"

UAT_EXIT=$?
set -e

echo ""
if [ $UAT_EXIT -eq 0 ]; then
  echo "✓ Phase 34 live UAT passed"
else
  echo "✗ Phase 34 live UAT failed (exit $UAT_EXIT)"
fi

exit $UAT_EXIT
