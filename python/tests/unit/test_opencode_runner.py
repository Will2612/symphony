"""Unit tests for `symphony.runner.opencode`.

Plan ref: §11 step 14, SPEC §10.7 (runner contract) + §10.4
(event mapping) + §10.6 (error categories).

The tests use a `FakeACPStdioServer` that simulates the opencode
app-server in-process. The runner is wired against an
`AcpStdioServer` Protocol so the fake plugs in cleanly.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from symphony.config.schema import SymphonyConfig
from symphony.errors import (
    CodexNotFound,
    InvalidWorkspaceCwd,
    PortExit,
    ResponseError,
    ResponseTimeout,
    TurnCancelled,
    TurnFailed,
    TurnInputRequired,
    TurnTimeout,
)
from symphony.runner.base import (
    EventKind,
    Runner,
    RunnerEvent,
    RunnerResult,
    RunOutcome,
)
from symphony.runner.opencode import OpenCodeRunner, _classify_event, _scrub_env
from symphony.workspace.manager import Workspace

# ---------------------------------------------------------------------------
# FakeACPStdioServer — test double for the opencode acp subprocess
# ---------------------------------------------------------------------------


@dataclass
class _QueuedResponse:
    """A scripted response or event the fake will emit on demand."""

    message: dict[str, Any]
    delay_s: float = 0.0


@dataclass
class FakeACPStdioServer:
    """Simulates an opencode acp JSON-RPC stdio server in-process.

    The fake:
    - accepts `initialize` → returns server capabilities
    - accepts `session/new` → returns a session id
    - accepts `session/prompt` → returns a turn id, then emits
      a sequence of scripted events
    - captures all received requests for assertions
    - can be programmed to fail with various error scenarios
    """

    init_response: dict[str, Any] = field(
        default_factory=lambda: {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"protocolVersion": "v1", "agentCapabilities": {}},
        }
    )
    session_response: dict[str, Any] = field(
        default_factory=lambda: {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {"sessionId": "sess-1"},
        }
    )
    turn_response: dict[str, Any] = field(
        default_factory=lambda: {
            "jsonrpc": "2.0",
            "id": 3,
            "result": {"turnId": "turn-1"},
        }
    )
    # Optional scripted events to emit after the turn is started
    # (each is a JSON-RPC notification; ids are not required).
    turn_events: list[dict[str, Any]] = field(default_factory=list)
    # If set, the next call to handle `session/prompt` raises the
    # given exception (simulating a JSON-RPC error response).
    turn_error: dict[str, Any] | None = None
    # If set, the fake returns this instead of `turn_response` for
    # the `session/prompt` call (simulating immediate failure).
    turn_response_override: dict[str, Any] | None = None
    # If set, the fake crashes the transport with this returncode
    # at the start.
    crash_after_init: int | None = None
    # If True, the fake returns EOF immediately.
    eof: bool = False
    # The fake captures all received requests.
    received: list[dict[str, Any]] = field(default_factory=list)
    # Optional: simulate a `turn_timeout` by sleeping before sending
    # the first event for `turn_timeout_after_s` seconds.
    turn_timeout_after_s: float | None = None
    # Optional: program the fake to send a response_timeout by
    # ignoring a specific id.
    ignore_id: int | None = None

    async def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:  # noqa: PLR0911
        self.received.append(request)
        if self.eof:
            return None
        if self.ignore_id is not None and request.get("id") == self.ignore_id:
            return None
        method = request.get("method", "")
        if method == "initialize":
            return self.init_response
        if method == "session/new":
            return self.session_response
        if method == "session/prompt":
            if self.turn_error is not None:
                return self.turn_error
            if self.turn_response_override is not None:
                return self.turn_response_override
            return self.turn_response
        # Unknown method → return an error
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "error": {"code": -32601, "message": "method not found"},
        }

    def scripted_events(self) -> list[dict[str, Any]]:
        return list(self.turn_events)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config(**overrides: Any) -> SymphonyConfig:
    base: dict[str, Any] = {
        "tracker": {
            "kind": "memory",
            "active_states": ["open"],
            "terminal_states": ["closed"],
        },
        "codex": {
            "command": "opencode acp",
            "read_timeout_ms": 1000,
            "turn_timeout_ms": 5000,
            "stall_timeout_ms": 0,
            "approval_policy": "auto-approve",
            "thread_sandbox": "workspace-write",
            "turn_sandbox_policy": {"writable_roots": ["WORKSPACE"]},
        },
    }
    for k, v in overrides.items():
        if isinstance(v, dict) and k in base:
            base[k].update(v)  # type: ignore[union-attr]
        else:
            base[k] = v
    return SymphonyConfig.model_validate(base)


def _make_workspace(tmp_path: Path) -> Workspace:
    """Create a real `Workspace` on disk so the runner's path-safety
    check passes."""
    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    return Workspace(path=str(ws_dir), key="test-ws", created_now=False)


def _recorder() -> tuple[list[RunnerEvent], Callable[[RunnerEvent], Awaitable[None]]]:
    captured: list[RunnerEvent] = []

    async def _cb(event: RunnerEvent) -> None:
        captured.append(event)

    return captured, _cb


# ---------------------------------------------------------------------------
# Construction & startup
# ---------------------------------------------------------------------------


def test_opencode_runner_is_a_runner() -> None:
    runner = OpenCodeRunner(_config(), server_factory=lambda *a, **kw: None)
    assert isinstance(runner, Runner)


def test_opencode_runner_uses_bash_lc_with_path(tmp_path: Path) -> None:
    """The command is spawned via `bash -lc <cmd>` so PATH is
    inherited (SPEC §10.1)."""
    captured_cmd: dict[str, Any] = {}

    class _FakeServer:
        async def start(self, *, cwd: Path, env: dict[str, str]) -> None:
            captured_cmd["cwd"] = cwd
            captured_cmd["env"] = env

        async def read_message(self) -> dict[str, Any] | None:
            return None

        async def send_message(self, message: dict[str, Any]) -> None:
            pass

        async def wait_closed(self) -> int:
            return 0

        async def kill(self) -> None:
            pass

    def _factory(cmd: list[str], *, cwd: Path) -> Any:
        captured_cmd["cmd"] = cmd
        return _FakeServer()

    runner = OpenCodeRunner(_config(), server_factory=_factory)
    ws = _make_workspace(tmp_path)
    _, cb = _recorder()
    cancel = asyncio.Event()

    async def _run() -> RunnerResult:
        return await runner.run(
            workspace=ws,
            prompt="hello",
            event_callback=cb,
            cancel=cancel,
        )

    with pytest.raises(PortExit):
        asyncio.run(_run())
    assert "cmd" in captured_cmd
    cmd = captured_cmd["cmd"]
    assert cmd[0] == "bash"
    assert cmd[1] == "-lc"
    assert cmd[2] == "opencode acp"
    assert str(captured_cmd["cwd"]) == ws.path


# ---------------------------------------------------------------------------
# End-to-end via custom fake
# ---------------------------------------------------------------------------


@dataclass
class _ScriptedServer:
    """A more flexible fake that yields a scripted sequence of
    messages (responses or notifications) interleaved with sleeps."""

    script: list[tuple[float, dict[str, Any] | None]] = field(default_factory=list)
    sent: list[dict[str, Any]] = field(default_factory=list)
    killed: bool = False
    closed: bool = False

    async def start(self, *, cwd: Path, env: dict[str, str]) -> None:
        pass

    async def read_message(self) -> dict[str, Any] | None:
        if not self.script:
            return None
        delay, msg = self.script.pop(0)
        if delay > 0:
            await asyncio.sleep(delay)
        return msg

    async def send_message(self, message: dict[str, Any]) -> None:
        self.sent.append(message)

    async def wait_closed(self) -> int:
        return 0

    async def kill(self) -> None:
        self.killed = True


def test_opencode_runner_emits_session_started_event(tmp_path: Path) -> None:
    """On a successful initialize, the runner emits SESSION_STARTED."""
    server = _ScriptedServer(
        script=[
            (0.0, {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "v1"}}),
            (0.0, {"jsonrpc": "2.0", "id": 2, "result": {"sessionId": "sess-1"}}),
            (0.0, {"jsonrpc": "2.0", "id": 3, "result": {"turnId": "turn-1"}}),
            (0.0, {"jsonrpc": "2.0", "method": "session/update", "params": {"kind": "done"}}),
            (0.0, None),  # EOF
        ]
    )
    runner = OpenCodeRunner(_config(), server_factory=lambda *a, **kw: server)
    ws = _make_workspace(tmp_path)
    captured, cb = _recorder()
    cancel = asyncio.Event()

    result = asyncio.run(runner.run(workspace=ws, prompt="hi", event_callback=cb, cancel=cancel))
    assert result.status == RunOutcome.SUCCEEDED
    kinds = [e.event for e in captured]
    assert EventKind.SESSION_STARTED in kinds
    assert EventKind.TURN_COMPLETED in kinds


def test_opencode_runner_returns_succeeded_with_usage(tmp_path: Path) -> None:
    """Usage info from a turn message is aggregated into the result."""
    server = _ScriptedServer(
        script=[
            (0.0, {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "v1"}}),
            (0.0, {"jsonrpc": "2.0", "id": 2, "result": {"sessionId": "sess-1"}}),
            (0.0, {"jsonrpc": "2.0", "id": 3, "result": {"turnId": "turn-1"}}),
            (
                0.0,
                {
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {
                        "kind": "usage",
                        "input_tokens": 100,
                        "output_tokens": 50,
                    },
                },
            ),
            (0.0, {"jsonrpc": "2.0", "method": "session/update", "params": {"kind": "done"}}),
            (0.0, None),
        ]
    )
    runner = OpenCodeRunner(_config(), server_factory=lambda *a, **kw: server)
    ws = _make_workspace(tmp_path)
    _, cb = _recorder()
    cancel = asyncio.Event()

    result = asyncio.run(runner.run(workspace=ws, prompt="hi", event_callback=cb, cancel=cancel))
    assert result.status == RunOutcome.SUCCEEDED
    assert result.usage.get("input_tokens") == 100
    assert result.usage.get("output_tokens") == 50


# ---------------------------------------------------------------------------
# Error categories
# ---------------------------------------------------------------------------


def test_opencode_runner_raises_invalid_workspace_cwd(tmp_path: Path) -> None:
    """A non-existent workspace path raises InvalidWorkspaceCwd."""
    runner = OpenCodeRunner(_config(), server_factory=lambda *a, **kw: None)
    missing_ws = Workspace(path=str(tmp_path / "does-not-exist"), key="x", created_now=False)
    _, cb = _recorder()
    cancel = asyncio.Event()

    with pytest.raises(InvalidWorkspaceCwd):
        asyncio.run(runner.run(workspace=missing_ws, prompt="hi", event_callback=cb, cancel=cancel))


def test_opencode_runner_raises_response_timeout_on_init(tmp_path: Path) -> None:
    """If the initialize response is never received within
    read_timeout_ms, ResponseTimeout is raised."""

    class _HangingServer:
        async def start(self, *, cwd: Path, env: dict[str, str]) -> None:
            pass

        async def read_message(self) -> dict[str, Any] | None:
            await asyncio.sleep(10)  # never returns
            return None

        async def send_message(self, message: dict[str, Any]) -> None:
            pass

        async def wait_closed(self) -> int:
            return 0

        async def kill(self) -> None:
            pass

    cfg = _config(codex={"read_timeout_ms": 50})
    runner = OpenCodeRunner(cfg, server_factory=lambda *a, **kw: _HangingServer())
    ws = _make_workspace(tmp_path)
    _, cb = _recorder()
    cancel = asyncio.Event()

    with pytest.raises(ResponseTimeout):
        asyncio.run(runner.run(workspace=ws, prompt="hi", event_callback=cb, cancel=cancel))


def test_opencode_runner_raises_response_error_on_jsonrpc_error(tmp_path: Path) -> None:
    """A JSON-RPC error response from initialize raises ResponseError."""
    server = _ScriptedServer(
        script=[
            (
                0.0,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "error": {"code": -32600, "message": "bad init"},
                },
            ),
            (0.0, None),
        ]
    )
    runner = OpenCodeRunner(_config(), server_factory=lambda *a, **kw: server)
    ws = _make_workspace(tmp_path)
    _, cb = _recorder()
    cancel = asyncio.Event()

    with pytest.raises(ResponseError):
        asyncio.run(runner.run(workspace=ws, prompt="hi", event_callback=cb, cancel=cancel))


def test_opencode_runner_raises_turn_timeout(tmp_path: Path) -> None:
    """If the turn never produces a terminal event within
    turn_timeout_ms, TurnTimeout is raised."""

    class _HangingTurnServer:
        def __init__(self) -> None:
            self.handshakes_sent = 0
            self.hang = False

        async def start(self, *, cwd: Path, env: dict[str, str]) -> None:
            pass

        async def read_message(self) -> dict[str, Any] | None:
            if self.hang:
                await asyncio.sleep(10)
                return None
            self.handshakes_sent += 1
            if self.handshakes_sent == 1:
                return {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "v1"}}
            if self.handshakes_sent == 2:
                return {"jsonrpc": "2.0", "id": 2, "result": {"sessionId": "sess-1"}}
            if self.handshakes_sent == 3:
                return {"jsonrpc": "2.0", "id": 3, "result": {"turnId": "turn-1"}}
            # After the prompt is acknowledged, hang forever.
            self.hang = True
            await asyncio.sleep(10)
            return None

        async def send_message(self, message: dict[str, Any]) -> None:
            pass

        async def wait_closed(self) -> int:
            return 0

        async def kill(self) -> None:
            pass

    cfg = _config(codex={"turn_timeout_ms": 50, "read_timeout_ms": 1000})
    runner = OpenCodeRunner(cfg, server_factory=lambda *a, **kw: _HangingTurnServer())
    ws = _make_workspace(tmp_path)
    _, cb = _recorder()
    cancel = asyncio.Event()

    with pytest.raises(TurnTimeout):
        asyncio.run(runner.run(workspace=ws, prompt="hi", event_callback=cb, cancel=cancel))


def test_opencode_runner_raises_port_exit_on_early_eof(tmp_path: Path) -> None:
    """If the server returns EOF during startup (before init
    response), PortExit is raised."""
    server = _ScriptedServer(script=[(0.0, None)])
    runner = OpenCodeRunner(_config(), server_factory=lambda *a, **kw: server)
    ws = _make_workspace(tmp_path)
    _, cb = _recorder()
    cancel = asyncio.Event()

    with pytest.raises(PortExit):
        asyncio.run(runner.run(workspace=ws, prompt="hi", event_callback=cb, cancel=cancel))


def test_opencode_runner_raises_turn_failed_on_failed_event(tmp_path: Path) -> None:
    """A `session/update` with `kind=failed` raises TurnFailed."""
    server = _ScriptedServer(
        script=[
            (0.0, {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "v1"}}),
            (0.0, {"jsonrpc": "2.0", "id": 2, "result": {"sessionId": "sess-1"}}),
            (0.0, {"jsonrpc": "2.0", "id": 3, "result": {"turnId": "turn-1"}}),
            (
                0.0,
                {
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {"kind": "failed", "message": "boom"},
                },
            ),
            (0.0, None),
        ]
    )
    runner = OpenCodeRunner(_config(), server_factory=lambda *a, **kw: server)
    ws = _make_workspace(tmp_path)
    _, cb = _recorder()
    cancel = asyncio.Event()

    with pytest.raises(TurnFailed):
        asyncio.run(runner.run(workspace=ws, prompt="hi", event_callback=cb, cancel=cancel))


def test_opencode_runner_raises_turn_cancelled_on_cancelled_event(tmp_path: Path) -> None:
    """A `session/update` with `kind=cancelled` raises TurnCancelled."""
    server = _ScriptedServer(
        script=[
            (0.0, {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "v1"}}),
            (0.0, {"jsonrpc": "2.0", "id": 2, "result": {"sessionId": "sess-1"}}),
            (0.0, {"jsonrpc": "2.0", "id": 3, "result": {"turnId": "turn-1"}}),
            (
                0.0,
                {
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {"kind": "cancelled"},
                },
            ),
            (0.0, None),
        ]
    )
    runner = OpenCodeRunner(_config(), server_factory=lambda *a, **kw: server)
    ws = _make_workspace(tmp_path)
    _, cb = _recorder()
    cancel = asyncio.Event()

    with pytest.raises(TurnCancelled):
        asyncio.run(runner.run(workspace=ws, prompt="hi", event_callback=cb, cancel=cancel))


def test_opencode_runner_raises_turn_input_required(tmp_path: Path) -> None:
    """A `session/update` with `kind=input_required` raises
    TurnInputRequired (SPEC §10.5: hard-fail high-trust policy)."""
    server = _ScriptedServer(
        script=[
            (0.0, {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "v1"}}),
            (0.0, {"jsonrpc": "2.0", "id": 2, "result": {"sessionId": "sess-1"}}),
            (0.0, {"jsonrpc": "2.0", "id": 3, "result": {"turnId": "turn-1"}}),
            (
                0.0,
                {
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {"kind": "input_required", "message": "approve?"},
                },
            ),
            (0.0, None),
        ]
    )
    runner = OpenCodeRunner(_config(), server_factory=lambda *a, **kw: server)
    ws = _make_workspace(tmp_path)
    _, cb = _recorder()
    cancel = asyncio.Event()

    with pytest.raises(TurnInputRequired):
        asyncio.run(runner.run(workspace=ws, prompt="hi", event_callback=cb, cancel=cancel))


# ---------------------------------------------------------------------------
# CodexNotFound: surfaced when the binary is missing
# ---------------------------------------------------------------------------


def test_opencode_runner_raises_codex_not_found(tmp_path: Path) -> None:
    """If the server factory returns None, the runner treats it as
    a missing binary."""

    def _factory(*a: Any, **kw: Any) -> None:
        return None

    runner = OpenCodeRunner(_config(), server_factory=_factory)
    ws = _make_workspace(tmp_path)
    _, cb = _recorder()
    cancel = asyncio.Event()

    with pytest.raises(CodexNotFound):
        asyncio.run(runner.run(workspace=ws, prompt="hi", event_callback=cb, cancel=cancel))


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


def test_opencode_runner_cancellation_kills_server(tmp_path: Path) -> None:
    server = _ScriptedServer(
        script=[
            (0.0, {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "v1"}}),
            (0.0, {"jsonrpc": "2.0", "id": 2, "result": {"sessionId": "sess-1"}}),
            (0.0, {"jsonrpc": "2.0", "id": 3, "result": {"turnId": "turn-1"}}),
        ]
    )
    runner = OpenCodeRunner(_config(), server_factory=lambda *a, **kw: server)
    ws = _make_workspace(tmp_path)
    _, cb = _recorder()
    cancel = asyncio.Event()
    cancel.set()  # pre-cancelled

    with pytest.raises(TurnCancelled):
        asyncio.run(runner.run(workspace=ws, prompt="hi", event_callback=cb, cancel=cancel))
    assert server.killed


# ---------------------------------------------------------------------------
# Subprocess transport (skipped in unit tests; live e2e in Step 26)
# ---------------------------------------------------------------------------


def test_classify_event_malformed_payload() -> None:
    """A JSON-RPC message with no method AND no id is classified as MALFORMED."""
    kind, _, _ = _classify_event({})
    assert kind == EventKind.MALFORMED


def test_classify_event_session_update_kinds() -> None:
    """All session/update `kind` values map to the expected EventKind."""
    cases = [
        ({"method": "session/update", "params": {"kind": "done"}}, EventKind.TURN_COMPLETED),
        ({"method": "session/update", "params": {"kind": "failed"}}, EventKind.TURN_FAILED),
        ({"method": "session/update", "params": {"kind": "cancelled"}}, EventKind.TURN_CANCELLED),
        (
            {"method": "session/update", "params": {"kind": "ended_with_error"}},
            EventKind.TURN_ENDED_WITH_ERROR,
        ),
        (
            {"method": "session/update", "params": {"kind": "input_required"}},
            EventKind.TURN_INPUT_REQUIRED,
        ),
        (
            {"method": "session/update", "params": {"kind": "approval_auto_approved"}},
            EventKind.APPROVAL_AUTO_APPROVED,
        ),
        (
            {"method": "session/update", "params": {"kind": "unsupported_tool_call"}},
            EventKind.UNSUPPORTED_TOOL_CALL,
        ),
        ({"method": "session/update", "params": {"kind": "agent_message"}}, EventKind.NOTIFICATION),
        (
            {"method": "session/update", "params": {"kind": "agent_thought_chunk"}},
            EventKind.NOTIFICATION,
        ),
        ({"method": "notifications/status", "params": {}}, EventKind.NOTIFICATION),
        (
            {"method": "session/update", "params": {"update": {"sessionUpdate": "user_message"}}},
            EventKind.NOTIFICATION,
        ),
        ({"method": "some/other", "params": {}}, EventKind.OTHER_MESSAGE),
    ]
    for msg, expected in cases:
        kind, _, _ = _classify_event(msg)
        assert kind == expected, f"expected {expected} for {msg}, got {kind}"


def test_classify_event_usage_extracts_tokens() -> None:
    """A usage notification returns the token-count dict."""
    _, _, usage = _classify_event(
        {
            "method": "session/update",
            "params": {"kind": "usage", "input_tokens": 5, "output_tokens": 3},
        }
    )
    assert usage == {"input_tokens": 5, "output_tokens": 3}


def test_classify_event_usage_no_tokens_returns_none() -> None:
    _, _, usage = _classify_event({"method": "session/update", "params": {"kind": "usage"}})
    assert usage is None


def test_opencode_runner_emits_malformed_event(tmp_path: Path) -> None:
    """A malformed JSON message from the server yields a MALFORMED event."""
    server = _ScriptedServer(
        script=[
            (0.0, {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "v1"}}),
            (0.0, {"jsonrpc": "2.0", "id": 2, "result": {"sessionId": "sess-1"}}),
            (0.0, {"jsonrpc": "2.0", "id": 3, "result": {"turnId": "turn-1"}}),
            (0.0, {"_malformed": True, "raw": "not json"}),
            (0.0, {"jsonrpc": "2.0", "method": "session/update", "params": {"kind": "done"}}),
            (0.0, None),
        ]
    )
    runner = OpenCodeRunner(_config(), server_factory=lambda *a, **kw: server)
    ws = _make_workspace(tmp_path)
    captured, cb = _recorder()
    cancel = asyncio.Event()
    result = asyncio.run(runner.run(workspace=ws, prompt="hi", event_callback=cb, cancel=cancel))
    assert result.status == RunOutcome.SUCCEEDED
    assert EventKind.MALFORMED in [e.event for e in captured]


def test_opencode_runner_emits_unsupported_tool_call(tmp_path: Path) -> None:
    server = _ScriptedServer(
        script=[
            (0.0, {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "v1"}}),
            (0.0, {"jsonrpc": "2.0", "id": 2, "result": {"sessionId": "sess-1"}}),
            (0.0, {"jsonrpc": "2.0", "id": 3, "result": {"turnId": "turn-1"}}),
            (
                0.0,
                {
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {"kind": "unsupported_tool_call", "tool": "linear_graphql"},
                },
            ),
            (0.0, {"jsonrpc": "2.0", "method": "session/update", "params": {"kind": "done"}}),
            (0.0, None),
        ]
    )
    runner = OpenCodeRunner(_config(), server_factory=lambda *a, **kw: server)
    ws = _make_workspace(tmp_path)
    captured, cb = _recorder()
    cancel = asyncio.Event()
    result = asyncio.run(runner.run(workspace=ws, prompt="hi", event_callback=cb, cancel=cancel))
    assert result.status == RunOutcome.SUCCEEDED
    assert EventKind.UNSUPPORTED_TOOL_CALL in [e.event for e in captured]


def test_opencode_runner_emits_ended_with_error_event(tmp_path: Path) -> None:
    """A `kind=ended_with_error` is treated as TurnFailed."""
    server = _ScriptedServer(
        script=[
            (0.0, {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "v1"}}),
            (0.0, {"jsonrpc": "2.0", "id": 2, "result": {"sessionId": "sess-1"}}),
            (0.0, {"jsonrpc": "2.0", "id": 3, "result": {"turnId": "turn-1"}}),
            (
                0.0,
                {
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {"kind": "ended_with_error", "message": "boom"},
                },
            ),
            (0.0, None),
        ]
    )
    runner = OpenCodeRunner(_config(), server_factory=lambda *a, **kw: server)
    ws = _make_workspace(tmp_path)
    _, cb = _recorder()
    cancel = asyncio.Event()
    with pytest.raises(TurnFailed):
        asyncio.run(runner.run(workspace=ws, prompt="hi", event_callback=cb, cancel=cancel))


def test_opencode_runner_malformed_response_during_startup(tmp_path: Path) -> None:
    """A malformed line during startup raises PortExit."""
    server = _ScriptedServer(
        script=[
            (0.0, {"_malformed": True, "raw": "garbage"}),
            (0.0, None),
        ]
    )
    runner = OpenCodeRunner(_config(), server_factory=lambda *a, **kw: server)
    ws = _make_workspace(tmp_path)
    _, cb = _recorder()
    cancel = asyncio.Event()
    with pytest.raises(PortExit):
        asyncio.run(runner.run(workspace=ws, prompt="hi", event_callback=cb, cancel=cancel))


def test_opencode_runner_malformed_response_at_session_new(tmp_path: Path) -> None:
    """A malformed response for session/new raises PortExit."""
    server = _ScriptedServer(
        script=[
            (0.0, {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "v1"}}),
            (0.0, {"_malformed": True, "raw": "garbage"}),
            (0.0, None),
        ]
    )
    runner = OpenCodeRunner(_config(), server_factory=lambda *a, **kw: server)
    ws = _make_workspace(tmp_path)
    _, cb = _recorder()
    cancel = asyncio.Event()
    with pytest.raises(PortExit):
        asyncio.run(runner.run(workspace=ws, prompt="hi", event_callback=cb, cancel=cancel))


def test_opencode_runner_malformed_response_at_prompt(tmp_path: Path) -> None:
    """A malformed response for session/prompt raises PortExit."""
    server = _ScriptedServer(
        script=[
            (0.0, {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "v1"}}),
            (0.0, {"jsonrpc": "2.0", "id": 2, "result": {"sessionId": "sess-1"}}),
            (0.0, {"_malformed": True, "raw": "garbage"}),
            (0.0, None),
        ]
    )
    runner = OpenCodeRunner(_config(), server_factory=lambda *a, **kw: server)
    ws = _make_workspace(tmp_path)
    _, cb = _recorder()
    cancel = asyncio.Event()
    with pytest.raises(PortExit):
        asyncio.run(runner.run(workspace=ws, prompt="hi", event_callback=cb, cancel=cancel))


def test_opencode_runner_emits_approval_auto_approved(tmp_path: Path) -> None:
    server = _ScriptedServer(
        script=[
            (0.0, {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "v1"}}),
            (0.0, {"jsonrpc": "2.0", "id": 2, "result": {"sessionId": "sess-1"}}),
            (0.0, {"jsonrpc": "2.0", "id": 3, "result": {"turnId": "turn-1"}}),
            (
                0.0,
                {
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {"kind": "approval_auto_approved", "tool": "bash"},
                },
            ),
            (0.0, {"jsonrpc": "2.0", "method": "session/update", "params": {"kind": "done"}}),
            (0.0, None),
        ]
    )
    runner = OpenCodeRunner(_config(), server_factory=lambda *a, **kw: server)
    ws = _make_workspace(tmp_path)
    captured, cb = _recorder()
    cancel = asyncio.Event()
    result = asyncio.run(runner.run(workspace=ws, prompt="hi", event_callback=cb, cancel=cancel))
    assert result.status == RunOutcome.SUCCEEDED
    assert EventKind.APPROVAL_AUTO_APPROVED in [e.event for e in captured]


# ---------------------------------------------------------------------------
# _scrub_env: credential scrubbing
# ---------------------------------------------------------------------------


def test_scrub_env_drops_credentials_only() -> None:
    """Verify _scrub_env drops secret-leaking vars but preserves opencode-needed ones."""
    import os

    # Set up test env with mix of secret and non-secret vars
    os.environ["GITHUB_TOKEN"] = "x"
    os.environ["OPENCODE_API_KEY"] = "y"
    os.environ["MY_API_KEY"] = "z"
    os.environ["HOME"] = "/h"
    os.environ["PATH"] = "/p"
    os.environ["XDG_CONFIG_HOME"] = "/x"
    os.environ["GIT_DIR"] = "/g"

    scrubbed = _scrub_env()

    # Should be dropped (secret-leaking)
    assert "GITHUB_TOKEN" not in scrubbed, "GITHUB_TOKEN (orchestrator PAT) should be dropped"
    assert "MY_API_KEY" not in scrubbed, "MY_API_KEY should be dropped"

    # Should be preserved (opencode needs OPENCODE_API_KEY for LLM auth)
    assert "OPENCODE_API_KEY" in scrubbed, "OPENCODE_API_KEY must be preserved for opencode LLM auth"
    assert scrubbed["OPENCODE_API_KEY"] == "y"

    # Should be preserved (non-secret)
    assert "HOME" in scrubbed, "HOME should be preserved"
    assert "PATH" in scrubbed, "PATH should be preserved"
    assert "XDG_CONFIG_HOME" in scrubbed, "XDG_CONFIG_HOME should be preserved"
    assert "GIT_DIR" in scrubbed, "GIT_DIR should be preserved"
