"""MemoryTracker — in-memory Tracker Protocol implementation.

Step 1 skeleton: implements the Tracker Protocol shape from
`plan.md` §3 against an in-process dict. Doubles as a real
`tracker.kind: "memory"` adapter for local dev (per checklist C7).

Production logic (label filtering, lowercased labels, pagination
order, error mapping) lands in the tracker steps (plan §11
steps 10-12).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass
class Issue:
    """Minimal Issue shape; the real type lives in `symphony.tracker.normalize`."""

    id: str
    identifier: str
    title: str
    state: str
    labels: tuple[str, ...] = ()


@dataclass
class MemoryTracker:
    """An in-memory Tracker adapter.

    The shape below is the minimum needed for tests to construct one
    and assert behavior; it is NOT yet a fully-typed Protocol
    implementation. The Protocol conformance is added in the tracker
    work-plan step.
    """

    name: str = "memory"
    issues: dict[str, Issue] = field(default_factory=dict)

    def add(self, issue: Issue) -> None:
        self.issues[issue.id] = issue

    async def fetch_candidate_issues(self) -> Sequence[Issue]:
        return list(self.issues.values())

    async def fetch_issues_by_states(self, state_names: Sequence[str]) -> Sequence[Issue]:
        states = set(state_names)
        return [i for i in self.issues.values() if i.state in states]

    async def fetch_issue_states_by_ids(self, ids: Sequence[str]) -> Sequence[Issue]:
        return [self.issues[i] for i in ids if i in self.issues]

    async def create_comment(self, issue_id: str, body: str) -> None:
        return None

    async def update_issue_state(self, issue_id: str, state_name: str) -> None:
        if issue_id in self.issues:
            self.issues[issue_id].state = state_name
