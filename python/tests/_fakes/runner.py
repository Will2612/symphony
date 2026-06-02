"""ScriptedRunner — a Runner Protocol stub that records prompts and replays events.

Step 1 skeleton: provides a `record_prompts` list and a `scripted_events`
queue. Real Protocol conformance and the full event vocabulary land
in the runner work-plan step (plan §11 step 14).
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class EventKind(StrEnum):
    """Subset of the SPEC §10.4 event vocabulary; full enum lives in
    `symphony.runner.base` once the runner module is implemented."""

    SESSION_STARTED = "session_started"
    TURN_COMPLETED = "turn_completed"
    TURN_FAILED = "turn_failed"
    TURN_CANCELLED = "turn_cancelled"
    TURN_INPUT_REQUIRED = "turn_input_required"
    APPROVAL_REQUIRED = "approval_required"
    NOTIFICATION = "notification"
    OTHER_MESSAGE = "other_message"
    MALFORMED = "malformed"
    UNSUPPORTED_TOOL_CALL = "unsupported_tool_call"
    APPROVAL_AUTO_APPROVED = "approval_auto_approved"


@dataclass
class Event:
    kind: EventKind
    payload: dict[str, object] = field(default_factory=dict)
    session_id: str = ""
    ts: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


@dataclass
class ScriptedRunner:
    """A Runner stub that records prompts and replays scripted events.

    Real Protocol conformance (Runner.start_session / run_turn /
    stop_session) is added in the runner work-plan step.
    """

    name: str = "scripted"
    recorded_prompts: list[str] = field(default_factory=list)
    scripted_events: list[Event] = field(default_factory=list)

    def queue(self, *events: Event) -> None:
        self.scripted_events.extend(events)

    async def start_session(self, workspace: object, codex_cfg: dict[str, object]) -> object:
        return object()

    async def run_turn(
        self,
        session: object,
        prompt: str,
        on_event: Callable[[Event], Awaitable[None]],
    ) -> str:
        self.recorded_prompts.append(prompt)
        for event in self.scripted_events:
            await on_event(event)
        return "success"

    async def stop_session(self, session: object) -> None:
        return None
