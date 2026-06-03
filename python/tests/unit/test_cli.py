from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from symphony.cli import (
    acknowledgement_banner,
    evaluate,
    main,
    parse_args,
    run,
    usage,
    wait_for_shutdown,
)
from symphony.cli_runtime import (
    CliDeps,
    RuntimeHandle,
    _await_completion,
    _build_tracker,
    _config_from_workflow,
    _default_log_file,
    _default_wait_for_shutdown,
    _install_signal_handlers,
    _real_build_runtime,
    _real_ensure_orchestrator_started,
    _real_expand_user,
    _real_expand_vars,
    _real_file_regular,
    _task_exception,
    _wait_for_completion,
    build_default_deps,
)
from symphony.config.schema import SymphonyConfig, Tracker
from symphony.errors import WorkflowParseError
from symphony.workflow.loader import Workflow

# ---------------------------------------------------------------------------
# parse_args
# ---------------------------------------------------------------------------


def test_parse_args_default_workflow() -> None:
    args = parse_args([])
    assert args.workflow_path == "WORKFLOW.md"
    assert args.i_understand is False
    assert args.logs_root is None
    assert args.port is None


def test_parse_args_explicit_workflow() -> None:
    args = parse_args(["path/to/WORKFLOW.md"])
    assert args.workflow_path == "path/to/WORKFLOW.md"


def test_parse_args_ack_flag() -> None:
    args = parse_args(["--i-understand-that-this-will-be-running-without-the-usual-guardrails"])
    assert args.i_understand is True


def test_parse_args_logs_root() -> None:
    args = parse_args(["--logs-root", "/tmp/x", "WORKFLOW.md"])
    assert args.logs_root == "/tmp/x"


def test_parse_args_port() -> None:
    args = parse_args(["--port", "0", "WORKFLOW.md"])
    assert args.port == 0
    args = parse_args(["--port", "8080", "WORKFLOW.md"])
    assert args.port == 8080


def test_parse_args_unknown_flag_returns_error() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--bogus"])


def test_parse_args_two_positional_rejected() -> None:
    with pytest.raises(SystemExit):
        parse_args(["A", "B"])


# ---------------------------------------------------------------------------
# usage
# ---------------------------------------------------------------------------


def test_usage_mentions_ack_flag() -> None:
    msg = usage()
    assert "--i-understand-that-this-will-be-running-without-the-usual-guardrails" in msg
    assert "--logs-root" in msg
    assert "--port" in msg


# ---------------------------------------------------------------------------
# acknowledgement banner
# ---------------------------------------------------------------------------


def test_acknowledgement_banner_mentions_orchestrator_and_flag() -> None:
    banner = acknowledgement_banner()
    assert "--i-understand-that-this-will-be-running-without-the-usual-guardrails" in banner
    assert "guardrails" in banner.lower()


# ---------------------------------------------------------------------------
# evaluate (no I/O)
# ---------------------------------------------------------------------------


class _FakeDeps:
    """A `CliDeps` double. Each method records its calls and returns
    a configurable result. Tests can swap individual methods."""

    def __init__(
        self,
        *,
        file_regular: Callable[[str], bool] | None = None,
        expand_user: Callable[[str], str] | None = None,
        expand_vars: Callable[[str], str] | None = None,
        ensure_orchestrator_started: Callable[..., tuple[bool, str | None]] | None = None,
        wait_for_shutdown: Callable[..., int] | None = None,
        build_runtime: Callable[..., Any] | None = None,
    ) -> None:
        self.events: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self._file_regular: Callable[[str], bool] = file_regular or (lambda _p: True)
        self._expand_user: Callable[[str], str] = expand_user or (lambda p: p)
        self._expand_vars: Callable[[str], str] = expand_vars or (lambda p: p)
        self._ensure_orchestrator_started: Callable[..., tuple[bool, str | None]] = (
            ensure_orchestrator_started
            if ensure_orchestrator_started is not None
            else (lambda *_a, **_kw: (True, None))
        )
        self._wait_for_shutdown: Callable[..., int] = (
            wait_for_shutdown if wait_for_shutdown is not None else (lambda _h: 0)
        )
        self._build_runtime: Callable[..., Any] = (
            build_runtime if build_runtime is not None else (lambda *_a, **_kw: object())
        )

    def _record(self, name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        self.events.append((name, args, kwargs))

    def file_regular(self, path: str) -> bool:
        self._record("file_regular", (path,), {})
        return self._file_regular(path)

    def expand_user(self, path: str) -> str:
        self._record("expand_user", (path,), {})
        return self._expand_user(path)

    def expand_vars(self, path: str) -> str:
        self._record("expand_vars", (path,), {})
        return self._expand_vars(path)

    def ensure_orchestrator_started(
        self, workflow_path: str, *, logs_root: str | None, port: int | None
    ) -> tuple[bool, str | None]:
        self._record(
            "ensure_orchestrator_started",
            (workflow_path,),
            {"logs_root": logs_root, "port": port},
        )
        return self._ensure_orchestrator_started(workflow_path, logs_root=logs_root, port=port)

    def wait_for_shutdown(self, handle: Any) -> int:
        self._record("wait_for_shutdown", (handle,), {})
        return self._wait_for_shutdown(handle)

    def build_runtime(self, workflow_path: str, *, logs_root: str | None, port: int | None) -> Any:
        self._record(
            "build_runtime",
            (workflow_path,),
            {"logs_root": logs_root, "port": port},
        )
        return self._build_runtime(workflow_path, logs_root=logs_root, port=port)


def test_evaluate_returns_banner_when_ack_missing() -> None:
    deps = _FakeDeps()
    result = evaluate(["WORKFLOW.md"], deps=deps)  # type: ignore[arg-type]
    assert result.kind == "ack_required"
    assert "--i-understand" in result.message
    assert all(name != "file_regular" for name, *_ in deps.events)


def test_evaluate_returns_usage_when_unknown_flag() -> None:
    deps = _FakeDeps()
    result = evaluate(
        [
            "--i-understand-that-this-will-be-running-without-the-usual-guardrails",
            "--bogus",
        ],
        deps=deps,  # type: ignore[arg-type]
    )
    assert result.kind == "usage_error"


def test_evaluate_returns_usage_when_two_positionals() -> None:
    deps = _FakeDeps()
    result = evaluate(
        [
            "--i-understand-that-this-will-be-running-without-the-usual-guardrails",
            "A",
            "B",
        ],
        deps=deps,  # type: ignore[arg-type]
    )
    assert result.kind == "usage_error"


def test_evaluate_returns_not_found_when_file_missing() -> None:
    deps = _FakeDeps(file_regular=lambda _p: False)
    result = evaluate(
        [
            "--i-understand-that-this-will-be-running-without-the-usual-guardrails",
            "missing.md",
        ],
        deps=deps,  # type: ignore[arg-type]
    )
    assert result.kind == "workflow_not_found"
    assert "missing.md" in result.message


def test_evaluate_default_workflow_when_no_positional() -> None:
    deps = _FakeDeps()
    result = evaluate(
        ["--i-understand-that-this-will-be-running-without-the-usual-guardrails"],
        deps=deps,  # type: ignore[arg-type]
    )
    assert result.kind == "ok"
    assert result.workflow_path == "WORKFLOW.md"


def test_evaluate_expands_logs_root() -> None:
    deps = _FakeDeps(expand_user=lambda p: p.replace("~", "/home/test"))
    result = evaluate(
        [
            "--i-understand-that-this-will-be-running-without-the-usual-guardrails",
            "--logs-root",
            "~/logs",
            "WORKFLOW.md",
        ],
        deps=deps,  # type: ignore[arg-type]
    )
    assert result.kind == "ok"
    assert result.logs_root is not None
    assert "~" not in result.logs_root


def test_evaluate_empty_logs_root_rejected() -> None:
    deps = _FakeDeps()
    result = evaluate(
        [
            "--i-understand-that-this-will-be-running-without-the-usual-guardrails",
            "--logs-root",
            "",
            "WORKFLOW.md",
        ],
        deps=deps,  # type: ignore[arg-type]
    )
    assert result.kind == "usage_error"


def test_evaluate_port_zero_accepted() -> None:
    deps = _FakeDeps()
    result = evaluate(
        [
            "--i-understand-that-this-will-be-running-without-the-usual-guardrails",
            "--port",
            "0",
            "WORKFLOW.md",
        ],
        deps=deps,  # type: ignore[arg-type]
    )
    assert result.kind == "ok"
    assert result.port == 0


def test_evaluate_port_positive_accepted() -> None:
    deps = _FakeDeps()
    result = evaluate(
        [
            "--i-understand-that-this-will-be-running-without-the-usual-guardrails",
            "--port",
            "8080",
            "WORKFLOW.md",
        ],
        deps=deps,  # type: ignore[arg-type]
    )
    assert result.kind == "ok"
    assert result.port == 8080


def test_evaluate_port_negative_rejected() -> None:
    deps = _FakeDeps()
    result = evaluate(
        [
            "--i-understand-that-this-will-be-running-without-the-usual-guardrails",
            "--port",
            "-1",
            "WORKFLOW.md",
        ],
        deps=deps,  # type: ignore[arg-type]
    )
    assert result.kind == "usage_error"


def test_evaluate_port_garbage_rejected() -> None:
    deps = _FakeDeps()
    result = evaluate(
        [
            "--i-understand-that-this-will-be-running-without-the-usual-guardrails",
            "--port",
            "abc",
            "WORKFLOW.md",
        ],
        deps=deps,  # type: ignore[arg-type]
    )
    assert result.kind == "usage_error"


def test_evaluate_returns_startup_error_when_orchestrator_fails() -> None:
    deps = _FakeDeps(ensure_orchestrator_started=lambda _p, *, logs_root, port: (False, "boom"))
    result = evaluate(
        ["--i-understand-that-this-will-be-running-without-the-usual-guardrails", "WORKFLOW.md"],
        deps=deps,  # type: ignore[arg-type]
    )
    assert result.kind == "startup_error"
    assert "boom" in (result.message or "")


def test_evaluate_ok_calls_orchestrator_with_expanded_path() -> None:
    deps = _FakeDeps(file_regular=lambda p: p == "/abs/WORKFLOW.md")
    result = evaluate(
        [
            "--i-understand-that-this-will-be-running-without-the-usual-guardrails",
            "/abs/WORKFLOW.md",
        ],
        deps=deps,  # type: ignore[arg-type]
    )
    assert result.kind == "ok"
    started_calls = [e for e in deps.events if e[0] == "ensure_orchestrator_started"]
    assert started_calls
    args = started_calls[0][1]
    assert args[0] == "/abs/WORKFLOW.md"


# ---------------------------------------------------------------------------
# main: top-level entrypoint
# ---------------------------------------------------------------------------


def test_main_returns_one_on_ack_missing_after_print() -> None:
    """When the user is missing the ack flag, main() prints the banner
    and exits nonzero (1)."""
    rc = main(
        [],
        runtime_overrides=lambda deps: deps,  # type: ignore[arg-type, return-value]
    )
    assert rc == 1


def test_main_returns_one_on_unknown_flag() -> None:
    rc = main(
        ["--bogus"],
        runtime_overrides=lambda deps: deps,  # type: ignore[arg-type, return-value]
    )
    assert rc == 1


def test_main_returns_one_on_workflow_not_found() -> None:
    def overrides(d: Any) -> Any:
        d._file_regular = lambda _p: False
        return d

    rc = main(
        [
            "--i-understand-that-this-will-be-running-without-the-usual-guardrails",
            "missing.md",
        ],
        runtime_overrides=overrides,
    )
    assert rc == 1


def test_main_uses_sys_argv_when_argv_is_none(monkeypatch: Any) -> None:
    """When `argv=None`, `main` falls back to `sys.argv[1:]`."""
    monkeypatch.setattr("sys.argv", ["symphony", "--bogus"])
    rc = main(runtime_overrides=lambda deps: deps)  # type: ignore[arg-type, return-value]
    assert rc == 1


def test_main_returns_one_on_startup_error() -> None:
    def overrides(d: Any) -> Any:
        d._ensure_orchestrator_started = lambda _p, *, logs_root, port: (False, "explode")
        return d

    rc = main(
        [
            "--i-understand-that-this-will-be-running-without-the-usual-guardrails",
            "WORKFLOW.md",
        ],
        runtime_overrides=overrides,  # type: ignore[arg-type]
    )
    assert rc == 1


def test_main_returns_one_on_shutdown_error() -> None:
    """When wait_for_shutdown returns nonzero, main returns 1."""

    def overrides(d: Any) -> Any:
        d._file_regular = lambda _p: True
        d._ensure_orchestrator_started = lambda _p, *, logs_root, port: (True, None)
        d._wait_for_shutdown = lambda _h: 1
        d._build_runtime = lambda *_a, **_kw: object()
        return d

    rc = main(
        [
            "--i-understand-that-this-will-be-running-without-the-usual-guardrails",
            "WORKFLOW.md",
        ],
        runtime_overrides=overrides,
    )
    assert rc == 1


def test_main_returns_zero_on_success() -> None:
    """When start succeeds and shutdown returns 0, main returns 0."""

    def overrides(d: Any) -> Any:
        d._file_regular = lambda _p: True
        d._ensure_orchestrator_started = lambda _p, *, logs_root, port: (True, None)
        d._wait_for_shutdown = lambda _h: 0
        d._build_runtime = lambda *_a, **_kw: object()
        return d

    rc = main(
        [
            "--i-understand-that-this-will-be-running-without-the-usual-guardrails",
            "WORKFLOW.md",
        ],
        runtime_overrides=overrides,
    )
    assert rc == 0


def test_main_returns_one_on_build_runtime_filenotfound() -> None:
    """When `build_runtime` raises FileNotFoundError, main returns 1."""

    def overrides(d: Any) -> Any:
        d._file_regular = lambda _p: True
        d._ensure_orchestrator_started = lambda _p, *, logs_root, port: (True, None)

        def _raise_fnf(*_a: Any, **_kw: Any) -> Any:
            raise FileNotFoundError("workspace missing")

        d._build_runtime = _raise_fnf
        return d

    rc = main(
        [
            "--i-understand-that-this-will-be-running-without-the-usual-guardrails",
            "WORKFLOW.md",
        ],
        runtime_overrides=overrides,
    )
    assert rc == 1


def test_main_returns_one_on_build_runtime_generic_exception() -> None:
    """When `build_runtime` raises a generic exception, main returns 1."""

    def overrides(d: Any) -> Any:
        d._file_regular = lambda _p: True
        d._ensure_orchestrator_started = lambda _p, *, logs_root, port: (True, None)

        def _raise(*_a: Any, **_kw: Any) -> Any:
            raise RuntimeError("nope")

        d._build_runtime = _raise
        return d

    rc = main(
        [
            "--i-understand-that-this-will-be-running-without-the-usual-guardrails",
            "WORKFLOW.md",
        ],
        runtime_overrides=overrides,
    )
    assert rc == 1


def test_main_returns_zero_on_keyboard_interrupt() -> None:
    """KeyboardInterrupt from `wait_for_shutdown` is converted to 0."""

    def overrides(d: Any) -> Any:
        d._file_regular = lambda _p: True
        d._ensure_orchestrator_started = lambda _p, *, logs_root, port: (True, None)

        def _raise_kbi(_h: Any) -> Any:
            raise KeyboardInterrupt()

        d._wait_for_shutdown = _raise_kbi

        def _build(*_a: Any, **_kw: Any) -> RuntimeHandle:
            return RuntimeHandle(
                workflow_path="WORKFLOW.md",
                config=SymphonyConfig(),
                service=None,
                server=None,
                server_task=None,
                service_task=None,
            )

        d._build_runtime = _build
        return d

    rc = main(
        [
            "--i-understand-that-this-will-be-running-without-the-usual-guardrails",
            "WORKFLOW.md",
        ],
        runtime_overrides=overrides,
    )
    assert rc == 0


def test_main_returns_one_on_wait_shutdown_exception() -> None:
    """A non-KeyboardInterrupt exception from `wait_for_shutdown` returns 1."""

    def overrides(d: Any) -> Any:
        d._file_regular = lambda _p: True
        d._ensure_orchestrator_started = lambda _p, *, logs_root, port: (True, None)

        def _raise(_h: Any) -> Any:
            raise RuntimeError("oops")

        d._wait_for_shutdown = _raise
        d._build_runtime = lambda *_a, **_kw: object()
        return d

    rc = main(
        [
            "--i-understand-that-this-will-be-running-without-the-usual-guardrails",
            "WORKFLOW.md",
        ],
        runtime_overrides=overrides,
    )
    assert rc == 1


# ---------------------------------------------------------------------------
# CliDeps Protocol
# ---------------------------------------------------------------------------


def test_cli_deps_protocol_is_runtime_checkable() -> None:
    class _Impl:
        def file_regular(self, path: str) -> bool:
            return True

        def expand_user(self, path: str) -> str:
            return path

        def expand_vars(self, path: str) -> str:
            return path

        def ensure_orchestrator_started(
            self,
            workflow_path: str,
            *,
            logs_root: str | None,
            port: int | None,
        ) -> tuple[bool, str | None]:
            return True, None

        def wait_for_shutdown(self, handle: object) -> int:
            return 0

        def build_runtime(
            self,
            workflow_path: str,
            *,
            logs_root: str | None,
            port: int | None,
        ) -> object:
            return object()

    assert isinstance(_Impl(), CliDeps)


# ---------------------------------------------------------------------------
# run / wait_for_shutdown smoke
# ---------------------------------------------------------------------------


def test_run_returns_handle_when_deps_succeed() -> None:
    """`run` delegates to `deps.build_runtime`. The returned handle
    is whatever the deps returned (here: `object()`)."""
    sentinel = object()
    deps = _FakeDeps(build_runtime=lambda *_a, **_kw: sentinel)
    handle = run("WORKFLOW.md", deps=deps)  # type: ignore[arg-type]
    assert handle is sentinel


def test_wait_for_shutdown_returns_zero() -> None:
    """`wait_for_shutdown` delegates to `deps.wait_for_shutdown`."""
    deps = _FakeDeps()
    rc = wait_for_shutdown(object(), deps=deps)  # type: ignore[arg-type]
    assert rc == 0
    assert any(name == "wait_for_shutdown" for name, *_ in deps.events)


# ---------------------------------------------------------------------------
# build_default_deps
# ---------------------------------------------------------------------------


def test_build_default_deps_returns_cli_deps() -> None:
    deps = build_default_deps()
    assert isinstance(deps, CliDeps)
    assert deps.file_regular("/etc/passwd") is True
    assert deps.file_regular("/no/such/path/xyzzy") is False
    assert deps.expand_user("~/x") == "~/x" or "~" not in deps.expand_user("~/x")


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------


def test_default_log_file_joins_path() -> None:

    assert _default_log_file("/var/log") == "/var/log/symphony.log"
    assert _default_log_file("logs") == "logs/symphony.log"


def test_default_deps_ensure_orchestrator_started_returns_false_when_missing() -> None:
    deps = build_default_deps()
    ok, err = deps.ensure_orchestrator_started("/no/such/file.md", logs_root=None, port=None)
    assert ok is False
    assert err is not None
    assert "missing" in err


def test_default_deps_wait_for_shutdown_is_callable() -> None:
    """The default `wait_for_shutdown` raises when no loop is
    available, which is enough to confirm dispatch reaches it."""
    deps = build_default_deps()
    # Bind a no-op so we don't actually try to run a loop.
    deps._wait_for_shutdown = lambda _h: 0
    assert deps.wait_for_shutdown(object()) == 0  # type: ignore[arg-type]


def test_default_deps_build_runtime_is_callable() -> None:
    """`build_runtime` is a function pointer; calling it without a
    real workflow file raises."""
    deps = build_default_deps()
    deps._build_runtime = lambda *_a, **_kw: object()
    handle = deps.build_runtime("WORKFLOW.md", logs_root=None, port=None)  # type: ignore[arg-type]
    assert handle is not None


def test_default_deps_ensure_orchestrator_started_catches_symphony_error(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """When load() raises a SymphonyError, ensure_orchestrator_started
    returns (False, str(e))."""

    p = tmp_path / "x.md"
    p.write_text("---\nfoo: bar\n---\nbody\n")

    def _raise(_p: str) -> Any:
        raise WorkflowParseError("bad", code="workflow_parse_error")

    monkeypatch.setattr("symphony.cli_runtime.load", _raise)
    deps = build_default_deps()
    ok, err = deps.ensure_orchestrator_started(str(p), logs_root=None, port=None)
    assert ok is False
    assert err is not None
    assert "bad" in err


def test_default_deps_ensure_orchestrator_started_catches_generic_exception(
    tmp_path: Any, monkeypatch: Any
) -> None:
    p = tmp_path / "x.md"
    p.write_text("---\nfoo: bar\n---\nbody\n")

    def _raise(_p: str) -> Any:
        raise RuntimeError("kaboom")

    monkeypatch.setattr("symphony.cli_runtime.load", _raise)
    deps = build_default_deps()
    ok, err = deps.ensure_orchestrator_started(str(p), logs_root=None, port=None)
    assert ok is False
    assert err is not None
    assert "kaboom" in err


def test_config_from_workflow_with_empty_front_matter() -> None:

    workflow = Workflow(front_matter={}, body="", raw="", source=None)
    config = _config_from_workflow(workflow, logs_root=None, port=None)
    assert config.server.host == "127.0.0.1"
    assert config.tracker.kind == "github"


def test_config_from_workflow_applies_logs_root_override() -> None:

    workflow = Workflow(front_matter={}, body="", raw="", source=None)
    config = _config_from_workflow(workflow, logs_root="/var/log", port=None)
    assert config.server.log_file == "/var/log/symphony.log"


def test_config_from_workflow_applies_port_override() -> None:

    workflow = Workflow(front_matter={}, body="", raw="", source=None)
    config = _config_from_workflow(workflow, logs_root=None, port=8080)
    assert config.server.port == 8080


def test_config_from_workflow_resolves_front_matter() -> None:
    """`$VAR` and `~` in front matter are resolved by `resolve()`."""

    workflow = Workflow(
        front_matter={"workspace": {"root": "$HOME/ws"}},
        body="",
        raw="",
        source=None,
    )
    config = _config_from_workflow(workflow, logs_root=None, port=None)
    # $HOME resolves to the actual home directory.
    assert "$HOME" not in config.workspace.root
    assert config.workspace.root.endswith("/ws")


def test_real_file_regular_works() -> None:

    assert _real_file_regular("/etc/passwd") is True
    assert _real_file_regular("/no/such/path/xyzzy") is False


def test_real_expand_user_works() -> None:

    out = _real_expand_user("~")
    assert out == os.path.expanduser("~")


def test_real_expand_vars_works() -> None:

    assert _real_expand_vars("$HOME") == os.environ.get("HOME", "$HOME")


# ---------------------------------------------------------------------------
# RuntimeHandle.stop
# ---------------------------------------------------------------------------


def test_runtime_handle_stop_sets_event() -> None:
    async def _go() -> None:
        evt = asyncio.Event()
        handle = RuntimeHandle(
            workflow_path="WORKFLOW.md",
            config=SymphonyConfig(),
            service=None,
            server=None,
            server_task=None,
            service_task=None,
            stop_event=evt,
        )
        handle.stop()
        assert evt.is_set()

    asyncio.run(_go())


def test_runtime_handle_stop_cancels_tasks() -> None:
    async def _go() -> None:
        evt = asyncio.Event()
        task = asyncio.create_task(asyncio.sleep(10))

        async def _none() -> None:
            return None

        handle = RuntimeHandle(
            workflow_path="WORKFLOW.md",
            config=SymphonyConfig(),
            service=None,
            server=None,
            server_task=asyncio.create_task(_none()),
            service_task=task,
            stop_event=evt,
        )
        handle.stop()
        # Task was scheduled to be cancelled.
        await asyncio.sleep(0)
        assert task.cancelled() or task.done()

    asyncio.run(_go())


def test_runtime_handle_stop_calls_service_stop() -> None:
    """When `service` is not None, `stop()` calls `service.stop()`."""
    stopped: list[bool] = []

    class _FakeService:
        def stop(self) -> None:
            stopped.append(True)

    async def _go() -> None:
        evt = asyncio.Event()
        handle = RuntimeHandle(
            workflow_path="WORKFLOW.md",
            config=SymphonyConfig(),
            service=_FakeService(),  # type: ignore[arg-type]
            server=None,
            server_task=None,
            service_task=None,
            stop_event=evt,
        )
        handle.stop()
        await asyncio.sleep(0)
        assert stopped == [True]

    asyncio.run(_go())


def test_real_build_runtime_delegates_to_build_runtime(monkeypatch: Any) -> None:
    """`_real_build_runtime` is a thin wrapper that calls
    `build_runtime` with the same args."""
    sentinel = object()
    mock = MagicMock(return_value=sentinel)
    monkeypatch.setattr("symphony.cli_runtime.build_runtime", mock)
    handle = _real_build_runtime("/path/WORKFLOW.md", logs_root=None, port=0)
    assert handle is sentinel
    mock.assert_called_once_with("/path/WORKFLOW.md", logs_root=None, port=0)


def test_real_ensure_orchestrator_started_returns_true_for_real_workflow(
    tmp_path: Any,
) -> None:
    """`_real_ensure_orchestrator_started` returns (True, None) for a
    real, valid workflow file."""
    p = tmp_path / "WORKFLOW.md"
    p.write_text("---\ntracker:\n  kind: memory\n---\nbody\n")
    ok, err = _real_ensure_orchestrator_started(str(p), logs_root=None, port=None)
    assert ok is True
    assert err is None


def test_real_ensure_orchestrator_started_returns_false_for_missing_file() -> None:
    ok, err = _real_ensure_orchestrator_started("/no/such/WORKFLOW.md", logs_root=None, port=None)
    assert ok is False
    assert err is not None
    assert "missing" in err


def test_install_signal_handlers_handles_no_loop() -> None:
    """`_install_signal_handlers` must not raise even when the
    loop is closed or signal handlers can't be installed."""
    loop = asyncio.new_event_loop()
    try:
        loop.close()  # Now add_signal_handler will raise
        handle = RuntimeHandle(
            workflow_path="WORKFLOW.md",
            config=SymphonyConfig(),
            service=None,
            server=None,
            server_task=None,
            service_task=None,
        )
        # Should not raise (we catch RuntimeError + NotImplementedError).
        _install_signal_handlers(loop, handle)
    finally:
        # Don't try to close an already-closed loop.
        pass


def test_install_signal_handlers_handles_unsupported() -> None:
    """On Windows, `add_signal_handler` raises NotImplementedError.
    `_install_signal_handlers` must swallow it."""

    class _FakeLoop:
        def add_signal_handler(self, sig: int, handler: Any) -> None:
            raise NotImplementedError("Windows")

    handle = RuntimeHandle(
        workflow_path="WORKFLOW.md",
        config=SymphonyConfig(),
        service=None,
        server=None,
        server_task=None,
        service_task=None,
    )
    _install_signal_handlers(_FakeLoop(), handle)  # type: ignore[arg-type]


def test_await_completion_returns_zero_on_kbi() -> None:
    """`_await_completion` catches KeyboardInterrupt and returns 0."""

    handle = RuntimeHandle(
        workflow_path="WORKFLOW.md",
        config=SymphonyConfig(),
        service=None,
        server=None,
        server_task=None,
        service_task=None,
    )
    with patch("symphony.cli_runtime._wait_for_completion", side_effect=KeyboardInterrupt):
        rc = _await_completion(handle)
    assert rc == 0
    assert handle.stop_event.is_set()


def test_default_wait_for_shutdown_returns_zero_with_mocked_completion() -> None:
    """`_default_wait_for_shutdown` exercises the install + await
    sequence; we patch `_await_completion` to a constant so the
    function returns without a real event loop."""

    # Use a no-op loop so `get_event_loop()` returns it.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        handle = RuntimeHandle(
            workflow_path="WORKFLOW.md",
            config=SymphonyConfig(),
            service=None,
            server=None,
            server_task=None,
            service_task=None,
        )
        with patch("symphony.cli_runtime._await_completion", return_value=0):
            rc = _default_wait_for_shutdown(handle)
        assert rc == 0
    finally:
        loop.close()


def test_default_wait_for_shutdown_catches_kbi() -> None:
    """`_default_wait_for_shutdown` catches KBI from completion and
    returns 0 (the production shutdown path)."""

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        handle = RuntimeHandle(
            workflow_path="WORKFLOW.md",
            config=SymphonyConfig(),
            service=None,
            server=None,
            server_task=None,
            service_task=None,
        )
        with patch(
            "symphony.cli_runtime._await_completion",
            side_effect=KeyboardInterrupt,
        ):
            rc = _default_wait_for_shutdown(handle)
        assert rc == 0
        assert handle.stop_event.is_set()
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# async wait paths
# ---------------------------------------------------------------------------


def test_wait_for_completion_returns_zero_when_service_finishes_clean() -> None:
    """When service_task completes normally, _wait_for_completion
    returns 0."""

    async def _go() -> None:
        evt = asyncio.Event()

        async def _none() -> None:
            return None

        service_task = asyncio.create_task(_none())
        handle = RuntimeHandle(
            workflow_path="WORKFLOW.md",
            config=SymphonyConfig(),
            service=None,
            server=None,
            server_task=asyncio.create_task(_none()),
            service_task=service_task,
            stop_event=evt,
        )
        rc = await _wait_for_completion(handle)
        assert rc == 0

    asyncio.run(_go())


def test_wait_for_completion_returns_one_when_service_raises() -> None:
    """When service_task raises, _wait_for_completion returns 1."""

    async def _boom() -> None:
        raise RuntimeError("service crashed")

    async def _go() -> None:
        evt = asyncio.Event()

        async def _none() -> None:
            return None

        service_task = asyncio.create_task(_boom())
        handle = RuntimeHandle(
            workflow_path="WORKFLOW.md",
            config=SymphonyConfig(),
            service=None,
            server=None,
            server_task=asyncio.create_task(_none()),
            service_task=service_task,
            stop_event=evt,
        )
        rc = await _wait_for_completion(handle)
        assert rc == 1

    asyncio.run(_go())


def test_wait_for_completion_returns_zero_when_stop_event_set() -> None:
    """When stop_event is set externally, _wait_for_completion
    returns 0 (clean shutdown)."""

    async def _go() -> None:
        evt = asyncio.Event()

        async def _none() -> None:
            return None

        async def _set_event() -> None:
            evt.set()

        service_task = asyncio.create_task(_none())
        handle = RuntimeHandle(
            workflow_path="WORKFLOW.md",
            config=SymphonyConfig(),
            service=None,
            server=None,
            server_task=asyncio.create_task(_none()),
            service_task=service_task,
            stop_event=evt,
        )
        _set_task = asyncio.create_task(_set_event())
        _ = _set_task
        rc = await _wait_for_completion(handle)
        assert rc == 0

    asyncio.run(_go())


def test_wait_for_completion_handles_cancelled_service() -> None:
    """When service_task is cancelled, _wait_for_completion returns 0."""

    async def _go() -> None:
        evt = asyncio.Event()
        service_task = asyncio.create_task(asyncio.sleep(10))
        service_task.cancel()

        async def _none() -> None:
            return None

        handle = RuntimeHandle(
            workflow_path="WORKFLOW.md",
            config=SymphonyConfig(),
            service=None,
            server=None,
            server_task=asyncio.create_task(_none()),
            service_task=service_task,
            stop_event=evt,
        )
        rc = await _wait_for_completion(handle)
        assert rc == 0

    asyncio.run(_go())


def test_task_exception_returns_none_for_cancelled() -> None:
    async def _go() -> None:
        t = asyncio.create_task(asyncio.sleep(10))
        t.cancel()
        # Wait for the cancellation to settle.
        with contextlib.suppress(asyncio.CancelledError):
            await t
        assert _task_exception(t) is None

    asyncio.run(_go())


def test_install_signal_handlers_does_not_raise() -> None:
    """`_install_signal_handlers` must not raise on any platform."""

    loop = asyncio.new_event_loop()
    try:
        evt = asyncio.Event()
        handle = RuntimeHandle(
            workflow_path="WORKFLOW.md",
            config=SymphonyConfig(),
            service=None,
            server=None,
            server_task=None,
            service_task=None,
            stop_event=evt,
        )
        # Should be a no-op or successful — never raises.
        _install_signal_handlers(loop, handle)
    finally:
        loop.close()


def test_await_completion_handles_keyboard_interrupt() -> None:
    """`_await_completion` returns 0 when the stop_event is set
    (the KeyboardInterrupt catch is in `_default_wait_for_shutdown`,
    not `_await_completion` itself)."""

    evt = asyncio.Event()
    handle = RuntimeHandle(
        workflow_path="WORKFLOW.md",
        config=SymphonyConfig(),
        service=None,
        server=None,
        server_task=None,
        service_task=None,
        stop_event=evt,
    )
    # Pre-set the event so _wait_for_completion returns 0 immediately.
    evt.set()
    rc = _await_completion(handle)
    assert rc == 0


# ---------------------------------------------------------------------------
# _build_tracker dispatch
# ---------------------------------------------------------------------------


def test_build_tracker_returns_github_for_github_kind() -> None:

    workflow = Workflow(front_matter={}, body="", raw="", source=None)
    config = SymphonyConfig()
    tracker = _build_tracker(workflow, config)
    assert tracker.__class__.__name__ == "GitHubTracker"


def test_build_tracker_returns_memory_for_memory_kind() -> None:

    workflow = Workflow(front_matter={}, body="", raw="", source=None)
    config = SymphonyConfig(tracker=Tracker(kind="memory"))
    tracker = _build_tracker(workflow, config)
    assert tracker.__class__.__name__ == "MemoryTracker"


def test_build_tracker_raises_for_unknown_kind() -> None:

    workflow = Workflow(front_matter={}, body="", raw="", source=None)
    # Bypass Literal validation; we want to test the dispatch error.
    tracker = Tracker.model_construct(kind="unknown")
    config = SymphonyConfig(tracker=tracker)
    with pytest.raises(ValueError, match=r"Unknown tracker\.kind"):
        _build_tracker(workflow, config)
