# Symphony Swift (this repo)

Swift port of the [Symphony service spec](SPEC.md). Active branch:
`swift-implementation`. Image registry: `ghcr.io/will2612/symphony`.

## What this repo is right now

**M0 — Swift runtime shell — is complete.** The daemon itself is not
implemented yet; business logic lands in M1–M4 (see `Plan.md` §2). Stay
inside the current milestone; do not jump ahead.

`Plan.md` is the source of truth for milestone scope, decisions, and the
verification checklist. `Plan.md` §4 lists open decisions that must be
resolved before the next milestone: template engine (M1), worker protocol
version pinning (M2), GitHub Projects v2 state-name normalisation (M1),
and the WORKFLOW.md watcher mechanism (M3). Read §4 before starting a new
milestone.

## Layout

- `Package.swift` — `swift-tools-version: 6.3`, single
  `executableTarget("Symphony")`, **0 third-party deps** in M0.
- `Sources/Symphony/main.swift` — CLI entry. Recognises only
  `--version` / `-v` / `--help` / `-h`. Missing or unknown arg → exit
  **64** (`EX_USAGE`) with a stderr hint. The literal `64` is kept on
  purpose (Plan §6: M0 prefers no abstractions). Version string is a
  hardcoded constant, not `git describe`.
- `deploy/Dockerfile` — multi-stage; **uses `$TARGETPLATFORM`** (Swift
  has no native cross-compile; arm64 goes through QEMU); copies the
  binary **out of the build cache mount** — `cp /build/.build/release/symphony
  /symphony` is load-bearing because the BuildKit cache mount is not
  visible to later `COPY`; non-root `symphony` user (UID 10001); final
  image is `swift:6.3.2-noble-slim`.
- `deploy/docker-compose.yml` — `context: ..` is **required**: the file
  lives in `deploy/`, so `.` resolves to `deploy/`. Default `command:
  ["--version"]` exits immediately; M0 only verifies the pipeline.
- `deploy/.env.example` — commented-out env vars grouped by milestone.
  M0 reads none of them.
- `.github/workflows/release.yml` — only workflow. Triggers on `push` to
  `swift-implementation`, `push` to `v*` tags, and `workflow_dispatch`.
  Single job, QEMU multi-arch (`linux/amd64,linux/arm64`). All `uses:`
  are **SHA-pinned** with a version comment. Tags emitted: `:dev`
  (always), `:vX.Y.Z` from semver tags (preserves the `v` prefix),
  `:sha-<short>`. `provenance: false` and `sbom: false` prevent OCI
  image-index ghost attestation manifests. `workflow_dispatch` builds
  but does not push.
- `.dockerignore` — also excludes `AGENTS.md`, `README.md`, `SPEC.md`,
  `Plan.md` from the build context (saves bytes; do not depend on
  them at runtime).
- `.gitignore` — ignores `.env*`, `repos/`, `logs/`, `workspaces/`
  (runtime scratch space; bind-mounted in compose).

## Toolchain

- **There is no Swift on the host.** Build inside Docker. CI uses
  `swift:6.3.2-noble`. Keep `SWIFT_VERSION` in the Dockerfile and
  `swift-tools-version` in `Package.swift` aligned.
- No `Makefile` / `justfile` (Plan §4, decided). The three commands are
  `swift build`, `docker build`, `docker compose`.
- No SwiftLint, no swift-format, no pre-commit hooks in M0 (Plan §4,
  decided).

## Build, test, verify

Run from the repo root unless noted.

```bash
# Build a release binary (Linux; matches the runtime image)
docker buildx build --platform linux/amd64 -f deploy/Dockerfile .

# Verify the CLI inside compose (exits 0 immediately)
docker compose -f deploy/docker-compose.yml up

# Local Swift build (only if you have Swift 6.3+ installed)
swift build -c release
./.build/release/symphony --version   # → symphony 0.0.0-dev (swift 6.3.2), exit 0
./.build/release/symphony             # → exit 64, "error: missing required option…"
```

There are **no tests in M0** — `swift test` is a no-op until M1+ adds
a test target. `Package.swift` declares no `.testTarget`.

To exercise the full multi-arch + GHCR path, push to
`swift-implementation` (CI does the rest). Pull the result with
`docker pull ghcr.io/will2612/symphony:dev`.

## Conventions that differ from defaults

- **Tracker is GitHub Projects v2** (not Linear).
- **Worker protocol is replaceable.** `AgentClient` is the abstract
  protocol. Default worker is opencode/ACP; codex v2 JSON-RPC is
  optional. Both reach the daemon over TCP via a `worker-bridge/`
  (Node.js stdio↔TCP bridge) on the worker side (M2+). Do not bake a
  single protocol into the Swift code.
- **`Package.resolved` is committed** (matches the Elixir `mix.lock`
  policy). M0 has no lockfile file yet because there are no
  dependencies; the rule activates in M1+.
- **Commit messages use conventional `type(scope):`** — see
  `.codex/skills/commit/SKILL.md`. Examples from M0 history:
  `feat(m0): …`, `fix(ci): …`, `chore(m0): …`, `docs(m0): …`. Use the
  milestone as the scope.
- **AGENTS.md / README.md / Plan.md / SPEC.md are excluded from the
  Docker build context** (`.dockerignore`). Do not depend on them
  being present at runtime.

## Skills inventory

`.codex/skills/` (inherited from the Elixir port, adapted where needed):

- `commit` — kept verbatim. Pure git + Codex Co-authored-by workflow.
- `pull` — kept verbatim. Pure merge/conflict workflow.
- `push` — adapted. Validation gate is now `docker buildx build …`
  (was `make -C elixir all`); PR body linter step removed (no
  `pr-description-lint` workflow exists in this repo).
- `land` — adapted. Pnpm lockfile failure paragraph removed; core PR
  landing / Codex review handling is language-agnostic and stays.
- `debug` — kept verbatim **but deferred**. The structure (correlation
  keys, triage flow, class-of-failure taxonomy) is good, but every
  concrete grep pattern and log string is Elixir-shaped and the Swift
  daemon has no `StructuredLogger` yet. Re-purpose in M3.

`linear` was dropped — Linear is not the tracker for this port.

## Boundaries

- **M0 is done; do not start M1+ code without a written plan.** M1 =
  `Configuration` + `Tracker` (GitHub Projects v2). M2 = worker
  protocol + bridges. M3 = orchestrator (polling, concurrency, retry,
  reconciliation, workspace safety). M4 = production polish. See
  `Plan.md` §5 for the per-milestone scope.
- **Stay 0 third-party Swift deps in M0.** Adding a `Package.swift`
  dependency (Yams, swift-argument-parser, swift-log, …) is an M1+
  change.
- **Do not introduce tooling that Plan §4 explicitly defers**
  (SwiftLint, swift-format, Makefile, justfile).
