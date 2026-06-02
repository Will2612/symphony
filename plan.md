# Symphony — Python Implementation Plan

Status: Draft v1
Source spec: [`SPEC.md`](./SPEC.md) (Symphony service specification, v1, language-agnostic)
Elixir reference: [`elixir/`](./elixir/) (used for architecture parity only; not copied)

## 0. Permissions & Environment Snapshot

Confirmed locally (read-only, before any code is written):

**Already available**
- Python 3.12.3 at `/usr/bin/python3`
- `pytest` 9.0.3, `pytest-asyncio` 1.4.0
- `httpx` 0.28.1, `PyYAML` 6.0.1, `Jinja2` 3.1.2
- `watchfiles` 1.2.0, `watchdog` 6.0.0
- `pydantic` 2.13.4, `pydantic-settings` 2.14.1
- `fastapi` 0.136.3, `starlette` 1.2.1, `uvicorn` 0.48.0
- `opencode` 1.15.13 at `/home/will/.opencode/bin/opencode` (subcommands: `acp`, `serve`, `run`, `session`, `pr`, `github`)

**Likely to need permission to grant in implementation phase**

| Permission | Why |
|---|---|
| `bash`: `pip install` for dev tooling (`ruff`, `mypy`, `pytest-bdd`, `types-*`) | Lint/type/BDD gate |
| `bash`: `pytest`, `pytest --cov`, `mypy`, `ruff` | TDD/BDD loop + conformance gate |
| `bash`: `git init` / `git add` / `git commit` inside `python/` | Subdir-only, will use repo root |
| `bash`: `mkdir -p python/{src/symphony/...}` etc. | Layout scaffolding |
| `bash`: `gh api ...` (opt-in live e2e) | Real GitHub round-trip; gated by `SYMPHONY_RUN_LIVE_E2E=1` |
| `bash`: spawning `opencode acp` in subprocess (opt-in) | Real runner integration; mostly mocked in unit tests |
| Network: `api.github.com` | Live e2e only |
| Filesystem read+write inside new `python/` directory | Implementation |

## 1. Project Layout

```
python/
├── pyproject.toml             # package + ruff + mypy + pytest config
├── Makefile                   # `make all` -> fmt, lint, type, test, coverage
├── README.md                  # how to run/install
├── AGENTS.md                  # repo-local rules (mirrors elixir/AGENTS.md)
├── src/symphony/
│   ├── __init__.py
│   ├── __main__.py            # `python -m symphony …`
│   ├── cli.py                 # CLI: positional WORKFLOW.md, --port, --logs-root, --i-understand-…
│   ├── errors.py              # typed result/error hierarchy
│   ├── ids.py                 # workspace_key sanitization, session_id, normalize_issue_state
│   ├── workflow/
│   │   ├── loader.py          # WORKFLOW.md read + front-matter split + parse
│   │   └── store.py           # hot-reload cache (last-known-good)
│   ├── config/
│   │   ├── schema.py          # pydantic Settings (typed view)
│   │   ├── resolution.py      # $VAR indirection, ~, $VAR-for-path, defaults
│   │   └── validate.py        # dispatch preflight checks
│   ├── tracker/
│   │   ├── base.py            # Tracker Protocol (replaceable)
│   │   ├── memory.py          # in-memory adapter (tests + dev)
│   │   ├── github.py          # GitHubTracker (httpx + REST/GraphQL)
│   │   └── normalize.py       # Section 4.1.1 Issue model
│   ├── workspace/
│   │   ├── path_safety.py     # canonicalize + root containment (Invariant 1-3)
│   │   ├── manager.py         # create/reuse, hooks
│   │   └── hooks.py           # after_create / before_run / after_run / before_remove
│   ├── runner/
│   │   ├── base.py            # Runner Protocol (replaceable)
│   │   ├── opencode.py        # OpenCodeRunner over `opencode acp` (JSON-RPC stdio)
│   │   └── factory.py         # runner_for(config) -> Runner
│   ├── prompt/
│   │   └── builder.py         # Jinja2 strict (StrictUndefined + UndefinedError on unknown filter)
│   ├── orchestrator/
│   │   ├── state.py           # dataclass State (running/claimed/retry/...)
│   │   ├── dispatch.py        # sort, candidate, per-state slots, blocker rule
│   │   ├── reconcile.py       # stall + tracker state refresh
│   │   ├── retry.py           # backoff formula + continuation vs failure
│   │   └── service.py         # main async loop, single-authority mutations
│   └── observability/
│       ├── log.py             # structured key=value logger (issue_id/issue_identifier/session_id)
│       ├── snapshot.py        # section 13.3 payload builder
│       └── server.py          # FastAPI: /, /api/v1/state, /api/v1/<id>, /api/v1/refresh
├── tests/
│   ├── conftest.py            # fakes: FakeClock, FakeFileSystem, MemoryTracker, FakeRunner
│   ├── unit/                  # TDD: per-component, per-spec-section tests
│   │   ├── test_ids.py
│   │   ├── test_errors.py
│   │   ├── test_workflow_loader.py
│   │   ├── test_workflow_store.py
│   │   ├── test_config_resolution.py
│   │   ├── test_config_validate.py
│   │   ├── test_workspace_path_safety.py
│   │   ├── test_workspace_manager.py
│   │   ├── test_workspace_hooks.py
│   │   ├── test_prompt_builder.py
│   │   ├── test_tracker_normalize.py
│   │   ├── test_tracker_github.py
│   │   ├── test_tracker_memory.py
│   │   ├── test_runner_opencode.py
│   │   ├── test_dispatch.py
│   │   ├── test_retry.py
│   │   ├── test_reconcile.py
│   │   ├── test_orchestrator_service.py
│   │   ├── test_snapshot.py
│   │   └── test_observability_server.py
│   ├── features/              # BDD: Gherkin for behavior-level acceptance
│   │   ├── workflow_loading.feature
│   │   ├── config_resolution.feature
│   │   ├── workspace_safety.feature
│   │   ├── tracker_github.feature
│   │   ├── orchestrator_dispatch.feature
│   │   ├── orchestrator_retry.feature
│   │   ├── runner_opencode.feature
│   │   └── observability.feature
│   ├── steps/                 # pytest-bdd step defs (one file per feature)
│   ├── live/                  # opt-in only (env-gated)
│   │   └── test_live_github.py
│   └── fixtures/              # WORKFLOW.md samples, GitHub payload fixtures
└── examples/
    ├── WORKFLOW.github-opencode.md
    └── WORKFLOW.memory-dev.md
```

## 2. Architecture (mirrors SPEC §3.2)

| Layer | Python module | Notes |
|---|---|---|
| Policy | `examples/*.md` + user repo's `WORKFLOW.md` | unchanged |
| Configuration | `symphony.config.*` | pydantic `BaseSettings` typed view; `$VAR`/`~`/relative resolution |
| Coordination | `symphony.orchestrator.*` | single async task with an `asyncio.Lock` around `State` mutations (the "single authority") |
| Execution | `symphony.workspace.*` + `symphony.runner.*` | subprocess via `asyncio.create_subprocess_exec` (or `opencode acp` stdio) |
| Integration | `symphony.tracker.*` | Protocol + adapters (memory, github) |
| Observability | `symphony.observability.*` | structured logs (Python `logging` with a kv Formatter), FastAPI server (optional) |

## 3. Replaceable Tracker Interface (SPEC §11)

```python
# symphony/tracker/base.py
from typing import Protocol, Sequence
from symphony.tracker.normalize import Issue

class Tracker(Protocol):
    name: str

    async def fetch_candidate_issues(self) -> Sequence[Issue]: ...
    async def fetch_issues_by_states(self, state_names: Sequence[str]) -> Sequence[Issue]: ...
    async def fetch_issue_states_by_ids(self, ids: Sequence[str]) -> Sequence[Issue]: ...

    # OPTIONAL writes (Section 11.5 — not used by orchestrator, available for tools)
    async def create_comment(self, issue_id: str, body: str) -> None: ...
    async def update_issue_state(self, issue_id: str, state_name: str) -> None: ...
```

The orchestrator depends on **only** the `Tracker` Protocol. Two adapters ship:

- `MemoryTracker` — in-process dict, used by tests + local dev. Sends `memory_tracker_*` events on an optional `asyncio.Queue` for assertions.
- `GitHubTracker` — uses `httpx.AsyncClient` against `https://api.github.com` (REST for issues/comments, GraphQL for `project_slug` projects v2 when needed). Maps:
  - `tracker.kind: "github"`
  - `tracker.project_slug: "owner/repo"`
  - `tracker.api_key: $GITHUB_TOKEN` (default env `GITHUB_TOKEN`)
  - `tracker.active_states: ["open"]` (default)
  - `tracker.terminal_states: ["closed"]` (default)
  - `tracker.endpoint: "https://api.github.com"` (default; supports GH Enterprise)
  - 30s network timeout, 50/page pagination, exponential retry on 5xx with backoff capped at 5s

A future Linear adapter is a drop-in: the Protocol is small.

## 4. Replaceable Runner Interface (SPEC §10)

```python
# symphony/runner/base.py
class Session: ...  # opaque handle (subprocess or socket)
class TurnResult: ...  # success | failure | timeout | cancelled | input_required

class Runner(Protocol):
    name: str

    async def start_session(self, workspace: Path, codex_cfg: dict) -> Session: ...
    async def run_turn(self, session: Session, prompt: str, on_event: Callable[[Event], Awaitable[None]]) -> TurnResult: ...
    async def stop_session(self, session: Session) -> None: ...
```

`OpenCodeRunner` (the "github+opencode" target):

- Launch: `bash -lc "opencode acp"` inside the workspace, via `asyncio.create_subprocess_exec(..., stdin=PIPE, stdout=PIPE, stderr=PIPE, cwd=workspace)`. 10 MB line buffer.
- Wire: ACP JSON-RPC over stdio (newline-delimited). We discover the actual schema by reading the ACP docs / opencode source — **not** the spec; per SPEC §10 we follow the targeted protocol source of truth.
- Lifecycle: `initialize` → `newSession` (cwd = workspace) → `prompt` for first turn → `prompt` for continuation on the same session id → `cancel` / terminate subprocess at end.
- Event mapping: we extract `session_id = thread_id-turn_id` style identifier from ACP, normalize to the SPEC's event vocabulary (`session_started`, `turn_completed`, `turn_failed`, `turn_cancelled`, `turn_input_required`, `approval_required`, `notification`, `other_message`, `malformed`) and forward to the orchestrator.
- Approval/input policy: starts as a documented "auto-approve + fail-on-input-required" high-trust posture (matches Elixir example). The `symphony.runner.policy.ApprovalPolicy` is a small Strategy so a future operator-gated policy can replace it without touching the runner.
- Timeouts: `codex.turn_timeout_ms`, `codex.read_timeout_ms`, `codex.stall_timeout_ms` honored identically — the names stay because the WORKFLOW.md schema is the SPEC, not the runner.

The interface is identical in shape to what a future `CodexAppServerRunner` would implement, so the SPEC's protocol contract is preserved at the orchestrator level.

## 5. BDD + TDD Methodology (Strictly)

The two layers are not redundant — they test different scales.

### 5.1 TDD (red → green → refactor) — `tests/unit/`
- One test per behavior listed in SPEC §17, grouped by component.
- Per test: written before code. Run pytest, see it fail for the right reason, then implement.
- Use `pytest.mark.parametrize` for boundary conditions (priority sort, backoff exponent, terminal-state matching).
- Fakes (in `conftest.py`): `FakeClock` (advances time without sleeping), `FakeFileSystem` (in-memory FS), `MemoryTracker`, `ScriptedRunner` (records prompt + emits scripted events), `CapturingLogHandler`.

### 5.2 BDD (acceptance) — `tests/features/*.feature` + `tests/steps/*.py`
- One `.feature` per user-visible capability from the spec.
- Each `Scenario` reads like a sentence from §17 (e.g. "Workspace path outside the root is rejected", "Normal worker exit schedules a 1 s continuation retry").
- Steps glue feature to fakes; no network, no real subprocesses, no real filesystem outside `tmp_path`.
- Runs under `pytest-bdd`.

### 5.3 Conformance gate — `make all`
1. `ruff check` + `ruff format --check`
2. `mypy --strict src/symphony`
3. `pytest tests/unit tests/features` (≥ 95 % coverage on `src/symphony/`)
4. (gated) `SYMPHONY_RUN_LIVE_E2E=1 pytest tests/live` — skipped, not silently passed, when env is absent.

## 6. SPEC §17 Conformance Map

| SPEC §17.x behavior | TDD test | BDD scenario |
|---|---|---|
| 17.1 explicit runtime path / cwd default | `test_workflow_loader.py` | `workflow_loading.feature` |
| 17.1 front-matter not a map | `test_workflow_loader.py` | `workflow_loading.feature` |
| 17.1 `tracker.kind` validation | `test_config_validate.py` | `config_resolution.feature` |
| 17.1 `$VAR` indirection for api_key + paths | `test_config_resolution.py` | `config_resolution.feature` |
| 17.1 `~` expansion | `test_config_resolution.py` | `config_resolution.feature` |
| 17.1 `codex.command` preserved | `test_config_resolution.py` | `config_resolution.feature` |
| 17.1 per-state limit normalization | `test_config_resolution.py` | `config_resolution.feature` |
| 17.1 strict template render / unknown var | `test_prompt_builder.py` | `config_resolution.feature` |
| 17.2 deterministic workspace path | `test_workspace_manager.py` | `workspace_safety.feature` |
| 17.2 missing/existing workspace handled | `test_workspace_manager.py` | `workspace_safety.feature` |
| 17.2 `after_create` only on new workspace | `test_workspace_hooks.py` | `workspace_safety.feature` |
| 17.2 `before_run` aborts attempt | `test_workspace_hooks.py` | `workspace_safety.feature` |
| 17.2 `after_run` ignored on failure | `test_workspace_hooks.py` | `workspace_safety.feature` |
| 17.2 `before_remove` ignored on failure | `test_workspace_hooks.py` | `workspace_safety.feature` |
| 17.2 path sanitization & root containment | `test_workspace_path_safety.py` | `workspace_safety.feature` |
| 17.2 agent cwd == workspace path | `test_runner_opencode.py` | `runner_opencode.feature` |
| 17.3 candidate uses active states + slug | `test_tracker_github.py` | `tracker_github.feature` |
| 17.3 GraphQL `[ID!]` typing for refresh | `test_tracker_github.py` | `tracker_github.feature` |
| 17.3 empty state list → empty, no API | `test_tracker_github.py` | `tracker_github.feature` |
| 17.3 pagination order preserved | `test_tracker_github.py` | `tracker_github.feature` |
| 17.3 blockers from inverse "blocks" | `test_tracker_normalize.py` | `tracker_github.feature` |
| 17.3 labels lowercased | `test_tracker_normalize.py` | `tracker_github.feature` |
| 17.3 error mapping (request/status/graphql/malformed) | `test_tracker_github.py` | `tracker_github.feature` |
| 17.4 dispatch sort priority/created/identifier | `test_dispatch.py` | `orchestrator_dispatch.feature` |
| 17.4 `Todo` w/ non-terminal blockers blocked | `test_dispatch.py` | `orchestrator_dispatch.feature` |
| 17.4 active-state refresh updates running snapshot | `test_reconcile.py` | `orchestrator_dispatch.feature` |
| 17.4 non-active state stops w/o cleanup | `test_reconcile.py` | `orchestrator_dispatch.feature` |
| 17.4 terminal state stops + cleans workspace | `test_reconcile.py` | `orchestrator_dispatch.feature` |
| 17.4 reconciliation no-op when no running | `test_reconcile.py` | `orchestrator_dispatch.feature` |
| 17.4 normal exit → 1 s continuation retry | `test_retry.py` | `orchestrator_retry.feature` |
| 17.4 abnormal exit → exponential backoff | `test_retry.py` | `orchestrator_retry.feature` |
| 17.4 backoff cap = `agent.max_retry_backoff_ms` | `test_retry.py` | `orchestrator_retry.feature` |
| 17.4 retry entry shape (attempt, due, id, err) | `test_retry.py` | `orchestrator_retry.feature` |
| 17.4 stall detection kills & retries | `test_reconcile.py` | `orchestrator_dispatch.feature` |
| 17.4 slot exhaustion requeues w/ error | `test_retry.py` | `orchestrator_dispatch.feature` |
| 17.4 snapshot API shape | `test_snapshot.py` | `observability.feature` |
| 17.4 snapshot timeout/unavailable | `test_observability_server.py` | `observability.feature` |
| 17.5 launch `bash -lc <cmd>` w/ workspace cwd | `test_runner_opencode.py` | `runner_opencode.feature` |
| 17.5 startup handshake | `test_runner_opencode.py` | `runner_opencode.feature` |
| 17.5 `session_started` event shape | `test_runner_opencode.py` | `runner_opencode.feature` |
| 17.5 read timeout enforced | `test_runner_opencode.py` | `runner_opencode.feature` |
| 17.5 turn timeout enforced | `test_runner_opencode.py` | `runner_opencode.feature` |
| 17.5 transport framing | `test_runner_opencode.py` | `runner_opencode.feature` |
| 17.5 approvals handled per policy | `test_runner_opencode.py` | `runner_opencode.feature` |
| 17.5 unsupported tool → failure, not stall | `test_runner_opencode.py` | `runner_opencode.feature` |
| 17.5 user input required → fail per policy | `test_runner_opencode.py` | `runner_opencode.feature` |
| 17.5 token & rate-limit extraction | `test_runner_opencode.py` + `test_orchestrator_service.py` | `runner_opencode.feature` |
| 17.5 advertised tool specs | `test_runner_opencode.py` | `runner_opencode.feature` |
| 17.5 `linear_graphql` ext (N/A here; skipped, doc-stubbed) | — | — |
| 17.6 operator-visible validation failures | `test_orchestrator_service.py` | `observability.feature` |
| 17.6 structured logging context | `test_observability_log.py` | `observability.feature` |
| 17.6 sink failure does not crash | `test_observability_log.py` | `observability.feature` |
| 17.6 token aggregation across updates | `test_orchestrator_service.py` | `observability.feature` |
| 17.7 CLI positional + default | `test_cli.py` | `workflow_loading.feature` |
| 17.7 CLI failure on missing file | `test_cli.py` | `workflow_loading.feature` |
| 17.7 CLI clean exit / nonzero on startup fail | `test_cli.py` | `workflow_loading.feature` |
| 17.8 live e2e | `tests/live/test_live_github.py` (env-gated) | — |

## 7. Concurrency Model

- **One** orchestrator task owns the `State` dataclass. All state mutations go through `await self._lock.acquire()` (an `asyncio.Lock`) to satisfy SPEC §7.4 "single authority".
- Worker tasks (per dispatched issue) are spawned with `asyncio.create_task`, communicate events back to the orchestrator via an `asyncio.Queue` keyed by issue_id, and the orchestrator drains via `await queue.get()` at the top of each tick. This mirrors the Elixir `{:codex_worker_update, issue_id, msg}` pattern but in idiomatic asyncio.
- Watcher for `WORKFLOW.md` uses `watchfiles.awatch` running as a separate task that calls `WorkflowStore.force_reload()`.
- HTTP server is an `uvicorn.Server` running in a `startup` task; orchestrator registers shutdown via `signal.signal(SIGINT/SIGTERM)`.

## 8. Failure Model (SPEC §14)

| Class | Python behavior |
|---|---|
| `missing_workflow_file` | `WorkflowError` raised on startup; CLI exits nonzero with operator-visible message |
| `workflow_parse_error`, `workflow_front_matter_not_a_map` | same |
| `template_parse_error` / `template_render_error` | returned from `PromptBuilder.build()`; orchestrator treats as worker failure, schedules retry |
| `tracker_*` (request/status/graphql/malformed) | logged, dispatch skipped for that tick (matches SPEC §14.2) |
| `runner_*` (startup/turn/timeout/port_exit) | worker task exits non-normal → orchestrator schedules exponential-backoff retry |
| `dispatch validation` (per-tick) | logged error, reconciliation still runs |
| Log sink failure | caught and logged at WARN; orchestration continues |

No silent fallbacks. No broad `except Exception` — `symphony.errors.SymphonyError` is the base; only declared subtypes are caught at each layer.

## 9. Security & Safety (SPEC §15)

- Workspace path containment is checked twice: (a) in `Workspace.create_for_issue` (spec Invariant 2), (b) again in `OpenCodeRunner.start_session` before any subprocess spawn (defense in depth).
- `~` and `$VAR` expansion is gated to **path-typed** fields only (the resolution module whitelists which keys are paths). URI / command strings (`tracker.endpoint`, `codex.command`, GraphQL host names) are never rewritten.
- `api_key` is never logged. Log formatter is custom and whitelists field names; everything else is a single `redacted` token.
- Hook output is truncated to 2 KB in logs (matches Elixir `sanitize_hook_output_for_log`).
- `symphony.cli` requires `--i-understand-that-this-will-be-running-without-the-usual-guardrails` before starting (mirrors Elixir CLI). Documented in README.

## 10. Observability Surface (SPEC §13.7)

- Default: structured `logging` to stderr + a tee'd file at `<logs_root>/symphony.log`.
- When `--port` is set (or `server.port` in WORKFLOW.md), start `uvicorn` serving:
  - `GET  /` — minimal HTML dashboard (server-rendered, no client framework)
  - `GET  /api/v1/state`
  - `GET  /api/v1/<issue_identifier>`
  - `POST /api/v1/refresh`
  - `405` envelope `{"error":{"code":"method_not_allowed","message":"…"}}` on wrong methods
  - `404` envelope on unknown issue
  - Binds `127.0.0.1` by default; configurable via `server.host`

## 11. Work Plan (Implementation Order, TDD per step)

1. **Skeleton** — `pyproject.toml`, `src/symphony/__init__.py`, `tests/conftest.py`, fakes, `make test` is green (no tests yet). **No code in `src/` yet.**
2. `errors.py` + `ids.py` (sanitization, normalize_state) — TDD unit tests
3. `workflow/loader.py` (load, split, parse) — TDD
4. `config/schema.py` (pydantic Settings) + `config/resolution.py` ($VAR, ~) — TDD
5. `config/validate.py` (preflight) — TDD
6. `workflow/store.py` (hot reload) — TDD with `watchfiles` fake
7. `workspace/path_safety.py` — TDD (the Invariants)
8. `workspace/manager.py` + `workspace/hooks.py` — TDD
9. `prompt/builder.py` (strict Jinja2) — TDD
10. `tracker/normalize.py` — TDD
11. `tracker/base.py` Protocol + `tracker/memory.py` — TDD
12. `tracker/github.py` (httpx) — TDD with `httpx.MockTransport`
13. `runner/base.py` Protocol
14. `runner/opencode.py` — TDD with a fake stdio server (we spawn a small `python` script that pretends to be opencode acp, feeding scripted JSON lines)
15. `orchestrator/state.py` + `orchestrator/dispatch.py` + `orchestrator/retry.py` + `orchestrator/reconcile.py` — TDD
16. `orchestrator/service.py` (the loop) — TDD with fakes for everything
17. `observability/log.py` + `observability/snapshot.py` — TDD
18. `observability/server.py` (FastAPI) — TDD using `httpx.AsyncClient(app=app)` in tests
19. `cli.py` — TDD
20. `__main__.py` wiring all of the above
21. BDD features + step files (one per capability; map back to SPEC §17)
22. `examples/WORKFLOW.github-opencode.md` + `examples/WORKFLOW.memory-dev.md`
23. `README.md` + `AGENTS.md`
24. **Conformance sweep**: walk SPEC §17 line by line, confirm each item has at least one test (TDD or BDD). Update a `docs/CONFORMANCE.md` table.
25. (optional, env-gated) Live e2e: real `httpx` against `api.github.com` using a disposable repo + token, and a real `opencode acp` run inside a tmp workspace.

Each step ends with `make all` green.

## 12. Open Questions

- **Q1. Location.** Put the new implementation in `python/` (mirroring `elixir/`)? Or `py/`, or top-level `symphony_py/`?
- **Q2. OpenCode integration depth.**
  - (A) **Full**: implement `OpenCodeRunner` against the real `opencode acp` protocol (we'd need to study the actual ACP messages). Tests use a fake stdio server.
  - (B) **Stub + real**: ship a working `OpenCodeRunner` using the simpler `opencode run --format json` for v1 (one turn at a time, no continuation), and leave a documented extension point for ACP-based continuation.
- **Q3. BDD framework.** `pytest-bdd` (extra dep) — recommended.
- **Q4. Config model.** Pydantic `BaseSettings` — recommended.
- **Q5. SSH worker pool (Appendix A).** Defer to v2 — recommended.
- **Q6. Linear adapter.** Ship a stub `LinearAdapter` that raises `UnsupportedTrackerKind`? — recommended yes.
- **Q7. Snapshot API + dashboard.** JSON-only for v1 — recommended.
- **Q8. Live e2e.** OK to include `tests/live/test_live_github.py` as opt-in?

## 13. What we will NOT do without explicit confirmation

- No file writes anywhere in the repo while in plan mode.
- No `pip install` of new packages (dev tooling like `ruff`/`mypy` will need it later — flagging now).
- No real network calls to GitHub.
- No real `opencode` subprocess spawns during plan exploration.
- No references to any external repo.
