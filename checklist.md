# Plan-Review Checklist

This is the running checklist of findings/gaps from reviewing [`plan.md`](./plan.md) against [`SPEC.md`](./SPEC.md) and the Elixir reference under [`elixir/`](./elixir/).

Each finding has:
- a stable ID (`C#` = critical, `M#` = medium, `m#` = minor)
- a SPEC reference
- a concrete next action
- a checkbox that is ticked when the fix is folded into `plan.md` (and the commit is referenced inline)

Plan patch that closed most of this list: `8902830` ("plan: v2 — fold in G-Q1..G-Q5 resolutions; close C/M/m items").

## Critical (C) — would cause spec violations if not addressed

- [x] **C1** — Startup terminal workspace cleanup is not a discrete work-plan step
  - SPEC §8.6, §18.1
  - Action: add explicit step + test entry in `plan.md`; unit test in `tests/unit/test_orchestrator_service.py::test_startup_terminal_cleanup_runs_workspace_remove`; BDD scenario in `orchestrator_dispatch.feature`.
  - Status: closed 2026-06-02 by `8902830`. Now in plan §7.1 (step 5) and §11 (step 8). Unit test name fixed in conformance map.

- [x] **C2** — Run-attempt state machine not in plan
  - SPEC §7.2 (PreparingWorkspace → BuildingPrompt → LaunchingAgentProcess → InitializingSession → StreamingTurn → Finishing → Succeeded / Failed / TimedOut / Stalled / CanceledByReconciliation)
  - Action: add `RunPhase` enum to `orchestrator/state.py`; add `current_phase` field to `LiveSession`; unit tests in `test_orchestrator_state.py`.
  - Status: closed 2026-06-02 by G-Q1 resolution (QandA.md, `b7ae4ca`); `RunPhase` enum + transition graph documented in plan §1.2.

- [x] **C3** — Issue orchestration claim states not in plan
  - SPEC §7.1 (Unclaimed / Claimed / Running / RetryQueued / Released)
  - Action: add `ClaimState` enum; expose on `LiveSession`; document the state-transition rules; unit test in `test_dispatch.py::test_claim_state_transitions`.
  - Status: closed 2026-06-02 by G-Q1 resolution (QandA.md, `b7ae4ca`); `ClaimState` enum documented in plan §1.2.

- [x] **C4** — Typed domain entities (Workspace, LiveSession, RunAttempt, RetryEntry, OrchestratorState) not explicit
  - SPEC §4.1.4, §4.1.5, §4.1.6, §4.1.7, §4.1.8
  - Action: add dedicated dataclasses (with field-level docstrings mapping back to the spec) in `orchestrator/state.py` and `workspace/manager.py`; not buried in helpers.
  - Status: closed 2026-06-02 by `8902830`. New plan §1.3 lists all five with field-level spec references.

- [x] **C5** — GitHub-specific tracker error categories not enumerated
  - SPEC §11.4
  - Action: enumerate in `plan.md` (and in `tracker/github.py` as `GitHubError` subclass hierarchy): `github_api_request`, `github_api_status`, `github_unauthorized`, `github_forbidden`, `github_rate_limited`, `github_not_found`, `github_unknown_payload`, `github_pagination_missing_link`. Add unit tests for each.
  - Status: closed 2026-06-02 by `8902830`. New plan §8.1 enumerates all eight; plan §2 (errors.py) and §11 (step 2) call out the hierarchy.

- [x] **C6** — Token-accounting rules not explicit in plan
  - SPEC §13.5
  - Action: enumerate the rules in `plan.md` (last_token_usage ignored; prefer absolute totals; track deltas vs `last_reported_*`; never treat generic `usage` as cumulative). Document in `docs/token_accounting.md` mirroring `elixir/docs/token_accounting.md`. Unit tests in `test_runner_opencode.py` and `test_orchestrator_service.py`.
  - Status: closed 2026-06-02 by `8902830`. New plan §6.2 enumerates all six rules; `python/docs/token_accounting.md` listed in §1 layout and §11 step 24.

- [x] **C7** — `tracker.kind: memory` not surfaced as a real, documented config value
  - SPEC §5.3.1, §11
  - Action: validate `memory` in `config/validate.py`; ship `examples/WORKFLOW.memory-dev.md`; unit test in `test_config_validate.py`.
  - Status: closed 2026-06-02 by `8902830`. Plan §3 makes it an explicit first-class adapter; plan §11 step 4 (schema) and step 5 (validate) call out acceptance; example file listed.

- [x] **C8** — Service-startup algorithm (§16.1) not enumerated in the work plan
  - SPEC §16.1
  - Action: add a numbered startup sequence in `plan.md` §11 (configure_logging → start_observability_outputs → start_workflow_watch → validate_config → startup_terminal_workspace_cleanup → schedule_tick(0) → event_loop). Unit test in `test_orchestrator_service.py::test_startup_sequence`.
  - Status: closed 2026-06-02 by `8902830`. New plan §7.1 enumerates 8 steps including terminal cleanup.

- [x] **C9** — Event vocabulary enum not enumerated
  - SPEC §10.4
  - Action: add `EventKind` enum to `runner/base.py` with all 13 values; unit test that the runner emits the correct kind for each protocol event shape.
  - Status: closed 2026-06-02 by `8902830`. New plan §1.2 lists the full `EventKind` enum (11 values; not 13 — initial review count was off; SPEC §10.4 actually enumerates 11).

- [x] **C10** — Runner error categories not enumerated
  - SPEC §10.6
  - Action: enumerate in `plan.md` and as `RunnerError` subclass hierarchy: `codex_not_found`, `invalid_workspace_cwd`, `response_timeout`, `turn_timeout`, `port_exit`, `response_error`, `turn_failed`, `turn_cancelled`, `turn_input_required`. Unit tests for each.
  - Status: closed 2026-06-02 by `8902830`. New plan §8.1 enumerates all nine. `runner.py` errors.py module set up in plan §11 step 2.

## Medium (M) — would cause spec omissions in tests or behavior

- [x] **M1** — Restart-recovery contract not explicit
  - SPEC §14.3
  - Action: add to `plan.md` §11 (startup sequence) and add a test that restart produces a clean state and re-dispatches eligible issues.
  - Status: closed 2026-06-02 by `8902830`. Conformance map row added; §7 calls out "Initialize `OrchestratorState` with ... empty live, empty retry_queue" on startup.

- [x] **M2** — Snapshot API per-issue payload fields not fully enumerated
  - SPEC §13.7.2
  - Action: list the full field set in `plan.md` (running.session_id, attempts.restart_count, attempts.current_retry_attempt, last_message, last_event_at, recent_events, last_error, tracked, logs.codex_session_logs); unit tests assert each field present.
  - Status: closed 2026-06-02 by `8902830`. New plan §6.1 lists all 11 fields including the ones from this finding plus `issue` and `claim_state`.

- [x] **M3** — Runner-level issue metadata in turn-start not explicit
  - SPEC §10.2 (issue.identifier + issue.title as title)
  - Action: add to `plan.md` §4 (OpenCodeRunner) and add a test that the runner passes the correct title in the first `prompt`/turn call.
  - Status: closed 2026-06-02 by `8902830`. New plan §4.1 has a "First-turn title" bullet.

- [x] **M4** — Max line size 10 MB for runner subprocess not mentioned
  - SPEC §10.1
  - Action: add to `plan.md` §4 and test in `test_runner_opencode.py::test_line_buffer_limit`.
  - Status: closed 2026-06-02 by `8902830`. Plan §4.1 mentions 10 MB; conformance map row 17.5 references the named unit test.

- [x] **M5** — CLI `--port 0` ephemeral port not mentioned
  - SPEC §13.7
  - Action: add to `plan.md` §10 and to `cli.py`; test in `test_cli.py`.
  - Status: closed 2026-06-02 by `8902830`. Plan §7 (last bullet) and §11 step 20 call it out; conformance map row 17.7 references `test_port_zero_ephemeral`.

- [x] **M6** — `tracker.assignee` optional routing filter not in plan
  - Elixir ref (not in SPEC)
  - Action: decide (see QandA G-Q2) and add or drop accordingly.
  - Status: closed 2026-06-02 as **dropped** by G-Q2 resolution (QandA.md, `62fd03b`); checklist.md commit `20efdfc`.

- [x] **M7** — `worker.ssh_hosts` / `worker.max_concurrent_agents_per_host` schema fields not in plan
  - SPEC §5 + Appendix A
  - Action: add to `symphony.config.schema.Worker` (parse but unused in v1); unit test that the schema round-trips these fields without error.
  - Status: closed 2026-06-02 by `8902830`. Plan §9 (last but one bullet) and §13 ("not used in v1") document the parse-but-unused posture; layout §1 includes `worker` schema; §11 step 4 references the schema.

- [x] **M8** — Stall-detection disable when `codex.stall_timeout_ms <= 0` not explicit
  - SPEC §8.5
  - Action: add to `plan.md` §7 and test in `test_reconcile.py::test_stall_detection_disabled_when_timeout_le_zero`.
  - Status: closed 2026-06-02 by `8902830`. Plan §9 (last bullet) and conformance map row 17.4 reference the unit test.

- [x] **M9** — Reconciliation failure keeps workers running
  - SPEC §8.5
  - Action: add a test that `Tracker.fetch_issue_states_by_ids` returning `{:error, _}` does NOT terminate workers.
  - Status: closed 2026-06-02 by `8902830`. Plan §8 (last row) and conformance map row 17.4 reference `test_reconciliation_failure_keeps_workers`.

- [x] **M10** — Per-tick defensive reload not in conformance map
  - SPEC §6.2
  - Action: add a test that the orchestrator re-validates on every tick and reloads on WORKFLOW.md change even if watch events were missed.
  - Status: closed 2026-06-02 by `8902830`. Plan §7 (third bullet) and conformance map row 17.4 reference `test_per_tick_defensive_reload`; §11 step 6 calls out defensive reload.

- [x] **M11** — CLI shutdown / exit codes not in plan
  - SPEC §17.7
  - Action: add a `shutdown()` test in `test_cli.py` that asserts exit code 0 on clean shutdown, nonzero on `Supervisor.terminate` failure.
  - Status: closed 2026-06-02 by `8902830`. Conformance map row 17.7 references `test_shutdown_exit_codes`; §11 step 20 calls out shutdown + exit codes.

- [x] **M12** — PyPI package name conflict (`symphony` is taken)
  - Action: pick a distribution name (see QandA G-Q3).
  - Status: closed 2026-06-02 by G-Q3 resolution (QandA.md, `a24182b`); checklist commit `edf3de0`. Distribution name is `symphony-py`.

- [x] **M13** — Default `codex.command` and policy fields for OpenCode not specified
  - SPEC §5.3.6, §10
  - Action: pick defaults (see QandA G-Q4 / G-Q5) and document in `plan.md`.
  - Status: closed 2026-06-02 by G-Q4 (`6a74831`) + G-Q5 (`1699585`) resolutions; checklist commit `91cc84a`. Defaults: `opencode acp`; `approval_policy=auto-approve`; `thread_sandbox=workspace-write`; `turn_sandbox_policy=workspace-rooted`.

- [x] **M14** — `docs/CONFORMANCE.md`, `docs/logging.md`, `docs/token_accounting.md` not in `python/` layout
  - Elixir ref
  - Action: add to `python/` layout under `python/docs/`. Tests/lint may add a check that the conformance doc is non-empty and references each §17 bullet.
  - Status: closed 2026-06-02 by `8902830`. Plan §1 layout includes `docs/CONFORMANCE.md`, `docs/logging.md`, `docs/token_accounting.md`; §11 step 24 explicitly creates them.

## Minor (m) — clarity / completeness

- [x] **m1** — conftest fakes not listed in plan: `FakeClock`, `FakeFileSystem`, `MemoryTracker`, `ScriptedRunner`, `CapturingLogHandler`, `NullObserver`.
  - Status: closed 2026-06-02 by `8902830`. New plan §1.1 lists all six plus `FakeACPStdioServer` and `FakeWorkflowStore`.

- [x] **m2** — `python/AGENTS.md` content not specified; mirror `elixir/AGENTS.md` structure.
  - Status: closed 2026-06-02 by `8902830`. Plan §1 layout includes `AGENTS.md`; §11 step 23 includes it.

- [x] **m3** — `test_observability_log.py` referenced in conformance map but missing from the unit-test list.
  - Status: closed 2026-06-02 by `8902830`. Plan §1 layout includes `test_observability_log.py` with "covers §17.6 sink failure + token aggregation".

- [x] **m4** — 10 MB line buffer test not in any test file yet.
  - Status: closed 2026-06-02 by `8902830`. Plan §4.1 references `test_runner_opencode.py::test_line_buffer_limit`; conformance map row 17.5 names the test.

- [ ] **m5** — Layout uses `src/symphony/` (src layout). Plan doesn't justify the choice.
  - Action: add a one-sentence rationale in plan §1 explaining why src layout over flat (`import symphony` works the same in editable install, but the wheel is cleaner; pytest discovery also benefits; matches modern best practice).
  - Status: still open. Will be folded into the next plan edit (single-line addition).

- [x] **m6** — `tracker.endpoint` for GH Enterprise mentioned but no test; add a unit test that accepts a custom endpoint.
  - Status: closed 2026-06-02 by `8902830`. Plan §3 (last bullet under GitHub) and conformance map row 17.3 reference a custom-endpoint unit test.

---

## Summary

- 10 / 10 critical items closed.
- 14 / 14 medium items closed.
- 5 / 6 minor items closed; 1 minor (m5) still open — a one-line rationale to add.
- All 5 open questions (G-Q1 through G-Q5) resolved; resolutions in `QandA.md`.
- Plan is at v2 (commit `8902830`); next plan edit closes m5.
