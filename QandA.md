# Q&A

Living document of design questions raised during plan review and implementation, with their resolutions. When a question is resolved, the resolution is recorded here and committed. Open questions are listed in the "Open" section at the top; resolved questions move to the "Resolved" section in chronological order.

---

## Open

### G-Q3

Raised by: plan review 2026-06-02.
Context: The Elixir reference supports `tracker.assignee: "me"` (resolves to viewer) and `tracker.assignee: "<id>"` (route to a specific user). The SPEC itself does not mandate this. For the GitHub adapter, the equivalent is `tracker.assignee: "username"` filtering on the GH assignee field.
Question: ship v1 with assignee-based routing, or drop it (and add later if needed)?
Recommendation in plan-review gap analysis: drop for v1 (not spec-mandated; adds a `viewer` query and a config key). Resolution will determine whether checklist item M6 closes as "done" or "dropped".

### G-Q3 — Python distribution name (PyPI conflict with existing `symphony`)
Raised by: plan review 2026-06-02 (checklist M12). _Not yet resolved._

### G-Q4 — Default `codex.command` for the OpenCode runner

Raised by: plan review 2026-06-02 (checklist M13).
Context: SPEC §5.3.6 says default is `codex app-server`. For the OpenCode runner, the equivalent is either `opencode acp` (long-lived stdio session, supports continuation on the same thread) or `opencode run --format json` (one-shot, no continuation). The trade-off is fidelity to SPEC §10.2 ("continuation turns on the same live thread") vs. time-to-ship.
Recommendation in gap analysis: full ACP for v1 (matches SPEC §10.2 exactly), test with a fake stdio server.

### G-Q5 — Default `codex.approval_policy` / `codex.thread_sandbox` / `codex.turn_sandbox_policy` for the OpenCode runner

Raised by: plan review 2026-06-02 (checklist M13).
Context: SPEC §5.3.6 says these are "implementation-defined" defaults. The Elixir reference uses a strict `reject` policy + `workspace-write` sandbox + workspace-rooted turn-sandbox-policy. For OpenCode, the equivalent depends on what the ACP protocol actually supports.
Options:
- mirror the Elixir strict defaults (translates to ACP equivalents; may not map 1:1)
- start permissive (`auto-approve`, full disk) and require user to opt in to stricter
- ask OpenCode for a recommendation
Recommendation in gap analysis: start with the same high-trust posture described in SPEC §10.5 ("Auto-approve command execution approvals for the session. Auto-approve file-change approvals for the session. Treat user-input-required turns as hard failure."), but document each default explicitly.

---

## Resolved

### G-Q2 — `tracker.assignee` filter: in scope for v1 or follow-up?

Raised by: plan review 2026-06-02.
Context: the Elixir reference supports `tracker.assignee: "me"` (resolves to viewer) and `tracker.assignee: "<id>"` (route to a specific user). The SPEC itself does not mandate this. For the GitHub adapter, the equivalent is `tracker.assignee: "username"` filtering on the GH assignee field.

**Resolution (2026-06-02):** Drop for v1. The SPEC does not require it, and shipping it would force an extra `viewer` resolver on the Linear side and an extra config key on the GitHub side. GitHub adapter will only filter by `state` and `labels` (the spec-mandated filters).

Concretely:
- The Pydantic config schema for `Tracker` does NOT include an `assignee` field in v1.
- `GitHubAdapter.fetch_candidate_issues()` does NOT pass any assignee filter to the GitHub REST API.
- Checklist item **M6** is closed as "dropped" (not "done").
- A follow-up issue can re-introduce it later, by adding the field to the schema and a corresponding filter to the adapter. The QandA G-Q2 entry remains the historical record.

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
