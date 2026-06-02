"""Orchestrator service (SPEC §7.1 + §8.1 + §8.6).

The `OrchestratorService` is the single authority on scheduling
state. It owns:

- the resolved `SymphonyConfig`
- a `Tracker` (any implementation of the Protocol)
- a `Runner` (currently `OpenCodeRunner`)
- a `WorkspaceManager`
- an `Observer` callback (consumed by the observability layer)
- the `OrchestratorState` (running/claimed/retry_attempts)
- an `asyncio.Lock` guarding all state mutations

Public surface:

- `await svc.startup()` — terminal cleanup (SPEC §8.6); safe to
  call once on boot.
- `await svc.tick()` — one poll iteration: reconcile, preflight,
  fetch, select, dispatch, observe.
- `await svc.run_forever()` — schedule `tick()` on the configured
  polling interval until `stop()` is called.
- `svc.stop()` — request graceful shutdown.

Errors:
- Tracker failures during candidate fetch are LOGGED and
  dispatch is skipped for that tick (SPEC §11.4).
- Worker exceptions are caught and trigger an exponential-backoff
  retry entry on the same issue (handled by `tick()` after the
  worker task returns).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from symphony.config.schema import SymphonyConfig
from symphony.orchestrator.dispatch import available_slots, select_dispatchable_issues
from symphony.orchestrator.reconcile import reconcile_active_runs
from symphony.orchestrator.retry import (
    compute_continuation_delay_ms,
    compute_failure_delay_ms,
)
from symphony.orchestrator.state import (
    LiveSession,
    OrchestratorState,
    RetryEntry,
)
from symphony.prompt.builder import build_prompt
from symphony.runner.base import Runner, RunnerEvent
from symphony.tracker.base import Tracker
from symphony.workspace.manager import Workspace, WorkspaceManager

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Observer protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class Observer(Protocol):
    """Hook for the observability layer. The orchestrator calls
    `on_state` after each tick with the current state snapshot."""

    def on_state(self, state: OrchestratorState) -> None: ...


# ---------------------------------------------------------------------------
# Outcomes
# ---------------------------------------------------------------------------


@dataclass
class StartupOutcome:
    """What the startup sequence did."""

    cleaned_workspaces: int = 0
    tracker_error: str | None = None


@dataclass
class TickOutcome:
    """What one tick did."""

    dispatched: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    stalled: list[str] = field(default_factory=list)
    tracker_error: str | None = None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class OrchestratorService:
    """The orchestration loop. See module docstring for behavior."""

    def __init__(
        self,
        *,
        config: SymphonyConfig,
        tracker: Tracker,
        runner: Runner,
        workspace_manager: WorkspaceManager,
        observer: Observer | None = None,
    ) -> None:
        self.config = config
        self.tracker = tracker
        self.runner = runner
        self.workspace_manager = workspace_manager
        self.observer = observer
        self.state = OrchestratorState()
        self._stop = asyncio.Event()
        self._worker_tasks: dict[str, asyncio.Task[None]] = {}

    # --- lifecycle ------------------------------------------------------

    def stop(self) -> None:
        """Request graceful shutdown of `run_forever`."""
        self._stop.set()

    async def startup(self) -> StartupOutcome:
        """Run terminal workspace cleanup (SPEC §8.6).

        Fetches issues in terminal states and removes their
        workspaces. Tracker errors are logged but do not block
        startup.
        """
        outcome = StartupOutcome()
        terminal = list(self.config.tracker.terminal_states)
        try:
            issues = await self.tracker.fetch_issues_by_states(terminal)
        except Exception as e:
            _LOGGER.warning("startup terminal cleanup failed: %s", e)
            outcome.tracker_error = str(e)
            return outcome
        for issue in issues:
            ws = Workspace(
                path=f"{self.config.workspace.root.rstrip('/')}/{issue.identifier}",
                key=issue.identifier,
                created_now=False,
            )
            await self.workspace_manager.remove(ws)
            outcome.cleaned_workspaces += 1
        return outcome

    async def run_forever(self) -> None:
        """Schedule `tick()` on `polling.interval_ms` until `stop()`."""
        first = True
        while not self._stop.is_set():
            try:
                await self.tick()
            except Exception:
                _LOGGER.exception("tick raised")
            if first:
                first = False
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self.config.polling.interval_ms / 1000.0,
                )
            except TimeoutError:
                continue

    # --- one iteration --------------------------------------------------

    async def tick(self) -> TickOutcome:
        """One poll iteration."""
        outcome = TickOutcome()
        now = datetime.now(UTC)
        async with self.state.lock:
            # 1) Reconcile (stall + state refresh).
            reconcile_outcome = await reconcile_active_runs(
                state=self.state,
                tracker=self.tracker,
                config=self.config,
                now=now,
            )
            outcome.stalled = list(reconcile_outcome.stalled)
            # 2) Fetch candidates.
            try:
                candidates = await self.tracker.fetch_candidate_issues()
            except Exception as e:
                _LOGGER.warning("candidate fetch failed: %s", e)
                outcome.tracker_error = str(e)
                self._notify_observer()
                return outcome
            # 3) Select dispatchable.
            slots = available_slots(self.state, self.config)
            selected = select_dispatchable_issues(
                issues=list(candidates),
                state=self.state,
                config=self.config,
                slots_available=slots,
            )
            # 4) Dispatch.
            for issue in selected:
                ok = await self._dispatch_one(issue, now=now, outcome=outcome)
                if not ok:
                    # Stop dispatching on first failure; remaining
                    # candidates will be retried next tick.
                    break
        # Outside the lock: notify observer.
        self._notify_observer()
        return outcome

    # --- internals -------------------------------------------------------

    async def _dispatch_one(
        self,
        issue: Any,  # noqa: ANN401
        *,
        now: datetime,
        outcome: TickOutcome,
    ) -> bool:
        """Spawn one worker for `issue`. Returns True on success,
        False on failure.

        Caller MUST hold `self.state.lock`."""
        try:
            workspace = self.workspace_manager.create_for_issue(issue.identifier, issue_id=issue.id)
        except Exception:
            _LOGGER.exception("workspace creation failed for %s", issue.identifier)
            outcome.failed.append(issue.identifier)
            return False
        # Claim + record session.
        self.state.claim(issue.id)
        session = LiveSession(
            issue_id=issue.id,
            identifier=issue.identifier,
            session_id=f"opencode-{int(now.timestamp() * 1000)}",
            started_at=now,
        )
        self.state.running[issue.id] = session
        # Build prompt.
        try:
            prompt = build_prompt("default", issue=issue, attempt=session.attempt)
        except Exception:
            _LOGGER.exception("prompt build failed for %s", issue.identifier)
            self._schedule_failure_retry_locked(issue, "prompt_build_error")
            outcome.failed.append(issue.identifier)
            return False
        # Spawn worker task.
        cancel = asyncio.Event()
        task = asyncio.create_task(
            self._run_worker(session=session, workspace=workspace, prompt=prompt, cancel=cancel)
        )
        self._worker_tasks[issue.id] = task
        outcome.dispatched.append(issue.identifier)
        return True

    async def _run_worker(
        self,
        *,
        session: LiveSession,
        workspace: Any,  # noqa: ANN401
        prompt: str,
        cancel: asyncio.Event,
    ) -> None:
        """Drive the runner for one session, then update state."""
        try:
            await self.runner.run(
                workspace=workspace,
                prompt=prompt,
                event_callback=self._make_event_callback(session),
                cancel=cancel,
            )
        except Exception as e:
            _LOGGER.warning("worker for %s raised: %s", session.identifier, e)
            async with self.state.lock:
                await self._schedule_failure_retry_for(session, str(e))
        else:
            async with self.state.lock:
                # Continuation retry (1 s) so we re-check the issue.
                entry = RetryEntry(
                    issue_id=session.issue_id,
                    identifier=session.identifier,
                    attempt=session.attempt,
                    error="",
                    due_at_ms=int(datetime.now(UTC).timestamp() * 1000)
                    + compute_continuation_delay_ms(),
                )
                self.state.mark_retry_queued(session.issue_id, entry)
        finally:
            self._worker_tasks.pop(session.issue_id, None)

    def _make_event_callback(
        self, session: LiveSession
    ) -> Callable[[RunnerEvent], Awaitable[None]]:
        async def _cb(event: RunnerEvent) -> None:
            session.last_codex_timestamp = datetime.now(UTC)
            if event.usage:
                for k, v in event.usage.items():
                    if isinstance(v, int):
                        session.usage[k] = session.usage.get(k, 0) + v

        return _cb

    async def _schedule_failure_retry(
        self,
        issue: Any,  # noqa: ANN401
        error: str,
    ) -> None:
        async with self.state.lock:
            self._schedule_failure_retry_locked(issue, error)

    def _schedule_failure_retry_locked(
        self,
        issue: Any,  # noqa: ANN401
        error: str,
    ) -> None:
        """Like `_schedule_failure_retry` but assumes the caller
        already holds `self.state.lock`.

        Goes directly from CLAIMED → RETRY_QUEUED (no intermediate
        RELEASED), per the `ClaimState` transition graph."""
        attempt = 1
        entry = RetryEntry(
            issue_id=issue.id,
            identifier=issue.identifier,
            attempt=attempt,
            error=error,
            due_at_ms=int(datetime.now(UTC).timestamp() * 1000)
            + compute_failure_delay_ms(attempt=attempt, config=self.config),
        )
        self.state.mark_retry_queued(issue.id, entry)

    async def _schedule_failure_retry_for(self, session: LiveSession, error: str) -> None:
        attempt = session.attempt + 1
        entry = RetryEntry(
            issue_id=session.issue_id,
            identifier=session.identifier,
            attempt=attempt,
            error=error,
            due_at_ms=int(datetime.now(UTC).timestamp() * 1000)
            + compute_failure_delay_ms(attempt=attempt, config=self.config),
        )
        self.state.mark_retry_queued(session.issue_id, entry)

    def _notify_observer(self) -> None:
        if self.observer is None:
            return
        try:
            self.observer.on_state(self.state)
        except Exception as e:
            _LOGGER.warning("observer.on_state raised: %s", e)
