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
- 4 GB RAM minimum, 8 GB recommended
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
  prerequisite** — `install.sh` does NOT install it. The host path is configurable
  via `OPENCODE_BIND_SOURCE` in `deploy/.env`; default is `~/.opencode/bin/opencode`.
  If you have opencode elsewhere, edit `OPENCODE_BIND_SOURCE` in `deploy/.env` after
  running `install.sh`.
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

## Install

Log in as root (or `sudo -i`):

```bash
curl -fsSL https://raw.githubusercontent.com/Will2612/symphony/python_implementation_trial/deploy/install.sh \
  | sudo bash -s -- --repo https://github.com/Will2612/symphony
```

This script:
1. Clones the repo to `/opt/symphony` (reuses existing clone if present)
2. Checks out `python_implementation_trial`
3. Seeds `/etc/symphony/symphony.env` from the example
4. Seeds `/etc/symphony/WORKFLOW.md` from `python/examples/`
5. Installs the three systemd units (`symphony-py.service`, `symphony-py-pull.service`, `symphony-py.timer`)
6. Seeds `deploy/.env` and records `OPENCODE_BIND_SOURCE` (the host path to your opencode install). The script does NOT install opencode; opencode is a prerequisite. See `deploy/README.md §Prerequisites`.

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

- **No `arm64` image for Apple Silicon Macs** — the image only builds for
  `linux/arm64`. Intel/AMD Pi hardware is also fine.
- **No built-in HTTPS** — the orchestrator listens on plain HTTP. Put it behind
  a reverse proxy (Caddy, nginx) if you need TLS.
- **Single-host only** — no clustering or multi-node orchestration in v1.
- **Workspace on named volume** — workspaces are stored in Docker's named
  volume, not on the host filesystem. Bind-mount a host directory into the
  container if you need host access to workspace artifacts.

## Pi 5 Environment Checklist

Run these on the Pi before installing. Fix any missing items before proceeding.

### Hardware & OS
- [ ] `uname -m` → `aarch64` (Pi 5 is arm64; image is linux/arm64 only)
- [ ] `df -h /` — ≥ 32 GB available on root or a dedicated SSD/SD
- [ ] `free -h` — ≥ 4 GB RAM (8 GB recommended)

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
