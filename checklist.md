# Plan-Review Checklist

This is the running checklist of findings/gaps from reviewing [`plan.md`](./plan.md) against [`SPEC.md`](./SPEC.md) and the Elixir reference under [`elixir/`](./elixir/).

Each finding has:
- a stable ID (`C#` = critical, `M#` = medium, `m#` = minor)
- a SPEC reference
- a concrete next action
- a checkbox that we tick when addressed (and at that point, the fix is folded into `plan.md` and `checklist.md` is updated in a single commit per fix, or batched)

## Critical (C) — would cause spec violations if not addressed

- [ ] **C1** — Startup terminal workspace cleanup is not a discrete work-plan step
  - SPEC §8.6, §18.1
  - Action: add explicit step + test entry in `plan.md`; unit test in `tests/unit/test_orchestrator_service.py::test_startup_terminal_cleanup_runs_workspace_remove`; BDD scenario in `orchestrator_dispatch.feature`.

- [x] **C2** — Run-attempt state machine not in plan
  - SPEC §7.2 (PreparingWorkspace → BuildingPrompt → LaunchingAgentProcess → InitializingSession → StreamingTurn → Finishing → Succeeded / Failed / TimedOut / Stalled / CanceledByReconciliation)
  - Action: add `RunPhase` enum to `orchestrator/state.py`; add `current_phase` field to `LiveSession`; unit tests in `test_orchestrator_state.py`.
  - Status: closed 2026-06-02 by G-Q1 resolution (QandA.md). `RunPhase` enum + transition graph decided.

- [x] **C3** — Issue orchestration claim states not in plan
  - SPEC §7.1 (Unclaimed / Claimed / Running / RetryQueued / Released)
  - Action: add `ClaimState` enum; expose on `LiveSession`; document the state-transition rules; unit test in `test_dispatch.py::test_claim_state_transitions`.
  - Status: closed 2026-06-02 by G-Q1 resolution (QandA.md). `ClaimState` enum + transition graph decided.

- [ ] **C4** — Typed domain entities (Workspace, LiveSession, RunAttempt, RetryEntry, OrchestratorState) not explicit
  - SPEC §4.1.4, §4.1.5, §4.1.6, §4.1.7, §4.1.8
  - Action: add dedicated dataclasses (with field-level docstrings mapping back to the spec) in `orchestrator/state.py` and `workspace/manager.py`; not buried in helpers.

- [ ] **C5** — GitHub-specific tracker error categories not enumerated
  - SPEC §11.4
  - Action: enumerate in `plan.md` (and in `tracker/github.py` as `GitHubError` subclass hierarchy): `github_api_request`, `github_api_status`, `github_unauthorized`, `github_forbidden`, `github_rate_limited`, `github_not_found`, `github_unknown_payload`, `github_pagination_missing_link`. Add unit tests for each.

- [ ] **C6** — Token-accounting rules not explicit in plan
  - SPEC §13.5
  - Action: enumerate the rules in `plan.md` (last_token_usage ignored; prefer absolute totals; track deltas vs `last_reported_*`; never treat generic `usage` as cumulative). Document in `docs/token_accounting.md` mirroring `elixir/docs/token_accounting.md`. Unit tests in `test_runner_opencode.py` and `test_orchestrator_service.py`.

- [ ] **C7** — `tracker.kind: memory` not surfaced as a real, documented config value
  - SPEC §5.3.1, §11
  - Action: validate `memory` in `config/validate.py`; ship `examples/WORKFLOW.memory-dev.md`; unit test in `test_config_validate.py`.

- [ ] **C8** — Service-startup algorithm (§16.1) not enumerated in the work plan
  - SPEC §16.1
  - Action: add a numbered startup sequence in `plan.md` §11 (configure_logging → start_observability_outputs → start_workflow_watch → validate_config → startup_terminal_workspace_cleanup → schedule_tick(0) → event_loop). Unit test in `test_orchestrator_service.py::test_startup_sequence`.

- [ ] **C9** — Event vocabulary enum not enumerated
  - SPEC §10.4
  - Action: add `EventKind` enum to `runner/base.py` with all 13 values; unit test that the runner emits the correct kind for each protocol event shape.

- [ ] **C10** — Runner error categories not enumerated
  - SPEC §10.6
  - Action: enumerate in `plan.md` and as `RunnerError` subclass hierarchy: `codex_not_found`, `invalid_workspace_cwd`, `response_timeout`, `turn_timeout`, `port_exit`, `response_error`, `turn_failed`, `turn_cancelled`, `turn_input_required`. Unit tests for each.

## Medium (M) — would cause spec omissions in tests or behavior

- [ ] **M1** — Restart-recovery contract not explicit
  - SPEC §14.3
  - Action: add to `plan.md` §11 (startup sequence) and add a test that restart produces a clean state and re-dispatches eligible issues.

- [ ] **M2** — Snapshot API per-issue payload fields not fully enumerated
  - SPEC §13.7.2
  - Action: list the full field set in `plan.md` (running.session_id, attempts.restart_count, attempts.current_retry_attempt, last_message, last_event_at, recent_events, last_error, tracked, logs.codex_session_logs); unit tests assert each field present.

- [ ] **M3** — Runner-level issue metadata in turn-start not explicit
  - SPEC §10.2 (issue.identifier + issue.title as title)
  - Action: add to `plan.md` §4 (OpenCodeRunner) and add a test that the runner passes the correct title in the first `prompt`/turn call.

- [ ] **M4** — Max line size 10 MB for runner subprocess not mentioned
  - SPEC §10.1
  - Action: add to `plan.md` §4 and test in `test_runner_opencode.py::test_line_buffer_limit`.

- [ ] **M5** — CLI `--port 0` ephemeral port not mentioned
  - SPEC §13.7
  - Action: add to `plan.md` §10 and to `cli.py`; test in `test_cli.py`.

- [x] **M6** — `tracker.assignee` optional routing filter not in plan
  - Elixir ref (not in SPEC)
  - Action: decide (see QandA G-Q2) and add or drop accordingly.
  - Status: closed 2026-06-02 by G-Q2 resolution (QandA.md). Dropped for v1.

- [ ] **M7** — `worker.ssh_hosts` / `worker.max_concurrent_agents_per_host` schema fields not in plan
  - SPEC §5 + Appendix A
  - Action: add to `symphony.config.schema.Worker` (parse but unused in v1); unit test that the schema round-trips these fields without error.

- [ ] **M8** — Stall-detection disable when `codex.stall_timeout_ms <= 0` not explicit
  - SPEC §8.5
  - Action: add to `plan.md` §7 and test in `test_reconcile.py::test_stall_detection_disabled_when_timeout_le_zero`.

- [ ] **M9** — Reconciliation failure keeps workers running
  - SPEC §8.5
  - Action: add a test that `Tracker.fetch_issue_states_by_ids` returning `{:error, _}` does NOT terminate workers.

- [ ] **M10** — Per-tick defensive reload not in conformance map
  - SPEC §6.2
  - Action: add a test that the orchestrator re-validates on every tick and reloads on WORKFLOW.md change even if watch events were missed.

- [ ] **M11** — CLI shutdown / exit codes not in plan
  - SPEC §17.7
  - Action: add a `shutdown()` test in `test_cli.py` that asserts exit code 0 on clean shutdown, nonzero on `Supervisor.terminate` failure.

- [ ] **M12** — PyPI package name conflict (`symphony` is taken)
  - Action: pick a distribution name (see QandA G-Q3).

- [ ] **M13** — Default `codex.command` and policy fields for OpenCode not specified
  - SPEC §5.3.6, §10
  - Action: pick defaults (see QandA G-Q4 / G-Q5) and document in `plan.md`.

- [ ] **M14** — `docs/CONFORMANCE.md`, `docs/logging.md`, `docs/token_accounting.md` not in `python/` layout
  - Elixir ref
  - Action: add to `python/` layout under `python/docs/`. Tests/lint may add a check that the conformance doc is non-empty and references each §17 bullet.

## Minor (m) — clarity / completeness

- [ ] **m1** — conftest fakes not listed in plan: `FakeClock`, `FakeFileSystem`, `MemoryTracker`, `ScriptedRunner`, `CapturingLogHandler`, `NullObserver`.
- [ ] **m2** — `python/AGENTS.md` content not specified; mirror `elixir/AGENTS.md` structure.
- [ ] **m3** — `test_observability_log.py` referenced in conformance map but missing from the unit-test list.
- [ ] **m4** — 10 MB line buffer test not in any test file yet.
- [ ] **m5** — Layout uses `src/symphony/` (src layout). Plan doesn't justify the choice.
- [ ] **m6** — `tracker.endpoint` for GH Enterprise mentioned but no test; add a unit test that accepts a custom endpoint.
