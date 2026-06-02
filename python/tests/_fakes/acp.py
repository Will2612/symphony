"""FakeACPStdioServer — an in-memory stand-in for the `opencode acp` subprocess.

Step 1 skeleton: holds a `StreamReader`/`StreamWriter` pair on each
end. The script-driven protocol logic lands in the runner work-plan
step (plan §11 step 14).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass
class _End:
    reader: object
    writer: object


@dataclass
class FakeACPStdioServer:
    """A bidirectional in-memory pipe that pretends to be `opencode acp`.

    The test wires one end to the runner's subprocess stdin/stdout
    and drives the other end from the test. The protocol parsing
    logic lands in the runner work-plan step.
    """

    _server_end: _End | None = None
    _client_end: _End | None = None
    sent_lines: list[str] = field(default_factory=list)
    scripted_replies: list[str] = field(default_factory=list)

    @contextmanager
    def ends(self) -> Iterator[tuple[object, object, object, object]]:
        raise NotImplementedError(
            "FakeACPStdioServer.ends() lands in the runner work-plan step "
            "(plan §11 step 14). Use MemoryTracker + ScriptedRunner for "
            "current tests."
        )
