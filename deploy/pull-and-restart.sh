#!/usr/bin/env bash
# Pull the latest Symphony image from GHCR and recreate the running
# container. Idempotent: no-op when nothing changed.
#
# Triggered by deploy/symphony-py.timer. Runs as root.
# Safe to run by hand: sudo ~/.symphony/deploy/pull-and-restart.sh
# Override the install location with REPO_DIR=/path/to/repo.
#
# $HOME note: this script is invoked by the systemd timer as root, in
# which case $HOME=/root and the default REPO_DIR resolves to
# /root/.symphony — matching where install.sh (also run as root via
# sudo) clones the repo. If you ever change the timer to run as a
# non-root user, also pass REPO_DIR explicitly to point at the user's
# install.
set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/.symphony}"
LOCK_FILE="${REPO_DIR}/.lock/symphony-pull-lock"
mkdir -p "$(dirname "$LOCK_FILE")"

COMPOSE_DIR="${COMPOSE_DIR:-$REPO_DIR}"
SERVICE_NAME="${SERVICE_NAME:-symphony}"

log() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; sync; }
err() { log "ERROR: $*" >&2; }

# Acquire the lock and run the entire pull+recreate body inside the
# subshell so FD 200 stays open (and the lock held) for the duration.
# Without this, flock's subshell would exit immediately after acquiring
# the lock, releasing it before any docker work runs — defeating the
# protection against the 1-min timer firing while a slow pull is in
# progress.
(
  flock -n 200 || { log "another pull in progress; exiting"; exit 0; }

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
) 200>"$LOCK_FILE"
