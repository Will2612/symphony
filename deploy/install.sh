#!/usr/bin/env bash
# One-shot installer for Symphony (Docker-based) on Ubuntu / Pi 5.
# Run as root: sudo /opt/symphony/deploy/install.sh
#
# Idempotent. Skips steps that are already done.
# Prerequisite: Docker Engine 24+ and the docker compose v2 plugin.
# This script does NOT install Docker. See deploy/README.md §Prerequisites.
# Does NOT start the orchestrator service — you do that after configuring.
set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/symphony}"
BRANCH="${BRANCH:-python_implementation_trial}"
if [ -d "$REPO_DIR/.git" ]; then
  REPO_URL="${REPO_URL:-$(git -C "$REPO_DIR" remote get-url origin)}"
else
  REPO_URL="${REPO_URL:-https://github.com/openai/symphony.git}"
fi
PYTHON_DIR="${PYTHON_DIR:-${REPO_DIR}/python}"
ETC_DIR="${ETC_DIR:-/etc/symphony}"
DEPLOY_DIR="${REPO_DIR}/deploy"

log() { printf '[install] %s\n' "$*"; }
err() { log "ERROR: $*" >&2; }
die() { err "$*"; exit 1; }

[ "$(id -u)" -eq 0 ] || die "must run as root (use sudo)"

command -v docker >/dev/null 2>&1 \
  || die "docker not on PATH. Install Docker first: see deploy/README.md §Prerequisites"
docker compose version >/dev/null 2>&1 \
  || die "docker compose v2 plugin not found. Install docker-compose-plugin"

if [ ! -d "$REPO_DIR/.git" ]; then
  log "cloning $REPO_URL -> $REPO_DIR (branch: $BRANCH)"
  git clone --branch "$BRANCH" "$REPO_URL" "$REPO_DIR"
fi

cd "$REPO_DIR"
if ! git symbolic-ref --quiet --short HEAD >/dev/null; then
  die "$REPO_DIR is in detached HEAD; please 'git checkout $BRANCH' manually."
fi
if [ "$(git symbolic-ref --quiet --short HEAD)" != "$BRANCH" ]; then
  log "switching working tree to branch $BRANCH"
  git checkout --quiet "$BRANCH"
fi

install -d -m 0750 -o root -g root "$ETC_DIR"
if [ ! -f "$ETC_DIR/symphony.env" ]; then
  log "seeding $ETC_DIR/symphony.env from template (you must edit it)"
  install -m 0640 -o root -g root \
    "$DEPLOY_DIR/symphony-py.env.example" "$ETC_DIR/symphony.env"
fi
if [ ! -f "$ETC_DIR/WORKFLOW.md" ]; then
  if [ -f "$PYTHON_DIR/examples/WORKFLOW.github-opencode.md" ]; then
    log "seeding $ETC_DIR/WORKFLOW.md from python/examples/"
    install -m 0640 -o root -g root \
      "$PYTHON_DIR/examples/WORKFLOW.github-opencode.md" "$ETC_DIR/WORKFLOW.md"
  else
    log "WARN: no WORKFLOW.md example found; create $ETC_DIR/WORKFLOW.md by hand"
  fi
fi

log "installing systemd units to /etc/systemd/system/"
install -m 0644 "$DEPLOY_DIR/symphony-py.service" \
                 /etc/systemd/system/symphony-py.service
install -m 0644 "$DEPLOY_DIR/symphony-py-pull.service" \
                 /etc/systemd/system/symphony-py-pull.service
install -m 0644 "$DEPLOY_DIR/symphony-py.timer" \
                 /etc/systemd/system/symphony-py.timer
systemctl daemon-reload

cat <<EOF

Installed. Orchestrator service NOT started yet (configure first).

  Repo:        $REPO_DIR
  Compose:     $DEPLOY_DIR/docker-compose.yml
  Env file:    $ETC_DIR/symphony.env       chmod 640
  Workflow:    $ETC_DIR/WORKFLOW.md        chmod 640
  Pull timer:  NOT enabled (no surprises during manual testing)
  Service:     NOT enabled

Next steps:
  1. Edit  $ETC_DIR/symphony.env   (set GITHUB_TOKEN, etc.)
  2. Edit  $ETC_DIR/WORKFLOW.md    (point tracker.project_slug at Will2612/symphony, etc.)
  3. Pre-pull the image:
       cd $REPO_DIR && docker compose pull
  4. Foreground test (Ctrl-C to stop):
       cd $REPO_DIR && docker compose up
  5. Once satisfied, start as a background service:
       sudo systemctl enable --now symphony-py.service
  6. Optional: enable the 1-min pull timer (auto-update on GHCR push):
       sudo systemctl enable --now symphony-py.timer
  7. Watch:
       sudo journalctl -u symphony-py.service -f
       sudo journalctl -u symphony-py-pull.service -f
       docker compose -f $DEPLOY_DIR/docker-compose.yml logs -f
EOF
