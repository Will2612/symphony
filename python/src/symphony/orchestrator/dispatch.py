"""Candidate selection and slot accounting (SPEC §8.2 + §8.3).

`select_dispatchable_issues` filters and sorts a list of
candidate issues; the orchestrator's tick handler calls it to
decide which issues to dispatch. Concurrency is computed via
`available_slots`.

Eligibility (SPEC §8.2):
- state is in `active_states` and not in `terminal_states`
- not already running
- not already claimed
- a global slot is available
- blocker rule for `todo` state: no non-terminal blockers

Sorting (SPEC §8.2):
1. `priority` ASC (1..4 preferred; null sorts last)
2. `created_at` ASC
3. `identifier` ASC
"""

from __future__ import annotations

from symphony.config.schema import SymphonyConfig
from symphony.orchestrator.state import OrchestratorState
from symphony.tracker.normalize import Issue


def available_slots(state: OrchestratorState, config: SymphonyConfig) -> int:
    """Global available slots: `max(max_concurrent - running_count, 0)`."""
    return max(config.agent.max_concurrent_agents - state.running_count(), 0)


def _is_blocker_terminal(state: str | None, terminal_states_lower: set[str]) -> bool:
    """A blocker with no state is conservatively considered non-terminal."""
    if state is None:
        return False
    return state.lower() in terminal_states_lower


def _eligible(
    issue: Issue,
    state: OrchestratorState,
    config: SymphonyConfig,
) -> bool:
    active_lower = {s.lower() for s in config.tracker.active_states}
    terminal_lower = {s.lower() for s in config.tracker.terminal_states}
    s = issue.state.lower()
    if s in terminal_lower:
        return False
    if s not in active_lower:
        return False
    if state.is_running(issue.id):
        return False
    if state.is_claimed(issue.id):
        return False
    # Blocker rule: only for `todo` state.
    if s == "todo" and issue.blocked_by:
        active_lower_discard = active_lower  # noqa: F841
        for blocker in issue.blocked_by:
            if not _is_blocker_terminal(blocker.state, terminal_lower):
                return False
    return True


def _sort_key(issue: Issue) -> tuple[int, float, str]:
    """Sort key: priority (None -> 99), created_at epoch, identifier."""
    priority = 99 if issue.priority is None else issue.priority
    created_epoch = issue.created_at.timestamp() if issue.created_at else 0.0
    return (priority, created_epoch, issue.identifier)


def select_dispatchable_issues(
    *,
    issues: list[Issue],
    state: OrchestratorState,
    config: SymphonyConfig,
    slots_available: int,
) -> list[Issue]:
    """Return the dispatchable subset, sorted per SPEC §8.2.

    Caller passes `slots_available` from `available_slots(state, config)`.
    """
    if slots_available <= 0:
        return []
    eligible = [i for i in issues if _eligible(i, state, config)]
    eligible.sort(key=_sort_key)
    return eligible[:slots_available]
