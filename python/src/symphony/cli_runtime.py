"""Symphony CLI runtime (SPEC §17.7 + §7.1).

This module is split out from `symphony.cli` so that the pure
arg-parsing logic stays testable. The runtime module owns the
side-effecting factories:

- `CliDeps` — Protocol bundling all the side-effecting functions
  the CLI needs.
- `build_default_deps()` — returns a real `CliDeps` bound to the
  standard library.
- `build_runtime(workflow_path, *, deps)` — loads WORKFLOW.md,
  configures logging, builds a `Tracker`/`Runner`/`WorkspaceManager`,
  starts the `OrchestratorService` as a background asyncio task,
  and starts the observability HTTP server. Returns a
  `RuntimeHandle` the caller can stop and await.
- `wait_for_shutdown(handle, *, deps)` — blocks until the
  orchestrator task finishes, then returns 0 for a clean
  shutdown or 1 for anything else.

The default `wait_for_shutdown` implementation monitors the
background task and propagates KeyboardInterrupt via SIGINT
handlers.
"""

from __future__ import annotations

import asyncio
import os
import signal
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from symphony.config.resolution import resolve
from symphony.config.schema import SymphonyConfig
from symphony.errors import SymphonyError
from symphony.observability.log import configure
from symphony.observability.server import ObservabilityServer, start as obs_start
from symphony.orchestrator.service import OrchestratorService
from symphony.runner.opencode import OpenCodeRunner
from symphony.tracker.github import GitHubTracker
from symphony.tracker.memory import MemoryTracker
from symphony.workflow.loader import Workflow, load
from symphony.workspace.manager import WorkspaceManager

# ---------------------------------------------------------------------------
# CliDeps
# ---------------------------------------------------------------------------


@runtime_checkable
class CliDeps(Protocol):
    """All side-effecting operations the CLI needs."""

    def file_regular(self, path: str) -> bool: ...

    def expand_user(self, path: str) -> str: ...

    def expand_vars(self, path: str) -> str: ...

    def ensure_orchestrator_started(
        self, workflow_path: str, *, logs_root: str | None, port: int | None
    ) -> tuple[bool, str | None]: ...

    def wait_for_shutdown(self, handle: RuntimeHandle) -> int: ...

    def build_runtime(
        self, workflow_path: str, *, logs_root: str | None, port: int | None
    ) -> RuntimeHandle: ...


# ---------------------------------------------------------------------------
# RuntimeHandle
# ---------------------------------------------------------------------------


@dataclass
class RuntimeHandle:
    """The live orchestrator + observability server. Caller must
    `await wait_for_shutdown(handle)` to block until the process
    should exit."""

    workflow_path: str
    config: SymphonyConfig
    service: OrchestratorService | None
    server: ObservabilityServer | None
    server_task: asyncio.Task[None] | None
    service_task: asyncio.Task[None] | None
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)

    def stop(self) -> None:
        """Request graceful shutdown."""
        self.stop_event.set()
        if self.service is not None:
            self.service.stop()
        # NOTE: obs_shutdown is async; we rely on server task
        # cancellation to release the listening socket.
        for task in (self.service_task, self.server_task):
            if task is not None and not task.done():
                task.cancel()


# ---------------------------------------------------------------------------
# default impl
# ---------------------------------------------------------------------------


def _real_file_regular(path: str) -> bool:
    return os.path.isfile(path)


def _real_expand_user(path: str) -> str:
    return os.path.expanduser(path)


def _real_expand_vars(path: str) -> str:
    return os.path.expandvars(path)


def build_default_deps() -> CliDeps:
    """Returns a real `CliDeps` bound to the stdlib + the
    default factories. Tests can pass `runtime_overrides=...` to
    swap individual methods."""
    return _DefaultDeps()


class _DefaultDeps:
    """Default `CliDeps`. Methods dispatch to private fields so
    tests can rebind behavior at runtime (e.g. `deps._file_regular = ...`).
    """

    def __init__(self) -> None:
        self._file_regular: Callable[[str], bool] = _real_file_regular
        self._expand_user: Callable[[str], str] = _real_expand_user
        self._expand_vars: Callable[[str], str] = _real_expand_vars
        self._ensure_orchestrator_started: Callable[..., tuple[bool, str | None]] = (
            _real_ensure_orchestrator_started
        )
        self._build_runtime: Callable[..., RuntimeHandle] = _real_build_runtime
        self._wait_for_shutdown: Callable[[RuntimeHandle], int] = _default_wait_for_shutdown

    def file_regular(self, path: str) -> bool:
        return self._file_regular(path)

    def expand_user(self, path: str) -> str:
        return self._expand_user(path)

    def expand_vars(self, path: str) -> str:
        return self._expand_vars(path)

    def ensure_orchestrator_started(
        self, workflow_path: str, *, logs_root: str | None, port: int | None
    ) -> tuple[bool, str | None]:
        return self._ensure_orchestrator_started(workflow_path, logs_root=logs_root, port=port)

    def build_runtime(
        self, workflow_path: str, *, logs_root: str | None, port: int | None
    ) -> RuntimeHandle:
        return self._build_runtime(workflow_path, logs_root=logs_root, port=port)

    def wait_for_shutdown(self, handle: RuntimeHandle) -> int:
        return self._wait_for_shutdown(handle)


def _real_ensure_orchestrator_started(
    workflow_path: str, *, logs_root: str | None, port: int | None
) -> tuple[bool, str | None]:
    _ = logs_root, port
    if not _real_file_regular(workflow_path):
        return False, f"workflow file missing: {workflow_path}"
    try:
        load(workflow_path)
    except SymphonyError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)
    return True, None


def _real_build_runtime(
    workflow_path: str, *, logs_root: str | None, port: int | None
) -> RuntimeHandle:
    return build_runtime(workflow_path, logs_root=logs_root, port=port)


# ---------------------------------------------------------------------------
# Real runtime builder
# ---------------------------------------------------------------------------


def build_runtime(
    workflow_path: str,
    *,
    logs_root: str | None = None,
    port: int | None = None,
    deps: CliDeps | None = None,
) -> RuntimeHandle:
    """Load WORKFLOW.md, build the orchestrator + observability
    server, and start them in the background. Returns a
    `RuntimeHandle`.

    Implementation note: this entire function runs inside a
    single `asyncio.run()` so the event loop is created,
    used, and torn down atomically. The `asyncio.get_event_loop()`
    calls below would otherwise raise `RuntimeError: There is no
    current event loop in thread 'MainThread'` on Python 3.12+."""
    _ = deps  # accepted for interface uniformity
    return asyncio.run(_build_runtime_async(workflow_path, logs_root, port))


async def _build_runtime_async(
    workflow_path: str,
    logs_root: str | None,
    port: int | None,
) -> RuntimeHandle:
    workflow = load(workflow_path)
    config = _config_from_workflow(workflow, logs_root=logs_root, port=port)
    configure(config)

    workspace_manager = WorkspaceManager(config=config)
    tracker = _build_tracker(workflow, config)
    runner = OpenCodeRunner(config=config)
    service = OrchestratorService(
        config=config,
        tracker=tracker,
        runner=runner,
        workspace_manager=workspace_manager,
    )

    server = await obs_start(config, service)

    loop = asyncio.get_event_loop()
    service_task = loop.create_task(service.run_forever(), name="symphony-orchestrator")
    server_task = loop.create_task(server.server.serve(), name="symphony-server")
    return RuntimeHandle(
        workflow_path=workflow_path,
        config=config,
        service=service,
        server=server,
        server_task=server_task,
        service_task=service_task,
    )


def _config_from_workflow(
    workflow: Workflow, *, logs_root: str | None, port: int | None
) -> SymphonyConfig:
    """Materialize a `SymphonyConfig` from WORKFLOW.md front matter,
    applying CLI overrides for `server.log_file` and `server.port`.

    The base config is built from the YAML mapping in
    `workflow.front_matter` (or the schema defaults if empty).
    """
    base = SymphonyConfig.model_validate(workflow.front_matter or {})
    if logs_root is not None:
        base = base.model_copy(
            update={
                "server": base.server.model_copy(update={"log_file": _default_log_file(logs_root)})
            }
        )
    if port is not None:
        base = base.model_copy(update={"server": base.server.model_copy(update={"port": port})})
    return resolve(base)


def _default_log_file(logs_root: str) -> str:
    return os.path.join(logs_root, "symphony.log")


def _build_tracker(workflow: Workflow, config: SymphonyConfig) -> Any:  # noqa: ANN401
    kind = config.tracker.kind
    if kind == "memory":
        return MemoryTracker()
    if kind == "github":
        return GitHubTracker(config=config)
    raise ValueError(f"Unknown tracker.kind: {kind!r}")


# ---------------------------------------------------------------------------
# wait_for_shutdown — default
# ---------------------------------------------------------------------------


def _default_wait_for_shutdown(handle: RuntimeHandle) -> int:
    """Block until the orchestrator task ends, or the process is
    signalled. Returns 0 for clean, 1 for abnormal.

    The shutdown is initiated by SIGINT/SIGTERM in production and
    by `RuntimeHandle.stop()` in tests.
    """
    loop = asyncio.get_event_loop()
    _install_signal_handlers(loop, handle)
    try:
        return _await_completion(handle)
    except KeyboardInterrupt:
        handle.stop()
        return 0


def _install_signal_handlers(loop: asyncio.AbstractEventLoop, handle: RuntimeHandle) -> None:
    def _handler() -> None:
        handle.stop()

    try:
        loop.add_signal_handler(signal.SIGINT, _handler)
        loop.add_signal_handler(signal.SIGTERM, _handler)
    except (NotImplementedError, RuntimeError):
        # Windows or non-main thread: fall back to default handling.
        pass


def _await_completion(handle: RuntimeHandle) -> int:
    """Wait for service_task; return 0 for clean exit, 1 for error."""
    try:
        return asyncio.run(_wait_for_completion(handle))
    except KeyboardInterrupt:
        handle.stop()
        return 0


async def _wait_for_completion(handle: RuntimeHandle) -> int:
    service_done = handle.service_task
    server_done = handle.server_task
    stop_wait = asyncio.create_task(handle.stop_event.wait())
    pending: set[asyncio.Future[Any] | asyncio.Task[Any]] = set()
    if service_done is not None:
        pending.add(service_done)
    if server_done is not None:
        pending.add(server_done)
    pending.add(stop_wait)
    try:
        done, _pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        if stop_wait in done:
            handle.stop()
            # Drain the rest.
            rest = set(pending) - {stop_wait}
            if rest:
                await asyncio.wait(rest, return_when=asyncio.ALL_COMPLETED)
            for t in rest:
                exc = _task_exception(t)
                if exc is not None and not isinstance(exc, asyncio.CancelledError):
                    return 1
            return 0
        # service or server finished on its own
        handle.stop()
        for t in done:
            exc = _task_exception(t)
            if exc is not None and not isinstance(exc, asyncio.CancelledError):
                return 1
        return 0
    finally:
        if not stop_wait.done():
            stop_wait.cancel()


def _task_exception(task: Any) -> BaseException | None:  # noqa: ANN401
    try:
        return task.exception()  # type: ignore[no-any-return]
    except (asyncio.CancelledError, asyncio.InvalidStateError):
        return None


__all__ = [
    "CliDeps",
    "RuntimeHandle",
    "build_default_deps",
    "build_runtime",
]
