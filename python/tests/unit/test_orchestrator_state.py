"""Unit tests for `symphony.orchestrator.state`.

Plan ref: §11 step 15, SPEC §7.1 (claim states) + §7.2
(run attempt phases) + §7.3 (transition triggers).

The orchestrator is the single authority on scheduling state.
`ClaimState` and `RunPhase` are first-class `StrEnum` subclasses
with an `ALLOWED_TRANSITIONS` graph; the dataclasses describe
live sessions, run attempts, retry entries, and the global
state.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from symphony.errors import SymphonyError
from symphony.orchestrator.state import (
    ClaimState,
    LiveSession,
    OrchestratorState,
    RetryEntry,
    RunPhase,
    assert_allowed_transition,
    claim_state_transitions,
    run_phase_transitions,
)

# ---------------------------------------------------------------------------
# ClaimState
# ---------------------------------------------------------------------------


def test_claim_state_has_all_5_values() -> None:
    assert {c.value for c in ClaimState} == {
        "unclaimed",
        "claimed",
        "running",
        "retry_queued",
        "released",
    }


def test_claim_state_transitions_unclaimed() -> None:
    assert claim_state_transitions(ClaimState.UNCLAIMED) == frozenset({ClaimState.CLAIMED})


def test_claim_state_transitions_claimed() -> None:
    assert claim_state_transitions(ClaimState.CLAIMED) == frozenset(
        {ClaimState.RUNNING, ClaimState.RETRY_QUEUED, ClaimState.RELEASED}
    )


def test_claim_state_transitions_running() -> None:
    assert claim_state_transitions(ClaimState.RUNNING) == frozenset(
        {ClaimState.RETRY_QUEUED, ClaimState.RELEASED}
    )


def test_claim_state_transitions_retry_queued() -> None:
    assert claim_state_transitions(ClaimState.RETRY_QUEUED) == frozenset(
        {ClaimState.CLAIMED, ClaimState.RELEASED}
    )


def test_claim_state_transitions_released_is_terminal() -> None:
    """Released is terminal: no transitions out."""
    assert claim_state_transitions(ClaimState.RELEASED) == frozenset()


# ---------------------------------------------------------------------------
# RunPhase
# ---------------------------------------------------------------------------


def test_run_phase_has_all_11_values() -> None:
    assert {p.value for p in RunPhase} == {
        "preparing_workspace",
        "building_prompt",
        "launching_agent_process",
        "initializing_session",
        "streaming_turn",
        "finishing",
        "succeeded",
        "failed",
        "timed_out",
        "stalled",
        "canceled_by_reconciliation",
    }


def test_run_phase_transitions_preparing_workspace() -> None:
    assert run_phase_transitions(RunPhase.PREPARING_WORKSPACE) == frozenset(
        {RunPhase.BUILDING_PROMPT, RunPhase.FAILED}
    )


def test_run_phase_transitions_building_prompt() -> None:
    assert run_phase_transitions(RunPhase.BUILDING_PROMPT) == frozenset(
        {RunPhase.LAUNCHING_AGENT_PROCESS, RunPhase.FAILED}
    )


def test_run_phase_transitions_launching_agent_process() -> None:
    assert run_phase_transitions(RunPhase.LAUNCHING_AGENT_PROCESS) == frozenset(
        {RunPhase.INITIALIZING_SESSION, RunPhase.FAILED}
    )


def test_run_phase_transitions_initializing_session() -> None:
    assert run_phase_transitions(RunPhase.INITIALIZING_SESSION) == frozenset(
        {RunPhase.STREAMING_TURN, RunPhase.FAILED}
    )


def test_run_phase_transitions_streaming_turn() -> None:
    assert run_phase_transitions(RunPhase.STREAMING_TURN) == frozenset(
        {
            RunPhase.FINISHING,
            RunPhase.FAILED,
            RunPhase.TIMED_OUT,
            RunPhase.STALLED,
            RunPhase.CANCELED_BY_RECONCILIATION,
        }
    )


def test_run_phase_transitions_finishing() -> None:
    assert run_phase_transitions(RunPhase.FINISHING) == frozenset(
        {RunPhase.SUCCEEDED, RunPhase.FAILED}
    )


@pytest.mark.parametrize(
    "terminal",
    [
        RunPhase.SUCCEEDED,
        RunPhase.FAILED,
        RunPhase.TIMED_OUT,
        RunPhase.STALLED,
        RunPhase.CANCELED_BY_RECONCILIATION,
    ],
)
def test_run_phase_terminal_phases_have_no_outgoing(terminal: RunPhase) -> None:
    assert run_phase_transitions(terminal) == frozenset()


# ---------------------------------------------------------------------------
# assert_allowed_transition
# ---------------------------------------------------------------------------


def test_assert_allowed_transition_succeeds() -> None:
    assert_allowed_transition(ClaimState.UNCLAIMED, ClaimState.CLAIMED)


def test_assert_allowed_transition_raises_for_disallowed() -> None:
    """A disallowed transition raises a SymphonyError subclass."""
    with pytest.raises(SymphonyError) as excinfo:
        assert_allowed_transition(ClaimState.RELEASED, ClaimState.CLAIMED)
    # The error has a code identifying the bad transition.
    assert excinfo.value.code
    assert "released" in str(excinfo.value).lower()


def test_assert_allowed_transition_raises_for_run_phase() -> None:
    with pytest.raises(SymphonyError) as excinfo:
        assert_allowed_transition(RunPhase.SUCCEEDED, RunPhase.STREAMING_TURN)
    assert excinfo.value.code


# ---------------------------------------------------------------------------
# LiveSession
# ---------------------------------------------------------------------------


def test_live_session_starts_in_preparing_workspace() -> None:
    now = datetime(2024, 1, 1, tzinfo=UTC)
    session = LiveSession(
        issue_id="iss-1",
        identifier="#1",
        session_id="sess-1",
        started_at=now,
    )
    assert session.phase == RunPhase.PREPARING_WORKSPACE
    assert session.attempt == 1


def test_live_session_advance_phase_succeeds() -> None:
    now = datetime(2024, 1, 1, tzinfo=UTC)
    session = LiveSession(
        issue_id="iss-1",
        identifier="#1",
        session_id="sess-1",
        started_at=now,
    )
    session.advance_phase(RunPhase.BUILDING_PROMPT)
    assert session.phase == RunPhase.BUILDING_PROMPT


def test_live_session_advance_phase_raises_on_disallowed() -> None:
    now = datetime(2024, 1, 1, tzinfo=UTC)
    session = LiveSession(
        issue_id="iss-1",
        identifier="#1",
        session_id="sess-1",
        started_at=now,
    )
    with pytest.raises(SymphonyError):
        session.advance_phase(RunPhase.SUCCEEDED)


def test_live_session_records_last_codex_event() -> None:
    now = datetime(2024, 1, 1, tzinfo=UTC)
    later = now + timedelta(seconds=1)
    session = LiveSession(
        issue_id="iss-1",
        identifier="#1",
        session_id="sess-1",
        started_at=now,
    )
    session.last_codex_timestamp = later
    assert session.last_codex_timestamp == later


# ---------------------------------------------------------------------------
# RetryEntry
# ---------------------------------------------------------------------------


def test_retry_entry_basic_construction() -> None:
    now = datetime(2024, 1, 1, tzinfo=UTC)
    entry = RetryEntry(
        issue_id="iss-1",
        identifier="#1",
        attempt=2,
        error="boom",
        due_at_ms=int(now.timestamp() * 1000) + 5000,
    )
    assert entry.issue_id == "iss-1"
    assert entry.attempt == 2
    assert entry.due_at_ms > 0


# ---------------------------------------------------------------------------
# OrchestratorState
# ---------------------------------------------------------------------------


def test_orchestrator_state_starts_empty() -> None:
    state = OrchestratorState()
    assert state.running == {}
    assert state.claimed == set()
    assert state.retry_attempts == {}


def test_orchestrator_state_running_count() -> None:
    state = OrchestratorState()
    state.running["iss-1"] = LiveSession(
        issue_id="iss-1",
        identifier="#1",
        session_id="sess-1",
        started_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    state.running["iss-2"] = LiveSession(
        issue_id="iss-2",
        identifier="#2",
        session_id="sess-2",
        started_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    assert state.running_count() == 2


def test_orchestrator_state_is_claimed() -> None:
    state = OrchestratorState()
    state.claimed.add("iss-1")
    assert state.is_claimed("iss-1")
    assert not state.is_claimed("iss-2")


def test_orchestrator_state_is_running() -> None:
    state = OrchestratorState()
    state.running["iss-1"] = LiveSession(
        issue_id="iss-1",
        identifier="#1",
        session_id="sess-1",
        started_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    assert state.is_running("iss-1")
    assert not state.is_running("iss-2")


# ---------------------------------------------------------------------------
# Mutators
# ---------------------------------------------------------------------------


def test_orchestrator_state_claim_unclaimed() -> None:
    state = OrchestratorState()
    state.claim("iss-1")
    assert state.is_claimed("iss-1")


def test_orchestrator_state_claim_already_claimed() -> None:
    """Re-claiming an already-claimed issue is a no-op (the
    transition is allowed via the CLAIMED -> CLAIMED identity is
    not in the graph; the mutator short-circuits)."""
    state = OrchestratorState()
    state.claimed.add("iss-1")
    # The current state is CLAIMED; claim() should detect that and
    # not raise.
    state.claim("iss-1")
    assert state.is_claimed("iss-1")


def test_orchestrator_state_mark_running_after_claim() -> None:
    state = OrchestratorState()
    state.claim("iss-1")
    state.mark_running("iss-1")
    # mark_running requires CLAIMED -> RUNNING, but doesn't put
    # the session in `running`; the worker adds it. We just
    # verify the claim survived.
    assert state.is_claimed("iss-1")


def test_orchestrator_state_release_after_claim() -> None:
    state = OrchestratorState()
    state.claim("iss-1")
    state.release("iss-1")
    assert not state.is_claimed("iss-1")
    assert state.retry_attempts == {}


def test_orchestrator_state_release_after_running() -> None:
    state = OrchestratorState()
    state.claim("iss-1")
    state.running["iss-1"] = LiveSession(
        issue_id="iss-1",
        identifier="#1",
        session_id="sess-1",
        started_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    state.release("iss-1")
    assert not state.is_running("iss-1")
    assert not state.is_claimed("iss-1")


def test_orchestrator_state_release_after_retry_queued() -> None:
    state = OrchestratorState()
    state.claim("iss-1")
    state.running["iss-1"] = LiveSession(
        issue_id="iss-1",
        identifier="#1",
        session_id="sess-1",
        started_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    entry = RetryEntry(
        issue_id="iss-1",
        identifier="#1",
        attempt=1,
        error="boom",
        due_at_ms=1_000_000,
    )
    state.mark_retry_queued("iss-1", entry)
    assert "iss-1" in state.retry_attempts
    state.release("iss-1")
    assert "iss-1" not in state.retry_attempts
    assert "iss-1" not in state.claimed


def test_orchestrator_state_mark_retry_queued_from_running() -> None:
    state = OrchestratorState()
    state.claim("iss-1")
    state.running["iss-1"] = LiveSession(
        issue_id="iss-1",
        identifier="#1",
        session_id="sess-1",
        started_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    entry = RetryEntry(
        issue_id="iss-1",
        identifier="#1",
        attempt=2,
        error="boom",
        due_at_ms=1_000_000,
    )
    state.mark_retry_queued("iss-1", entry)
    assert "iss-1" in state.retry_attempts
    assert not state.is_running("iss-1")


def test_orchestrator_state_mark_retry_queued_from_claimed() -> None:
    """Startup failure path: claimed but never running."""
    state = OrchestratorState()
    state.claim("iss-1")
    entry = RetryEntry(
        issue_id="iss-1",
        identifier="#1",
        attempt=1,
        error="startup failed",
        due_at_ms=1_000_000,
    )
    state.mark_retry_queued("iss-1", entry)
    assert "iss-1" in state.retry_attempts


def test_orchestrator_state_remove_retry() -> None:
    state = OrchestratorState()
    state.retry_attempts["iss-1"] = RetryEntry(
        issue_id="iss-1",
        identifier="#1",
        attempt=1,
        error="boom",
        due_at_ms=1_000_000,
    )
    state.remove_retry("iss-1")
    assert "iss-1" not in state.retry_attempts


def test_orchestrator_state_remove_retry_noop_when_missing() -> None:
    state = OrchestratorState()
    state.remove_retry("nonexistent")
    assert state.retry_attempts == {}


def test_assert_allowed_transition_mixed_types_raises() -> None:
    """Mixing a ClaimState with a RunPhase is an error."""
    with pytest.raises(SymphonyError):
        assert_allowed_transition(ClaimState.UNCLAIMED, RunPhase.SUCCEEDED)
