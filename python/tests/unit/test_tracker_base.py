"""Unit tests for `symphony.tracker.base` (Protocol) and
`symphony.tracker.memory` (in-process adapter).

Plan ref: §11 step 11, SPEC §11.1.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from symphony.tracker.base import Tracker
from symphony.tracker.memory import MemoryTracker
from symphony.tracker.normalize import Issue


@runtime_checkable
class _ProtocolProbe(Protocol):
    """Helper to verify runtime protocol conformance."""

    async def fetch_candidate_issues(self) -> Sequence[Issue]: ...
    async def fetch_issues_by_states(self, state_names: Sequence[str]) -> Sequence[Issue]: ...
    async def fetch_issue_states_by_ids(self, issue_ids: Sequence[str]) -> Sequence[Issue]: ...
    async def create_comment(self, issue_id: str, body: str) -> None: ...
    async def update_issue_state(self, issue_id: str, state_name: str) -> None: ...


def _issue(
    id: str = "iss-1",
    identifier: str = "ABC-1",
    state: str = "open",
    title: str = "Test",
    **kwargs: object,
) -> Issue:
    return Issue(
        id=id,
        identifier=identifier,
        title=title,
        state=state,
        description=None,
        priority=None,
        branch_name=None,
        url=None,
        **kwargs,
    )


def test_memory_tracker_conforms_to_protocol() -> None:
    tracker = MemoryTracker()
    # runtime_checkable: MemoryTracker should be a Tracker.
    assert isinstance(tracker, Tracker)
    assert isinstance(tracker, _ProtocolProbe)


async def test_memory_tracker_fetch_candidate_issues_returns_all() -> None:
    tracker = MemoryTracker()
    tracker.add(_issue(id="1", state="open"))
    tracker.add(_issue(id="2", state="closed"))
    issues = await tracker.fetch_candidate_issues()
    assert len(issues) == 2
    ids = {i.id for i in issues}
    assert ids == {"1", "2"}


async def test_memory_tracker_fetch_candidate_issues_filters_by_active_states() -> None:
    """When configured with active_states, only matching issues are
    returned (normalized lowercase)."""
    tracker = MemoryTracker(active_states=("open",))
    tracker.add(_issue(id="1", state="open"))
    tracker.add(_issue(id="2", state="closed"))
    tracker.add(_issue(id="3", state="Open"))  # case-insensitive
    issues = await tracker.fetch_candidate_issues()
    ids = {i.id for i in issues}
    assert ids == {"1", "3"}


async def test_memory_tracker_no_active_states_returns_all() -> None:
    tracker = MemoryTracker()
    tracker.add(_issue(id="1", state="open"))
    tracker.add(_issue(id="2", state="closed"))
    issues = await tracker.fetch_candidate_issues()
    assert len(issues) == 2


async def test_memory_tracker_fetch_issues_by_states() -> None:
    tracker = MemoryTracker()
    tracker.add(_issue(id="1", state="open"))
    tracker.add(_issue(id="2", state="closed"))
    tracker.add(_issue(id="3", state="in_progress"))
    issues = await tracker.fetch_issues_by_states(["open", "in_progress"])
    ids = {i.id for i in issues}
    assert ids == {"1", "3"}


async def test_memory_tracker_fetch_issues_by_states_normalizes() -> None:
    """State names are normalized (lowercase, strip) before lookup."""
    tracker = MemoryTracker()
    tracker.add(_issue(id="1", state="Open"))
    tracker.add(_issue(id="2", state="Closed"))
    issues = await tracker.fetch_issues_by_states(["  open  ", "CLOSED"])
    ids = {i.id for i in issues}
    assert ids == {"1", "2"}


async def test_memory_tracker_fetch_issues_by_states_empty_returns_empty() -> None:
    """Empty state list returns empty without iteration (SPEC §17)."""
    tracker = MemoryTracker()
    tracker.add(_issue(id="1", state="open"))
    issues = await tracker.fetch_issues_by_states([])
    assert issues == []


async def test_memory_tracker_fetch_issue_states_by_ids() -> None:
    tracker = MemoryTracker()
    tracker.add(_issue(id="1", state="open"))
    tracker.add(_issue(id="2", state="closed"))
    issues = await tracker.fetch_issue_states_by_ids(["1", "3"])
    # Missing ID is silently skipped.
    assert [i.id for i in issues] == ["1"]


async def test_memory_tracker_fetch_issue_states_by_ids_empty() -> None:
    tracker = MemoryTracker()
    issues = await tracker.fetch_issue_states_by_ids([])
    assert issues == []


async def test_memory_tracker_create_comment_records_event() -> None:
    tracker = MemoryTracker()
    await tracker.create_comment("iss-1", "hello world")
    events = tracker.drain_events()
    assert ("comment", "iss-1", "hello world") in events


async def test_memory_tracker_update_issue_state_records_event() -> None:
    tracker = MemoryTracker()
    await tracker.update_issue_state("iss-1", "closed")
    events = tracker.drain_events()
    assert ("state_update", "iss-1", "closed") in events


async def test_memory_tracker_update_issue_state_does_not_mutate_local_issue() -> None:
    """update_issue_state should not mutate the in-memory record; it
    only emits an event (mirroring the Elixir behavior). The orchestrator
    re-fetches via fetch_issue_states_by_ids to see the new state."""
    tracker = MemoryTracker()
    issue = _issue(id="iss-1", state="open")
    tracker.add(issue)
    await tracker.update_issue_state("iss-1", "closed")
    # The in-memory record is unchanged.
    assert tracker.issues["iss-1"].state == "open"


def test_memory_tracker_drain_events_clears_buffer() -> None:
    async def _go() -> None:
        tracker = MemoryTracker()
        await tracker.create_comment("iss-1", "first")
        await tracker.create_comment("iss-2", "second")
        events1 = tracker.drain_events()
        assert len(events1) == 2
        events2 = tracker.drain_events()
        assert events2 == []

    asyncio.run(_go())


def test_memory_tracker_remove() -> None:
    tracker = MemoryTracker()
    tracker.add(_issue(id="iss-1"))
    tracker.remove("iss-1")
    assert "iss-1" not in tracker.issues


def test_memory_tracker_remove_missing_is_noop() -> None:
    tracker = MemoryTracker()
    tracker.remove("nonexistent")
    assert tracker.issues == {}


def test_memory_tracker_peek_events() -> None:
    """peek_events returns a copy without clearing."""

    async def _go() -> None:
        tracker = MemoryTracker()
        await tracker.create_comment("iss-1", "x")
        a = tracker.peek_events()
        b = tracker.peek_events()
        assert a == b
        # Buffer is preserved.
        assert len(tracker.drain_events()) == 1

    asyncio.run(_go())


def test_tracker_protocol_has_all_required_methods() -> None:
    """The Tracker Protocol declares all five methods required by
    SPEC §11.1 + writes per §11.5."""
    members = {name for name in dir(Tracker) if not name.startswith("_")}
    assert "fetch_candidate_issues" in members
    assert "fetch_issues_by_states" in members
    assert "fetch_issue_states_by_ids" in members
    assert "create_comment" in members
    assert "update_issue_state" in members


async def test_memory_tracker_concurrent_fetches() -> None:
    """Multiple async fetches can be issued in parallel."""
    tracker = MemoryTracker()
    for i in range(5):
        tracker.add(_issue(id=str(i), state="open"))

    results = await asyncio.gather(
        tracker.fetch_candidate_issues(),
        tracker.fetch_issues_by_states(["open"]),
        tracker.fetch_issue_states_by_ids(["0", "1"]),
    )
    assert len(results[0]) == 5
    assert len(results[1]) == 5
    assert len(results[2]) == 2
