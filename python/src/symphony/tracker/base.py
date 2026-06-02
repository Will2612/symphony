"""Tracker adapter Protocol.

A `Tracker` is a replaceable boundary (plan §3.2) that exposes the
operations required by SPEC §11.1 + §11.5:

- `fetch_candidate_issues()`: return issues that are eligible for
  new dispatches (active states, configured project). Implementations
  decide what "configured project" means.
- `fetch_issues_by_states(state_names)`: return issues in the given
  states (used for startup terminal cleanup per SPEC §16.2).
- `fetch_issue_states_by_ids(issue_ids)`: return the full normalized
  record for the given IDs (used for active-run reconciliation per
  SPEC §16.3).
- `create_comment(issue_id, body)`: post a comment (used by the
  agent during a run; SPEC §11.5 says writes are an agent concern
  but the orchestrator surfaces the capability).
- `update_issue_state(issue_id, state_name)`: transition an issue
  (used for terminal cleanup per SPEC §16.2).

The Protocol is async. Concrete adapters (`MemoryTracker`,
`GitHubTracker`) are injected into the orchestrator at startup
based on `config.tracker.kind`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from symphony.tracker.normalize import Issue

__all__ = ["Tracker"]


@runtime_checkable
class Tracker(Protocol):
    """Async tracker adapter Protocol (SPEC §11.1 + §11.5)."""

    async def fetch_candidate_issues(self) -> Sequence[Issue]:
        """Return issues eligible for dispatch (active states, project)."""
        ...

    async def fetch_issues_by_states(self, state_names: Sequence[str]) -> Sequence[Issue]:
        """Return issues whose state matches any of `state_names`
        (case-insensitive, normalized)."""
        ...

    async def fetch_issue_states_by_ids(self, issue_ids: Sequence[str]) -> Sequence[Issue]:
        """Return the full normalized record for each ID. Missing IDs
        are silently skipped (the orchestrator's reconciliation
        tolerates this)."""
        ...

    async def create_comment(self, issue_id: str, body: str) -> None:
        """Post a comment on the given issue."""
        ...

    async def update_issue_state(self, issue_id: str, state_name: str) -> None:
        """Transition the issue to the given state (best-effort)."""
        ...
