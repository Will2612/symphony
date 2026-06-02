"""Unit tests for `symphony.orchestrator.reconcile`.

Plan ref: §11 step 16, SPEC §8.5 (active-run reconciliation).

Reconciliation runs every tick and has two parts:

**Part A — Stall detection.** For each running issue, compute
`elapsed_ms` since `last_codex_timestamp` (or `started_at` if
none). If `elapsed_ms > codex.stall_timeout_ms`, terminate the
worker and queue a retry. If `stall_timeout_ms <= 0`, skip stall
detection entirely.

**Part B — Tracker state refresh.** Fetch current issue states
for all running issue IDs. For each running issue:
- terminal state -> terminate worker and clean workspace
- still active  -> update in-memory snapshot
- neither active nor terminal -> terminate without cleanup

If state refresh fails, keep workers running and try again on
the next tick.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from symphony.config.schema import SymphonyConfig
from symphony.orchestrator.reconcile import (
    reconcile_active_runs,
)
from symphony.orchestrator.state import LiveSession, OrchestratorState
from symphony.tracker.normalize import Issue


def _config(**overrides: object) -> SymphonyConfig:
    base = {
        "agent": {
            "max_retry_backoff_ms": 300_000,
            "max_turns": 5,
        },
        "codex": {
            "stall_timeout_ms": 60_000,
        },
        "tracker": {
            "kind": "memory",
            "active_states": ["open"],
            "terminal_states": ["closed"],
        },
    }
    for k, v in overrides.items():
        if isinstance(v, dict) and k in base:
            base[k].update(v)  # type: ignore[union-attr]
        else:
            base[k] = v
    return SymphonyConfig.model_validate(base)


@dataclass
class _FakeTracker:
    """Memory-backed tracker for tests."""

    issues: dict[str, Issue] = field(default_factory=dict)
    fetch_raises: Exception | None = None

    async def fetch_candidate_issues(self) -> list[Issue]:
        return list(self.issues.values())

    async def fetch_issues_by_states(self, state_names: list[str]) -> list[Issue]:
        wanted = {s.lower() for s in state_names}
        return [i for i in self.issues.values() if i.state.lower() in wanted]

    async def fetch_issue_states_by_ids(self, issue_ids: list[str]) -> list[Issue]:
        if self.fetch_raises is not None:
            raise self.fetch_raises
        return [self.issues[i] for i in issue_ids if i in self.issues]

    async def create_comment(self, issue_id: str, body: str) -> None:
        pass

    async def update_issue_state(self, issue_id: str, state_name: str) -> None:
        if issue_id in self.issues:
            current = self.issues[issue_id]
            self.issues[issue_id] = Issue(
                id=current.id,
                identifier=current.identifier,
                title=current.title,
                state=state_name,
                description=current.description,
                priority=current.priority,
                branch_name=current.branch_name,
                url=current.url,
                labels=current.labels,
                blocked_by=current.blocked_by,
                created_at=current.created_at,
                updated_at=current.updated_at,
            )


def _issue(id: str, *, state: str = "open") -> Issue:
    return Issue(
        id=id,
        identifier=f"#{id}",
        title="t",
        state=state,
        description=None,
        priority=None,
        branch_name=None,
        url=None,
        labels=(),
        blocked_by=(),
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        updated_at=datetime(2024, 1, 1, tzinfo=UTC),
    )


def _session(
    issue_id: str,
    *,
    started_at: datetime,
    last_event: datetime | None = None,
) -> LiveSession:
    return LiveSession(
        issue_id=issue_id,
        identifier=f"#{issue_id}",
        session_id="sess-1",
        started_at=started_at,
        last_codex_timestamp=last_event,
    )


# ---------------------------------------------------------------------------
# Part A — stall detection
# ---------------------------------------------------------------------------


async def test_reconcile_skips_when_no_running() -> None:
    cfg = _config()
    state = OrchestratorState()
    tracker = _FakeTracker()
    outcome = await reconcile_active_runs(
        state=state,
        tracker=tracker,
        config=cfg,
        now=datetime(2024, 1, 1, tzinfo=UTC),
    )
    assert outcome.stalled == []
    assert outcome.terminated_due_to_state == []
    assert outcome.refresh_failures == []


async def test_reconcile_detects_stall() -> None:
    cfg = _config()
    state = OrchestratorState()
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    state.running["iss-1"] = _session("iss-1", started_at=now - timedelta(seconds=120))
    tracker = _FakeTracker(issues={"iss-1": _issue("iss-1", state="open")})
    outcome = await reconcile_active_runs(state=state, tracker=tracker, config=cfg, now=now)
    assert "iss-1" in outcome.stalled


async def test_reconcile_uses_last_codex_timestamp_for_stall() -> None:
    """If last_codex_timestamp is set, that's the basis for the
    stall check (not started_at)."""
    cfg = _config()
    state = OrchestratorState()
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    state.running["iss-1"] = _session(
        "iss-1",
        started_at=now - timedelta(seconds=300),  # very old
        last_event=now - timedelta(seconds=10),  # but a recent event
    )
    tracker = _FakeTracker(issues={"iss-1": _issue("iss-1", state="open")})
    outcome = await reconcile_active_runs(state=state, tracker=tracker, config=cfg, now=now)
    assert outcome.stalled == []  # not stalled because of recent event


async def test_reconcile_stall_disabled_when_timeout_zero() -> None:
    """stall_timeout_ms <= 0 disables stall detection entirely."""
    cfg = _config(codex={"stall_timeout_ms": 0})
    state = OrchestratorState()
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    state.running["iss-1"] = _session("iss-1", started_at=now - timedelta(seconds=99999))
    tracker = _FakeTracker(issues={"iss-1": _issue("iss-1", state="open")})
    outcome = await reconcile_active_runs(state=state, tracker=tracker, config=cfg, now=now)
    assert outcome.stalled == []


async def test_reconcile_stall_disabled_when_negative() -> None:
    cfg = _config(codex={"stall_timeout_ms": -1})
    state = OrchestratorState()
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    state.running["iss-1"] = _session("iss-1", started_at=now - timedelta(seconds=99999))
    tracker = _FakeTracker(issues={"iss-1": _issue("iss-1", state="open")})
    outcome = await reconcile_active_runs(state=state, tracker=tracker, config=cfg, now=now)
    assert outcome.stalled == []


# ---------------------------------------------------------------------------
# Part B — state refresh
# ---------------------------------------------------------------------------


async def test_reconcile_terminates_on_terminal_state() -> None:
    """Tracker returns a terminal state -> worker is terminated."""
    cfg = _config()
    state = OrchestratorState()
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    state.running["iss-1"] = _session("iss-1", started_at=now - timedelta(seconds=10))
    tracker = _FakeTracker(issues={"iss-1": _issue("iss-1", state="closed")})
    outcome = await reconcile_active_runs(state=state, tracker=tracker, config=cfg, now=now)
    assert "iss-1" in outcome.terminated_due_to_state
    # Worker is removed from running.
    assert not state.is_running("iss-1")


async def test_reconcile_keeps_active_state() -> None:
    cfg = _config()
    state = OrchestratorState()
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    state.running["iss-1"] = _session("iss-1", started_at=now - timedelta(seconds=10))
    tracker = _FakeTracker(issues={"iss-1": _issue("iss-1", state="open")})
    outcome = await reconcile_active_runs(state=state, tracker=tracker, config=cfg, now=now)
    assert outcome.terminated_due_to_state == []
    assert state.is_running("iss-1")


async def test_reconcile_terminates_on_neither_active_nor_terminal() -> None:
    """A state outside active+terminal terminates the worker
    without workspace cleanup (SPEC §8.5 part B)."""
    cfg = _config()
    state = OrchestratorState()
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    state.running["iss-1"] = _session("iss-1", started_at=now - timedelta(seconds=10))
    # Tracker has no record of the issue.
    tracker = _FakeTracker(issues={})
    outcome = await reconcile_active_runs(state=state, tracker=tracker, config=cfg, now=now)
    assert "iss-1" in outcome.terminated_due_to_state
    assert not state.is_running("iss-1")


async def test_reconcile_keeps_workers_when_state_refresh_fails() -> None:
    """If tracker fetch fails, workers continue running (SPEC §8.5)."""
    cfg = _config()
    state = OrchestratorState()
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    state.running["iss-1"] = _session("iss-1", started_at=now - timedelta(seconds=10))
    tracker = _FakeTracker(issues={}, fetch_raises=RuntimeError("boom"))
    outcome = await reconcile_active_runs(state=state, tracker=tracker, config=cfg, now=now)
    assert "iss-1" in outcome.refresh_failures
    assert state.is_running("iss-1")  # still running


async def test_reconcile_combines_stall_and_termination() -> None:
    """A running issue that is both stalled and in a terminal
    state is reported under both categories."""
    cfg = _config()
    state = OrchestratorState()
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    state.running["iss-1"] = _session("iss-1", started_at=now - timedelta(seconds=300))
    tracker = _FakeTracker(issues={"iss-1": _issue("iss-1", state="closed")})
    outcome = await reconcile_active_runs(state=state, tracker=tracker, config=cfg, now=now)
    assert "iss-1" in outcome.stalled
    assert "iss-1" in outcome.terminated_due_to_state
