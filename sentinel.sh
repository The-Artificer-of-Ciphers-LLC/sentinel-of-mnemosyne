#!/bin/bash
# sentinel.sh — Convenience wrapper for Docker Compose
# Usage: ./sentinel.sh [--discord] [--messages] [--music] [--finance] [--trader] <docker compose command>
# Examples:
#   ./sentinel.sh up -d
#   ./sentinel.sh --discord up -d
#   ./sentinel.sh --discord --finance up -d
#   ./sentinel.sh down
#   ./sentinel.sh logs -f

set -e

COMPOSE_FILES="-f docker-compose.yml"

# Parse flags — consume them before passing remaining args to docker compose
ARGS=()
for arg in "$@"; do
  case $arg in
    --discord)  COMPOSE_FILES="$COMPOSE_FILES -f interfaces/discord/docker-compose.override.yml" ;;
    --messages) COMPOSE_FILES="$COMPOSE_FILES -f interfaces/messages/docker-compose.override.yml" ;;
    --music)    COMPOSE_FILES="$COMPOSE_FILES -f modules/music/docker-compose.override.yml" ;;
    --finance)  COMPOSE_FILES="$COMPOSE_FILES -f modules/finance/docker-compose.override.yml" ;;
    --trader)   COMPOSE_FILES="$COMPOSE_FILES -f modules/trader/docker-compose.override.yml" ;;
    --pathfinder) COMPOSE_FILES="$COMPOSE_FILES -f modules/pathfinder/docker-compose.override.yml" ;;
    --coder)    COMPOSE_FILES="$COMPOSE_FILES -f modules/coder/docker-compose.override.yml" ;;
    *)          ARGS+=("$arg") ;;
  esac
done

echo "Starting Sentinel with: $COMPOSE_FILES"
docker compose $COMPOSE_FILES "${ARGS[@]}"
