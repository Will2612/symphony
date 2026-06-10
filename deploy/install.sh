#!/usr/bin/env bash
# One-shot installer for Symphony (Docker-based) on Ubuntu / Pi 5.
# Run as root: sudo /opt/symphony/deploy/install.sh
#
# Idempotent. Skips steps that are already done.
# Prerequisite: Docker Engine 24+ and the docker compose v2 plugin.
# This script does NOT install Docker. See deploy/README.md §Prerequisites.
# Does NOT start the orchestrator service — you do that after configuring.
set -euo pipefail

# ---------------------------------------------------------------------------
# Step 0/5: Resolve paths and defaults (no I/O, cannot fail)
# ---------------------------------------------------------------------------
# All path defaults are computed up front so every later step can log its
# target paths in advance.
REPO_DIR="${REPO_DIR:-~/.symphony}"
BRANCH="${BRANCH:-python_implementation_trial}"
if [ -d "$REPO_DIR/.git" ]; then
  REPO_URL="${REPO_URL:-$(git -C "$REPO_DIR" remote get-url origin)}"
else
  REPO_URL="${REPO_URL:-https://github.com/Will2612/symphony.git}"
fi
PYTHON_DIR="${PYTHON_DIR:-${REPO_DIR}/python}"
ETC_DIR="${ETC_DIR:-~/.config/symphony}"
DEPLOY_DIR="${REPO_DIR}/deploy"

log() { printf '[install] %s\n' "$*"; sync; }
err() { log "ERROR: $*" >&2; }
die() { err "$*"; exit 1; }

# ---------------------------------------------------------------------------
# Step 1/5: Prerequisite checks (MUST pass before any host change)
# ---------------------------------------------------------------------------
# These checks are read-only and run before we touch the filesystem,
# systemd, or git. If any of them fail, the script aborts cleanly.
log "step 1/5: checking prerequisites"

# 1b. Docker Engine is required to run the orchestrator container.
log "  checking docker on PATH"
command -v docker >/dev/null 2>&1 \
  || die "docker not on PATH. Install Docker first: see deploy/README.md §Prerequisites"
log "    OK ($(command -v docker))"

# 1c. docker compose v2 plugin is used by the systemd units we install.
log "  checking docker compose v2 plugin"
docker compose version >/dev/null 2>&1 \
  || die "docker compose v2 plugin not found. Install docker-compose-plugin"
log "    OK"

# 1d. opencode binary is bind-mounted into the container at runtime.
# sudo's secure_path excludes ~/.opencode/bin/, hence the conventional-path fallback.
log "  checking opencode binary"
_user_home="$([ -n "${SUDO_USER:-}" ] && getent passwd "$SUDO_USER" | cut -d: -f6 || true)"
_user_home="${_user_home:-$HOME}"
_default_oc="$_user_home/.opencode/bin/opencode"
_oc_path=""
if _oc_path="$(command -v opencode 2>/dev/null)" && [ -x "$_oc_path" ]; then
  log "    OK (on PATH: $_oc_path)"
elif [ -x "$_default_oc" ]; then
  _oc_path="$_default_oc"
  log "    OK (default: $_oc_path)"
elif [ -f "$DEPLOY_DIR/.env" ]; then
  _custom_oc="$(. "$DEPLOY_DIR/.env" && printf '%s' "${OPENCODE_BIND_SOURCE:-}")"
  if [ -n "$_custom_oc" ] && [ -x "$_custom_oc" ]; then
    _oc_path="$_custom_oc"
    log "    OK (custom from $DEPLOY_DIR/.env: $_oc_path)"
  else
    die "opencode not found. Not on PATH, not at default ($_default_oc), and OPENCODE_BIND_SOURCE in $DEPLOY_DIR/.env points to '$_custom_oc' which is not executable. Install opencode or fix $DEPLOY_DIR/.env."
  fi
else
  die "opencode not found on PATH and not at default location: $_default_oc. Install opencode first (see deploy/README.md §Prerequisites), or set OPENCODE_BIND_SOURCE in $DEPLOY_DIR/.env after first install."
fi

log "step 1/5: prerequisites OK"

# ---------------------------------------------------------------------------
# Step 2/5: Clone or update the repository (first host change)
# ---------------------------------------------------------------------------
log "step 2/5: cloning/updating repository at $REPO_DIR (branch: $BRANCH)"

if [ ! -d "$REPO_DIR/.git" ]; then
  log "  no existing clone found; running: git clone --branch $BRANCH $REPO_URL $REPO_DIR"
  git clone --branch "$BRANCH" "$REPO_URL" "$REPO_DIR"
  log "  cloned OK -> $REPO_DIR"
else
  log "  existing clone found at $REPO_DIR; will verify branch"
fi

cd "$REPO_DIR"
log "  verifying working tree state"
if ! git symbolic-ref --quiet --short HEAD >/dev/null; then
  die "$REPO_DIR is in detached HEAD; please 'git checkout $BRANCH' manually."
fi
_current_branch="$(git symbolic-ref --quiet --short HEAD)"
if [ "$_current_branch" != "$BRANCH" ]; then
  log "  on branch '$_current_branch'; switching to '$BRANCH'"
  git checkout --quiet "$BRANCH"
  log "  switched OK"
else
  log "  already on branch '$BRANCH'"
fi
log "step 2/5: repository ready at $REPO_DIR"

# ---------------------------------------------------------------------------
# Step 3/5: Seed deploy/.env
# ---------------------------------------------------------------------------
# deploy/.env.example lives in the repo (cloned in step 2), so this step
# must run after the clone. The .env file holds OPENCODE_BIND_SOURCE
# (the host path to the opencode binary, bind-mounted into the container
# at runtime). The path comes from step 1d's resolution; we just record
# it here if not already set.
log "step 3/5: seeding deploy/.env"

DEPLOY_ENV="$DEPLOY_DIR/.env"
if [ ! -f "$DEPLOY_ENV" ]; then
  if [ ! -f "$DEPLOY_DIR/.env.example" ]; then
    die "missing $DEPLOY_DIR/.env.example; cannot seed $DEPLOY_ENV (repo at $REPO_DIR is incomplete?)"
  fi
  log "  seeding $DEPLOY_ENV from .env.example (m 0640)"
  install -m 0640 -o root -g root \
    "$DEPLOY_DIR/.env.example" "$DEPLOY_ENV"
  log "  seeded OK"
else
  log "  $DEPLOY_ENV already exists; preserving"
fi
if ! grep -q '^OPENCODE_BIND_SOURCE=' "$DEPLOY_ENV" 2>/dev/null; then
  printf '\nOPENCODE_BIND_SOURCE=%s\n' "${_oc_path/#\~/$HOME}" >> "$DEPLOY_ENV"
  log "  wrote OPENCODE_BIND_SOURCE=$_oc_path to $DEPLOY_ENV (from step 1d resolution)"
else
  log "  OPENCODE_BIND_SOURCE already set in $DEPLOY_ENV; preserving"
fi
log "step 3/5: deploy/.env ready"

# ---------------------------------------------------------------------------
# Step 4/5: Seed ~/.config/symphony (symphony.env, WORKFLOW.md)
# ---------------------------------------------------------------------------
log "step 4/5: seeding $ETC_DIR"

log "  ensuring $ETC_DIR exists (m 0750)"
install -d -m 0750 -o root -g root "$ETC_DIR"

if [ ! -f "$ETC_DIR/symphony.env" ]; then
  log "  seeding $ETC_DIR/symphony.env from $DEPLOY_DIR/symphony-py.env.example (m 0640)"
  install -m 0640 -o root -g root \
    "$DEPLOY_DIR/symphony-py.env.example" "$ETC_DIR/symphony.env"
  log "  seeded OK"
else
  log "  $ETC_DIR/symphony.env already exists; preserving"
fi

if [ ! -f "$ETC_DIR/WORKFLOW.md" ]; then
  if [ -f "$PYTHON_DIR/examples/WORKFLOW.github-opencode.md" ]; then
    log "  seeding $ETC_DIR/WORKFLOW.md from python/examples/ (m 0640)"
    install -m 0640 -o root -g root \
      "$PYTHON_DIR/examples/WORKFLOW.github-opencode.md" "$ETC_DIR/WORKFLOW.md"
    log "  seeded OK"
  else
    log "  WARN: no WORKFLOW.md example found at $PYTHON_DIR/examples/WORKFLOW.github-opencode.md; create $ETC_DIR/WORKFLOW.md by hand"
  fi
else
  log "  $ETC_DIR/WORKFLOW.md already exists; preserving"
fi
log "step 4/5: $ETC_DIR ready"

# ---------------------------------------------------------------------------
# Step 5/5: Install systemd units to /etc/systemd/system/
# ---------------------------------------------------------------------------
log "step 5/5: installing systemd units to /etc/systemd/system/"
# Intentional v1.1+ behavior: unconditionally overwrite. Re-runs pick up
# any service-file changes in the repo. See deploy/README.md "v1.1+" note.

# 5a. Detect any pre-existing service so we can warn the user before
# overwriting. We don't fail — overwriting is intentional — but the user
# should know whether a running service is about to be replaced.
if [ -f /etc/systemd/system/symphony-py.service ]; then
  log "  found existing /etc/systemd/system/symphony-py.service (will be overwritten)"
  if systemctl is-active --quiet symphony-py.service 2>/dev/null; then
    log "  WARN: symphony-py.service is currently ACTIVE — running container is unaffected, but the next start uses the new unit"
  fi
  if systemctl is-enabled --quiet symphony-py.service 2>/dev/null; then
    log "  INFO: symphony-py.service is currently ENABLED — it stays enabled across re-installs"
  fi
else
  log "  no existing service at /etc/systemd/system/symphony-py.service (fresh install)"
fi

log "  installing symphony-py.service (m 0644)"
install -m 0644 "$DEPLOY_DIR/symphony-py.service" \
                 /etc/systemd/system/symphony-py.service

log "  installing symphony-py-pull.service (m 0644)"
install -m 0644 "$DEPLOY_DIR/symphony-py-pull.service" \
                 /etc/systemd/system/symphony-py-pull.service

log "  installing symphony-py.timer (m 0644)"
install -m 0644 "$DEPLOY_DIR/symphony-py.timer" \
                 /etc/systemd/system/symphony-py.timer

log "  creating lock directory"
install -d -m 0755 -o root -g root ~/.symphony/.lock

log "  reloading systemd daemon"
if ! systemctl daemon-reload; then
  die "systemctl daemon-reload failed; is systemd running?"
fi
log "  daemon-reload OK"
log "step 5/5: systemd units installed"

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
