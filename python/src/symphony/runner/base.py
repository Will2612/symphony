"""Runner base types.

Plan ref: §11 step 13, SPEC §10.4 (event vocabulary),
SPEC §10.6 (error categories), SPEC §10.7 (runner contract).

The Runner is a thin wrapper around the OpenCode app-server (via
`opencode acp`). It exposes:

- `EventKind` — the 12-value enum from SPEC §10.4 that every
  emitted `RunnerEvent` is tagged with.
- `RunnerEvent` — frozen dataclass carrying one structured event
  from the runner to the orchestrator.
- `RunOutcome` — terminal status of a single `run()` invocation.
- `RunnerResult` — frozen dataclass returned from `run()`.
- `Runner` — runtime-checkable `Protocol` that every concrete
  runner (currently only `OpenCodeRunner`) must satisfy.
- `RunnerError` — base class for the 9 runner-layer error
  categories. Defined in `symphony.errors`; re-exported here for
  convenience.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from symphony.errors import RunnerError as _RunnerError

# Re-export so callers can `from symphony.runner.base import RunnerError`.
RunnerError = _RunnerError


class EventKind(StrEnum):
    """The 12 structured event kinds from SPEC §10.4."""

    SESSION_STARTED = "session_started"
    STARTUP_FAILED = "startup_failed"
    TURN_COMPLETED = "turn_completed"
    TURN_FAILED = "turn_failed"
    TURN_CANCELLED = "turn_cancelled"
    TURN_ENDED_WITH_ERROR = "turn_ended_with_error"
    TURN_INPUT_REQUIRED = "turn_input_required"
    APPROVAL_AUTO_APPROVED = "approval_auto_approved"
    UNSUPPORTED_TOOL_CALL = "unsupported_tool_call"
    NOTIFICATION = "notification"
    OTHER_MESSAGE = "other_message"
    MALFORMED = "malformed"


class RunOutcome(StrEnum):
    """Terminal status of a single `Runner.run()` invocation."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    STARTUP_FAILED = "startup_failed"


@dataclass(frozen=True)
class RunnerEvent:
    """One structured event emitted by the runner to the orchestrator.

    Fields:
    - `event`        — the `EventKind` tag.
    - `timestamp`    — UTC timestamp the event was observed.
    - `pid`          — the app-server subprocess PID (if known).
    - `usage`        — OPTIONAL token-count map (`input_tokens`,
                       `output_tokens`, etc.).
    - `payload`      — raw message fields for debugging.
    """

    event: EventKind
    timestamp: datetime
    pid: int | None = None
    usage: dict[str, int] | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RunnerResult:
    """Final result returned by `Runner.run()`.

    - `status`  — terminal outcome (see `RunOutcome`).
    - `events`  — every event emitted during the run.
    - `usage`   — aggregated token usage (caller may have already
                  summed events' usage maps).
    """

    status: RunOutcome
    events: Sequence[RunnerEvent]
    usage: dict[str, int] = field(default_factory=dict)


@runtime_checkable
class Runner(Protocol):
    """Async runner contract (SPEC §10.7).

    Implementations wrap a coding-agent app-server (OpenCode) and
    stream structured events to the orchestrator. A single
    `run()` invocation drives one or more turns; the runner
    returns when the attempt is terminal (success, failure,
    timeout, cancellation, or startup failure).
    """

    async def run(
        self,
        *,
        workspace: Any,  # noqa: ANN401
        prompt: str,
        event_callback: Callable[[RunnerEvent], Awaitable[None]],
        cancel: Any,  # noqa: ANN401
    ) -> RunnerResult: ...
