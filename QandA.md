# Q&A

Living document of design questions raised during plan review and implementation, with their resolutions. When a question is resolved, the resolution is recorded here and committed. Open questions are listed in the "Open" section at the top; resolved questions move to the "Resolved" section in chronological order.

---

## Open

### G-Q3

Raised by: plan review 2026-06-02.
Context: The Elixir reference supports `tracker.assignee: "me"` (resolves to viewer) and `tracker.assignee: "<id>"` (route to a specific user). The SPEC itself does not mandate this. For the GitHub adapter, the equivalent is `tracker.assignee: "username"` filtering on the GH assignee field.
Question: ship v1 with assignee-based routing, or drop it (and add later if needed)?
Recommendation in plan-review gap analysis: drop for v1 (not spec-mandated; adds a `viewer` query and a config key). Resolution will determine whether checklist item M6 closes as "done" or "dropped".

### G-Q4

### G-Q5

### G-Q5 — Default `codex.approval_policy` / `codex.thread_sandbox` / `codex.turn_sandbox_policy` for the OpenCode runner
Raised by: plan review 2026-06-02 (checklist M13). _Not yet resolved._

---

## Resolved

### G-Q4 — Default `codex.command` for the OpenCode runner

Raised by: plan review 2026-06-02 (checklist M13).
Context: SPEC §5.3.6 says default is `codex app-server`. For the OpenCode runner, the equivalent is either `opencode acp` (long-lived stdio session, supports continuation on the same thread) or `opencode run --format json` (one-shot, no continuation). The trade-off is fidelity to SPEC §10.2 ("continuation turns on the same live thread") vs. time-to-ship.

**Resolution (2026-06-02):** `opencode acp` (the Agent Client Protocol server over stdio). The default `codex.command` becomes `opencode acp` and the runner speaks JSON-RPC newline-delimited over the subprocess's stdin/stdout. This is the only option that matches SPEC §10.2 exactly: continuation turns happen on the same `live_session.thread_id` and the same subprocess.

Concretely:
- `OpenCodeRunner` launches `bash -lc "opencode acp"` with cwd = workspace and PATH inherited.
- 10 MB line buffer per §10.1.
- `runner/base.py` defines an `ACPMessage` parser; `runner/opencode.py` translates ACP events into the SPEC §10.4 event vocabulary.
- Tests inject a fake stdio server (an `asyncio` task that reads lines from one end of an in-memory pipe and writes scripted responses) so the test does not need a real `opencode` binary.
- Checklist item **M13** is closed for the `codex.command` part (the policies are settled in G-Q5).

### G-Q2 — `tracker.assignee` filter: in scope for v1 or follow-up?

Raised by: plan review 2026-06-02.
Context: the Elixir reference supports `tracker.assignee: "me"` (resolves to viewer) and `tracker.assignee: "<id>"` (route to a specific user). The SPEC itself does not mandate this. For the GitHub adapter, the equivalent is `tracker.assignee: "username"` filtering on the GH assignee field.

**Resolution (2026-06-02):** Drop for v1. The SPEC does not require it, and shipping it would force an extra `viewer` resolver on the Linear side and an extra config key on the GitHub side. GitHub adapter will only filter by `state` and `labels` (the spec-mandated filters).

Concretely:
- The Pydantic config schema for `Tracker` does NOT include an `assignee` field in v1.
- `GitHubAdapter.fetch_candidate_issues()` does NOT pass any assignee filter to the GitHub REST API.
- Checklist item **M6** is closed as "dropped" (not "done").
- A follow-up issue can re-introduce it later, by adding the field to the schema and a corresponding filter to the adapter. The QandA G-Q2 entry remains the historical record.

### G-Q3 — Python distribution name (PyPI conflict with existing `symphony`)

Raised by: plan review 2026-06-02 (checklist M12).
Context: the bare distribution name `symphony` is already installed locally (`symphony 0.1.0` at `/home/will/.local/lib/python3.12/site-packages`).

**Resolution (2026-06-02):** `symphony-py`. The CLI command is `symphony` (an `entry_points` console script named `symphony = symphony.cli:main`); the PyPI distribution is `symphony-py`. The importable Python package is `symphony` (we still own that name inside the venv; the conflict is only at the wheel/distribution level). This mirrors the `elixir/` directory naming and keeps imports clean.

Concretely:
- `python/pyproject.toml` has `[project] name = "symphony-py"`.
- `python/src/symphony/` is the importable package.
- `python/Makefile` builds a `dist/symphony_py-*.whl`.
- Checklist item **M12** is closed.
- The local pre-existing `symphony 0.1.0` install is left alone; users pip-installing `symphony-py` into a fresh venv will get only our code.

### G-Q1 — Run-attempt state machine + claim states: first-class enums or string/dict keys?

Raised by: plan review 2026-06-02.
Context: SPEC §7.1 (Issue Orchestration States: Unclaimed / Claimed / Running / RetryQueued / Released) and §7.2 (Run-Attempt Lifecycle: PreparingWorkspace → BuildingPrompt → LaunchingAgentProcess → InitializingSession → StreamingTurn → Finishing → Succeeded / Failed / TimedOut / Stalled / CanceledByReconciliation).

**Resolution (2026-06-02):** First-class Python enums. Add `ClaimState` and `RunPhase` `enum.Enum` subclasses to `src/symphony/orchestrator/state.py` and surface them as typed fields on `LiveSession` (e.g. `claim_state: ClaimState`, `current_phase: RunPhase`). Use `match/case` over enums for state transitions, which gives compile-time exhaustiveness under `mypy --strict`.

Concretely this means:
- `ClaimState` has values: `UNCLAIMED`, `CLAIMED`, `RUNNING`, `RETRY_QUEUED`, `RELEASED`.
- `RunPhase` has values: `PREPARING_WORKSPACE`, `BUILDING_PROMPT`, `LAUNCHING_AGENT_PROCESS`, `INITIALIZING_SESSION`, `STREAMING_TURN`, `FINISHING`, `SUCCEEDED`, `FAILED`, `TIMED_OUT`, `STALLED`, `CANCELED_BY_RECONCILIATION`.
- The state-transition graph from §7.1 and §7.2 is implemented as `ALLOWED_TRANSITIONS: dict[Enum, frozenset[Enum]]` so the orchestrator can assert every transition is valid before applying it.
- Snapshot API (§13.7) serializes enums as their `value` string.
- Checklist items **C2** and **C3** are closed by this resolution.

Why not strings: it loses compile-time exhaustiveness and lets typos slip in. Why not dict-keyed: the enum-based transition graph above gives the same flexibility with better typing.
