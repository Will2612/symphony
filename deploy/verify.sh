#!/usr/bin/env bash
# verify.sh — verify and smoke-test Symphony deployment artifacts.
#
# Usage:
#   ./verify.sh verify   — syntax-check shell scripts + docker compose config
#   ./verify.sh smoke    — run the verify container and check boot log
#
# verify mode: exits 0 on success, 1 on failure.
# smoke mode:  exits 0 if the orchestrator boot log is visible, 1 otherwise.
set -euo pipefail

SCRIPT_DIR="$(dirname "$0")"
COMPOSE_BASE="$SCRIPT_DIR/docker-compose.yml"
OVERRIDE_FILE="$SCRIPT_DIR/verify.override.yml"
WORKFLOW_FILE="$SCRIPT_DIR/verify.workflow.md"
ENV_FILE="$SCRIPT_DIR/.env"

# Defaults for the variables referenced by docker-compose.yml. The Makefile
# exports both; this fallback lets verify.sh also run by hand.
: "${CONFIG_DIR:=$(getent passwd "$(id -u)" | cut -d: -f6)/.config/symphony}"
: "${OPENCODE_BIND_SOURCE:=$(getent passwd "$(id -u)" | cut -d: -f6)/.opencode/bin/opencode}"
export CONFIG_DIR
export OPENCODE_BIND_SOURCE

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log()   { printf '[verify] %s\n' "$*"; }
err()   { log "ERROR: $*" >&2; }
die()   { err "$*"; exit 1; }

usage() {
  cat <<EOF
Usage: $(basename "$0") MODE

Modes:
  verify    — shell syntax check + docker compose config validation
  smoke     — run the verify container and check for boot log

Exit status: 0 = pass, 1 = fail
EOF
  exit 1
}

# ---------------------------------------------------------------------------
# verify mode
# ---------------------------------------------------------------------------
do_verify() {
  local rc=0

  # 1. bash -n on every *.sh in deploy/
  log "checking shell scripts with bash -n"
  while IFS= read -r -d '' f; do
    if ! bash -n "$f"; then
      err "bash -n failed: $f"
      rc=1
    else
      log "  OK: ${f##*/}"
    fi
  done < <(find "$SCRIPT_DIR" -maxdepth 1 -name '*.sh' -type f -print0)

  # 2. docker compose config validation
  log "checking docker compose config"
  if ! docker compose version >/dev/null 2>&1; then
    err "docker compose v2 plugin not found"
    rc=1
  elif ! docker compose -f "$COMPOSE_BASE" config --quiet 2>/dev/null; then
    err "docker compose config failed for $COMPOSE_BASE"
    rc=1
  else
    log "  OK: docker-compose.yml"
  fi

  if [ "$rc" -eq 0 ]; then
    log "verify: ALL PASS"
  fi
  return "$rc"
}

# ---------------------------------------------------------------------------
# smoke mode
# ---------------------------------------------------------------------------
do_smoke() {
  local rc=0

  # Pre-check: required files must exist
  if [ ! -f "$OVERRIDE_FILE" ]; then
    die "missing $OVERRIDE_FILE — create it before running smoke (see T3)"
  fi
  if [ ! -f "$WORKFLOW_FILE" ]; then
    die "missing $WORKFLOW_FILE — create it before running smoke (see T4)"
  fi
  if [ ! -f "$ENV_FILE" ]; then
    die "missing $ENV_FILE — run deploy/install.sh or create deploy/.env first"
  fi
  if ! command -v docker >/dev/null 2>&1; then
    die "docker not on PATH; install Docker first"
  fi
  if ! docker compose version >/dev/null 2>&1; then
    die "docker compose v2 plugin not found"
  fi

  # Create log directory alongside the script
  LOG_DIR="$SCRIPT_DIR/logs"
  mkdir -p "$LOG_DIR"
  LOG_FILE="$LOG_DIR/verify-smoke-$(date -u +%Y%m%d-%H%M%S).log"

  log "smoke test log: $LOG_FILE"
  log "running: docker compose -f $COMPOSE_BASE -f $OVERRIDE_FILE --env-file $ENV_FILE run --rm verify"

  # Run the verify container. Capture both stdout and stderr to the log file.
  # We intentionally do NOT exit on compose failure so we can inspect output.
  set +e
  docker compose \
    -f "$COMPOSE_BASE" \
    -f "$OVERRIDE_FILE" \
    --env-file "$ENV_FILE" \
    run --rm verify \
    >"$LOG_FILE" 2>&1
  local compose_exit=$?
  set -e

  log "container exited with status $compose_exit"

  # Check for orchestrator boot log in the output.
  # The orchestrator prints a boot banner / log line before attempting
  # tracker or runner operations. Even with stub credentials that cause
  # a non-zero exit, the boot log should be present.
  if grep -iq 'orchestrator' "$LOG_FILE" 2>/dev/null; then
    log "  found orchestrator boot log in output"
  else
    err "orchestrator boot log NOT FOUND in output"
    rc=1
  fi

  if [ "$rc" -eq 0 ]; then
    log "smoke: ALL PASS"
  fi
  return "$rc"
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
case "${1:-}" in
  verify)
    do_verify
    ;;
  smoke)
    do_smoke
    ;;
  *)
    usage
    ;;
esac
