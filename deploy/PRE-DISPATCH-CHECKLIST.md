# F3 — Pre-Dispatch QA Checklist

**Purpose:** Copy-paste this into a terminal on the dev machine (or Pi where noted)
to verify every gate before shipping. Each step shows the exact command and the
pass/fail signal.

**Legend:**
- **[DEV]** — run on the development machine (not the Pi)
- **[PI]**  — run on the Raspberry Pi after install
- **[BOTH]**— safe to run on either

---

## C1a — docker-compose.yml structure

**Why:** The compose file defines the container contract. Every field must be
present and correctly typed or the container won't start on the Pi.

| # | Command | Pass signal | Fail signal |
|---|---------|-------------|-------------|
| 1 | `docker compose -f deploy/docker-compose.yml --env-file deploy/.env config --quiet` | silent (exit 0) | non-zero + error text |
| 2 | `grep 'memory: 4G' deploy/docker-compose.yml` | `memory: 4G` printed | nothing printed |
| 3 | `grep '@sha256:REPLACEME' deploy/docker-compose.yml` | `@sha256:REPLACEME` printed | **FAIL — SHA not yet set; dispatch blocked** |
| 4 | `grep 'init: true' deploy/docker-compose.yml` | `init: true` printed | nothing printed |
| 5 | `grep 'max-size.*100m' deploy/docker-compose.yml` | `max-size: "100m"` printed | nothing printed |
| 6 | `grep 'cpus:' deploy/docker-compose.yml` | `cpus: "2.0"` (or similar) printed | nothing printed |
| 7 | `grep 'pids:' deploy/docker-compose.yml` | `pids: 512` (or similar) printed | nothing printed |
| 8 | `grep 'nofile' deploy/docker-compose.yml` | `nofile:` block printed | nothing printed |
| 9 | `grep 'container_name' deploy/docker-compose.yml` | `container_name: symphony` printed | nothing printed |

> **Precondition for C1a-1:** The compose file references `/etc/symphony/symphony.env`
> via `env_file`. This file is created by `install.sh` on the Pi. On the dev machine
> this check will fail because that path doesn't exist — run it on the Pi after
> install.sh completes, or create a stub env file as a workaround.
>
> **Note on C1a-3:** The `@sha256:REPLACEME` placeholder is intentional in the repo.
> It gets replaced by the CI workflow (`build-image.yml`) at image-build time
> with the real SHA. If you see `REPLACEME` at dispatch time, the image tag
> has not been updated — do not proceed until the CI has run and produced a
> real SHA (visible in the GHCR UI or in the `docker inspect` output of a
> successfully-pulled image).

---

## C2 — install.sh shell correctness

**Why:** install.sh runs as root on the Pi. A syntax error means the entire
install silently fails — leaving the user with no service and no clue.

| # | Command | Pass signal | Fail signal |
|---|---------|-------------|-------------|
| 1 | `bash -n deploy/install.sh` | silent (exit 0) | syntax error printed |
| 2 | `grep '_oc_path/#\\~/\$HOME' deploy/install.sh` | line printed (the tilde-expansion pattern) | nothing printed |
| 3 | `! grep realpath deploy/install.sh` | exit 0 (grep found nothing, `!` inverts) | exit 1 means `realpath` is used — **FAIL** |

> **Why C2-3:** `realpath` is not available on minimal Pi installations.
> The install script must use shell parameter expansion (`${var/#\~/$HOME}`)
> to expand `~` in paths — see `man bash` §Pathname Expansion.

---

## C3 — pull-and-restart.sh + install.sh lock directory

**Why:** The pull script uses `flock` on `/opt/symphony/.lock/symphony-pull-lock`
to prevent concurrent pulls. If the lock directory isn't created by install.sh,
the pull script will fail every time.

| # | Command | Pass signal | Fail signal |
|---|---------|-------------|-------------|
| 1 | `bash -n deploy/pull-and-restart.sh` | silent (exit 0) | syntax error printed |
| 2 | `grep 'flock' deploy/pull-and-restart.sh` | `flock` printed | nothing printed |
| 3 | `grep '/opt/symphony/.lock' deploy/pull-and-restart.sh` | `/opt/symphony/.lock` printed | nothing printed |
| 4 | `grep 'install -d.*\.lock' deploy/install.sh` | `install -d … /opt/symphony/.lock` line printed | nothing printed |

---

## C4 — python/Dockerfile layer hygiene

**Why:** `--no-cache-dir` keeps image layers small; `--no-compile` avoids
bytecode generation which can cause import errors across Python versions.
`__pycache__` in the image is wasted space and a contamination signal.

| # | Command | Pass signal | Fail signal |
|---|---------|-------------|-------------|
| 1 | `grep 'pip install --no-cache-dir --no-compile' python/Dockerfile` | line printed | nothing printed |
| 2 | `! grep '__pycache__' python/Dockerfile` | exit 0 (grep found nothing) | exit 1 — `__pycache__` found in Dockerfile — **FAIL** |

---

## C5a+C5b — env-scrubbing unit test

**Why:** The runner must never pass credentials to the subprocess environment.
This test asserts the scrub function drops `api_key`, `password`, `secret`,
`token` — and nothing else.

**Run on DEV machine only (requires pytest + the symphony-py package installed):**

```bash
cd /opt/symphony/python && \
python3 -m pytest tests/unit/test_opencode_runner.py::test_scrub_env_drops_credentials_only -v
```

| Pass signal | Fail signal |
|-------------|-------------|
| `PASSED` + test name | `FAILED` + assertion trace |

> If the test is missing or skipped, the scrub logic has regressed —
> **do not dispatch** until the test passes.

---

## C6+C7+C8 — systemd unit verification

**Why:** `systemd-analyze verify` catches unit file errors (missing dependencies,
bad paths, unknown directives) before the Pi tries to start the service.
A broken unit file will cause silent failures or cryptic systemd errors.

**Best run on PI after install.sh (not on dev machine) — the verify command
checks that `ExecStart` paths actually exist, and `/opt/symphony/` only
exists on the Pi after cloning.**

```bash
systemd-analyze verify /opt/symphony/deploy/symphony-py.service
systemd-analyze verify /opt/symphony/deploy/symphony-py-pull.service
systemd-analyze verify /opt/symphony/deploy/symphony-py.timer
```

| # | Unit file | Pass signal | Fail signal |
|---|-----------|-------------|-------------|
| 1 | `symphony-py.service` | silent (exit 0) | non-zero exit code |
| 2 | `symphony-py-pull.service` | silent (exit 0) | non-zero exit code |
| 3 | `symphony-py.timer` | silent (exit 0) | non-zero exit code |

> **Note:** `systemd-analyze verify` may emit warnings (not errors) for
> `ProtectSystem=strict` + `ReadWritePaths` combinations — these are
> intentional and can be ignored. Treat only non-zero exit codes as failures.
> A warning like `Unknown key name 'StartLimitIntervalSec'` is a
> deprecation notice from systemd 255+ and is non-fatal; ignore it.

---

## C9 — deploy/README.md hardware claims

**Why:** The README is the operator's source of truth. It must state the
actual hardware requirements (16 GB RAM, 256 GB storage) and include the
`reset-failed` troubleshooting command. Stating 4 GB RAM would turn away
users who need to provision a Pi correctly.

| # | Command | Pass signal | Fail signal |
|---|---------|-------------|-------------|
| 1 | `! grep '4 GB RAM minimum' /opt/symphony/deploy/README.md` | exit 0 (grep found nothing — old claim removed) | exit 1 — the 4 GB claim is still present — **FAIL** |
| 2 | `grep '16 GB' /opt/symphony/deploy/README.md` | `16 GB` printed | nothing printed |
| 3 | `grep '256 GB' /opt/symphony/deploy/README.md` | `256 GB` printed | nothing printed |
| 4 | `grep 'reset-failed' /opt/symphony/deploy/README.md` | `reset-failed` printed | nothing printed |

---

## C10 — Local deploy gate

**Why:** `make -C deploy all` runs the full two-stage deploy verification:
`syntax-check all shell scripts` + `validate docker-compose config`.

**Run on DEV machine only:**

```bash
make -C /opt/symphony/deploy all
```

| Stage | Pass signal | Fail signal |
|-------|-------------|-------------|
| `verify` | `verify: syntax OK, compose config OK` | non-zero or error text |
| `smoke` | `smoke: container booted` | non-zero or error text |

---

## VERDICT

```
If all C1a–C9 checks pass AND C10 (make -C deploy all) is green:

  ✅ READY TO DISPATCH

If any check fails:

  ❌ BLOCKED — fix the failing check before dispatch.
```

### Run-order recommendation

Run in this order — early failures stop you from wasting time on later checks:

```
1. C2  (shell syntax — fast, no deps)
2. C3  (shell syntax — fast, no deps)
3. C4  (Dockerfile grep — fast, no deps)
4. C9  (README grep — fast, no deps)
5. C1a (compose grep — fast; docker compose config needs Pi or stub env)
6. C6+C7+C8 (systemd-analyze — best on Pi; dev machine ok with path caveats)
7. C5a+C5b (pytest — needs dev env with pytest installed)
8. C10 (make -C deploy all — needs make + docker)
```

### Known caveats from this dev machine

| Check | Caveat |
|-------|--------|
| C1a-1 (`docker compose config`) | Fails on dev because `/etc/symphony/symphony.env` doesn't exist yet. Run on Pi after install.sh. |
| C6 (`symphony-py-pull.service` verify) | Fails on dev because `/opt/symphony/deploy/pull-and-restart.sh` doesn't exist yet. Run on Pi after install.sh. |
| C5a+C5b (pytest) | Requires `pytest` installed + symphony-py dev environment. Not available in this minimal dev environment. |
| C10 (`make -C deploy all`) | Requires `make` in PATH. Not available in this minimal dev environment. |

### Quick summary (copy-paste one-liner for DEV machine)

```bash
# C1a
docker compose -f deploy/docker-compose.yml --env-file deploy/.env config --quiet \
&& grep 'memory: 4G' deploy/docker-compose.yml \
&& grep '@sha256:REPLACEME' deploy/docker-compose.yml \
&& grep 'init: true' deploy/docker-compose.yml \
&& grep 'max-size.*100m' deploy/docker-compose.yml \
&& grep 'cpus:' deploy/docker-compose.yml \
&& grep 'pids:' deploy/docker-compose.yml \
&& grep 'nofile' deploy/docker-compose.yml \
&& grep 'container_name' deploy/docker-compose.yml \
&& echo "C1a: PASS" || echo "C1a: FAIL"

# C2
bash -n deploy/install.sh \
&& grep '_oc_path/#\\~/\$HOME' deploy/install.sh \
&& ! grep realpath deploy/install.sh \
&& echo "C2: PASS" || echo "C2: FAIL"

# C3
bash -n deploy/pull-and-restart.sh \
&& grep 'flock' deploy/pull-and-restart.sh \
&& grep '/opt/symphony/.lock' deploy/pull-and-restart.sh \
&& grep 'install -d.*\.lock' deploy/install.sh \
&& echo "C3: PASS" || echo "C3: FAIL"

# C4
grep 'pip install --no-cache-dir --no-compile' python/Dockerfile \
&& ! grep '__pycache__' python/Dockerfile \
&& echo "C4: PASS" || echo "C4: FAIL"

# C9
! grep '4 GB RAM minimum' deploy/README.md \
&& grep '16 GB' deploy/README.md \
&& grep '256 GB' deploy/README.md \
&& grep 'reset-failed' deploy/README.md \
&& echo "C9: PASS" || echo "C9: FAIL"

# C10
make -C deploy all && echo "C10: PASS" || echo "C10: FAIL"
```

> **C5a+C5b** (pytest) and **C6+C7+C8** (systemd-analyze) must be run separately
> as they have distinct pass/fail output that doesn't compress into a one-liner.