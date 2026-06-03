# Conformance Map

This document is the SPEC §17 → test pointer map for the Python
implementation. Each line of SPEC §17 is recorded with the unit
test(s) (or BDD scenario) that assert the behavior.

The BDD layer (`tests/features/*.feature`) is a documentation
contract — each scenario carries a `@unit-test("file.py[::test]")`
tag. The actual assertions live in the unit tests. The
`tests/steps/test_bdd_steps.py` walk verifies that every
pointer resolves to a real test in the suite.

Maintenance:
- When a new behavior is tested, add the bullet here AND the
  `@unit-test(...)` tag in the matching BDD scenario.
- The conformance sweep (Step 25) walks both columns and
  confirms there is a 1:1 mapping.

---

## §17.1 Workflow and Config Parsing

| SPEC bullet | Unit test(s) | BDD feature |
|---|---|---|
| Workflow file path precedence (explicit > cwd default) | `test_cli.py::test_evaluate_*` | `workflow_loading.feature` |
| Workflow file changes detected → re-read/re-apply | `test_workflow_store.py` | — |
| Invalid reload keeps last good config + operator-visible error | `test_workflow_store.py` | — |
| Missing `WORKFLOW.md` returns typed error | `test_cli.py::test_evaluate_returns_not_found_when_file_missing` | `workflow_loading.feature` |
| Invalid YAML front matter returns typed error | `test_workflow_loader.py` | — |
| Front matter non-map returns typed error | `test_workflow_loader.py` | — |
| Config defaults apply when OPTIONAL values are missing | `test_config_schema.py` | — |
| `tracker.kind` validation enforces currently supported kind | `test_config_validate.py::test_preflight_*` | `tracker_github.feature` (memory + github) |
| `tracker.api_key` works (including `$VAR` indirection) | `test_config_resolution.py`, `test_github_tracker.py` | `tracker_github.feature` |
| `$VAR` resolution for tracker API key and path values | `test_config_resolution.py` | — |
| `~` path expansion works | `test_config_resolution.py` | — |
| `codex.command` is preserved as a shell command string | `test_config_schema.py`, `test_opencode_runner.py` | `runner_opencode.feature` |
| Per-state concurrency override normalizes + ignores invalid | `test_config_schema.py` | — |
| Prompt template renders `issue` and `attempt` | `test_prompt_builder.py` | — |
| Prompt rendering fails on unknown variables (strict mode) | `test_prompt_builder.py::test_unknown_var_raises` | — |

## §17.2 Workspace Manager and Safety

| SPEC bullet | Unit test(s) | BDD feature |
|---|---|---|
| Deterministic workspace path per issue identifier | `test_workspace.py` | — |
| Missing workspace directory is created | `test_workspace.py` | — |
| Existing workspace directory is reused | `test_workspace.py` | — |
| Existing non-directory path handled safely | `test_workspace.py` | — |
| Workspace population/sync errors are surfaced | `test_workspace.py` | — |
| `after_create` hook runs only on new workspace creation | `test_workspace.py` | — |
| `before_run` hook runs before each attempt; aborts on failure | `test_workspace.py::test_run_before_run_hook_fatal_on_failure` | — |
| `after_run` hook runs after each attempt; ignores failure | `test_workspace.py::test_run_after_run_hook_ignores_failure` | — |
| `before_remove` hook runs on cleanup; ignores failure | `test_workspace.py::test_remove_runs_before_remove_hook` | — |
| Path sanitization + root containment | `test_path_safety.py` | — |
| Agent launch uses workspace cwd, rejects out-of-root | `test_opencode_runner.py::test_subprocess_*` | `runner_opencode.feature` |

## §17.3 Issue Tracker Client

| SPEC bullet | Unit test(s) | BDD feature |
|---|---|---|
| Candidate fetch uses active states + project slug | `test_github_tracker.py` | `tracker_github.feature` |
| (Linear-only) `slugId` field | N/A — Python ships GitHub only | — |
| Empty `fetch_issues_by_states([])` returns empty without API call | `test_github_tracker.py` | `tracker_github.feature` |
| Pagination preserves order across pages | `test_github_tracker.py::test_github_tracker_fetch_issues_by_states_pagination*` | `tracker_github.feature` |
| Blockers normalized from inverse relations of type `blocks` | `test_normalize.py` | `tracker_github.feature` |
| Labels normalized to lowercase | `test_normalize.py` | `tracker_github.feature` |
| Issue state refresh by ID returns minimal issues | `test_github_tracker.py` | — |
| (Linear-only) `[ID!]` GraphQL typing | N/A — Python ships GitHub only | — |
| Error mapping (request / non-200 / payload) | `test_github_tracker.py::test_github_tracker_401_raises_unauthorized` + 7 more | `tracker_github.feature` |

## §17.4 Orchestrator Dispatch, Reconciliation, and Retry

| SPEC bullet | Unit test(s) | BDD feature |
|---|---|---|
| Dispatch sort: priority then oldest creation | `test_orchestrator_dispatch.py` | `orchestrator_dispatch.feature` |
| `Todo` with non-terminal blockers not eligible | `test_orchestrator_dispatch.py` | `orchestrator_dispatch.feature` |
| `Todo` with terminal blockers eligible | `test_orchestrator_dispatch.py` | — |
| Active-state refresh updates running entry state | `test_orchestrator_reconcile.py` | `orchestrator_dispatch.feature` |
| Non-active state stops agent without cleanup | `test_orchestrator_reconcile.py` | `orchestrator_dispatch.feature` |
| Terminal state stops + cleans workspace | `test_orchestrator_reconcile.py` | `orchestrator_dispatch.feature` |
| Reconciliation with no running issues is no-op | `test_orchestrator_reconcile.py` | — |
| Normal worker exit → short continuation retry (attempt 1) | `test_orchestrator_retry.py` | `orchestrator_retry.feature` |
| Abnormal exit → 10s-based exponential backoff | `test_orchestrator_retry.py` | `orchestrator_retry.feature` |
| Retry backoff cap = `agent.max_retry_backoff_ms` | `test_orchestrator_retry.py` | `orchestrator_retry.feature` |
| Retry queue entry: attempt, due, id, error | `test_orchestrator_retry.py` | `orchestrator_retry.feature` |
| Stall detection kills + retries | `test_orchestrator_reconcile.py` | `orchestrator_dispatch.feature` |
| Slot exhaustion requeues with error | `test_orchestrator_retry.py` | `orchestrator_retry.feature` |
| Snapshot API: running, retry, token totals, rate limits | `test_observability_snapshot.py`, `test_observability_server.py` | `observability.feature` |
| Snapshot timeout / unavailable | `test_observability_server.py` | `observability.feature` |

## §17.5 Coding-Agent App-Server Client

| SPEC bullet | Unit test(s) | BDD feature |
|---|---|---|
| `bash -lc <codex.command>` with workspace cwd | `test_opencode_runner.py` | `runner_opencode.feature` |
| Session startup handshake | `test_opencode_runner.py` | `runner_opencode.feature` |
| Client identity / capability payloads valid | `test_opencode_runner.py` | — |
| Policy-related startup payloads use documented settings | `test_opencode_runner.py::test_opencode_runner_emits_approval_auto_approved` | `runner_opencode.feature` |
| Thread / turn identities → `session_started` | `test_opencode_runner.py` | — |
| Read timeout enforced | `test_opencode_runner.py` | `runner_opencode.feature` |
| Turn timeout enforced | `test_opencode_runner.py::test_opencode_runner_raises_turn_timeout` | `runner_opencode.feature` |
| Transport framing (10 MB line buffer) | `test_opencode_runner.py` | `runner_opencode.feature` |
| Stderr handling separate from protocol stream | `test_opencode_runner.py` | — |
| Approvals per documented policy (auto-approve) | `test_opencode_runner.py` | `runner_opencode.feature` |
| Unsupported dynamic tool calls → failure, not stall | `test_opencode_runner.py::test_opencode_runner_emits_unsupported_tool_call` | `runner_opencode.feature` |
| User input requests → failure per policy | `test_opencode_runner.py` | `runner_opencode.feature` |
| Usage + rate-limit telemetry extracted | `test_opencode_runner.py::test_classify_event_usage_*`, `test_orchestrator_service.py` | `runner_opencode.feature` |
| Signals interpreted per protocol | `test_opencode_runner.py` | — |
| Client-side tools advertise supported tool specs | `test_opencode_runner.py` | — |
| `linear_graphql` client-side tool (N/A — Python ships GitHub only) | N/A | — |

## §17.6 Observability

| SPEC bullet | Unit test(s) | BDD feature |
|---|---|---|
| Validation failures operator-visible | `test_orchestrator_service.py` | `observability.feature` |
| Structured logging with issue/session context | `test_observability_log.py` | `observability.feature` |
| Logging sink failures do not crash | `test_observability_log.py::test_sink_failure_*` | `observability.feature` |
| Token / rate-limit aggregation across updates | `test_observability_snapshot.py`, `test_orchestrator_service.py` | `observability.feature` |
| Status surface driven from orchestrator state (HTTP server) | `test_observability_server.py` | `observability.feature` |
| Humanized event summaries (status dashboard) | N/A — Python ships the HTTP API, not the LiveView dashboard | — |

## §17.7 CLI and Host Lifecycle

| SPEC bullet | Unit test(s) | BDD feature |
|---|---|---|
| CLI accepts positional workflow path | `test_cli.py::test_parse_args_*` | `workflow_loading.feature` |
| CLI uses `./WORKFLOW.md` when no path given | `test_cli.py::test_evaluate_default_workflow_when_no_positional` | `workflow_loading.feature` |
| CLI errors on nonexistent path or missing default | `test_cli.py::test_evaluate_returns_not_found_when_file_missing` | `workflow_loading.feature` |
| CLI surfaces startup failure cleanly | `test_cli.py::test_main_returns_one_on_startup_error` | `workflow_loading.feature` |
| CLI exits 0 on clean shutdown | `test_cli.py::test_main_returns_zero_on_success` | `workflow_loading.feature` |
| CLI exits nonzero on startup failure or abnormal exit | `test_cli.py::test_main_returns_one_on_*` | `workflow_loading.feature` |

## §17.8 Real Integration Profile (env-gated, optional)

| SPEC bullet | Unit test(s) | BDD feature |
|---|---|---|
| Real tracker smoke test with `LINEAR_API_KEY` | N/A — Python ships GitHub; `SYMPHONY_RUN_LIVE_E2E=1 make live` runs real GitHub e2e (Step 26) | — |
| Real integration tests use isolated identifiers + cleanup | N/A — Step 26 | — |

---

## BDD pointer map (machine-readable)

The BDD step file (`tests/steps/test_bdd_steps.py`) walks each
`.feature` and asserts every `@unit-test(...)` tag resolves.
The full pointer list (as of the last sweep) is below:

| Feature | Scenarios | Pointers |
|---|---|---|
| `workflow_loading.feature` | 5 | test_cli.py (×4), test_observability_server.py |
| `tracker_github.feature` | 8 | test_github_tracker.py (×4), test_config_validate.py, test_tracker_base.py, test_normalize.py (×2) |
| `orchestrator_dispatch.feature` | 11 | test_orchestrator_dispatch.py (×2), test_orchestrator_reconcile.py (×6), test_orchestrator_service.py (×3) |
| `orchestrator_retry.feature` | 5 | test_orchestrator_retry.py (×5) |
| `runner_opencode.feature` | 11 | test_opencode_runner.py (×10), test_orchestrator_service.py |
| `observability.feature` | 7 | test_observability_log.py (×2), test_observability_server.py (×3), test_orchestrator_service.py (×2) |
| `skeleton.feature` | 1 | test_skeleton.py |

Any pointer that becomes stale (file renamed, test removed) will
fail `test_every_unit_test_pointer_resolves[<file>.feature]` in
`tests/steps/test_bdd_steps.py` and break the build.
