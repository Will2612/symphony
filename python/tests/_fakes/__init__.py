"""Test doubles used by the test suite.

Re-exported here so `from tests._fakes import FakeClock` works.
Each fake is intentionally minimal in this skeleton step; behavior
lands alongside the production code in the relevant work-plan step.
"""

from tests._fakes.acp import FakeACPStdioServer
from tests._fakes.clock import FakeClock
from tests._fakes.filesystem import FakeFileSystem
from tests._fakes.log import CapturingLogHandler
from tests._fakes.observer import NullObserver
from tests._fakes.runner import Event, EventKind, ScriptedRunner
from tests._fakes.tracker import Issue, MemoryTracker
from tests._fakes.workflow import FakeWorkflowStore

__all__ = [
    "CapturingLogHandler",
    "Event",
    "EventKind",
    "FakeACPStdioServer",
    "FakeClock",
    "FakeFileSystem",
    "FakeWorkflowStore",
    "Issue",
    "MemoryTracker",
    "NullObserver",
    "ScriptedRunner",
]
