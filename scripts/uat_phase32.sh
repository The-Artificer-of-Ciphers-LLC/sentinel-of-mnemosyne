#!/bin/bash
# Phase 32 Monster Harvesting — live-stack UAT orchestrator.
#
# Rebuilds pf2e-module + discord containers (picks up Phase 32 source changes),
# waits for healthy, then runs scripts/uat_harvest.py against the live stack.
#
# Safe to re-run. No-op if nothing changed in the images.
#
# Usage: ./scripts/uat_phase32.sh
# Prereqs:
#   - .env populated with SENTINEL_API_KEY, OBSIDIAN_API_KEY, OBSIDIAN_API_URL
#   - LM Studio running on host (for LLM fallback tests)
#   - Obsidian running with Local REST API plugin
#   - Docker Desktop running

set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$PROJECT_ROOT"

echo "── Phase 32 UAT: rebuild + test ──"
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
echo "── Step 3: Confirm pf2e-module registered with sentinel-core ──"
REG_RETRIES=15
while [ $REG_RETRIES -gt 0 ]; do
  if curl -sf -H "X-Sentinel-Key: $SENTINEL_API_KEY" \
     "${UAT_SENTINEL_URL:-http://localhost:8000}/modules" 2>/dev/null | grep -q '"pathfinder"'; then
    echo "✓ pf2e-module registered"
    break
  fi
  REG_RETRIES=$((REG_RETRIES - 1))
  sleep 2
done
if [ $REG_RETRIES -eq 0 ]; then
  echo "⚠ pf2e-module not yet registered — running UAT anyway (container smoke will flag)"
fi

echo ""
echo "── Step 4: Run harvest UAT against live stack ──"

# Run inside interfaces/discord venv (has httpx + discord.py).
# OBSIDIAN_API_URL in .env is `host.docker.internal:27123` (container perspective);
# the host must use localhost:27123 instead — host.docker.internal doesn't resolve
# from macOS shells.
HOST_OBSIDIAN_URL="${OBSIDIAN_API_URL//host.docker.internal/localhost}"

cd "$PROJECT_ROOT/interfaces/discord"
LIVE_TEST=1 \
  UAT_SENTINEL_URL="${UAT_SENTINEL_URL:-http://localhost:8000}" \
  UAT_SENTINEL_KEY="$SENTINEL_API_KEY" \
  UAT_OBSIDIAN_URL="${HOST_OBSIDIAN_URL:-http://localhost:27123}" \
  UAT_OBSIDIAN_KEY="$OBSIDIAN_API_KEY" \
  uv run --no-sync python "$PROJECT_ROOT/scripts/uat_harvest.py"

UAT_EXIT=$?

echo ""
if [ $UAT_EXIT -eq 0 ]; then
  echo "✓ Phase 32 live UAT passed"
else
  echo "✗ Phase 32 live UAT failed (exit $UAT_EXIT)"
fi

exit $UAT_EXIT
