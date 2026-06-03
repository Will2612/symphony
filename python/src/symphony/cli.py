"""Symphony CLI (SPEC §17.7).

Public surface:

- `main(argv, runtime_overrides=...)` — entrypoint used by
  `__main__.py`. Returns the process exit code.
- `parse_args(argv)` — pure: returns a `CliArgs` dataclass. Raises
  `SystemExit` on bad input.
- `evaluate(argv, *, deps)` — pure-ish: validates argv, performs
  side-effect-free setup (file existence check, log/port config),
  and returns a `CliResult`. The orchestrator is **not** started
  here.
- `run(workflow_path, *, deps)` — performs I/O (creates the real
  orchestrator + observability server). Returns a
  `RuntimeHandle`. Raises on startup failure.
- `wait_for_shutdown(handle, *, deps)` — blocks until the
  orchestrator stops. Returns the process exit code (0 = clean
  shutdown, 1 = abnormal).

The flow:

1. `parse_args` → `CliArgs`
2. `evaluate` → `CliResult`. On success, the result carries the
   expanded paths/port; the runtime is **not** started.
3. `run` → `RuntimeHandle` (config + service + server).
4. `wait_for_shutdown` → exit code.
5. `main` glues them together, prints messages, returns the code.

`run` is dependency-injectable via `CliDeps` so tests can stub
the file system, the orchestrator factory, and the shutdown waiter
without touching the real runtime.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass

from symphony.cli_runtime import (
    CliDeps,
    RuntimeHandle,
    build_default_deps,
)

__all__ = [
    "ACK_FLAG",
    "DEFAULT_WORKFLOW",
    "CliArgs",
    "CliDeps",
    "CliResult",
    "RuntimeHandle",
    "acknowledgement_banner",
    "build_default_deps",
    "evaluate",
    "main",
    "parse_args",
    "run",
    "usage",
    "wait_for_shutdown",
]


DEFAULT_WORKFLOW = "WORKFLOW.md"
ACK_FLAG = "--i-understand-that-this-will-be-running-without-the-usual-guardrails"


# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CliArgs:
    """Parsed CLI args. All values are validated and pre-resolved."""

    workflow_path: str
    i_understand: bool
    logs_root: str | None
    port: int | None


def parse_args(argv: list[str]) -> CliArgs:
    """Parse argv into a `CliArgs`. Raises `SystemExit` on bad input."""
    parser = _build_parser()
    ns = parser.parse_args(argv)
    return CliArgs(
        workflow_path=ns.workflow_path,
        i_understand=bool(ns.i_understand),
        logs_root=ns.logs_root,
        port=ns.port,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="symphony",
        description="Symphony orchestrator (SPEC §17.7).",
        add_help=True,
    )
    parser.add_argument(
        ACK_FLAG,
        dest="i_understand",
        action="store_true",
        help="Acknowledge the reduced-guardrails preview banner.",
    )
    parser.add_argument(
        "--logs-root",
        dest="logs_root",
        default=None,
        help="Directory for the structured log file (default: <cwd>/logs).",
    )
    parser.add_argument(
        "--port",
        dest="port",
        type=int,
        default=None,
        help="Bind port for the observability HTTP server (0 = ephemeral).",
    )
    parser.add_argument(
        "workflow_path",
        nargs="?",
        default=DEFAULT_WORKFLOW,
        help="Path to the WORKFLOW.md file (default: ./WORKFLOW.md).",
    )
    return parser


# ---------------------------------------------------------------------------
# Usage / banner
# ---------------------------------------------------------------------------


def usage() -> str:
    return (
        f"Usage: symphony [{ACK_FLAG}] [--logs-root <path>] [--port <port>] [path-to-WORKFLOW.md]"
    )


def acknowledgement_banner() -> str:
    """The banner shown when the user is missing the ack flag."""
    lines = [
        "This Symphony implementation is a low key engineering preview.",
        "Coding agents will run without any guardrails.",
        "Symphony is not a supported product and is presented as-is.",
        f"To proceed, start with `{ACK_FLAG}` CLI argument.",
    ]
    width = max(len(s) for s in lines)
    border = "─" * (width + 2)
    top = "╭" + border + "╮"
    bottom = "╰" + border + "╯"
    spacer = "│ " + " " * width + " │"
    body = [top, spacer]
    body.extend("│ " + line.ljust(width) + " │" for line in lines)
    body.append(spacer)
    body.append(bottom)
    return "\n".join(body)


# ---------------------------------------------------------------------------
# evaluate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CliResult:
    """Outcome of `evaluate`. Either a success carrying the resolved
    parameters, or a tagged error."""

    kind: str  # "ok" | "ack_required" | "usage_error" | "workflow_not_found" | "startup_error"
    message: str = ""
    workflow_path: str = ""
    logs_root: str | None = None
    port: int | None = None


def evaluate(argv: list[str], *, deps: CliDeps) -> CliResult:  # noqa: PLR0911
    """Parse argv, validate, and prepare runtime parameters. Does NOT
    start the orchestrator.

    The result is either `"ok"` (with the expanded workflow path and
    log/port settings) or one of the error kinds. Errors are
    rendered as a `message` string suitable for stderr.
    """
    try:
        args = parse_args(argv)
    except SystemExit:
        return CliResult(kind="usage_error", message=usage())

    if not args.i_understand:
        return CliResult(kind="ack_required", message=acknowledgement_banner())

    expanded_logs_root: str | None = None
    if args.logs_root is not None:
        stripped = args.logs_root.strip()
        if stripped == "":
            return CliResult(kind="usage_error", message=usage())
        expanded_logs_root = _expand(stripped, deps=deps)
    port = args.port
    if port is not None and port < 0:
        return CliResult(kind="usage_error", message=usage())

    expanded_path = _expand(args.workflow_path, deps=deps)
    if not deps.file_regular(expanded_path):
        return CliResult(
            kind="workflow_not_found",
            message=f"Workflow file not found: {expanded_path}",
        )

    ok, err = deps.ensure_orchestrator_started(
        expanded_path, logs_root=expanded_logs_root, port=port
    )
    if not ok:
        return CliResult(
            kind="startup_error",
            message=f"Failed to start Symphony with workflow {expanded_path}: {err or 'unknown'}",
        )

    return CliResult(
        kind="ok",
        workflow_path=expanded_path,
        logs_root=expanded_logs_root,
        port=port,
    )


def _expand(path: str, *, deps: CliDeps) -> str:
    """`~` + `$VAR` expansion with the standard semantics."""
    return deps.expand_vars(deps.expand_user(path))


# ---------------------------------------------------------------------------
# run / wait_for_shutdown
# ---------------------------------------------------------------------------


def run(workflow_path: str, *, deps: CliDeps) -> RuntimeHandle:
    """Build the runtime. Raises on failure.

    The runtime is fully constructed and running; the orchestrator
    has been started as a background task. The caller must invoke
    `wait_for_shutdown(handle)` to block until it stops.
    """
    return deps.build_runtime(workflow_path, logs_root=None, port=None)


def wait_for_shutdown(handle: RuntimeHandle, *, deps: CliDeps) -> int:
    """Block until the orchestrator stops. Returns the exit code.

    0 = clean shutdown (orchestrator stopped normally).
    1 = abnormal (startup error, crashed, or shutdown hook raised).
    """
    return deps.wait_for_shutdown(handle)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


_ERROR_KINDS = frozenset({"ack_required", "usage_error", "workflow_not_found", "startup_error"})


def main(
    argv: list[str] | None = None,
    *,
    runtime_overrides: Callable[[CliDeps], CliDeps] | None = None,
) -> int:
    """Top-level entrypoint. Returns the process exit code.

    `argv` defaults to `sys.argv[1:]`. `runtime_overrides` lets a
    test install a fake `CliDeps` (and/or a fake shutdown waiter)
    without spawning a real orchestrator.
    """
    if argv is None:
        argv = sys.argv[1:]

    deps = (
        build_default_deps()
        if runtime_overrides is None
        else runtime_overrides(build_default_deps())
    )

    result = evaluate(argv, deps=deps)
    if result.kind in _ERROR_KINDS:
        sys.stderr.write(result.message + "\n")
        sys.stderr.flush()
        return 1

    try:
        handle = deps.build_runtime(
            result.workflow_path,
            logs_root=result.logs_root,
            port=result.port,
        )
    except FileNotFoundError as e:
        sys.stderr.write(f"{e}\n")
        sys.stderr.flush()
        return 1
    except Exception as e:
        sys.stderr.write(f"Failed to start Symphony: {e}\n")
        sys.stderr.flush()
        return 1

    try:
        return wait_for_shutdown(handle, deps=deps)
    except KeyboardInterrupt:
        handle.stop()
        return 0
    except Exception:
        return 1
