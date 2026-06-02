"""Unit tests for `symphony.orchestrator.dispatch`.

Plan ref: §11 step 16, SPEC §8.2 (candidate selection) + §8.3
(concurrency control).

The dispatcher:
- Filters candidates to those that pass all eligibility checks
  (active+not-terminal, not running, not claimed, slots
  available, blocker rule for `Todo`).
- Sorts by `priority` ASC, then `created_at` ASC, then
  `identifier` ASC.
- Returns the selected issues (caller turns them into workers).
- Counts per-state concurrency (falls back to global when no
  per-state limit).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from symphony.config.schema import SymphonyConfig
from symphony.orchestrator.dispatch import (
    available_slots,
    select_dispatchable_issues,
)
from symphony.orchestrator.state import LiveSession, OrchestratorState
from symphony.tracker.normalize import BlockerRef, Issue


def _config(**overrides: object) -> SymphonyConfig:
    base = {
        "agent": {
            "max_concurrent_agents": 5,
        },
        "tracker": {
            "kind": "memory",
            "active_states": ["open", "todo"],
            "terminal_states": ["closed", "done"],
        },
    }
    for k, v in overrides.items():
        if isinstance(v, dict) and k in base:
            base[k].update(v)  # type: ignore[union-attr]
        else:
            base[k] = v
    return SymphonyConfig.model_validate(base)


def _issue(
    id: str,
    *,
    state: str = "open",
    priority: int | None = None,
    created_at: datetime | None = None,
    blocked_by: tuple[BlockerRef, ...] = (),
) -> Issue:
    if created_at is None:
        created_at = datetime(2024, 1, 1, tzinfo=UTC)
    return Issue(
        id=id,
        identifier=f"#{id}",
        title="t",
        state=state,
        description=None,
        priority=priority,
        branch_name=None,
        url=None,
        labels=(),
        blocked_by=blocked_by,
        created_at=created_at,
        updated_at=created_at,
    )


def _state(*running_ids: str, claimed: tuple[str, ...] = ()) -> OrchestratorState:
    state = OrchestratorState()
    for rid in running_ids:
        state.running[rid] = LiveSession(
            issue_id=rid,
            identifier=f"#{rid}",
            session_id="sess",
            started_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
    state.claimed.update(claimed)
    return state


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------


def test_select_empty() -> None:
    cfg = _config()
    state = _state()
    selected = select_dispatchable_issues(issues=[], state=state, config=cfg, slots_available=5)
    assert selected == []


def test_select_skips_terminal_state() -> None:
    cfg = _config()
    state = _state()
    issues = [_issue("1", state="closed"), _issue("2", state="open")]
    selected = select_dispatchable_issues(issues=issues, state=state, config=cfg, slots_available=5)
    assert [i.id for i in selected] == ["2"]


def test_select_skips_non_active_state() -> None:
    cfg = _config()
    state = _state()
    issues = [_issue("1", state="backlog"), _issue("2", state="open")]
    selected = select_dispatchable_issues(issues=issues, state=state, config=cfg, slots_available=5)
    assert [i.id for i in selected] == ["2"]


def test_select_skips_already_running() -> None:
    cfg = _config()
    state = _state("1")
    issues = [_issue("1", state="open"), _issue("2", state="open")]
    selected = select_dispatchable_issues(issues=issues, state=state, config=cfg, slots_available=5)
    assert [i.id for i in selected] == ["2"]


def test_select_skips_already_claimed() -> None:
    cfg = _config()
    state = _state(claimed=("1",))
    issues = [_issue("1", state="open"), _issue("2", state="open")]
    selected = select_dispatchable_issues(issues=issues, state=state, config=cfg, slots_available=5)
    assert [i.id for i in selected] == ["2"]


def test_select_respects_slot_limit() -> None:
    cfg = _config()
    state = _state()
    issues = [_issue(str(i), state="open") for i in range(10)]
    selected = select_dispatchable_issues(issues=issues, state=state, config=cfg, slots_available=3)
    assert len(selected) == 3


def test_select_skips_zero_slots() -> None:
    cfg = _config()
    state = _state()
    issues = [_issue("1", state="open")]
    selected = select_dispatchable_issues(issues=issues, state=state, config=cfg, slots_available=0)
    assert selected == []


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------


def test_select_sorts_by_priority_ascending() -> None:
    cfg = _config()
    state = _state()
    issues = [
        _issue("a", priority=3),
        _issue("b", priority=1),
        _issue("c", priority=2),
    ]
    selected = select_dispatchable_issues(issues=issues, state=state, config=cfg, slots_available=5)
    assert [i.id for i in selected] == ["b", "c", "a"]


def test_select_sorts_by_created_at_when_priority_equal() -> None:
    cfg = _config()
    state = _state()
    base = datetime(2024, 1, 1, tzinfo=UTC)
    issues = [
        _issue("a", priority=1, created_at=base + timedelta(seconds=2)),
        _issue("b", priority=1, created_at=base + timedelta(seconds=0)),
        _issue("c", priority=1, created_at=base + timedelta(seconds=1)),
    ]
    selected = select_dispatchable_issues(issues=issues, state=state, config=cfg, slots_available=5)
    assert [i.id for i in selected] == ["b", "c", "a"]


def test_select_sorts_by_identifier_lexicographic() -> None:
    """Final tie-breaker is the issue identifier."""
    cfg = _config()
    state = _state()
    base = datetime(2024, 1, 1, tzinfo=UTC)
    issues = [
        _issue("c", priority=1, created_at=base),
        _issue("a", priority=1, created_at=base),
        _issue("b", priority=1, created_at=base),
    ]
    selected = select_dispatchable_issues(issues=issues, state=state, config=cfg, slots_available=5)
    # identifiers are #a, #b, #c
    assert [i.identifier for i in selected] == ["#a", "#b", "#c"]


def test_select_sorts_null_priority_last() -> None:
    cfg = _config()
    state = _state()
    issues = [
        _issue("a", priority=None),
        _issue("b", priority=1),
        _issue("c", priority=2),
    ]
    selected = select_dispatchable_issues(issues=issues, state=state, config=cfg, slots_available=5)
    # null sorts last
    assert [i.id for i in selected] == ["b", "c", "a"]


# ---------------------------------------------------------------------------
# Blocker rule for Todo
# ---------------------------------------------------------------------------


def test_select_todo_with_open_blocker_is_skipped() -> None:
    """If the issue state is `todo` and a blocker is non-terminal,
    do not dispatch (SPEC §8.2)."""
    cfg = _config()
    state = _state()
    blocker = BlockerRef(id="99", identifier="#99", state="open")
    issues = [
        _issue("1", state="todo", blocked_by=(blocker,)),
        _issue("2", state="todo"),
    ]
    selected = select_dispatchable_issues(issues=issues, state=state, config=cfg, slots_available=5)
    # Issue 1 is blocked by an open issue; issue 2 has no blockers.
    assert [i.id for i in selected] == ["2"]


def test_select_todo_with_terminal_blocker_is_ok() -> None:
    cfg = _config()
    state = _state()
    blocker = BlockerRef(id="99", identifier="#99", state="closed")
    issues = [
        _issue("1", state="todo", blocked_by=(blocker,)),
    ]
    selected = select_dispatchable_issues(issues=issues, state=state, config=cfg, slots_available=5)
    assert [i.id for i in selected] == ["1"]


def test_select_todo_with_unknown_blocker_state_treated_as_blocked() -> None:
    """A blocker with no known state is conservatively considered
    non-terminal (i.e., still blocking)."""
    cfg = _config()
    state = _state()
    blocker = BlockerRef(id="99", identifier="#99", state=None)
    issues = [_issue("1", state="todo", blocked_by=(blocker,))]
    selected = select_dispatchable_issues(issues=issues, state=state, config=cfg, slots_available=5)
    assert selected == []


def test_select_non_todo_blocker_does_not_apply() -> None:
    """The blocker rule only applies to `todo` state issues."""
    cfg = _config()
    state = _state()
    blocker = BlockerRef(id="99", identifier="#99", state="open")
    issues = [_issue("1", state="open", blocked_by=(blocker,))]
    selected = select_dispatchable_issues(issues=issues, state=state, config=cfg, slots_available=5)
    assert [i.id for i in selected] == ["1"]


# ---------------------------------------------------------------------------
# Concurrency accounting
# ---------------------------------------------------------------------------


def test_available_slots_helper() -> None:
    """`available_slots = max(max_concurrent - running_count, 0)`."""
    cfg = _config()
    state = _state("1", "2")
    assert available_slots(state, cfg) == 3

    state.running["3"] = LiveSession(
        issue_id="3",
        identifier="#3",
        session_id="sess",
        started_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    state.running["4"] = LiveSession(
        issue_id="4",
        identifier="#4",
        session_id="sess",
        started_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    state.running["5"] = LiveSession(
        issue_id="5",
        identifier="#5",
        session_id="sess",
        started_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    assert available_slots(state, cfg) == 0

    state.running["6"] = LiveSession(
        issue_id="6",
        identifier="#6",
        session_id="sess",
        started_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    # Already over: clamp to 0.
    assert available_slots(state, cfg) == 0
