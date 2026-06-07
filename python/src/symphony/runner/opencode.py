"""OpenCode (acp) runner.

Plan ref: §11 step 14, SPEC §10.7 (runner contract) + §10.4
(event vocabulary) + §10.6 (error mapping).

The runner drives an `opencode acp` subprocess and translates
the stream of JSON-RPC messages into typed `RunnerEvent`s
emitted via the orchestrator's `event_callback`.

Spawning rules (SPEC §10.1):
- `bash -lc <codex.command>` so PATH is inherited
- `cwd=workspace`
- 10 MB line buffer on stdout

Error mapping (SPEC §10.6):
- missing binary        -> CodexNotFound
- bad cwd               -> InvalidWorkspaceCwd
- no init response      -> ResponseTimeout
- no turn terminal      -> TurnTimeout
- early EOF             -> PortExit
- JSON-RPC error resp   -> ResponseError
- turn-failed event     -> TurnFailed
- turn-cancelled event  -> TurnCancelled
- turn-input-required   -> TurnInputRequired (hard fail per §10.5)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

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

_LOGGER = logging.getLogger(__name__)

_LINE_BUFFER_BYTES = 10 * 1024 * 1024  # SPEC §10.1 mandatory 10 MB line buffer


# ---------------------------------------------------------------------------
# Forward declarations
# ---------------------------------------------------------------------------


def _make_default_server(cmd: list[str], *, cwd: Path) -> AcpStdioServer:
    return _SubprocessStdioServer(cmd=cmd)


# ---------------------------------------------------------------------------
# AcpStdioServer — abstraction over the opencode subprocess transport
# ---------------------------------------------------------------------------


@runtime_checkable
class AcpStdioServer(Protocol):
    """Async-friendly stdio JSON-RPC transport.

    Concrete implementation spawns the `opencode acp` process via
    `bash -lc <cmd>` with a 10 MB line buffer. Tests inject a fake
    implementation that yields scripted messages.
    """

    async def start(self, *, cwd: Path, env: dict[str, str]) -> None: ...
    async def read_message(self) -> dict[str, Any] | None: ...
    async def send_message(self, message: dict[str, Any]) -> None: ...
    async def wait_closed(self) -> int: ...
    async def kill(self) -> None: ...


@dataclass
class _SubprocessStdioServer:
    """Real subprocess transport that spawns `bash -lc <cmd>`."""

    cmd: list[str]
    process: asyncio.subprocess.Process | None = None
    _reader_task: asyncio.Task[None] | None = None
    _messages: asyncio.Queue[dict[str, Any] | None] = field(default_factory=asyncio.Queue)
    _eof: bool = False

    async def start(self, *, cwd: Path, env: dict[str, str]) -> None:
        try:
            self.process = await asyncio.create_subprocess_exec(
                *self.cmd,
                cwd=str(cwd),
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=_LINE_BUFFER_BYTES,
            )
        except FileNotFoundError as e:
            raise CodexNotFound(
                f"binary not found: {self.cmd[0]}: {e}", code="codex_not_found"
            ) from e
        self._reader_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        assert self.process is not None
        assert self.process.stdout is not None
        try:
            while True:
                line = await self.process.stdout.readline()
                if not line:
                    await self._messages.put(None)
                    self._eof = True
                    return
                try:
                    msg = json.loads(line.decode("utf-8").rstrip("\n"))
                except json.JSONDecodeError:
                    await self._messages.put(
                        {"_malformed": True, "raw": line.decode("utf-8", errors="replace")}
                    )
                    continue
                await self._messages.put(msg)
        except asyncio.CancelledError:
            return

    async def read_message(self) -> dict[str, Any] | None:
        return await self._messages.get()

    async def send_message(self, message: dict[str, Any]) -> None:
        assert self.process is not None
        assert self.process.stdin is not None
        encoded = (json.dumps(message) + "\n").encode("utf-8")
        self.process.stdin.write(encoded)
        await self.process.stdin.drain()

    async def wait_closed(self) -> int:
        assert self.process is not None
        return await self.process.wait()

    async def kill(self) -> None:
        if self._reader_task is not None and not self._reader_task.done():
            self._reader_task.cancel()
        if self.process is not None and self.process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                self.process.kill()


# ---------------------------------------------------------------------------
# OpenCodeRunner
# ---------------------------------------------------------------------------


def _scrub_env() -> dict[str, str]:
    """Drop secret-leaking env vars before spawning opencode subprocess.

    Drops: *API_KEY*, *TOKEN*, *SECRET*, *PASSWORD*, *KEY
    except OPENCODE_API_KEY (opencode needs it for LLM auth).
    GITHUB_TOKEN is the orchestrator's tracker PAT — opencode doesn't
    need it, so it gets dropped.
    """
    SCRUB_SUFFIXES = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "KEY")
    scrub = {
        k for k in os.environ
        if any(k.endswith(s) for s in SCRUB_SUFFIXES)
    }
    scrub.discard("OPENCODE_API_KEY")
    return {k: v for k, v in os.environ.items() if k not in scrub}


@dataclass
class OpenCodeRunner:
    """Async runner that drives `opencode acp` and emits RunnerEvents."""

    config: SymphonyConfig
    server_factory: Callable[..., AcpStdioServer | None] = _make_default_server

    async def run(
        self,
        *,
        workspace: Any,  # noqa: ANN401
        prompt: str,
        event_callback: Callable[[RunnerEvent], Awaitable[None]],
        cancel: Any,  # noqa: ANN401
    ) -> RunnerResult:
        # Extract the path from a Workspace dataclass (preferred) or
        # accept a string path / Path-like as a fallback.
        ws_path_str = getattr(workspace, "path", None)
        if ws_path_str is None:
            ws_path_str = str(workspace)
        ws_path = Path(ws_path_str)
        if not ws_path.is_absolute():
            raise InvalidWorkspaceCwd(
                f"workspace path must be absolute: {ws_path_str}",
                code="invalid_workspace_cwd",
            )
        if not ws_path.is_dir():
            raise InvalidWorkspaceCwd(
                f"workspace not a directory: {ws_path}", code="invalid_workspace_cwd"
            )

        cmd = self._build_command()
        server = self.server_factory(cmd, cwd=ws_path)
        if server is None:
            raise CodexNotFound(f"failed to spawn {cmd!r}", code="codex_not_found")

        events: list[RunnerEvent] = []
        usage: dict[str, int] = {}
        pid: int | None = None

        try:
            env = _scrub_env()
            await server.start(cwd=ws_path, env=env)
            pid = _safe_pid(server)

            # 1) initialize
            await server.send_message(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": 1},
                }
            )
            init_response = await _read_with_timeout(server, self.config.codex.read_timeout_ms)
            _check_error_response(init_response)
            await _emit(
                events,
                EventKind.SESSION_STARTED,
                pid=pid,
                usage=None,
                payload=init_response,
                callback=event_callback,
            )

            # 2) session/new
            await server.send_message(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "session/new",
                    "params": {"cwd": str(ws_path), "mcpServers": []},
                }
            )
            session_response = await _read_with_timeout(server, self.config.codex.read_timeout_ms)
            _check_error_response(session_response)

            # 3) session/prompt
            await server.send_message(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "session/prompt",
                    "params": {
                        "sessionId": _extract_session_id(session_response),
                        "prompt": [{"type": "text", "text": prompt}],
                    },
                }
            )
            turn_response = await _read_with_timeout(server, self.config.codex.read_timeout_ms)
            _check_error_response(turn_response)
            _ = _extract_turn_id(turn_response)  # captured for diagnostics later

            # 4) Stream events until terminal.
            terminal = await self._stream_events(
                server=server,
                pid=pid,
                events=events,
                usage=usage,
                event_callback=event_callback,
                cancel=cancel,
            )
            if terminal is None:
                # Reached EOF without a terminal event.
                raise PortExit(
                    "opencode acp closed stream without terminal event",
                    code="port_exit",
                )
            if terminal is EventKind.TURN_INPUT_REQUIRED:
                raise TurnInputRequired(
                    "opencode acp requested user input (high-trust policy: hard fail)",
                    code="turn_input_required",
                )
            if terminal is EventKind.TURN_FAILED:
                raise TurnFailed(
                    "opencode acp reported turn failure",
                    code="turn_failed",
                )
            if terminal is EventKind.TURN_CANCELLED:
                raise TurnCancelled(
                    "opencode acp reported turn cancellation",
                    code="turn_cancelled",
                )
            if terminal is EventKind.TURN_ENDED_WITH_ERROR:
                raise TurnFailed(
                    "opencode acp ended turn with error",
                    code="turn_failed",
                )
            return RunnerResult(status=RunOutcome.SUCCEEDED, events=events, usage=usage)
        finally:
            await server.kill()
            # best-effort: don't fail if already closed
            with contextlib.suppress(Exception):  # transport may have crashed already
                await server.wait_closed()

    # -- helpers -----------------------------------------------------------

    def _build_command(self) -> list[str]:
        cmd_str = self.config.codex.command
        return ["bash", "-lc", cmd_str]

    async def _stream_events(
        self,
        *,
        server: AcpStdioServer,
        pid: int | None,
        events: list[RunnerEvent],
        usage: dict[str, int],
        event_callback: Callable[[RunnerEvent], Awaitable[None]],
        cancel: Any,  # noqa: ANN401
    ) -> EventKind | None:
        """Read events until a terminal kind or EOF. Returns the
        terminal kind, or None on EOF / cancellation."""
        turn_timeout_s = self.config.codex.turn_timeout_ms / 1000.0
        loop = asyncio.get_event_loop()
        deadline = loop.time() + turn_timeout_s
        while True:
            if cancel is not None and cancel.is_set():
                return EventKind.TURN_CANCELLED
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TurnTimeout(f"turn exceeded {turn_timeout_s:.0f}s", code="turn_timeout")
            try:
                msg = await asyncio.wait_for(server.read_message(), timeout=remaining)
            except TimeoutError as e:
                raise TurnTimeout(
                    f"turn exceeded {turn_timeout_s:.0f}s", code="turn_timeout"
                ) from e
            if msg is None:
                return None
            if msg.get("_malformed"):
                await _emit(
                    events,
                    EventKind.MALFORMED,
                    pid=pid,
                    usage=None,
                    payload={"raw": msg.get("raw", "")},
                    callback=event_callback,
                )
                continue
            kind, payload, event_usage = _classify_event(msg)
            if event_usage is not None:
                for k, v in event_usage.items():
                    if isinstance(v, int):
                        usage[k] = usage.get(k, 0) + v
            await _emit(
                events,
                kind,
                pid=pid,
                usage=event_usage,
                payload=payload,
                callback=event_callback,
            )
            if kind in _TERMINAL_KINDS:
                return kind


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


_TERMINAL_KINDS = frozenset(
    {
        EventKind.TURN_COMPLETED,
        EventKind.TURN_FAILED,
        EventKind.TURN_CANCELLED,
        EventKind.TURN_ENDED_WITH_ERROR,
        EventKind.TURN_INPUT_REQUIRED,
    }
)


def _safe_pid(server: AcpStdioServer) -> int | None:
    proc = getattr(server, "process", None)
    if proc is None:
        return None
    return getattr(proc, "pid", None)


async def _read_with_timeout(server: AcpStdioServer, timeout_ms: int) -> dict[str, Any]:
    timeout_s = timeout_ms / 1000.0
    try:
        msg = await asyncio.wait_for(server.read_message(), timeout=timeout_s)
    except TimeoutError as e:
        raise ResponseTimeout(f"no response within {timeout_ms}ms", code="response_timeout") from e
    if msg is None:
        raise PortExit("opencode acp closed stream during startup", code="port_exit")
    if msg.get("_malformed"):
        raise PortExit(
            f"opencode acp returned malformed JSON: {msg.get('raw', '')[:200]}",
            code="port_exit",
        )
    return msg


def _check_error_response(msg: dict[str, Any]) -> None:
    if "error" in msg:
        err = msg["error"]
        raise ResponseError(
            f"json-rpc error: {err.get('message', err)}",
            code="response_error",
        )


def _extract_session_id(msg: dict[str, Any]) -> str:
    result = msg.get("result") or {}
    sid = result.get("sessionId") or result.get("session_id") or "sess-unknown"
    return str(sid)


def _extract_turn_id(msg: dict[str, Any]) -> str:
    result = msg.get("result") or {}
    tid = result.get("turnId") or result.get("turn_id") or "turn-unknown"
    return str(tid)


def _classify_event(  # noqa: PLR0911, PLR0912 - one branch per event kind
    msg: dict[str, Any],
) -> tuple[EventKind, dict[str, Any], dict[str, int] | None]:
    """Map an opencode JSON-RPC notification to a (EventKind, payload, usage)."""
    method = msg.get("method", "")
    params = msg.get("params") or {}
    # OpenCode uses `kind` for high-level turn updates and
    # `sessionUpdate` for streaming message types.
    kind = params.get("kind") or params.get("update", {}).get("sessionUpdate")
    if method == "session/update" and kind == "done":
        return EventKind.TURN_COMPLETED, params, None
    if method == "session/update" and kind == "failed":
        return EventKind.TURN_FAILED, params, None
    if method == "session/update" and kind == "cancelled":
        return EventKind.TURN_CANCELLED, params, None
    if method == "session/update" and kind == "ended_with_error":
        return EventKind.TURN_ENDED_WITH_ERROR, params, None
    if method == "session/update" and kind == "input_required":
        return EventKind.TURN_INPUT_REQUIRED, params, None
    if method == "session/update" and kind == "approval_auto_approved":
        return EventKind.APPROVAL_AUTO_APPROVED, params, None
    if method == "session/update" and kind == "unsupported_tool_call":
        return EventKind.UNSUPPORTED_TOOL_CALL, params, None
    # Streaming text/tool messages.
    if method == "session/update" and kind in {
        "agent_message",
        "user_message",
        "agent_thought_chunk",
    }:
        return EventKind.NOTIFICATION, params, None
    if method == "session/update" and kind == "usage":
        usage_dict: dict[str, int] = {}
        for k, v in params.items():
            if isinstance(v, int) and k.endswith("_tokens"):
                usage_dict[k] = v
        return EventKind.NOTIFICATION, params, usage_dict or None
    if method.startswith("notifications/"):
        return EventKind.NOTIFICATION, params, None
    if method:
        return EventKind.OTHER_MESSAGE, params, None
    return EventKind.MALFORMED, params, None


async def _emit(
    events: list[RunnerEvent],
    kind: EventKind,
    *,
    pid: int | None,
    usage: dict[str, int] | None,
    payload: dict[str, Any],
    callback: Callable[[RunnerEvent], Awaitable[None]],
) -> None:
    event = RunnerEvent(
        event=kind,
        timestamp=datetime.now(UTC),
        pid=pid,
        usage=usage,
        payload=payload,
    )
    events.append(event)
    await callback(event)


# Sanity: ensure the dataclass satisfies the Runner Protocol at runtime.
_ = isinstance(OpenCodeRunner(config=None), Runner)  # type: ignore[arg-type]
