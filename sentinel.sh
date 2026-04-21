#!/bin/bash
# Sentinel of Mnemosyne — Docker Compose wrapper
set -euo pipefail

PROFILES=()
ARGS=()

for arg in "$@"; do
  case "$arg" in
    --discord)    PROFILES+=("discord") ;;
    --imessage)   echo "iMessage runs natively on Mac, not in Docker." && exit 1 ;;
    --pathfinder) PROFILES+=("pathfinder") ;;
    --music)      PROFILES+=("music") ;;
    --finance)    PROFILES+=("finance") ;;
    --trader)     PROFILES+=("trader") ;;
    --coder)      PROFILES+=("coder") ;;
    --pi)         PROFILES+=("pi") ;;
    *)            ARGS+=("$arg") ;;
  esac
done

PROFILE_FLAGS=()
for p in ${PROFILES[@]+"${PROFILES[@]}"}; do
  PROFILE_FLAGS+=("--profile" "$p")
done

docker compose ${PROFILE_FLAGS[@]+"${PROFILE_FLAGS[@]}"} ${ARGS[@]+"${ARGS[@]}"}
