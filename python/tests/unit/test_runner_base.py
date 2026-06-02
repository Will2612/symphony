"""Unit tests for `symphony.runner.base`.

Plan ref: §11 step 13, SPEC §10.4 (event vocabulary) + §10.6
(error categories) + §10.7 (runner contract).

The base module provides the `Runner` Protocol, the `EventKind`
enum (12 values per SPEC §10.4), and a `RunnerError` hierarchy
that all 9 runner-specific error categories inherit from.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from symphony.errors import (
    CodexNotFound,
    InvalidWorkspaceCwd,
    PortExit,
    ResponseError,
    ResponseTimeout,
    SymphonyError,
    TurnCancelled,
    TurnFailed,
    TurnInputRequired,
    TurnTimeout,
)
from symphony.runner.base import (
    EventKind,
    Runner,
    RunnerError,
    RunnerEvent,
    RunnerResult,
    RunOutcome,
)

# ---------------------------------------------------------------------------
# EventKind
# ---------------------------------------------------------------------------


def test_event_kind_has_all_12_values() -> None:
    expected = {
        "session_started",
        "startup_failed",
        "turn_completed",
        "turn_failed",
        "turn_cancelled",
        "turn_ended_with_error",
        "turn_input_required",
        "approval_auto_approved",
        "unsupported_tool_call",
        "notification",
        "other_message",
        "malformed",
    }
    assert {e.value for e in EventKind} == expected


def test_event_kind_string_values_match_spec() -> None:
    """The string form is part of the log/observability contract."""
    assert EventKind.SESSION_STARTED.value == "session_started"
    assert EventKind.STARTUP_FAILED.value == "startup_failed"
    assert EventKind.TURN_COMPLETED.value == "turn_completed"
    assert EventKind.TURN_FAILED.value == "turn_failed"
    assert EventKind.TURN_CANCELLED.value == "turn_cancelled"
    assert EventKind.TURN_ENDED_WITH_ERROR.value == "turn_ended_with_error"
    assert EventKind.TURN_INPUT_REQUIRED.value == "turn_input_required"
    assert EventKind.APPROVAL_AUTO_APPROVED.value == "approval_auto_approved"
    assert EventKind.UNSUPPORTED_TOOL_CALL.value == "unsupported_tool_call"
    assert EventKind.NOTIFICATION.value == "notification"
    assert EventKind.OTHER_MESSAGE.value == "other_message"
    assert EventKind.MALFORMED.value == "malformed"


# ---------------------------------------------------------------------------
# RunOutcome
# ---------------------------------------------------------------------------


def test_run_outcome_values() -> None:
    assert RunOutcome.SUCCEEDED.value == "succeeded"
    assert RunOutcome.FAILED.value == "failed"
    assert RunOutcome.TIMED_OUT.value == "timed_out"
    assert RunOutcome.CANCELLED.value == "cancelled"
    assert RunOutcome.STARTUP_FAILED.value == "startup_failed"


# ---------------------------------------------------------------------------
# RunnerEvent
# ---------------------------------------------------------------------------


def test_runner_event_is_frozen() -> None:
    ts = datetime(2024, 1, 1, tzinfo=UTC)
    event = RunnerEvent(
        event=EventKind.SESSION_STARTED, timestamp=ts, pid=1234, usage=None, payload={}
    )
    with pytest.raises((AttributeError, TypeError)):  # FrozenInstanceError
        event.event = EventKind.TURN_COMPLETED  # type: ignore[misc]


def test_runner_event_default_payload() -> None:
    ts = datetime(2024, 1, 1, tzinfo=UTC)
    event = RunnerEvent(event=EventKind.SESSION_STARTED, timestamp=ts)
    assert event.pid is None
    assert event.usage is None
    assert event.payload == {}


def test_runner_event_preserves_payload() -> None:
    ts = datetime(2024, 1, 1, tzinfo=UTC)
    event = RunnerEvent(
        event=EventKind.NOTIFICATION,
        timestamp=ts,
        pid=42,
        usage={"input_tokens": 100, "output_tokens": 50},
        payload={"method": "some/jsonrpc/method", "data": {"x": 1}},
    )
    assert event.event == EventKind.NOTIFICATION
    assert event.pid == 42
    assert event.usage == {"input_tokens": 100, "output_tokens": 50}
    assert event.payload == {"method": "some/jsonrpc/method", "data": {"x": 1}}


# ---------------------------------------------------------------------------
# RunnerResult
# ---------------------------------------------------------------------------


def test_runner_result_carries_status_and_events() -> None:
    ts = datetime(2024, 1, 1, tzinfo=UTC)
    events = [
        RunnerEvent(event=EventKind.SESSION_STARTED, timestamp=ts),
        RunnerEvent(event=EventKind.TURN_COMPLETED, timestamp=ts),
    ]
    result = RunnerResult(status=RunOutcome.SUCCEEDED, events=events, usage={"input_tokens": 10})
    assert result.status == RunOutcome.SUCCEEDED
    assert list(result.events) == events
    assert result.usage == {"input_tokens": 10}


def test_runner_result_defaults_to_empty_usage() -> None:
    result = RunnerResult(status=RunOutcome.FAILED, events=[])
    assert result.usage == {}


# ---------------------------------------------------------------------------
# RunnerError hierarchy
# ---------------------------------------------------------------------------


def test_runner_error_is_symphony_error() -> None:
    assert issubclass(RunnerError, SymphonyError)


@pytest.mark.parametrize(
    "cls",
    [
        CodexNotFound,
        InvalidWorkspaceCwd,
        ResponseTimeout,
        TurnTimeout,
        PortExit,
        ResponseError,
        TurnFailed,
        TurnCancelled,
        TurnInputRequired,
    ],
)
def test_all_runner_specific_errors_inherit_from_runner_error(cls: type[Exception]) -> None:
    assert issubclass(cls, RunnerError)
    assert issubclass(cls, SymphonyError)


def test_runner_error_can_catch_all_9_categories() -> None:
    """`except RunnerError:` catches every runner-layer error."""
    classes = [
        CodexNotFound,
        InvalidWorkspaceCwd,
        ResponseTimeout,
        TurnTimeout,
        PortExit,
        ResponseError,
        TurnFailed,
        TurnCancelled,
        TurnInputRequired,
    ]
    for cls in classes:
        try:
            raise cls("boom")
        except RunnerError as caught:
            assert caught.code
        else:
            pytest.fail(f"{cls.__name__} did not raise as RunnerError")


# ---------------------------------------------------------------------------
# Runner Protocol
# ---------------------------------------------------------------------------


def test_runner_protocol_runtime_checkable_accepts_conforming_class() -> None:
    class _MyRunner:
        async def run(
            self,
            *,
            workspace: Any,
            prompt: str,
            event_callback: Any,
            cancel: Any,
        ) -> RunnerResult:
            return RunnerResult(status=RunOutcome.SUCCEEDED, events=[])

    assert isinstance(_MyRunner(), Runner)


def test_runner_protocol_rejects_class_without_run() -> None:
    class _NotARunner:
        pass

    assert not isinstance(_NotARunner(), Runner)
