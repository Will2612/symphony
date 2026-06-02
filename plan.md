# Symphony — Python Implementation Plan

Status: v2 (resolutions from plan review 2026-06-02 folded in; see `QandA.md` and `checklist.md`)
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

**Distribution**
- PyPI distribution name: **`symphony-py`** (PyPI is the only name conflict; the bare `symphony` is already taken locally — see QandA G-Q3). CLI command stays `symphony`; importable package is `symphony`; wheel is `symphony_py-*.whl`.

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

> **Why `src/symphony/` (src layout) and not a flat `symphony/` package:** src layout makes the wheel importable only when installed (no accidental import from a stale working tree), forces tests to use the installed package (matching what users will run), and is the modern best practice for libraries. Editable install (`pip install -e`) handles `import symphony` exactly the same way; the user-visible CLI command `symphony` is unaffected.

```
python/
├── pyproject.toml             # name=symphony-py; ruff + mypy + pytest config
├── Makefile                   # `make all` -> fmt, lint, type, test, coverage
├── README.md                  # how to run/install
├── AGENTS.md                  # repo-local rules (mirrors elixir/AGENTS.md)
├── src/symphony/
│   ├── __init__.py
│   ├── __main__.py            # `python -m symphony …`
│   ├── cli.py                 # CLI: positional WORKFLOW.md, --port, --logs-root, --i-understand-…
│   ├── errors.py              # typed result/error hierarchy (incl. GitHub + Runner categories)
│   ├── ids.py                 # workspace_key sanitization, session_id, normalize_issue_state
│   ├── workflow/
│   │   ├── loader.py          # WORKFLOW.md read + front-matter split + parse
│   │   └── store.py           # hot-reload cache (last-known-good)
│   ├── config/
│   │   ├── schema.py          # pydantic Settings (typed view)
│   │   ├── resolution.py      # $VAR indirection, ~, $VAR-for-path, defaults
│   │   └── validate.py        # dispatch preflight checks
│   ├── tracker/
│   │   ├── base.py            # Tracker Protocol (replaceable) + EventKind enum
│   │   ├── memory.py          # in-memory adapter (tests + dev; also a real `tracker.kind: "memory"` value)
│   │   ├── github.py          # GitHubTracker (httpx + REST; GH-typed error categories)
│   │   └── normalize.py       # Section 4.1.1 Issue model
│   ├── workspace/
│   │   ├── path_safety.py     # canonicalize + root containment (Invariant 1-3)
│   │   ├── manager.py         # create/reuse, hooks
│   │   └── hooks.py           # after_create / before_run / after_run / before_remove
│   ├── runner/
│   │   ├── base.py            # Runner Protocol (replaceable) + EventKind/RunnerError base
│   │   ├── opencode.py        # OpenCodeRunner over `opencode acp` (JSON-RPC stdio)
│   │   ├── policy.py          # ApprovalPolicy Strategy (auto-approve | reject | …)
│   │   └── factory.py         # runner_for(config) -> Runner
│   ├── prompt/
│   │   └── builder.py         # Jinja2 strict (StrictUndefined + UndefinedError on unknown filter)
│   ├── orchestrator/
│   │   ├── state.py           # dataclass State; ClaimState + RunPhase enums; transition graph
│   │   ├── dispatch.py        # sort, candidate, per-state slots, blocker rule
│   │   ├── reconcile.py       # stall + tracker state refresh + reconciliation-failure-keeps-workers
│   │   ├── retry.py           # backoff formula + continuation vs failure
│   │   └── service.py         # main async loop, single-authority mutations, startup sequence
│   └── observability/
│       ├── log.py             # structured key=value logger (issue_id/issue_identifier/session_id)
│       ├── snapshot.py        # section 13.3 payload builder (full per-issue field set)
│       └── server.py          # FastAPI: /, /api/v1/state, /api/v1/<id>, /api/v1/refresh
├── tests/
│   ├── conftest.py            # fakes (see §1.1)
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
│   │   ├── test_tracker_github.py            # covers all GH error categories (see §8.1)
│   │   ├── test_tracker_memory.py
│   │   ├── test_runner_opencode.py           # covers all Runner error categories (see §8.1)
│   │   ├── test_dispatch.py
│   │   ├── test_retry.py
│   │   ├── test_reconcile.py
│   │   ├── test_orchestrator_service.py      # covers startup sequence, token accounting, etc.
│   │   ├── test_snapshot.py                  # covers all per-issue snapshot fields (see §6.1)
│   │   ├── test_observability_log.py         # covers §17.6 sink failure + token aggregation
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
├── examples/
│   ├── WORKFLOW.github-opencode.md
│   └── WORKFLOW.memory-dev.md
└── docs/
    ├── CONFORMANCE.md         # SPEC §17 line-by-line map (generated/updated by step 24)
    ├── logging.md             # mirroring elixir/docs/logging.md
    └── token_accounting.md    # mirroring elixir/docs/token_accounting.md; rules from §13.5
```

### 1.1 Conftest Fakes

`tests/conftest.py` exports these fakes. Every test imports from `conftest` only.

- `FakeClock` — `now()` returns a controllable monotonic; `advance(ms)` without sleeping.
- `FakeFileSystem` — in-memory FS for path-safety + workspace tests; preserves `lstat` semantics for symlink resolution (Invariant 1-3).
- `MemoryTracker` — implements the `Tracker` Protocol against an in-process dict; doubles as a real `tracker.kind: "memory"` adapter for local dev.
- `ScriptedRunner` — implements the `Runner` Protocol; records every `prompt` and emits a scripted `Event` stream per turn; can simulate `turn_completed`, `turn_failed`, `turn_timeout`, `turn_input_required`, `approval_required`, `malformed`.
- `FakeACPStdioServer` — `asyncio` task that reads lines from one end of an in-memory pipe and writes scripted JSON-RPC responses; the `OpenCodeRunner` test points its subprocess at this fake.
- `FakeWorkflowStore` — synchronous in-memory equivalent of `WorkflowStore` for tests that don't care about hot-reload.
- `CapturingLogHandler` — attaches to the root logger; captures emitted records; assertions on `extra` fields.
- `NullObserver` — `symphony.observability.snapshot.Observer` that always returns `None`; used to disable HTTP server in tests.

### 1.2 Domain Enumerations

All enumerations live in `src/symphony/orchestrator/state.py` and `src/symphony/runner/base.py` as `enum.Enum` subclasses. Transitions are validated against an `ALLOWED_TRANSITIONS: dict[Enum, frozenset[Enum]]` constant; the orchestrator raises `InvalidStateTransition` on a disallowed move. Serialization to the snapshot API uses the enum's `value` (a snake_case string).

- **`ClaimState`** (SPEC §7.1): `UNCLAIMED`, `CLAIMED`, `RUNNING`, `RETRY_QUEUED`, `RELEASED`.
- **`RunPhase`** (SPEC §7.2): `PREPARING_WORKSPACE`, `BUILDING_PROMPT`, `LAUNCHING_AGENT_PROCESS`, `INITIALIZING_SESSION`, `STREAMING_TURN`, `FINISHING`, `SUCCEEDED`, `FAILED`, `TIMED_OUT`, `STALLED`, `CANCELED_BY_RECONCILIATION`.
- **`EventKind`** (SPEC §10.4): `SESSION_STARTED`, `TURN_COMPLETED`, `TURN_FAILED`, `TURN_CANCELLED`, `TURN_INPUT_REQUIRED`, `APPROVAL_REQUIRED`, `NOTIFICATION`, `OTHER_MESSAGE`, `MALFORMED`, `UNSUPPORTED_TOOL_CALL`, `APPROVAL_AUTO_APPROVED`.

### 1.3 Typed Domain Entities (SPEC §4.1)

Each entity is a `@dataclass` in the module most natural to its owner:

- **`Issue`** (`tracker/normalize.py`, §4.1.1) — `id`, `identifier`, `title`, `description`, `state`, `labels: tuple[str, ...]`, `priority: float`, `created_at: datetime`, `url`, `blocked_by: tuple[str, ...]`. Blockers come from the inverse of the issue's "blocks" relationship.
- **`Workspace`** (`workspace/manager.py`, §4.1.4) — `path: Path`, `key: str`, `issue_id: str`, `created_at: datetime`, `last_used_at: datetime`, `state: Literal["creating","ready","running","completed","removed"]`.
- **`RunAttempt`** (`orchestrator/state.py`, §4.1.5) — `attempt_number: int`, `started_at: datetime`, `current_phase: RunPhase`, `session_id: str | None`, `last_event_at: datetime | None`, `last_error: str | None`, `last_token_usage: TokenUsage | None`, `last_reported_total_tokens: int | None`.
- **`LiveSession`** (`orchestrator/state.py`, §4.1.6) — `issue_id: str`, `claim_state: ClaimState`, `current_phase: RunPhase`, `current_attempt: RunAttempt | None`, `attempts: list[RunAttempt]`, `restart_count: int`, `current_retry_attempt: int`, `runner_session_id: str | None`, `last_message: str | None`, `last_event_at: datetime | None`, `recent_events: tuple[Event, ...]` (capped to last N), `last_error: str | None`, `tracked: bool`.
- **`RetryEntry`** (`orchestrator/retry.py`, §4.1.7) — `issue_id: str`, `attempt: int`, `due_at: datetime`, `id: str`, `error: str | None`, `kind: Literal["continuation","failure"]`.
- **`OrchestratorState`** (`orchestrator/state.py`, §4.1.8) — `live: dict[str, LiveSession]`, `retry_queue: list[RetryEntry]`, `running_issue_ids: set[str]`, `last_tick_at: datetime`, `effective_config: Config | None`, `recent_log_tail: tuple[LogRecord, ...]`.

## 2. Architecture (mirrors SPEC §3.2)

| Layer | Python module | Notes |
|---|---|---|
| Policy | `examples/*.md` + user repo's `WORKFLOW.md` | unchanged |
| Configuration | `symphony.config.*` | pydantic `BaseSettings` typed view; `$VAR`/`~`/relative resolution |
| Coordination | `symphony.orchestrator.*` | single async task with an `asyncio.Lock` around `OrchestratorState` mutations (the "single authority") |
| Execution | `symphony.workspace.*` + `symphony.runner.*` | subprocess via `asyncio.create_subprocess_exec` (`opencode acp` stdio) |
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

The orchestrator depends on **only** the `Tracker` Protocol. Adapters:

- **`MemoryTracker`** — in-process dict. Doubles as: (a) the fake used by tests, (b) a real `tracker.kind: "memory"` adapter for local dev (no tracker creds needed). The Pydantic config validator accepts `"memory"` as a `tracker.kind` value. Sends `memory_tracker_*` events on an optional `asyncio.Queue` for assertions.
- **`GitHubTracker`** — uses `httpx.AsyncClient` against `tracker.endpoint` (default `https://api.github.com`, supports GH Enterprise). REST for issues/comments. Pydantic config:
  - `tracker.kind: "github"`
  - `tracker.project_slug: "owner/repo"`
  - `tracker.api_key: $GITHUB_TOKEN` (default env `GITHUB_TOKEN`); **never** logged
  - `tracker.active_states: ["open"]` (default)
  - `tracker.terminal_states: ["closed"]` (default)
  - `tracker.endpoint: "https://api.github.com"` (default; supports GH Enterprise — a unit test in `test_tracker_github.py` asserts a custom endpoint is accepted)
  - 30s network timeout, 50/page pagination, exponential retry on 5xx with backoff capped at 5s
  - GH-specific error categories (see §8.1) for every failure path
- **`LinearAdapter`** (stub) — raises `UnsupportedTrackerKind` until needed.

> **v1 scope decision (QandA G-Q2):** no `tracker.assignee` filter. The Pydantic schema does NOT include an `assignee` field, and the GitHub adapter does NOT pass any assignee filter to the GitHub REST API. Filtering is by `state` and `labels` only.

## 4. Replaceable Runner Interface (SPEC §10)

```python
# symphony/runner/base.py
class Session: ...  # opaque handle (subprocess or socket)
class TurnResult: ...  # success | failure | timeout | cancelled | input_required
class EventKind(enum.Enum): ...  # see §1.2
class Event: ...  # kind: EventKind; payload: dict; session_id: str; ts: datetime

class Runner(Protocol):
    name: str

    async def start_session(self, workspace: Path, codex_cfg: dict) -> Session: ...
    async def run_turn(self, session: Session, prompt: str, on_event: Callable[[Event], Awaitable[None]]) -> TurnResult: ...
    async def stop_session(self, session: Session) -> None: ...
```

### 4.1 `OpenCodeRunner` (the v1 "github+opencode" target)

- **Default command**: `opencode acp` (QandA G-Q4). The Elixir reference's `codex app-server` is replaced 1:1 by the ACP server; SPEC §10.2 ("continuation turns on the same live thread") is preserved.
- **Launch**: `bash -lc "opencode acp"` inside the workspace, via `asyncio.create_subprocess_exec(..., stdin=PIPE, stdout=PIPE, stderr=PIPE, cwd=workspace)`. PATH inherited. 10 MB line buffer (SPEC §10.1; unit test `test_runner_opencode.py::test_line_buffer_limit`).
- **Wire**: ACP JSON-RPC over stdio (newline-delimited). ACP schema lives in the `opencode` source / docs, not in SPEC.
- **Lifecycle**: `initialize` → `newSession` (cwd = workspace) → `prompt` for the first turn → `prompt` for continuations on the same `session_id` → `cancel` / terminate subprocess at end.
- **First-turn title**: passes `<issue.identifier>: <issue.title>` as the `prompt` title (SPEC §10.2; unit test asserts).
- **Event mapping**: normalizes ACP events to the `EventKind` enum from §1.2.
- **Default policies** (QandA G-Q5, mirrors SPEC §10.5):
  - `codex.approval_policy = "auto-approve"` — both command and file-change prompts are auto-approved for the session.
  - `codex.thread_sandbox = "workspace-write"` — read-anywhere, write only inside the workspace.
  - `codex.turn_sandbox_policy = { writable_roots: [workspace_abs_path] }` — per-turn, the writable root is the specific issue's workspace.
  - `user_input_required` events are surfaced as a hard failure (run attempt is marked `FAILED` with `code: "user_input_required"`).
- **Errors**: every failure path raises a `RunnerError` subclass from the hierarchy in §8.1.
- **Tests**: `test_runner_opencode.py` uses `FakeACPStdioServer` (see §1.1) so tests do not need a real `opencode` binary.

## 5. BDD + TDD Methodology (Strictly)

The two layers are not redundant — they test different scales.

### 5.1 TDD (red → green → refactor) — `tests/unit/`
- One test per behavior listed in SPEC §17, grouped by component.
- Per test: written before code. Run pytest, see it fail for the right reason, then implement.
- Use `pytest.mark.parametrize` for boundary conditions (priority sort, backoff exponent, terminal-state matching).
- Fakes come from `tests/conftest.py` — see §1.1.

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
| 17.1 `tracker.kind` validation (incl. `"memory"`) | `test_config_validate.py` | `config_resolution.feature` |
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
| 17.2 startup terminal workspace cleanup (per §16.1) | `test_orchestrator_service.py::test_startup_terminal_cleanup` | `orchestrator_dispatch.feature` |
| 17.3 candidate uses active states + slug | `test_tracker_github.py` | `tracker_github.feature` |
| 17.3 GraphQL `[ID!]` typing for refresh | `test_tracker_github.py` | `tracker_github.feature` |
| 17.3 empty state list → empty, no API | `test_tracker_github.py` | `tracker_github.feature` |
| 17.3 pagination order preserved | `test_tracker_github.py` | `tracker_github.feature` |
| 17.3 blockers from inverse "blocks" | `test_tracker_normalize.py` | `tracker_github.feature` |
| 17.3 labels lowercased | `test_tracker_normalize.py` | `tracker_github.feature` |
| 17.3 error mapping (all GH categories, §8.1) | `test_tracker_github.py` | `tracker_github.feature` |
| 17.3 `tracker.kind: "memory"` accepted | `test_config_validate.py` + `test_tracker_memory.py` | `tracker_github.feature` |
| 17.3 custom `tracker.endpoint` accepted | `test_tracker_github.py` | `tracker_github.feature` |
| 17.4 dispatch sort priority/created/identifier | `test_dispatch.py` | `orchestrator_dispatch.feature` |
| 17.4 `Todo` w/ non-terminal blockers blocked | `test_dispatch.py` | `orchestrator_dispatch.feature` |
| 17.4 active-state refresh updates running snapshot | `test_reconcile.py` | `orchestrator_dispatch.feature` |
| 17.4 non-active state stops w/o cleanup | `test_reconcile.py` | `orchestrator_dispatch.feature` |
| 17.4 terminal state stops + cleans workspace | `test_reconcile.py` | `orchestrator_dispatch.feature` |
| 17.4 reconciliation no-op when no running | `test_reconcile.py` | `orchestrator_dispatch.feature` |
| 17.4 reconciliation failure keeps workers | `test_reconcile.py::test_reconciliation_failure_keeps_workers` | `orchestrator_dispatch.feature` |
| 17.4 normal exit → 1 s continuation retry | `test_retry.py` | `orchestrator_retry.feature` |
| 17.4 abnormal exit → exponential backoff | `test_retry.py` | `orchestrator_retry.feature` |
| 17.4 backoff cap = `agent.max_retry_backoff_ms` | `test_retry.py` | `orchestrator_retry.feature` |
| 17.4 retry entry shape (attempt, due, id, err) | `test_retry.py` | `orchestrator_retry.feature` |
| 17.4 stall detection kills & retries | `test_reconcile.py` | `orchestrator_dispatch.feature` |
| 17.4 stall detection disabled when `stall_timeout_ms <= 0` | `test_reconcile.py::test_stall_detection_disabled` | `orchestrator_dispatch.feature` |
| 17.4 slot exhaustion requeues w/ error | `test_retry.py` | `orchestrator_dispatch.feature` |
| 17.4 restart-recovery contract (§14.3) | `test_orchestrator_service.py::test_restart_recovery` | `orchestrator_dispatch.feature` |
| 17.4 per-tick defensive reload (§6.2) | `test_orchestrator_service.py::test_per_tick_defensive_reload` | `orchestrator_dispatch.feature` |
| 17.4 snapshot API shape (full field set, §6.1) | `test_snapshot.py` | `observability.feature` |
| 17.4 snapshot timeout/unavailable | `test_observability_server.py` | `observability.feature` |
| 17.5 launch `bash -lc <cmd>` w/ workspace cwd | `test_runner_opencode.py` | `runner_opencode.feature` |
| 17.5 startup handshake | `test_runner_opencode.py` | `runner_opencode.feature` |
| 17.5 `session_started` event shape | `test_runner_opencode.py` | `runner_opencode.feature` |
| 17.5 read timeout enforced | `test_runner_opencode.py` | `runner_opencode.feature` |
| 17.5 turn timeout enforced | `test_runner_opencode.py` | `runner_opencode.feature` |
| 17.5 transport framing (10 MB line buffer) | `test_runner_opencode.py::test_line_buffer_limit` | `runner_opencode.feature` |
| 17.5 approvals handled per policy | `test_runner_opencode.py` | `runner_opencode.feature` |
| 17.5 unsupported tool → failure, not stall | `test_runner_opencode.py` | `runner_opencode.feature` |
| 17.5 user input required → fail per policy | `test_runner_opencode.py` | `runner_opencode.feature` |
| 17.5 token & rate-limit extraction (per §6.2) | `test_runner_opencode.py` + `test_orchestrator_service.py` | `runner_opencode.feature` |
| 17.5 advertised tool specs | `test_runner_opencode.py` | `runner_opencode.feature` |
| 17.5 `linear_graphql` ext (N/A here; skipped, doc-stubbed) | — | — |
| 17.6 operator-visible validation failures | `test_orchestrator_service.py` | `observability.feature` |
| 17.6 structured logging context | `test_observability_log.py` | `observability.feature` |
| 17.6 sink failure does not crash | `test_observability_log.py` | `observability.feature` |
| 17.6 token aggregation across updates (per §6.2) | `test_orchestrator_service.py` | `observability.feature` |
| 17.7 CLI positional + default | `test_cli.py` | `workflow_loading.feature` |
| 17.7 CLI `--port 0` ephemeral port | `test_cli.py::test_port_zero_ephemeral` | `workflow_loading.feature` |
| 17.7 CLI failure on missing file | `test_cli.py` | `workflow_loading.feature` |
| 17.7 CLI clean exit / nonzero on startup fail | `test_cli.py` | `workflow_loading.feature` |
| 17.7 CLI shutdown / exit codes | `test_cli.py::test_shutdown_exit_codes` | `workflow_loading.feature` |
| 17.8 live e2e | `tests/live/test_live_github.py` (env-gated) | — |

### 6.1 Snapshot API Per-Issue Fields (SPEC §13.7.2)

`GET /api/v1/<issue_identifier>` returns at minimum these fields, asserted by `test_snapshot.py::test_snapshot_full_field_set`:

```
running.session_id:           str | null
attempts.restart_count:      int
attempts.current_retry_attempt: int
attempts.current:             RunAttempt (current_phase, last_error, last_event_at, last_token_usage)
last_message:                 str | null
last_event_at:                datetime | null
recent_events:                tuple[Event, ...]   # last N (cap = 50)
last_error:                   str | null
tracked:                      bool
logs.codex_session_logs:      tuple[LogRecord, ...]
issue:                        Issue
claim_state:                  ClaimState
```

### 6.2 Token Accounting Rules (SPEC §13.5)

Documented in `python/docs/token_accounting.md` and enforced in `orchestrator/service.py`:

1. `last_token_usage` from a runner update is **ignored** as a cumulative number; it is only used for deltas.
2. The authoritative total is the **absolute total tokens** field on the runner's `token_usage` payload (e.g. ACP `tokenUsage.total`).
3. For each update, compute `delta = absolute_total - last_reported_total_tokens` and add to the run-attempt's running total. If `last_reported_total_tokens` is `None`, treat the first update's absolute as the running total (no delta).
4. The orchestrator tracks `last_reported_total_tokens` per `LiveSession` and updates it on every accepted update.
5. A generic `usage` field (no absolute total) is **never** treated as cumulative; if the runner only emits a `usage` field, the orchestrator logs `runner_token_accounting_unresolved` and the run-attempt's token total stays at its previous value.
6. Rate-limit data (`rate_limit.remaining`, `rate_limit.reset_at`) is recorded in the snapshot but is not part of the run-attempt total.

## 7. Concurrency Model

- **One** orchestrator task owns `OrchestratorState`. All state mutations go through `await self._lock.acquire()` (an `asyncio.Lock`) to satisfy SPEC §7.4 "single authority".
- Worker tasks (per dispatched issue) are spawned with `asyncio.create_task`, communicate events back to the orchestrator via an `asyncio.Queue` keyed by issue_id, and the orchestrator drains via `await queue.get()` at the top of each tick. This mirrors the Elixir `{:codex_worker_update, issue_id, msg}` pattern but in idiomatic asyncio.
- Watcher for `WORKFLOW.md` uses `watchfiles.awatch` running as a separate task that calls `WorkflowStore.force_reload()`. The orchestrator also re-validates on every tick (defensive; SPEC §6.2).
- HTTP server is an `uvicorn.Server` running in a `startup` task; orchestrator registers shutdown via `signal.signal(SIGINT/SIGTERM)`.
- CLI `--port 0` means "ephemeral"; the server picks a free port and logs the chosen port (unit test `test_cli.py::test_port_zero_ephemeral`).

### 7.1 Service-Startup Algorithm (SPEC §16.1)

`OrchestratorService.start()` runs this sequence, in order, with each step's failure surfaced as a typed `SymphonyError` subclass:

1. **Configure logging** — `observability.log.configure(root_logger, level=INFO, file=<logs_root>/symphony.log)`.
2. **Start observability outputs** — attach the file sink + the structured stderr sink. (Failure to open the file sink is logged at WARN; orchestration continues.)
3. **Start workflow watch** — spawn the `watchfiles.awatch` task pointing at the WORKFLOW.md's directory.
4. **Load and validate config** — first load (no cached config yet), run `config.validate.preflight()`. On failure: log at ERROR, exit with code 2.
5. **Startup terminal workspace cleanup** — iterate `Workspace.list_terminal_workspaces()` (workspaces whose issue is in a terminal state per the tracker) and call `Workspace.remove()` (running `before_remove` hook, then `rm -rf`). SPEC §8.6, §18.1. (Unit test: `test_startup_terminal_cleanup_runs_workspace_remove`.)
6. **Initialize `OrchestratorState`** with `effective_config`, empty `live`, empty `retry_queue`.
7. **Schedule first tick** — `loop.call_soon(self._tick)` (zero-delay first tick).
8. **Enter event loop** — `await self._run_loop()`.

## 8. Failure Model (SPEC §14)

| Class | Python behavior |
|---|---|
| `missing_workflow_file` | `WorkflowError` raised on startup; CLI exits nonzero with operator-visible message |
| `workflow_parse_error`, `workflow_front_matter_not_a_map` | same |
| `template_parse_error` / `template_render_error` | returned from `PromptBuilder.build()`; orchestrator treats as worker failure, schedules retry |
| GitHub `github_*` (see §8.1) | logged at the matching severity; dispatch skipped for that tick (matches SPEC §14.2) |
| Runner `runner_*` (see §8.1) | worker task exits non-normal → orchestrator schedules exponential-backoff retry |
| `dispatch validation` (per-tick) | logged error, reconciliation still runs |
| Log sink failure | caught and logged at WARN; orchestration continues |
| Reconciliation failure (`tracker.fetch_issue_states_by_ids` returns `{:error, _}`) | workers for the affected issues are **not** terminated; the next tick retries (SPEC §8.5) |

No silent fallbacks. No broad `except Exception` — `symphony.errors.SymphonyError` is the base; only declared subtypes are caught at each layer.

### 8.1 Error Category Hierarchy

All error categories are subclasses of `symphony.errors.SymphonyError`. Each is logged with a stable `code` string and a typed message; tests assert the code on every code path.

**GitHub tracker (SPEC §11.4):**
- `GitHubAPIRequest` (`code: "github_api_request"`) — connection / DNS / TLS failure.
- `GitHubAPIStatus` (`code: "github_api_status"`) — non-2xx HTTP status with a structured body.
- `GitHubUnauthorized` (`code: "github_unauthorized"`) — HTTP 401.
- `GitHubForbidden` (`code: "github_forbidden"`) — HTTP 403.
- `GitHubRateLimited` (`code: "github_rate_limited"`) — HTTP 429 or 403 with `X-RateLimit-Remaining: 0`; carries `reset_at` for the orchestrator.
- `GitHubNotFound` (`code: "github_not_found"`) — HTTP 404.
- `GitHubUnknownPayload` (`code: "github_unknown_payload"`) — body failed Pydantic validation.
- `GitHubPaginationMissingLink` (`code: "github_pagination_missing_link"`) — paginated response with no `Link: rel="next"` and `page * per_page < total_count`.

**Runner (SPEC §10.6):**
- `CodexNotFound` (`code: "codex_not_found"`) — `opencode` binary not on PATH (mirrors SPEC name for parity; the runner is OpenCode but the code string stays for log compatibility).
- `InvalidWorkspaceCwd` (`code: "invalid_workspace_cwd"`) — workspace path missing or not a directory.
- `ResponseTimeout` (`code: "response_timeout"`) — no JSON-RPC response within `codex.read_timeout_ms`.
- `TurnTimeout` (`code: "turn_timeout"`) — a `prompt` did not produce a turn-final event within `codex.turn_timeout_ms`.
- `PortExit` (`code: "port_exit"`) — subprocess exited unexpectedly (non-zero rc or EOF on stdin/stdout).
- `ResponseError` (`code: "response_error"`) — JSON-RPC `error` object received.
- `TurnFailed` (`code: "turn_failed"`) — runner emitted `TURN_FAILED`.
- `TurnCancelled` (`code: "turn_cancelled"`) — runner emitted `TURN_CANCELLED` (orchestrator distinguishes from `CanceledByReconciliation`).
- `TurnInputRequired` (`code: "turn_input_required"`) — runner emitted `TURN_INPUT_REQUIRED`; the orchestrator hard-fails the attempt per SPEC §10.5.

## 9. Security & Safety (SPEC §15)

- Workspace path containment is checked twice: (a) in `Workspace.create_for_issue` (spec Invariant 2), (b) again in `OpenCodeRunner.start_session` before any subprocess spawn (defense in depth).
- `~` and `$VAR` expansion is gated to **path-typed** fields only (the resolution module whitelists which keys are paths). URI / command strings (`tracker.endpoint`, `codex.command`, GraphQL host names) are never rewritten.
- `api_key` is never logged. Log formatter is custom and whitelists field names; everything else is a single `redacted` token.
- Hook output is truncated to 2 KB in logs (matches Elixir `sanitize_hook_output_for_log`).
- `symphony.cli` requires `--i-understand-that-this-will-be-running-without-the-usual-guardrails` before starting (mirrors Elixir CLI). Documented in README.
- `worker.ssh_hosts` / `worker.max_concurrent_agents_per_host` are **parsed** by the Pydantic schema (so WORKFLOW.md can declare them) but **not used** in v1; SSH worker pool is deferred to v2. A unit test asserts the schema round-trips these fields without error.
- `codex.stall_timeout_ms <= 0` disables stall detection entirely (SPEC §8.5; unit test `test_stall_detection_disabled_when_timeout_le_zero`).

## 10. Observability Surface (SPEC §13.7)

- Default: structured `logging` to stderr + a tee'd file at `<logs_root>/symphony.log`.
- When `--port` is set (or `server.port` in WORKFLOW.md), start `uvicorn` serving:
  - `GET  /` — minimal HTML dashboard (server-rendered, no client framework)
  - `GET  /api/v1/state`
  - `GET  /api/v1/<issue_identifier>` (full field set, §6.1)
  - `POST /api/v1/refresh`
  - `405` envelope `{"error":{"code":"method_not_allowed","message":"…"}}` on wrong methods
  - `404` envelope on unknown issue
  - Binds `127.0.0.1` by default; configurable via `server.host`
- `symphony.observability.log` enforces structured `key=value` lines with whitelisted `extra` fields: `issue_id`, `issue_identifier`, `session_id`, `attempt`, `phase`, `error_code`. Any other field name is dropped and replaced with `redacted=true` in the line.

## 11. Work Plan (Implementation Order, TDD per step)

1. **Skeleton** — `pyproject.toml` (name=`symphony-py`), `src/symphony/__init__.py`, `tests/conftest.py` (all fakes from §1.1), `make test` is green (no tests yet). **No code in `src/` yet.**
2. `errors.py` (incl. GH + Runner hierarchies, §8.1) + `ids.py` (sanitization, normalize_state) — TDD unit tests
3. `workflow/loader.py` (load, split, parse) — TDD
4. `config/schema.py` (pydantic Settings; `tracker.kind: "memory"` accepted; `worker.ssh_hosts` parsed but unused) + `config/resolution.py` ($VAR, ~) — TDD
5. `config/validate.py` (preflight; `memory` kind allowed) — TDD
6. `workflow/store.py` (hot reload; defensive reload on every tick) — TDD with `watchfiles` fake
7. `workspace/path_safety.py` — TDD (the Invariants)
8. `workspace/manager.py` + `workspace/hooks.py` (incl. `remove()` for startup cleanup) — TDD
9. `prompt/builder.py` (strict Jinja2) — TDD
10. `tracker/normalize.py` (Issue with `blocked_by`, lowercased labels) — TDD
11. `tracker/base.py` Protocol + `tracker/memory.py` — TDD
12. `tracker/github.py` (httpx; all GH error categories; custom endpoint; pagination) — TDD with `httpx.MockTransport`
13. `runner/base.py` Protocol + `EventKind` enum + `RunnerError` base
14. `runner/opencode.py` — TDD with `FakeACPStdioServer`; 10 MB line buffer; explicit policies; first-turn title; all Runner error categories
15. `orchestrator/state.py` (ClaimState + RunPhase enums + transition graph; LiveSession, RunAttempt, RetryEntry, OrchestratorState dataclasses)
16. `orchestrator/dispatch.py` + `orchestrator/retry.py` + `orchestrator/reconcile.py` — TDD (reconciliation-failure keeps workers; stall-disable; restart-recovery; per-tick defensive reload)
17. `orchestrator/service.py` (the loop + startup sequence per §7.1) — TDD with fakes for everything
18. `observability/log.py` (kv formatter, whitelist, sink-failure handling) + `observability/snapshot.py` (full field set per §6.1; token aggregation per §6.2) — TDD
19. `observability/server.py` (FastAPI; `--port 0` ephemeral) — TDD using `httpx.AsyncClient(app=app)` in tests
20. `cli.py` (incl. shutdown + exit codes + `--port 0`) — TDD
21. `__main__.py` wiring all of the above
22. BDD features + step files (one per capability; map back to SPEC §17)
23. `examples/WORKFLOW.github-opencode.md` + `examples/WORKFLOW.memory-dev.md`
24. `python/docs/CONFORMANCE.md` (line-by-line SPEC §17 → test pointer) + `python/docs/logging.md` + `python/docs/token_accounting.md`
25. **Conformance sweep**: walk SPEC §17 line by line, confirm each item has at least one test (TDD or BDD). Cross-check against `python/docs/CONFORMANCE.md`. Coverage report must show ≥ 95 % on `src/symphony/`.
26. (optional, env-gated) Live e2e: real `httpx` against `api.github.com` using a disposable repo + token, and a real `opencode acp` run inside a tmp workspace.

Each step ends with `make all` green.

## 12. Resolved Decisions

The following decisions from plan review 2026-06-02 are baked into this v2 plan. Full resolutions and rationale are recorded in [`QandA.md`](./QandA.md); the running gap list is in [`checklist.md`](./checklist.md).

- **G-Q1** — `ClaimState` and `RunPhase` are first-class Python `enum.Enum` subclasses in `orchestrator/state.py` with an `ALLOWED_TRANSITIONS` graph; see §1.2.
- **G-Q2** — `tracker.assignee` is **dropped for v1**; GitHub adapter filters by `state` and `labels` only.
- **G-Q3** — PyPI distribution is **`symphony-py`**; CLI command is `symphony`; importable package is `symphony`.
- **G-Q4** — Default `codex.command` is **`opencode acp`** (long-lived stdio JSON-RPC session); tests use `FakeACPStdioServer`.
- **G-Q5** — Default policies are **high-trust** per SPEC §10.5: `approval_policy=auto-approve`, `thread_sandbox=workspace-write`, `turn_sandbox_policy={writable_roots=[workspace]}`. `user_input_required` is a hard failure.

## 13. What we will NOT do without explicit confirmation

- No file writes anywhere in the repo while in plan mode.
- No `pip install` of new packages (dev tooling like `ruff`/`mypy` will need it later — flagging now).
- No real network calls to GitHub.
- No real `opencode` subprocess spawns during plan exploration.
- No references to any external repo.
- No `tracker.assignee` filter in v1.
- No SSH worker pool in v1 (fields parsed, unused).
- No Linear adapter in v1 (stub only).
- No HTML dashboard refresh in v1 (server-rendered static shell only).
