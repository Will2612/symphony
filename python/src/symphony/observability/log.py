"""Structured kv logging for symphony (SPEC §13.1).

Public surface:

- `get_logger(name)` — return a configured `logging.Logger` with
  the kv formatter and the configured sinks attached.
- `configure(config)` — (re)configure the root "symphony" logger with
  sinks for stderr + `<logs_root>/symphony.log`. Idempotent: a second
  call replaces the handlers but does not duplicate.
- `KvFormatter` — formats `LogRecord`s as
  `timestamp level logger message key=value key=value ...`.
- `add_kv(record, key, value)` — extend `record.__dict__["kv"]` with
  a key/value pair; values that are not str/int/float/bool/None are
  rendered as their `repr`.

`api_key` is in the forbidden list and is NEVER logged (SPEC §13.1
"never log api_key" + AGENTS.md).
"""

from __future__ import annotations

import contextlib
import logging
import os
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from symphony.config.schema import SymphonyConfig

FORBIDDEN_LOG_FIELDS = frozenset({"api_key", "password", "secret", "token"})

_SIMPLE_TYPES = (str, int, float, bool, type(None))


def is_forbidden(key: str) -> bool:
    """True if `key` must NEVER be logged (case-insensitive)."""
    return key.lower() in FORBIDDEN_LOG_FIELDS


def add_kv(record: logging.LogRecord, key: str, value: Any) -> None:  # noqa: ANN401
    """Add a key/value pair to `record.kv`, redacting forbidden keys.

    Forbidden keys are silently dropped (SPEC §13.1 + AGENTS.md).
    Non-simple values are rendered as `repr(value)`.
    """
    if not hasattr(record, "kv"):
        record.kv = {}
    if is_forbidden(key):
        return
    record.kv[key] = _render_value(value)  # type: ignore[attr-defined]


def _render_value(value: Any) -> str:  # noqa: ANN401
    if isinstance(value, _SIMPLE_TYPES):
        return str(value)
    return repr(value)


class KvFormatter(logging.Formatter):
    """Format log records as `ts level logger msg k=v k=v ...`.

    Output is one line per record. Whitespace inside the message is
    preserved (no quoting). Keys and values are joined with `=` and
    no escaping — callers MUST NOT include spaces in keys.
    """

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds")
        level = record.levelname
        name = record.name
        message = record.getMessage()
        parts = [ts, level, name, message]
        kv = getattr(record, "kv", None)
        if isinstance(kv, Mapping):
            for k, v in kv.items():
                parts.append(f"{k}={v}")
        return " ".join(parts)


class _SafeFileHandler(logging.FileHandler):
    """A FileHandler that swallows emit errors.

    Per SPEC §13.2, a sink failure SHOULD continue running when
    possible and emit a warning to any remaining sink. We override
    `handleError` (called by `StreamHandler.emit` on exception) so
    the default traceback-on-stderr behavior is replaced with a
    short WARNING line.
    """

    def handleError(self, record: logging.LogRecord) -> None:
        # The default behaviour writes a traceback to `sys.stderr`
        # which is noisy and indistinguishable from real stderr
        # output. We replace it with a single WARNING line that
        # names the failing sink.
        sys.stderr.write(
            f"WARNING: log sink {self.baseFilename} failed for {record.getMessage()!r}\n"
        )
        sys.stderr.flush()


_CONFIGURED = False


def _set_configured(value: bool) -> None:
    global _CONFIGURED  # noqa: PLW0603
    _CONFIGURED = value


_ROOT_HANDLER_ATTR = "_symphony_configured_handlers"


def _build_formatter() -> KvFormatter:
    return KvFormatter()


def _build_console_handler() -> logging.Handler:
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(_build_formatter())
    return h


def _build_file_handler(log_file: str) -> logging.Handler:
    directory = os.path.dirname(log_file)
    if directory:
        os.makedirs(directory, exist_ok=True)
    h = _SafeFileHandler(log_file, encoding="utf-8")
    h.setFormatter(_build_formatter())
    return h


def _root_logger() -> logging.Logger:
    return logging.getLogger("symphony")


def configure(config: SymphonyConfig) -> None:
    """Configure the `symphony` logger with stderr + file sinks.

    Idempotent: subsequent calls replace the handlers but do not
    stack them.
    """
    root = _root_logger()
    # Idempotency: clear prior handlers we set.
    prior: list[logging.Handler] = getattr(root, _ROOT_HANDLER_ATTR, [])
    for h in prior:
        root.removeHandler(h)
    handlers: list[logging.Handler] = [_build_console_handler()]
    if config.server.log_file:
        try:
            handlers.append(_build_file_handler(config.server.log_file))
        except Exception as e:
            sys.stderr.write(f"WARNING: could not open log file {config.server.log_file}: {e}\n")
            sys.stderr.flush()
    for h in handlers:
        root.addHandler(h)
    setattr(root, _ROOT_HANDLER_ATTR, handlers)
    root.setLevel(logging.INFO)
    root.propagate = False
    _set_configured(True)


def get_logger(name: str) -> logging.Logger:
    """Return a child of the `symphony` logger. Always safe to call.

    If `configure()` has not been called, the logger still inherits
    the root logger's stderr handler (so logs are never silently
    lost)."""
    if not name.startswith("symphony"):
        name = f"symphony.{name}"
    return logging.getLogger(name)


def is_configured() -> bool:
    return _CONFIGURED


__all__ = [
    "FORBIDDEN_LOG_FIELDS",
    "KvFormatter",
    "add_kv",
    "configure",
    "get_logger",
    "is_configured",
    "is_forbidden",
]


def reset_for_tests() -> None:
    """Test helper: remove AND close all handlers we attached to
    the root logger, so file descriptors are released cleanly."""
    root = _root_logger()
    prior: list[logging.Handler] = getattr(root, _ROOT_HANDLER_ATTR, [])
    for h in prior:
        with contextlib.suppress(Exception):
            h.close()
        root.removeHandler(h)
    setattr(root, _ROOT_HANDLER_ATTR, [])
    _set_configured(False)
