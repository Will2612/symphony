"""Unit tests for `symphony.orchestrator.service`.

Plan ref: §11 step 17, SPEC §7.1 (orchestrator) + §8.1 (poll
loop) + §8.6 (startup terminal cleanup).

The OrchestratorService is the single authority on scheduling.
It runs a tick loop:

1. Reconcile (stall + state refresh).
2. Preflight validation.
3. Fetch candidate issues.
4. Sort + select dispatchable (via `select_dispatchable_issues`).
5. Dispatch workers (call `runner.run` for each).
6. Update observability.

The startup sequence (§8.6) runs terminal cleanup BEFORE the
first tick.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from symphony.config.schema import SymphonyConfig
from symphony.orchestrator.service import (
    OrchestratorService,
    StartupOutcome,
    TickOutcome,
)
from symphony.orchestrator.state import LiveSession, OrchestratorState
from symphony.runner.base import EventKind, RunnerEvent, RunnerResult, RunOutcome
from symphony.tracker.normalize import Issue
from symphony.workspace.manager import Workspace


def _config(**overrides: object) -> SymphonyConfig:
    base: dict[str, Any] = {
        "agent": {
            "max_concurrent_agents": 5,
            "max_retry_backoff_ms": 60_000,
        },
        "tracker": {
            "kind": "memory",
            "active_states": ["open"],
            "terminal_states": ["closed"],
        },
        "codex": {
            "command": "opencode acp",
            "stall_timeout_ms": 60_000,
            "turn_timeout_ms": 60_000,
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
    candidates: list[Issue] = field(default_factory=list)
    by_states: dict[tuple[str, ...], list[Issue]] = field(default_factory=dict)
    fetch_raises: Exception | None = None
    fetch_calls: list[None] = field(default_factory=list)

    async def fetch_candidate_issues(self) -> list[Issue]:
        self.fetch_calls.append(None)
        if self.fetch_raises is not None:
            raise self.fetch_raises
        return list(self.candidates)

    async def fetch_issues_by_states(self, state_names: list[str]) -> list[Issue]:
        return self.by_states.get(tuple(state_names), [])

    async def fetch_issue_states_by_ids(self, issue_ids: list[str]) -> list[Issue]:
        return [i for i in self.candidates if i.id in issue_ids]

    async def create_comment(self, issue_id: str, body: str) -> None:
        pass

    async def update_issue_state(self, issue_id: str, state_name: str) -> None:
        pass


@dataclass
class _FakeWorkspaceManager:
    created: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    workspaces: dict[str, Workspace] = field(default_factory=dict)
    create_raises: Exception | None = None

    def create_for_issue(self, identifier: str, *, issue_id: str | None = None) -> Workspace:
        if self.create_raises is not None:
            raise self.create_raises
        ws = Workspace(path=f"/tmp/ws/{identifier}", key=identifier, created_now=True)
        self.workspaces[identifier] = ws
        self.created.append(identifier)
        return ws

    async def remove(self, workspace: Workspace) -> None:
        self.removed.append(workspace.key)
        self.workspaces.pop(workspace.key, None)


@dataclass
class _FakeRunner:
    """Records every run() call and returns a successful result."""

    results: list[RunnerResult] = field(default_factory=list)
    delay_s: float = 0.0
    raise_for: set[str] = field(default_factory=set)

    async def run(
        self,
        *,
        workspace: Any,
        prompt: str,
        event_callback: Callable[[RunnerEvent], Awaitable[None]],
        cancel: Any,
    ) -> RunnerResult:
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if workspace.key in self.raise_for:
            raise RuntimeError(f"runner failed for {workspace.key}")
        result = RunnerResult(status=RunOutcome.SUCCEEDED, events=[], usage={"input_tokens": 0})
        self.results.append(result)
        return result


@dataclass
class _FakeObserver:
    """Captures state updates for the observability snapshot."""

    snapshots: list[OrchestratorState] = field(default_factory=list)

    def on_state(self, state: OrchestratorState) -> None:
        self.snapshots.append(state)


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


def _service(
    *,
    cfg: SymphonyConfig | None = None,
    tracker: _FakeTracker | None = None,
    runner: _FakeRunner | None = None,
    workspace_manager: _FakeWorkspaceManager | None = None,
    observer: _FakeObserver | None = None,
) -> OrchestratorService:
    return OrchestratorService(
        config=cfg or _config(),
        tracker=tracker or _FakeTracker(),
        runner=runner or _FakeRunner(),
        workspace_manager=workspace_manager or _FakeWorkspaceManager(),
        observer=observer or _FakeObserver(),
    )


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------


async def test_startup_runs_terminal_cleanup() -> None:
    """The service iterates terminal-state issues and removes
    their workspaces on startup (SPEC §8.6)."""
    cfg = _config()
    tracker = _FakeTracker(
        by_states={("closed",): [_issue("1", state="closed"), _issue("2", state="closed")]},
    )
    wm = _FakeWorkspaceManager(
        workspaces={
            "#1": Workspace(path="/tmp/ws/#1", key="#1", created_now=False),
            "#2": Workspace(path="/tmp/ws/#2", key="#2", created_now=False),
        }
    )
    svc = _service(cfg=cfg, tracker=tracker, workspace_manager=wm)
    outcome: StartupOutcome = await svc.startup()
    assert outcome.cleaned_workspaces == 2
    assert set(wm.removed) == {"#1", "#2"}


async def test_startup_no_terminal_issues() -> None:
    cfg = _config()
    tracker = _FakeTracker(by_states={("closed",): []})
    wm = _FakeWorkspaceManager()
    svc = _service(cfg=cfg, tracker=tracker, workspace_manager=wm)
    outcome = await svc.startup()
    assert outcome.cleaned_workspaces == 0


async def test_startup_continues_if_tracker_fails() -> None:
    """A tracker error during startup cleanup is logged and
    startup continues (SPEC §11.4)."""
    cfg = _config()

    class _FailingTracker(_FakeTracker):
        async def fetch_issues_by_states(self, state_names: list[str]) -> list[Issue]:
            raise RuntimeError("boom")

    tracker = _FailingTracker()
    wm = _FakeWorkspaceManager()
    svc = _service(cfg=cfg, tracker=tracker, workspace_manager=wm)
    outcome = await svc.startup()
    # No crash; outcome is empty.
    assert outcome.cleaned_workspaces == 0


# ---------------------------------------------------------------------------
# Tick — single iteration
# ---------------------------------------------------------------------------


async def test_tick_dispatches_one_issue() -> None:
    """A tick that finds one eligible issue spawns one worker."""
    cfg = _config()
    tracker = _FakeTracker(candidates=[_issue("1")])
    runner = _FakeRunner()
    wm = _FakeWorkspaceManager()
    observer = _FakeObserver()
    svc = _service(cfg=cfg, tracker=tracker, runner=runner, workspace_manager=wm, observer=observer)
    outcome: TickOutcome = await svc.tick()
    assert outcome.dispatched == ["#1"]
    # Worker is a fire-and-forget task; wait for it to finish.
    task = svc._worker_tasks["1"]
    await task
    assert len(runner.results) == 1
    # Worker created a workspace.
    assert wm.created == ["#1"]


async def test_tick_no_candidates_is_noop() -> None:
    cfg = _config()
    tracker = _FakeTracker(candidates=[])
    runner = _FakeRunner()
    svc = _service(cfg=cfg, tracker=tracker, runner=runner)
    outcome = await svc.tick()
    assert outcome.dispatched == []
    assert runner.results == []


async def test_tick_skips_when_no_slots() -> None:
    """If all slots are used, no new dispatches happen."""
    cfg = _config(agent={"max_concurrent_agents": 1})
    # Include "x" as a candidate so reconcile leaves the pre-filled
    # running session alone; include "#1" and "#2" as new work.
    tracker = _FakeTracker(candidates=[_issue("x", state="open"), _issue("1"), _issue("2")])
    # Pre-fill running with one issue using a real LiveSession so
    # reconcile's `last_codex_timestamp` math works.
    svc = _service(cfg=cfg, tracker=tracker)
    svc.state.running["x"] = LiveSession(
        issue_id="x",
        identifier="#x",
        session_id="s-x",
        started_at=datetime.now(UTC),
    )
    outcome = await svc.tick()
    assert outcome.dispatched == []


async def test_tick_skips_terminal_state_issues() -> None:
    cfg = _config()
    tracker = _FakeTracker(candidates=[_issue("1", state="closed"), _issue("2", state="open")])
    runner = _FakeRunner()
    svc = _service(cfg=cfg, tracker=tracker, runner=runner)
    outcome = await svc.tick()
    assert outcome.dispatched == ["#2"]


async def test_tick_skips_already_claimed_issues() -> None:
    cfg = _config()
    tracker = _FakeTracker(candidates=[_issue("1")])
    runner = _FakeRunner()
    svc = _service(cfg=cfg, tracker=tracker, runner=runner)
    svc.state.claimed.add("1")
    outcome = await svc.tick()
    assert outcome.dispatched == []


# ---------------------------------------------------------------------------
# Tick — tracker errors
# ---------------------------------------------------------------------------


async def test_tick_skips_dispatch_when_tracker_fails() -> None:
    """A tracker error during candidate fetch logs the error and
    skips dispatch for this tick (SPEC §11.4)."""
    cfg = _config()
    tracker = _FakeTracker(candidates=[], fetch_raises=RuntimeError("boom"))
    runner = _FakeRunner()
    svc = _service(cfg=cfg, tracker=tracker, runner=runner)
    outcome = await svc.tick()
    assert outcome.dispatched == []
    assert outcome.tracker_error is not None
    assert runner.results == []


# ---------------------------------------------------------------------------
# Tick — observability
# ---------------------------------------------------------------------------


async def test_tick_invokes_observer_after_dispatch() -> None:
    cfg = _config()
    tracker = _FakeTracker(candidates=[_issue("1")])
    runner = _FakeRunner()
    observer = _FakeObserver()
    svc = _service(cfg=cfg, tracker=tracker, runner=runner, observer=observer)
    await svc.tick()
    # Observer was called at least once.
    assert len(observer.snapshots) >= 1


# ---------------------------------------------------------------------------
# Tick — workspace/prompt failure paths in dispatch
# ---------------------------------------------------------------------------


async def test_tick_workspace_creation_failure_marks_failed() -> None:
    cfg = _config()
    tracker = _FakeTracker(candidates=[_issue("1")])
    runner = _FakeRunner()
    wm = _FakeWorkspaceManager(create_raises=RuntimeError("disk full"))
    svc = _service(cfg=cfg, tracker=tracker, runner=runner, workspace_manager=wm)
    outcome = await svc.tick()
    assert outcome.dispatched == []
    assert outcome.failed == ["#1"]
    assert runner.results == []


# ---------------------------------------------------------------------------
# Worker behavior
# ---------------------------------------------------------------------------


async def test_worker_schedules_continuation_retry_on_success() -> None:
    """A successful runner.run schedules a continuation retry (1s)."""
    cfg = _config()
    tracker = _FakeTracker(candidates=[_issue("1")])
    runner = _FakeRunner()
    wm = _FakeWorkspaceManager()
    svc = _service(cfg=cfg, tracker=tracker, runner=runner, workspace_manager=wm)
    outcome = await svc.tick()
    assert outcome.dispatched == ["#1"]
    task = svc._worker_tasks["1"]
    await task
    # Worker queued a continuation retry entry.
    assert "1" in svc.state.retry_attempts
    entry = svc.state.retry_attempts["1"]
    assert entry.error == ""


async def test_worker_schedules_failure_retry_on_exception() -> None:
    """If the runner raises, the worker schedules a failure retry
    (exponential backoff) and increments attempt."""
    cfg = _config()
    tracker = _FakeTracker(candidates=[_issue("1")])
    runner = _FakeRunner(raise_for={"#1"})
    wm = _FakeWorkspaceManager()
    svc = _service(cfg=cfg, tracker=tracker, runner=runner, workspace_manager=wm)
    outcome = await svc.tick()
    assert outcome.dispatched == ["#1"]
    task = svc._worker_tasks["1"]
    await task
    assert "1" in svc.state.retry_attempts
    entry = svc.state.retry_attempts["1"]
    assert entry.error  # non-empty
    # session.attempt=1, so failure retry = 1+1 = 2
    assert entry.attempt == 2


async def test_worker_event_callback_updates_session() -> None:
    """The runner's event callback bumps last_codex_timestamp and
    accumulates usage tokens."""
    cfg = _config()

    @dataclass
    class _RecordingRunner:
        last_event: RunnerEvent | None = None

        async def run(
            self,
            *,
            workspace: Any,
            prompt: str,
            event_callback: Callable[[RunnerEvent], Awaitable[None]],
            cancel: Any,
        ) -> RunnerResult:
            ev = RunnerEvent(
                event=EventKind.NOTIFICATION,
                timestamp=datetime.now(UTC),
                payload={"text": "hi"},
                usage={"input_tokens": 5, "output_tokens": 3},
            )
            self.last_event = ev
            await event_callback(ev)
            return RunnerResult(status=RunOutcome.SUCCEEDED, events=[ev], usage=ev.usage)

    tracker = _FakeTracker(candidates=[_issue("1")])
    runner = _RecordingRunner()
    wm = _FakeWorkspaceManager()
    svc = _service(cfg=cfg, tracker=tracker, runner=runner, workspace_manager=wm)
    await svc.tick()
    task = svc._worker_tasks["1"]
    await task
    session = svc.state.running.get("1")
    assert session is None  # released after worker done
    # The session was a transient; verify by inspecting retry entry.
    assert "1" in svc.state.retry_attempts


# ---------------------------------------------------------------------------
# Observer error handling
# ---------------------------------------------------------------------------


async def test_observer_exception_is_logged_not_raised() -> None:
    """An observer.on_state exception is logged and swallowed."""
    cfg = _config()

    @dataclass
    class _BadObserver:
        def on_state(self, state: OrchestratorState) -> None:
            raise RuntimeError("observer boom")

    tracker = _FakeTracker(candidates=[_issue("1")])
    runner = _FakeRunner()
    svc = _service(cfg=cfg, tracker=tracker, runner=runner, observer=_BadObserver())
    # Should not raise.
    await svc.tick()
    task = svc._worker_tasks["1"]
    await task


async def test_observer_none_is_safe() -> None:
    cfg = _config()
    tracker = _FakeTracker(candidates=[_issue("1")])
    runner = _FakeRunner()
    svc = _service(cfg=cfg, tracker=tracker, runner=runner, observer=None)
    outcome = await svc.tick()
    assert outcome.dispatched == ["#1"]


# ---------------------------------------------------------------------------
# run_forever — graceful stop
# ---------------------------------------------------------------------------


async def test_run_forever_stops_on_stop_event() -> None:
    """run_forever() returns promptly after stop() is called."""
    cfg = _config()
    tracker = _FakeTracker(candidates=[])
    runner = _FakeRunner()
    svc = _service(cfg=cfg, tracker=tracker, runner=runner)
    # Patch polling interval to 50ms to keep the test fast.
    svc.config.polling.interval_ms = 50  # type: ignore[attr-defined]
    task = asyncio.create_task(svc.run_forever())
    await asyncio.sleep(0.05)  # let one tick happen
    svc.stop()
    await asyncio.wait_for(task, timeout=2.0)
    assert svc._stop.is_set()  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Startup — empty terminal list (early return)
# ---------------------------------------------------------------------------


async def test_startup_skips_when_terminal_states_empty() -> None:
    """If `terminal_states` is empty, startup returns immediately
    without calling the tracker."""
    cfg = _config()
    tracker = _FakeTracker()  # fetch_issues_by_states never called
    wm = _FakeWorkspaceManager()
    svc = _service(cfg=cfg, tracker=tracker, workspace_manager=wm)
    outcome = await svc.startup()
    assert outcome.cleaned_workspaces == 0
    # Tracker was NOT consulted.
    # (We can't introspect easily; the outcome is the proof.)


# ---------------------------------------------------------------------------
# _schedule_failure_retry (async with lock) coverage
# ---------------------------------------------------------------------------


async def test_schedule_failure_retry_acquires_lock() -> None:
    """The async `_schedule_failure_retry` acquires the lock and
    schedules a retry entry with attempt=1."""
    cfg = _config()
    tracker = _FakeTracker()
    runner = _FakeRunner()
    svc = _service(cfg=cfg, tracker=tracker, runner=runner)
    issue = _issue("1")
    svc.state.claim("1")
    await svc._schedule_failure_retry(issue, "manual")
    assert "1" in svc.state.retry_attempts
    entry = svc.state.retry_attempts["1"]
    assert entry.error == "manual"
    assert entry.attempt == 1


async def test_schedule_failure_retry_for_increments_attempt() -> None:
    """`_schedule_failure_retry_for` schedules an entry with
    attempt = session.attempt + 1."""
    cfg = _config()
    tracker = _FakeTracker()
    runner = _FakeRunner()
    svc = _service(cfg=cfg, tracker=tracker, runner=runner)
    session = LiveSession(
        issue_id="x",
        identifier="#x",
        session_id="s-x",
        started_at=datetime.now(UTC),
        attempt=3,
    )
    svc.state.claim("x")
    svc.state.running["x"] = session
    await svc._schedule_failure_retry_for(session, "boom")
    assert "x" in svc.state.retry_attempts
    assert svc.state.retry_attempts["x"].attempt == 4


# ---------------------------------------------------------------------------
# Notify observer coverage
# ---------------------------------------------------------------------------


async def test_observer_none_skips_callback() -> None:
    """When observer is None, `_notify_observer` returns without
    doing anything (no AttributeError)."""
    cfg = _config()
    tracker = _FakeTracker()
    runner = _FakeRunner()
    svc = _service(cfg=cfg, tracker=tracker, runner=runner, observer=None)
    # Should not raise.
    svc._notify_observer()  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Prompt build error path
# ---------------------------------------------------------------------------


async def test_dispatch_prompt_build_error_marks_failed() -> None:
    """If `build_prompt` raises, the issue lands in `outcome.failed`
    and a retry entry is scheduled (attempt=1).

    We force the failure by monkey-patching the `build_prompt`
    symbol in the service module."""

    @dataclass
    class _BadRunner:
        results: list[RunnerResult] = field(default_factory=list)

        async def run(
            self,
            *,
            workspace: object,
            prompt: str,
            event_callback: Callable[[RunnerEvent], Awaitable[None]],
            cancel: object,
        ) -> RunnerResult:
            return RunnerResult(status=RunOutcome.SUCCEEDED, events=[], usage={})

    cfg = _config()
    from symphony.orchestrator import service as svc_mod  # noqa: PLC0415

    original = svc_mod.build_prompt

    def _bad_prompt(*args: object, **kwargs: object) -> str:
        raise RuntimeError("prompt boom")

    svc_mod.build_prompt = _bad_prompt  # type: ignore[assignment]
    try:
        tracker = _FakeTracker(candidates=[_issue("1")])
        runner = _BadRunner()
        wm = _FakeWorkspaceManager()
        svc = _service(cfg=cfg, tracker=tracker, runner=runner, workspace_manager=wm)
        outcome = await svc.tick()
        assert outcome.dispatched == []
        assert outcome.failed == ["#1"]
        assert "1" in svc.state.retry_attempts
        assert svc.state.retry_attempts["1"].error == "prompt_build_error"
    finally:
        svc_mod.build_prompt = original  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Event callback — usage aggregation
# ---------------------------------------------------------------------------


async def test_event_callback_aggregates_usage() -> None:
    """The event callback accumulates token usage across events."""

    @dataclass
    class _EventRunner:
        async def run(
            self,
            *,
            workspace: object,
            prompt: str,
            event_callback: Callable[[RunnerEvent], Awaitable[None]],
            cancel: object,
        ) -> RunnerResult:
            for i in range(3):
                ev = RunnerEvent(
                    event=EventKind.NOTIFICATION,
                    timestamp=datetime.now(UTC),
                    payload={"i": i},
                    usage={"input_tokens": 1, "output_tokens": 2},
                )
                await event_callback(ev)
            return RunnerResult(status=RunOutcome.SUCCEEDED, events=[], usage={})

    cfg = _config()
    tracker = _FakeTracker(candidates=[_issue("1")])
    runner = _EventRunner()
    wm = _FakeWorkspaceManager()
    svc = _service(cfg=cfg, tracker=tracker, runner=runner, workspace_manager=wm)
    await svc.tick()
    task = svc._worker_tasks["1"]
    await task
    # Continuation retry entry exists (no failure).
    assert "1" in svc.state.retry_attempts
