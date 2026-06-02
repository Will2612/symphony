"""pytest fixtures for the Symphony test suite.

This file imports the test doubles from `tests/_fakes/` and exposes
them as pytest fixtures, so individual tests can take them as
parameters without importing them directly.

The fakes are stubs in this skeleton step; their Protocol
conformance is added in the relevant work-plan step.
"""

from __future__ import annotations

import pytest

from tests._fakes import (
    CapturingLogHandler,
    FakeACPStdioServer,
    FakeClock,
    FakeFileSystem,
    FakeWorkflowStore,
    MemoryTracker,
    NullObserver,
    ScriptedRunner,
)


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def fake_filesystem() -> FakeFileSystem:
    return FakeFileSystem()


@pytest.fixture
def memory_tracker() -> MemoryTracker:
    return MemoryTracker()


@pytest.fixture
def scripted_runner() -> ScriptedRunner:
    return ScriptedRunner()


@pytest.fixture
def fake_acp() -> FakeACPStdioServer:
    return FakeACPStdioServer()


@pytest.fixture
def fake_workflow_store() -> FakeWorkflowStore:
    return FakeWorkflowStore()


@pytest.fixture
def capturing_log_handler() -> CapturingLogHandler:
    return CapturingLogHandler()


@pytest.fixture
def null_observer() -> NullObserver:
    return NullObserver()
