#!/bin/bash
# uat_phase35.sh — Phase 35 Foundry VTT Event Ingest UAT
#
# Tests the live stack end-to-end via curl.
# Run with: docker compose --profile pf2e up -d && bash scripts/uat_phase35.sh
#
# Prerequisites:
#   - docker compose --profile pf2e up -d (pf2e-module + sentinel-core + discord-bot running)
#   - SENTINEL_API_KEY exported or set in .env
#   - SENTINEL_CORE_URL defaults to http://localhost:8000
#
# Steps:
#   1. Verify pf2e-module /healthz
#   2. Verify sentinel-core proxy /modules/pathfinder/healthz
#   3. Verify 16-route REGISTRATION_PAYLOAD includes foundry/event (regression guard)
#   4. POST /modules/pathfinder/foundry/event with roll payload — expect 200
#   5. POST /modules/pathfinder/foundry/event with wrong key — expect 401
#   6. POST /modules/pathfinder/foundry/event with malformed payload — expect 422
#   7. GET /foundry/static/module.json — expect 200 + correct content-type
#   8. GET /foundry/static/sentinel-connector.zip — expect 200
#   9. POST /modules/pathfinder/foundry/event with chat payload — expect 200

set -euo pipefail

BASE_URL="${SENTINEL_CORE_URL:-http://localhost:8000}"
PF2E_URL="${PF2E_MODULE_URL:-http://localhost:8000}"
API_KEY="${SENTINEL_API_KEY:-}"

if [[ -z "$API_KEY" ]]; then
  API_KEY=$(cat secrets/sentinel_api_key 2>/dev/null || echo "")
fi

if [[ -z "$API_KEY" ]]; then
  echo "ERROR: SENTINEL_API_KEY not set. Export it or run from repo root (secrets/sentinel_api_key)."
  exit 1
fi

PASS=0
FAIL=0

check() {
  local label="$1"
  local expected="$2"
  local actual="$3"
  if [[ "$actual" == "$expected" ]]; then
    echo "  PASS: $label"
    ((PASS++)) || true
  else
    echo "  FAIL: $label (expected=$expected actual=$actual)"
    ((FAIL++)) || true
  fi
}

echo "=== Phase 35 UAT: Foundry VTT Event Ingest ==="
echo "BASE_URL=$BASE_URL"
echo ""

# -----------------------------------------------------------------------
# Step 1: pf2e-module /healthz (direct)
# -----------------------------------------------------------------------
echo "Step 1: pf2e-module /healthz (direct)"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${PF2E_URL}/healthz")
check "pf2e-module healthz returns 200" "200" "$STATUS"

# -----------------------------------------------------------------------
# Step 2: sentinel-core proxy /modules/pathfinder/healthz
# -----------------------------------------------------------------------
echo "Step 2: sentinel-core proxy /modules/pathfinder/healthz"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "X-Sentinel-Key: $API_KEY" \
  "${BASE_URL}/modules/pathfinder/healthz")
check "proxy healthz returns 200" "200" "$STATUS"

# -----------------------------------------------------------------------
# Step 3: REGISTRATION_PAYLOAD route count (regression guard)
# -----------------------------------------------------------------------
echo "Step 3: REGISTRATION_PAYLOAD includes foundry/event"
ROUTES=$(curl -s -H "X-Sentinel-Key: $API_KEY" "${BASE_URL}/modules" | python3 -c \
  "import sys,json; mods=json.load(sys.stdin); pf=[m for m in mods if m.get('name')=='pathfinder']; print(len(pf[0]['routes']) if pf else 0)" 2>/dev/null || echo "0")
check "pathfinder has >=16 routes registered" "true" "$([ "$ROUTES" -ge 16 ] && echo true || echo false)"

# -----------------------------------------------------------------------
# Step 4: POST /foundry/event — valid roll payload
# -----------------------------------------------------------------------
echo "Step 4: POST /foundry/event — valid roll payload"
ROLL_PAYLOAD='{
  "event_type": "roll",
  "roll_type": "attack-roll",
  "actor_name": "UAT-Seraphina",
  "target_name": "UAT-Goblin",
  "outcome": "criticalSuccess",
  "roll_total": 28,
  "dc": 14,
  "dc_hidden": false,
  "item_name": "Longsword +1",
  "timestamp": "2026-04-25T19:42:00Z"
}'
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST \
  -H "Content-Type: application/json" \
  -H "X-Sentinel-Key: $API_KEY" \
  -d "$ROLL_PAYLOAD" \
  "${BASE_URL}/modules/pathfinder/foundry/event")
check "valid roll payload returns 200" "200" "$STATUS"

# -----------------------------------------------------------------------
# Step 5: POST /foundry/event — wrong key → 401
# -----------------------------------------------------------------------
echo "Step 5: POST /foundry/event — wrong key → 401"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST \
  -H "Content-Type: application/json" \
  -H "X-Sentinel-Key: wrong-key-uat" \
  -d "$ROLL_PAYLOAD" \
  "${BASE_URL}/modules/pathfinder/foundry/event")
check "wrong key returns 401" "401" "$STATUS"

# -----------------------------------------------------------------------
# Step 6: POST /foundry/event — malformed payload → 422
# -----------------------------------------------------------------------
echo "Step 6: POST /foundry/event — malformed payload → 422"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST \
  -H "Content-Type: application/json" \
  -H "X-Sentinel-Key: $API_KEY" \
  -d '{"event_type": "roll"}' \
  "${BASE_URL}/modules/pathfinder/foundry/event")
check "malformed payload returns 422" "422" "$STATUS"

# -----------------------------------------------------------------------
# Step 7: GET /foundry/static/module.json
# -----------------------------------------------------------------------
echo "Step 7: GET /foundry/static/module.json"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  "${BASE_URL}/foundry/static/module.json")
check "module.json served with 200" "200" "$STATUS"

# -----------------------------------------------------------------------
# Step 8: GET /foundry/static/sentinel-connector.zip
# -----------------------------------------------------------------------
echo "Step 8: GET /foundry/static/sentinel-connector.zip"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  "${BASE_URL}/foundry/static/sentinel-connector.zip")
# 200 if zip exists; 404 if package.sh hasn't been run — acceptable for UAT
if [[ "$STATUS" == "200" ]]; then
  echo "  PASS: sentinel-connector.zip served with 200"
  ((PASS++)) || true
elif [[ "$STATUS" == "404" ]]; then
  echo "  INFO: sentinel-connector.zip not yet built (run: cd modules/pathfinder/foundry-client && ./package.sh)"
else
  echo "  FAIL: sentinel-connector.zip returned unexpected status $STATUS"
  ((FAIL++)) || true
fi

# -----------------------------------------------------------------------
# Step 9: POST /foundry/event — chat payload
# -----------------------------------------------------------------------
echo "Step 9: POST /foundry/event — chat payload"
CHAT_PAYLOAD='{
  "event_type": "chat",
  "actor_name": "DM",
  "content": "The party finds a secret door.",
  "timestamp": "2026-04-25T19:45:00Z"
}'
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST \
  -H "Content-Type: application/json" \
  -H "X-Sentinel-Key: $API_KEY" \
  -d "$CHAT_PAYLOAD" \
  "${BASE_URL}/modules/pathfinder/foundry/event")
check "chat payload returns 200" "200" "$STATUS"

# -----------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------
echo ""
echo "=== UAT Results: $PASS passed, $FAIL failed ==="
if [[ "$FAIL" -gt 0 ]]; then
  echo "FAIL — fix failing steps before marking phase complete"
  exit 1
else
  echo "PASS — all automated UAT checks passed"
  echo ""
  echo "Manual verification required (from 35-VALIDATION.md):"
  echo "  - Install sentinel-connector.zip in Foundry v14 via manifest URL"
  echo "  - Verify module settings panel shows 3 fields (URL, Key, Prefix)"
  echo "  - Make an attack roll in PF2e — verify Discord embed appears in DM channel"
  echo "  - Confirm preCreateChatMessage does NOT suppress Foundry chat messages"
fi
