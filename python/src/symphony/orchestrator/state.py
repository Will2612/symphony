"""Orchestrator state — the single authority on scheduling state.

Plan ref: §11 step 15, SPEC §7.1 (claim states) + §7.2
(run attempt phases) + §7.3 (transition triggers).

`ClaimState` and `RunPhase` are first-class `StrEnum` subclasses
with an `ALLOWED_TRANSITIONS` graph. State mutations MUST go
through `assert_allowed_transition` (or the convenience helpers
on `LiveSession.advance_phase`); the orchestrator holds an
`asyncio.Lock` and runs all mutations inside `OrchestratorState`
mutator methods.

The module also defines:
- `LiveSession` — an in-flight run (phase, started_at, …).
- `RetryEntry` — a queued retry timer.
- `OrchestratorState` — the global state: `running`, `claimed`,
  `retry_attempts`, plus lock-guarded mutators.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from symphony.errors import SymphonyError

# ---------------------------------------------------------------------------
# ClaimState
# ---------------------------------------------------------------------------


class ClaimState(StrEnum):
    """Per-issue claim state (SPEC §7.1)."""

    UNCLAIMED = "unclaimed"
    CLAIMED = "claimed"
    RUNNING = "running"
    RETRY_QUEUED = "retry_queued"
    RELEASED = "released"


_CLAIM_TRANSITIONS: dict[ClaimState, frozenset[ClaimState]] = {
    ClaimState.UNCLAIMED: frozenset({ClaimState.CLAIMED}),
    ClaimState.CLAIMED: frozenset(
        {ClaimState.RUNNING, ClaimState.RETRY_QUEUED, ClaimState.RELEASED}
    ),
    ClaimState.RUNNING: frozenset({ClaimState.RETRY_QUEUED, ClaimState.RELEASED}),
    ClaimState.RETRY_QUEUED: frozenset({ClaimState.CLAIMED, ClaimState.RELEASED}),
    ClaimState.RELEASED: frozenset(),
}


def claim_state_transitions(state: ClaimState) -> frozenset[ClaimState]:
    """Return the set of states reachable from `state`."""
    return _CLAIM_TRANSITIONS[state]


# ---------------------------------------------------------------------------
# RunPhase
# ---------------------------------------------------------------------------


class RunPhase(StrEnum):
    """Per-run-attempt phase (SPEC §7.2)."""

    PREPARING_WORKSPACE = "preparing_workspace"
    BUILDING_PROMPT = "building_prompt"
    LAUNCHING_AGENT_PROCESS = "launching_agent_process"
    INITIALIZING_SESSION = "initializing_session"
    STREAMING_TURN = "streaming_turn"
    FINISHING = "finishing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    STALLED = "stalled"
    CANCELED_BY_RECONCILIATION = "canceled_by_reconciliation"


_RUN_PHASE_TRANSITIONS: dict[RunPhase, frozenset[RunPhase]] = {
    RunPhase.PREPARING_WORKSPACE: frozenset({RunPhase.BUILDING_PROMPT, RunPhase.FAILED}),
    RunPhase.BUILDING_PROMPT: frozenset({RunPhase.LAUNCHING_AGENT_PROCESS, RunPhase.FAILED}),
    RunPhase.LAUNCHING_AGENT_PROCESS: frozenset({RunPhase.INITIALIZING_SESSION, RunPhase.FAILED}),
    RunPhase.INITIALIZING_SESSION: frozenset({RunPhase.STREAMING_TURN, RunPhase.FAILED}),
    RunPhase.STREAMING_TURN: frozenset(
        {
            RunPhase.FINISHING,
            RunPhase.FAILED,
            RunPhase.TIMED_OUT,
            RunPhase.STALLED,
            RunPhase.CANCELED_BY_RECONCILIATION,
        }
    ),
    RunPhase.FINISHING: frozenset({RunPhase.SUCCEEDED, RunPhase.FAILED}),
    RunPhase.SUCCEEDED: frozenset(),
    RunPhase.FAILED: frozenset(),
    RunPhase.TIMED_OUT: frozenset(),
    RunPhase.STALLED: frozenset(),
    RunPhase.CANCELED_BY_RECONCILIATION: frozenset(),
}


def run_phase_transitions(phase: RunPhase) -> frozenset[RunPhase]:
    """Return the set of phases reachable from `phase`."""
    return _RUN_PHASE_TRANSITIONS[phase]


# ---------------------------------------------------------------------------
# Transition guard
# ---------------------------------------------------------------------------


class IllegalStateTransition(SymphonyError):
    """Raised when a state/phase transition is not in the
    `ALLOWED_TRANSITIONS` graph. Has a stable `code` for log
    filtering."""

    code = "illegal_state_transition"


def assert_allowed_transition(
    current: ClaimState | RunPhase,
    target: ClaimState | RunPhase,
) -> None:
    """Raise `IllegalStateTransition` if `current -> target` is
    not in the graph; otherwise return None."""
    allowed: frozenset[ClaimState] | frozenset[RunPhase]
    if isinstance(current, ClaimState) and isinstance(target, ClaimState):
        allowed = _CLAIM_TRANSITIONS[current]
    elif isinstance(current, RunPhase) and isinstance(target, RunPhase):
        allowed = _RUN_PHASE_TRANSITIONS[current]
    else:
        raise IllegalStateTransition(
            f"cannot mix claim/phase: {current!r} -> {target!r}",
            code=IllegalStateTransition.code,
        )
    if target not in allowed:
        raise IllegalStateTransition(
            f"disallowed transition: {current.value!r} -> {target.value!r}",
            code=IllegalStateTransition.code,
        )


# ---------------------------------------------------------------------------
# LiveSession
# ---------------------------------------------------------------------------


@dataclass
class LiveSession:
    """An in-flight run for one issue.

    The `phase` starts at `PREPARING_WORKSPACE` and walks through
    the `RunPhase` graph. `last_codex_timestamp` is updated every
    time a runner event is observed; the orchestrator uses it for
    stall detection (SPEC §8.5).
    """

    issue_id: str
    identifier: str
    session_id: str
    started_at: datetime
    phase: RunPhase = RunPhase.PREPARING_WORKSPACE
    attempt: int = 1
    last_codex_timestamp: datetime | None = None
    turn_count: int = 0
    usage: dict[str, int] = field(default_factory=dict)

    def advance_phase(self, target: RunPhase) -> None:
        """Move to `target`, raising if the transition is disallowed."""
        assert_allowed_transition(self.phase, target)
        self.phase = target


# ---------------------------------------------------------------------------
# RetryEntry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetryEntry:
    """A pending retry timer (SPEC §8.4).

    The `due_at_ms` is a wall-clock millisecond timestamp; the
    orchestrator's main loop polls the due list each tick and
    dispatches any whose `due_at_ms <= now_ms`.
    """

    issue_id: str
    identifier: str
    attempt: int
    error: str
    due_at_ms: int


# ---------------------------------------------------------------------------
# OrchestratorState
# ---------------------------------------------------------------------------


@dataclass
class OrchestratorState:
    """The single authority on scheduling state.

    All mutations go through the lock-guarded mutators; raw dict
    / set access is for READ-ONLY inspection from inside the
    lock.
    """

    running: dict[str, LiveSession] = field(default_factory=dict)
    claimed: set[str] = field(default_factory=set)
    retry_attempts: dict[str, RetryEntry] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    runtime_seconds: int = 0
    latest_rate_limit: dict[str, object] | None = None

    # --- read-only inspection (no lock required) -----------------------

    def running_count(self) -> int:
        return len(self.running)

    def is_claimed(self, issue_id: str) -> bool:
        return issue_id in self.claimed

    def is_running(self, issue_id: str) -> bool:
        return issue_id in self.running

    # --- mutators (caller MUST hold `lock` or use Service) --------------

    def claim(self, issue_id: str) -> None:
        # Idempotent: re-claiming a claimed issue is a no-op.
        if issue_id in self.claimed:
            return
        assert_allowed_transition(ClaimState.UNCLAIMED, ClaimState.CLAIMED)
        self.claimed.add(issue_id)

    def release(self, issue_id: str) -> None:
        # RELEASE is reachable from CLAIMED, RUNNING, RETRY_QUEUED.
        # Pick the right current state based on membership.
        if issue_id in self.running:
            current = ClaimState.RUNNING
        elif issue_id in self.retry_attempts:
            current = ClaimState.RETRY_QUEUED
        elif issue_id in self.claimed:
            current = ClaimState.CLAIMED
        else:
            current = ClaimState.UNCLAIMED
        assert_allowed_transition(current, ClaimState.RELEASED)
        self.claimed.discard(issue_id)
        self.running.pop(issue_id, None)
        self.retry_attempts.pop(issue_id, None)

    def mark_running(self, issue_id: str) -> None:
        assert_allowed_transition(ClaimState.CLAIMED, ClaimState.RUNNING)
        # already claimed; just record the session
        if issue_id not in self.claimed:
            self.claimed.add(issue_id)

    def mark_retry_queued(self, issue_id: str, entry: RetryEntry) -> None:
        # RUNNING -> RETRY_QUEUED is the common case; CLAIMED -> RETRY_QUEUED
        # is allowed if startup failed.
        if issue_id in self.running:
            current = ClaimState.RUNNING
        elif issue_id in self.claimed:
            current = ClaimState.CLAIMED
        else:
            current = ClaimState.UNCLAIMED
        assert_allowed_transition(current, ClaimState.RETRY_QUEUED)
        self.running.pop(issue_id, None)
        self.retry_attempts[issue_id] = entry

    def remove_retry(self, issue_id: str) -> None:
        """Drop a retry entry (caller is re-dispatching now)."""
        self.retry_attempts.pop(issue_id, None)
