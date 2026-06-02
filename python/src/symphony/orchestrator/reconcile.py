"""Active-run reconciliation (SPEC §8.5).

The orchestrator runs `reconcile_active_runs` every tick. It
does two things:

**Part A — Stall detection.** For each running issue, compute
`elapsed_ms` since `last_codex_timestamp` (or `started_at` if
none). If `elapsed_ms > codex.stall_timeout_ms`, flag the issue
as stalled. The orchestrator's tick handler then terminates the
worker and queues a retry. If `stall_timeout_ms <= 0`, skip
stall detection entirely.

**Part B — Tracker state refresh.** Fetch current issue states
for all running issue IDs. For each running issue:
- terminal state                       -> terminate + clean workspace
- still active                          -> keep running
- neither active nor terminal          -> terminate without cleanup
- state refresh fails                   -> keep worker running

The function returns a `ReconcileOutcome` describing what
happened; the orchestrator dispatches follow-up actions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from symphony.config.schema import SymphonyConfig
from symphony.orchestrator.state import OrchestratorState

if TYPE_CHECKING:
    from symphony.tracker.base import Tracker


@dataclass
class ReconcileOutcome:
    """What `reconcile_active_runs` decided for one tick.

    - `stalled`                  — issue ids that exceeded the
                                   stall timeout.
    - `terminated_due_to_state`  — issue ids whose tracker state
                                   was terminal OR no longer
                                   active (per SPEC §8.5 part B).
    - `refresh_failures`         — issue ids for which the tracker
                                   fetch failed; workers are left
                                   running and retried next tick.
    """

    stalled: list[str] = field(default_factory=list)
    terminated_due_to_state: list[str] = field(default_factory=list)
    refresh_failures: list[str] = field(default_factory=list)


async def reconcile_active_runs(
    *,
    state: OrchestratorState,
    tracker: Tracker,
    config: SymphonyConfig,
    now: datetime,
) -> ReconcileOutcome:
    """Run Part A (stall) and Part B (state refresh) for one tick.

    Caller holds the orchestrator lock.
    """
    outcome = ReconcileOutcome()
    active_ids = list(state.running.keys())
    if not active_ids:
        return outcome

    # Part A — stall detection
    stall_timeout_ms = config.codex.stall_timeout_ms
    if stall_timeout_ms > 0:
        for issue_id, session in state.running.items():
            basis = session.last_codex_timestamp or session.started_at
            elapsed_ms = (now - basis).total_seconds() * 1000
            if elapsed_ms > stall_timeout_ms:
                outcome.stalled.append(issue_id)

    # Part B — state refresh
    try:
        issues = await tracker.fetch_issue_states_by_ids(active_ids)
    except Exception:
        outcome.refresh_failures = list(active_ids)
        return outcome

    by_id = {i.id: i for i in issues}
    active_states_lower = {s.lower() for s in config.tracker.active_states}
    terminal_states_lower = {s.lower() for s in config.tracker.terminal_states}

    for issue_id in active_ids:
        issue = by_id.get(issue_id)
        if issue is None:
            # Not in tracker response: no longer active, not terminal.
            outcome.terminated_due_to_state.append(issue_id)
            state.running.pop(issue_id, None)
            continue
        state_lower = issue.state.lower()
        if state_lower in terminal_states_lower:
            outcome.terminated_due_to_state.append(issue_id)
            state.running.pop(issue_id, None)
            continue
        if state_lower not in active_states_lower:
            # Neither active nor terminal — terminate without
            # workspace cleanup (SPEC §8.5 part B).
            outcome.terminated_due_to_state.append(issue_id)
            state.running.pop(issue_id, None)
            continue
        # Still active: leave the worker running.
    return outcome
