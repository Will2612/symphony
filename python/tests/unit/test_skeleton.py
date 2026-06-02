"""Smoke tests for the Step 1 skeleton.

These tests exist so `make test` is green on the empty package; the
real per-behavior tests land in the subsequent work-plan steps. They
deliberately exercise the public surfaces that the rest of the
suite will rely on:

- `symphony.__version__` is a non-empty string.
- Every fake from `tests._fakes` is importable and instantiable.
- The `FakeClock.now()` returns a UTC-aware `datetime`.
- The `MemoryTracker` records an issue and yields it back.
- The `ScriptedRunner` records a prompt and emits queued events.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest
from tests._fakes import (
    CapturingLogHandler,
    Event,
    EventKind,
    FakeACPStdioServer,
    FakeClock,
    FakeFileSystem,
    FakeWorkflowStore,
    Issue,
    MemoryTracker,
    NullObserver,
    ScriptedRunner,
)

import symphony


def test_symphony_version_is_non_empty_string() -> None:
    assert isinstance(symphony.__version__, str)
    assert symphony.__version__


def test_eight_fakes_are_importable() -> None:
    assert isinstance(FakeClock(), FakeClock)
    assert isinstance(FakeFileSystem(), FakeFileSystem)
    assert isinstance(MemoryTracker(), MemoryTracker)
    assert isinstance(ScriptedRunner(), ScriptedRunner)
    assert isinstance(FakeACPStdioServer(), FakeACPStdioServer)
    assert isinstance(FakeWorkflowStore(), FakeWorkflowStore)
    assert isinstance(CapturingLogHandler(), CapturingLogHandler)
    assert isinstance(NullObserver(), NullObserver)


def test_fake_clock_now_is_utc_aware() -> None:
    clock = FakeClock()
    now = clock.now()
    assert isinstance(now, datetime)
    assert now.tzinfo is not None
    assert now.utcoffset() is not None
    assert now.utcoffset().total_seconds() == 0


def test_fake_clock_advance_moves_time_forward() -> None:
    clock = FakeClock()
    start = clock.now()
    clock.advance(1_000)
    later = clock.now()
    assert (later - start).total_seconds() == pytest.approx(1.0)


def test_memory_tracker_records_and_yields_issue() -> None:
    tracker = MemoryTracker()
    issue = Issue(id="i-1", identifier="ORG-1", title="hello", state="open")
    tracker.add(issue)
    assert tracker.issues["i-1"] is issue


def test_scripted_runner_records_prompt_and_replays_events() -> None:
    runner = ScriptedRunner()
    seen: list[Event] = []

    async def collect(event: Event) -> None:
        seen.append(event)

    async def go() -> None:
        runner.queue(Event(kind=EventKind.SESSION_STARTED))
        runner.queue(Event(kind=EventKind.TURN_COMPLETED))
        session = await runner.start_session(workspace=object(), codex_cfg={})
        await runner.run_turn(session, "hello", collect)

    asyncio.run(go())

    assert runner.recorded_prompts == ["hello"]
    assert [e.kind for e in seen] == [EventKind.SESSION_STARTED, EventKind.TURN_COMPLETED]
