"""In-memory Tracker adapter (production).

This is the production implementation of the `Tracker` Protocol
for `tracker.kind == "memory"`. It is also useful for local
development and integration tests; the fake in
`tests/_fakes/tracker.py` is a deliberately minimal subset.

The `MemoryTracker`:

- Holds an in-process dict of `Issue` records keyed by `id`.
- `add(issue)`: insert or replace.
- `remove(issue_id)`: delete (idempotent).
- `fetch_*`: the documented async methods.
- `create_comment` / `update_issue_state`: do NOT mutate the
  in-memory record; they record an event in a thread-safe buffer
  that callers (or tests) can drain via `drain_events()` or peek
  via `peek_events()`. This mirrors the Elixir behavior, where
  the orchestrator observes writes by re-fetching.

State names are normalized (lowercase + strip) on lookup per
SPEC §5.1 and §11.3.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from symphony.ids import normalize_issue_state
from symphony.tracker.base import Tracker
from symphony.tracker.normalize import Issue

__all__ = ["MemoryTracker"]


class MemoryTracker:
    """In-process Tracker adapter.

    The buffer of emitted events is a list guarded by an
    `asyncio.Lock` for safe concurrent access. Each event is a
    3-tuple `(kind, issue_id, payload)` where `kind` is one of
    `"comment"` or `"state_update"`.
    """

    def __init__(
        self,
        *,
        issues: dict[str, Issue] | None = None,
        active_states: Sequence[str] | None = None,
    ) -> None:
        self.issues: dict[str, Issue] = dict(issues or {})
        self._active_states: tuple[str, ...] = tuple(
            normalize_issue_state(s) for s in (active_states or [])
        )
        self._events: list[tuple[str, str, Any]] = []
        self._lock = asyncio.Lock()

    def add(self, issue: Issue) -> None:
        self.issues[issue.id] = issue

    def remove(self, issue_id: str) -> None:
        self.issues.pop(issue_id, None)

    def drain_events(self) -> list[tuple[str, str, Any]]:
        """Return all buffered events and clear the buffer."""
        events = self._events
        self._events = []
        return events

    def peek_events(self) -> list[tuple[str, str, Any]]:
        """Return a copy of the buffered events without clearing."""
        return list(self._events)

    async def fetch_candidate_issues(self) -> Sequence[Issue]:
        if not self._active_states:
            return list(self.issues.values())
        wanted = set(self._active_states)
        return [i for i in self.issues.values() if normalize_issue_state(i.state) in wanted]

    async def fetch_issues_by_states(self, state_names: Sequence[str]) -> Sequence[Issue]:
        if not state_names:
            return []
        wanted = {normalize_issue_state(s) for s in state_names}
        return [i for i in self.issues.values() if normalize_issue_state(i.state) in wanted]

    async def fetch_issue_states_by_ids(self, issue_ids: Sequence[str]) -> Sequence[Issue]:
        return [self.issues[i] for i in issue_ids if i in self.issues]

    async def create_comment(self, issue_id: str, body: str) -> None:
        async with self._lock:
            self._events.append(("comment", issue_id, body))

    async def update_issue_state(self, issue_id: str, state_name: str) -> None:
        async with self._lock:
            self._events.append(("state_update", issue_id, state_name))


# Runtime check that the class conforms to the Protocol.
_ = isinstance(MemoryTracker(), Tracker)
