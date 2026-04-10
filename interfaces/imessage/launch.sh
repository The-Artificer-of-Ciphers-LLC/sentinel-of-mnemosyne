#!/usr/bin/env bash
# Sentinel iMessage Bridge — Launcher
#
# Usage:
#   IMESSAGE_ENABLED=true SENTINEL_API_KEY=... ./launch.sh
#
# Requires:
#   - Full Disk Access granted to Terminal.app (or your Python interpreter) in
#     System Settings -> Privacy & Security -> Full Disk Access
#   - macpymessenger and httpx installed: pip install macpymessenger>=0.2.0 httpx>=0.28.1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Guard: check feature flag before doing anything
if [[ "${IMESSAGE_ENABLED:-false}" != "true" ]]; then
    echo "[imessage-bridge] IMESSAGE_ENABLED=false — bridge is disabled."
    echo "[imessage-bridge] Set IMESSAGE_ENABLED=true to activate."
    echo "[imessage-bridge] See ${SCRIPT_DIR}/README.md for setup instructions."
    exit 0
fi

# Guard: require SENTINEL_API_KEY
if [[ -z "${SENTINEL_API_KEY:-}" ]]; then
    echo "[imessage-bridge] ERROR: SENTINEL_API_KEY is not set." >&2
    exit 1
fi

echo "[imessage-bridge] Starting bridge (IMESSAGE_ENABLED=true)..."
echo "[imessage-bridge] IMPORTANT: Ensure Full Disk Access is granted in System Settings."

exec python3 "${SCRIPT_DIR}/bridge.py"
