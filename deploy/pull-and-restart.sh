#!/usr/bin/env bash
# Pull the latest Symphony image from GHCR and recreate the running
# container. Idempotent: no-op when nothing changed.
#
# Triggered by deploy/symphony-py.timer. Runs as root.
# Safe to run by hand: sudo /opt/symphony/deploy/pull-and-restart.sh
set -euo pipefail

COMPOSE_DIR="${COMPOSE_DIR:-/opt/symphony}"
SERVICE_NAME="${SERVICE_NAME:-symphony}"

log() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; sync; }
err() { log "ERROR: $*" >&2; }

if ! command -v docker >/dev/null 2>&1; then
  err "docker not on PATH; install Docker first (see deploy/README.md §Prerequisites)"
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  err "docker compose v2 plugin not found; install docker-compose-plugin"
  exit 1
fi

cd "$COMPOSE_DIR"

log "pulling image"
if ! docker compose pull 2>&1 | sed 's/^/  /'; then
  err "docker compose pull failed (see lines above)"
  exit 1
fi

# Compare the running container's image ID to the freshly-pulled one.
LOCAL=$(docker inspect --format='{{.Image}}' "$SERVICE_NAME" 2>/dev/null || echo "")
REMOTE=$(docker image inspect --format='{{.Id}}' \
  $(docker compose config --images 2>/dev/null | head -1) 2>/dev/null || echo "")

if [ -n "$LOCAL" ] && [ "$LOCAL" = "$REMOTE" ]; then
  log "image unchanged; no restart needed"
  exit 0
fi

log "image changed (or container not running); recreating"
docker compose up -d --force-recreate --remove-orphans
log "done"
