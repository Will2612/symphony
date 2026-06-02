"""Workspace hook execution.

A hook is a shell command run in a workspace context per SPEC §9.4.
The four supported hooks are `after_create`, `before_run`, `after_run`,
`before_remove`; each is optional. The hook command runs under
`bash -lc <command>` with `cwd=workspace`.

Failure semantics (per SPEC §9.4):
- `after_create` failure or timeout is fatal to workspace creation.
- `before_run` failure or timeout is fatal to the current run attempt.
- `after_run` failure or timeout is logged and ignored.
- `before_remove` failure or timeout is logged and ignored.

The default `HookRunner` uses `asyncio.create_subprocess_exec` and
enforces a timeout (default `hooks.timeout_ms` from config, with a
hard floor of 1 ms). Tests can substitute `FakeHookRunner` from
`tests/_fakes/` to script responses without spawning a real bash.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol

from symphony.errors import HookFailed, HookTimeout

_LOGGER = logging.getLogger(__name__)

HookCommand = str
WorkspacePath = str


@dataclass(frozen=True)
class HookResult:
    """Result of a hook execution.

    `status` is the integer exit code (0 = success). `output` is the
    combined stdout+stderr text, truncated to 8 KB to avoid
    unbounded memory. `timed_out` is True if the process was killed
    because it exceeded the timeout.
    """

    status: int
    output: str
    timed_out: bool = False


class HookRunner(Protocol):
    """Strategy interface for executing a hook command."""

    async def run(
        self,
        command: HookCommand,
        workspace: WorkspacePath,
        timeout_ms: int,
    ) -> HookResult: ...


_DEFAULT_MAX_OUTPUT_BYTES = 8 * 1024


class SubprocessHookRunner:
    """Default `HookRunner` that shells out to `bash -lc <command>`."""

    def __init__(self, max_output_bytes: int = _DEFAULT_MAX_OUTPUT_BYTES) -> None:
        self._max_output_bytes = max_output_bytes

    async def run(
        self,
        command: HookCommand,
        workspace: WorkspacePath,
        timeout_ms: int,
    ) -> HookResult:
        timeout_seconds = max(timeout_ms, 1) / 1000.0
        proc = await asyncio.create_subprocess_exec(
            "bash",
            "-lc",
            command,
            cwd=workspace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            _LOGGER.warning(
                "hook timed out; process killed",
                extra={"workspace": workspace, "timeout_ms": timeout_ms},
            )
            return HookResult(status=-1, output="", timed_out=True)
        raw = stdout.decode("utf-8", errors="replace") if stdout else ""
        truncated = self._truncate(raw)
        return HookResult(
            status=proc.returncode if proc.returncode is not None else -1, output=truncated
        )

    def _truncate(self, text: str) -> str:
        if len(text.encode("utf-8")) <= self._max_output_bytes:
            return text
        return text[: self._max_output_bytes] + "... (truncated)"


class ScriptedHookRunner:
    """Test double: yields pre-scripted `HookResult`s in order.

    `script` is a list of `HookResult` objects (or callables that
    return a `HookResult`). After the list is exhausted, returns a
    successful result for any further call.
    """

    def __init__(self, script: list[HookResult] | None = None) -> None:
        self.script: list[HookResult] = list(script or [])
        self.calls: list[tuple[HookCommand, WorkspacePath, int]] = []

    async def run(
        self,
        command: HookCommand,
        workspace: WorkspacePath,
        timeout_ms: int,
    ) -> HookResult:
        self.calls.append((command, workspace, timeout_ms))
        if self.script:
            return self.script.pop(0)
        return HookResult(status=0, output="")


# Module-level helper used by `WorkspaceManager` and tests.
async def invoke_hook(
    runner: HookRunner,
    *,
    hook_name: str,
    command: HookCommand,
    workspace: WorkspacePath,
    timeout_ms: int,
    fatal: bool,
) -> HookResult:
    """Run a hook and translate non-zero/timeout into typed errors
    iff `fatal` is True. Returns the underlying `HookResult` either way."""
    _LOGGER.info(
        "running workspace hook",
        extra={"hook": hook_name, "workspace": workspace, "fatal": fatal},
    )
    result = await runner.run(command, workspace, timeout_ms)
    if result.timed_out:
        _LOGGER.warning(
            "hook timed out",
            extra={
                "hook": hook_name,
                "workspace": workspace,
                "timeout_ms": timeout_ms,
                "fatal": fatal,
            },
        )
        if fatal:
            raise HookTimeout(
                f"hook {hook_name!r} timed out after {timeout_ms}ms",
                hook_name=hook_name,
                timeout_ms=timeout_ms,
            )
        return result
    if result.status != 0:
        _LOGGER.warning(
            "hook failed",
            extra={
                "hook": hook_name,
                "workspace": workspace,
                "status": result.status,
                "fatal": fatal,
            },
        )
        if fatal:
            raise HookFailed(
                f"hook {hook_name!r} failed with status {result.status}",
                hook_name=hook_name,
                status=result.status,
                output=result.output,
            )
    return result


__all__ = [
    "HookCommand",
    "HookResult",
    "HookRunner",
    "ScriptedHookRunner",
    "SubprocessHookRunner",
    "WorkspacePath",
    "invoke_hook",
]
