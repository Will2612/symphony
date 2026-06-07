# Symphony deploy (Docker, Pi 5)

Single-host deployment for a Raspberry Pi 5 (Ubuntu 24.04+, `linux/arm64`)
that pulls a pre-built image from GHCR and runs the orchestrator in a
Docker container. The image is built in the cloud (GitHub Actions) on
every push to `python_implementation_trial`; the Pi just pulls and runs.

```
              +----------------------+      push to python_implementation_trial
              |  GitHub Actions      |-----------------------------+
              |  build-image.yml     |                             |
              +----------------------+                             v
                                                +-----------------------------+
                                                |  ghcr.io/Will2612/symphony  |
                                                |  :python_implementation_   |
                                                |  trial (linux/arm64)       |
                                                +--------------+--------------+
                                                               |
                          +--------------------------+           | docker pull
                          | systemd timer (1 min)    |           | (systemd pull svc or manual)
                          | symphony-py.timer        |---------->+
                          +--------------------------+           |
                                                               v
                                                +-----------------------------+
                                                |  docker compose up          |
                                                |  /opt/symphony              |
                                                |  (named volume: workspaces)|
                                                +--------------+--------------+
                                                               |
                                                               v
                                                +-----------------------------+
                                                |  Symphony container         |
                                                |  symphony-py.service        |
                                                +--------------+--------------+
```

## Prerequisites

### Hardware & OS

- Raspberry Pi 5 (or any `linux/arm64` host)
- Ubuntu 24.04 LTS Server or Raspberry Pi OS (64-bit)
- 16 GB RAM recommended (8 GB minimum)
- 32 GB SD card or SSD

### Software

- **Docker Engine 24+** — [Install on Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
- **docker compose v2 plugin** — ships with Docker Desktop; on server Ubuntu:
  ```bash
  apt install docker-compose-plugin
  ```
- **opencode (runner binary)** — the agent subprocess that the orchestrator spawns.
  Installed on the **host** and bind-mounted read-only into the container at
  `/usr/local/bin/opencode` (see `deploy/docker-compose.yml`). opencode is a **strict
  prerequisite** — `install.sh` does NOT install it. The install script discovers
  the host path in this order: (1) `command -v opencode` (opencode on `$PATH`),
  (2) the conventional `~/.opencode/bin/opencode`, (3) `OPENCODE_BIND_SOURCE` in
  `deploy/.env` (set this manually if opencode lives elsewhere).
  arm64 glibc binary is required (Pi 5 / Ubuntu 24.04 are glibc).

Verify:
```bash
docker compose version
# Docker Compose version v2.24+
```
```bash
grep OPENCODE_BIND_SOURCE /opt/symphony/deploy/.env
# OPENCODE_BIND_SOURCE=~/.opencode/bin/opencode
```

> **Not** using podman, containerd, or `docker-compose` (v1 standalone).
> The systemd units invoke `docker compose` (the v2 plugin).

### Multi-arch support

Starting with the current build pipeline, the Symphony image is built for **both**
`linux/arm64` and `linux/amd64` platforms. This means:

- **Raspberry Pi 5 / arm64 hosts** — pulls the `linux/arm64` variant as before.
- **Intel/AMD hosts** — can now pull the `linux/amd64` variant for local testing
  or non-Pi deployment.

The multi-arch build is configured in `.github/workflows/build-image.yml` via the
`platforms` field (`linux/arm64,linux/amd64`). Docker's manifest list ensures that
each host architecture automatically gets the correct variant on `docker pull`.

```bash
# Verify the image supports your architecture:
docker buildx imagetools inspect ghcr.io/will2612/symphony:python_implementation_trial
```

## Install

Log in as root (or `sudo -i`):

```bash
curl -fsSL https://raw.githubusercontent.com/Will2612/symphony/python_implementation_trial/deploy/install.sh \
  | sudo bash -s -- --repo https://github.com/Will2612/symphony
```

This script runs in 5 numbered steps, all logged to stdout (each step starts with a `step N/5: …` banner):

1. **Prerequisites** (read-only, fail-fast before any host change): running as root, `docker` on PATH, the `docker compose` v2 plugin, and the `opencode` binary. If any of these fail, the script aborts before touching the host.
2. **Clone or update the repository** at `/opt/symphony` (reuses an existing clone if present; switches the working tree to the target branch).
3. **Seed `deploy/.env`** from `deploy/.env.example`, recording `OPENCODE_BIND_SOURCE` if unset (auto-detected from the invoking user's `~/.opencode/bin/opencode`; the user can override by editing `deploy/.env`).
4. **Seed `/etc/symphony`** with `symphony.env` (from `deploy/symphony-py.env.example`) and `WORKFLOW.md` (from `python/examples/WORKFLOW.github-opencode.md`).
5. **Install the three systemd units** (`symphony-py.service`, `symphony-py-pull.service`, `symphony-py.timer`) to `/etc/systemd/system/`. If a prior service is already installed, the script logs a heads-up before overwriting; if it is active or enabled, it logs a `WARN` or `INFO` line. Finally runs `systemctl daemon-reload`.

It does **not** start or enable any services.

## Configure

Edit two files on the Pi:

### 1. `/etc/symphony/symphony.env`

```bash
# GitHub fine-grained PAT. Needs repo read+write.
# https://github.com/settings/personal-access-tokens
GITHUB_TOKEN=ghp_...

# OpenCode API key (from your OpenCode ACP account)
OPENCODE_API_KEY=sk_...
```

`chmod 640 /etc/symphony/symphony.env` after editing.

### 2. `/etc/symphony/WORKFLOW.md`

Point the tracker at your repo. Key fields:

```yaml
tracker:
  type: github
  config:
    project_slug: Will2612/symphony   # your repo
```

`chmod 640 /etc/symphony/WORKFLOW.md`.

## Pre-pull the image

Before running the orchestrator for the first time, pull the image so you can
verify it works without waiting for a pull on first start:

```bash
cd /opt/symphony && docker compose pull
```

## Foreground test (recommended first run)

```bash
cd /opt/symphony && docker compose up
```

You should see the Symphony banner and tracker polling output. Press **Ctrl-C**
to stop. Fix any configuration errors before proceeding.

## Enable systemd

Once satisfied with the foreground run:

```bash
# Start the orchestrator now AND on every boot:
sudo systemctl enable --now symphony-py.service

# Optional: enable the 1-minute pull timer (auto-updates on GHCR push):
sudo systemctl enable --now symphony-py.timer
```

## Observe

```bash
# Orchestrator logs
sudo journalctl -u symphony-py.service -f

# Image-pull service logs
sudo journalctl -u symphony-py-pull.service -f

# Container stdout/stderr
docker compose -f /opt/symphony/deploy/docker-compose.yml logs -f
```

## Update (new image on GHCR)

When `python_implementation_trial` is pushed to, GitHub Actions rebuilds the
image. The timer fires every minute and calls `pull-and-restart.sh`:

```bash
# Or trigger manually:
sudo /opt/symphony/deploy/pull-and-restart.sh
```

## Update branch / image tag

To pin to a specific SHA or a different branch:

```bash
cd /opt/symphony
git fetch origin
git checkout python_implementation_trial   # or a specific SHA
docker compose pull
docker compose up -d --force-recreate
```

## Roll back

To revert to the previously-running image (if the new one is broken):

```bash
docker images | grep symphony
# Find the previous image SHA from docker history or GHCR tags
docker tag ghcr.io/will2612/symphony:python_implementation_trial \
       ghcr.io/will2612/symphony:rollback
# Edit deploy/docker-compose.yml image tag, then:
docker compose up -d --force-recreate
```

## Troubleshooting

### Service stopped auto-restarting

After 3 rapid crashes within 5 minutes, systemd stops auto-restarting the
container. To re-enable:
```bash
sudo systemctl reset-failed symphony-py.service
sudo systemctl start symphony-py.service
```

## Uninstall

```bash
# Stop services
sudo systemctl disable --now symphony-py.service symphony-py-pull.service symphony-py.timer

# Remove systemd units
sudo rm /etc/systemd/system/symphony-py*.service /etc/systemd/system/symphony-py.timer
sudo systemctl daemon-reload

# Remove repo (optional)
rm -rf /opt/symphony

# Remove config (optional)
rm -rf /etc/symphony

# Remove images (optional)
docker rmi $(docker images 'ghcr.io/will2612/symphony*' -q)
```

## Known limitations

- **No built-in HTTPS** — the orchestrator listens on plain HTTP. Put it behind
  a reverse proxy (Caddy, nginx) if you need TLS.
- **Single-host only** — no clustering or multi-node orchestration in v1.
- **Workspace on named volume** — workspaces are stored in Docker's named
  volume, not on the host filesystem. Bind-mount a host directory into the
  container if you need host access to workspace artifacts.

### Verifying deploy changes

Before committing changes to `deploy/`, run the local verification gate:

```bash
make -C deploy all
```

This runs two stages:

1. **`verify`** — syntax-checks all shell scripts with `bash -n` and validates
   the `docker-compose.yml` config with `docker compose config --quiet`.
2. **`smoke`** — starts the orchestrator container once using stub credentials
   (`verify.override.yml`) to confirm it boots and produces log output.

The full `all` target runs both stages. Use `make -C deploy verify` for a quick
syntax-only check, or `make -C deploy smoke` to run only the container boot test.

## Pi 5 Environment Checklist

Run these on the Pi before installing. Fix any missing items before proceeding.

### Hardware & OS
- [ ] `uname -m` → `aarch64` (Pi 5 is arm64; image is linux/arm64 only)
- [ ] `df -h /` — ≥ 64 GB SSD/NVMe (256 GB recommended)
- [ ] `free -h` — ≥ 8 GB RAM (16 GB recommended)

### Core Software (all on host)
- [ ] `docker --version` — Docker Engine 24+ required
- [ ] `docker compose version` — v2 plugin (NOT v1 standalone `docker-compose`)
- [ ] `curl --version` — for the one-line install recipe
- [ ] `git --version` — for `install.sh` cloning and branch updates
- [ ] `bash --version` — ≥ 4 (Ubuntu 24.04 ships 5.1)
- [ ] `systemctl --version` — systemd ≥ 230 (Ubuntu 24.04 has 255)
- [ ] `dpkg -l ca-certificates` — for TLS to GHCR and GitHub

### Host-side Runner (NOT in container)
- [ ] `file ~/.opencode/bin/opencode` — must show `ELF 64-bit LSB executable, ARM aarch64` (glibc, not musl)
- [ ] `test -x ~/.opencode/bin/opencode` — executable bit set
- [ ] Or: `OPENCODE_BIND_SOURCE` set in `deploy/.env` if opencode is installed elsewhere

### Configuration Files
- [ ] `/etc/symphony/symphony.env` exists — `chmod 640`, owned `root:root`
  - [ ] `GITHUB_TOKEN` is set (fine-grained PAT with repo read+write)
  - [ ] `OPENCODE_API_KEY` is set (if your runner needs one)
- [ ] `/etc/symphony/WORKFLOW.md` exists — `chmod 640`
  - [ ] `tracker.project_slug` points to your repo (e.g. `Will2612/symphony`)
  - [ ] `workspace.root` is set and non-empty

### Systemd Units
- [ ] `systemctl status symphony-py-pull.service` — installed and not failed
- [ ] `systemctl status symphony-py.timer` — installed and not failed
- [ ] `systemctl status symphony-py.service` — installed and not failed

### Network (outbound, port 443)
- [ ] `curl -s -o /dev/null -w "%{http_code}" https://github.com` → 200
- [ ] `curl -s -o /dev/null -w "%{http_code}" https://ghcr.io` → 200
- [ ] `curl -s -o /dev/null -w "%{http_code}" https://api.github.com` → 200

### First-run Verification
```bash
# Pull the image (run once before enabling the service)
cd /opt/symphony && docker compose pull

# Foreground test — should see the Symphony banner and tracker polling
cd /opt/symphony && docker compose up

# Enable the service (after confirming the foreground test works)
sudo systemctl enable --now symphony-py.service

# Watch logs
sudo journalctl -u symphony-py.service -f
```

### ⚠️ `symphony-py.service` was rewritten (v1.1+)

The service file shipped before v1.1 called the Python venv directly
(`ExecStart=/opt/symphony/python/.venv/bin/symphony …`) and ran as a
non-root `symphony` user. That version is broken — `install.sh` does not
create that user or the venv.

If you are upgrading from an older install, re-run:
```bash
sudo systemctl disable --now symphony-py.service
sudo install -m 0644 /opt/symphony/deploy/symphony-py.service \
               /etc/systemd/system/symphony-py.service
sudo systemctl daemon-reload
sudo systemctl enable --now symphony-py.service
```

The new unit runs `docker compose up -d` as root and keeps the container
alive across reboots. The `symphony-py.timer` calls `pull-and-restart.sh`
to pull new images before the recreate.
