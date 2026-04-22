#!/bin/bash
# Sentinel of Mnemosyne — Docker Compose wrapper
set -euo pipefail

PROFILES=()
ARGS=()

for arg in "$@"; do
  case "$arg" in
    --discord)    PROFILES+=("discord") ;;
    --imessage)   echo "iMessage runs natively on Mac, not in Docker." && exit 1 ;;
    --pf2e)       PROFILES+=("pf2e") ;;
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

# On teardown, include all known opt-in profiles so profiled services (e.g. pi-harness)
# are stopped even when the caller didn't pass their --flag.
ALL_KNOWN_PROFILES=(pi discord pf2e music finance trader coder)
for arg in ${ARGS[@]+"${ARGS[@]}"}; do
  if [[ "$arg" == "down" ]]; then
    for p in "${ALL_KNOWN_PROFILES[@]}"; do
      PROFILE_FLAGS+=("--profile" "$p")
    done
    break
  fi
done

docker compose ${PROFILE_FLAGS[@]+"${PROFILE_FLAGS[@]}"} ${ARGS[@]+"${ARGS[@]}"}
