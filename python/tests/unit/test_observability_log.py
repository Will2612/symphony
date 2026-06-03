"""Unit tests for `symphony.observability.log` (kv logging)."""

from __future__ import annotations

import contextlib
import io
import logging
import os
import tempfile
from datetime import datetime
from typing import Any

import pytest

from symphony.config.schema import SymphonyConfig
from symphony.observability.log import (
    FORBIDDEN_LOG_FIELDS,
    KvFormatter,
    _build_console_handler,
    _build_file_handler,
    _SafeFileHandler,
    add_kv,
    configure,
    get_logger,
    is_configured,
    is_forbidden,
    reset_for_tests,
)


def _config(**overrides: Any) -> SymphonyConfig:
    base: dict[str, Any] = {
        "agent": {"max_concurrent_agents": 1, "max_retry_backoff_ms": 60_000},
        "tracker": {
            "kind": "memory",
            "active_states": ["open"],
            "terminal_states": ["closed"],
        },
        "codex": {
            "command": "opencode acp",
            "stall_timeout_ms": 60_000,
            "turn_timeout_ms": 60_000,
        },
        "server": {
            "host": "127.0.0.1",
            "port": 7842,
            "log_file": "",
        },
    }
    for k, v in overrides.items():
        if isinstance(v, dict) and k in base:
            base[k].update(v)
        else:
            base[k] = v
    return SymphonyConfig.model_validate(base)


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_for_tests()
    yield
    reset_for_tests()


# ---------------------------------------------------------------------------
# add_kv / forbidden
# ---------------------------------------------------------------------------


def test_add_kv_appends_to_record() -> None:
    record = logging.LogRecord(
        name="x", level=logging.INFO, pathname="", lineno=0, msg="m", args=(), exc_info=None
    )
    add_kv(record, "issue_id", "1")
    add_kv(record, "issue_identifier", "#1")
    assert record.kv == {"issue_id": "1", "issue_identifier": "#1"}  # type: ignore[attr-defined]


def test_add_kv_redacts_api_key() -> None:
    record = logging.LogRecord(
        name="x", level=logging.INFO, pathname="", lineno=0, msg="m", args=(), exc_info=None
    )
    add_kv(record, "api_key", "secret-value")
    add_kv(record, "API_KEY", "secret-value")  # case-insensitive
    add_kv(record, "password", "pw")
    add_kv(record, "token", "tok")
    assert record.kv == {}  # type: ignore[attr-defined]


def test_add_kv_renders_complex_values_as_repr() -> None:
    record = logging.LogRecord(
        name="x", level=logging.INFO, pathname="", lineno=0, msg="m", args=(), exc_info=None
    )
    add_kv(record, "obj", {"a": 1})
    assert record.kv == {"obj": "{'a': 1}"}  # type: ignore[attr-defined]


def test_add_kv_renders_none() -> None:
    record = logging.LogRecord(
        name="x", level=logging.INFO, pathname="", lineno=0, msg="m", args=(), exc_info=None
    )
    add_kv(record, "k", None)
    assert record.kv == {"k": "None"}  # type: ignore[attr-defined]


def test_is_forbidden_known_keys() -> None:
    for k in ("api_key", "API_KEY", "Api_Key", "password", "secret", "token"):
        assert is_forbidden(k)


def test_is_forbidden_safe_keys() -> None:
    for k in ("issue_id", "session_id", "event", "foo"):
        assert not is_forbidden(k)


def test_forbidden_log_fields_constant() -> None:
    assert frozenset({"api_key", "password", "secret", "token"}) == FORBIDDEN_LOG_FIELDS


# ---------------------------------------------------------------------------
# KvFormatter
# ---------------------------------------------------------------------------


def _make_record(msg: str, **kv: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="symphony.test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for k, v in kv.items():
        add_kv(record, k, v)
    return record


def test_kv_formatter_basic() -> None:
    record = _make_record("hello", issue_id="1", issue_identifier="#1")
    out = KvFormatter().format(record)
    assert "INFO" in out
    assert "symphony.test" in out
    assert "hello" in out
    assert "issue_id=1" in out
    assert "issue_identifier=#1" in out


def test_kv_formatter_no_kv() -> None:
    record = _make_record("hello")
    out = KvFormatter().format(record)
    assert out.endswith("hello")


def test_kv_formatter_timestamp_is_iso8601_utc() -> None:
    record = _make_record("hi")
    out = KvFormatter().format(record)
    prefix = out.split(" ")[0]
    # Parse to confirm ISO 8601 with timezone offset.
    parsed = datetime.fromisoformat(prefix)
    assert parsed.tzinfo is not None


# ---------------------------------------------------------------------------
# configure / get_logger
# ---------------------------------------------------------------------------


def test_configure_attaches_stderr_handler() -> None:
    cfg = _config()
    configure(cfg)
    assert is_configured()
    logger = get_logger("test")
    assert logger.name == "symphony.test"


def test_configure_attaches_file_handler() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        log_path = os.path.join(tmp, "symphony.log")
        cfg = _config(server={"log_file": log_path})
        configure(cfg)
        logger = get_logger("test")
        logger.info("disk-line", extra={})
        # Force flush on all attached handlers.
        handlers = list(logger.handlers)
        parent = logger.parent
        if parent is not None:
            handlers.extend(parent.handlers)
        for h in handlers:
            with contextlib.suppress(Exception):
                h.flush()
        with open(log_path) as f:
            content = f.read()
        assert "disk-line" in content
        # Tear down handlers to release file descriptors.
        reset_for_tests()


def test_configure_is_idempotent() -> None:
    cfg = _config()
    configure(cfg)
    handlers_first = list(_get_root_handlers())
    configure(cfg)
    handlers_second = list(_get_root_handlers())
    assert len(handlers_first) == len(handlers_second)


def _get_root_handlers() -> list[logging.Handler]:
    root = logging.getLogger("symphony")
    return list(getattr(root, "_symphony_configured_handlers", []))


def test_configure_bad_log_file_keeps_console() -> None:
    cfg = _config(server={"log_file": "/nonexistent/dir/log.txt"})
    # Should not raise; console handler remains.
    configure(cfg)
    assert any(isinstance(h, logging.StreamHandler) for h in _get_root_handlers())


def test_get_logger_normalizes_name() -> None:
    name = get_logger("foo.bar").name
    assert name == "symphony.foo.bar"


def test_get_logger_preserves_full_name() -> None:
    assert get_logger("symphony.x.y").name == "symphony.x.y"


# ---------------------------------------------------------------------------
# Sink-failure handling
# ---------------------------------------------------------------------------


def test_safe_file_handler_swallows_emit_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the underlying file write fails, the handler writes
    a warning to stderr instead of raising."""
    with tempfile.TemporaryDirectory() as tmp:
        log_path = os.path.join(tmp, "symphony.log")
        h = _build_file_handler(log_path)
        assert isinstance(h, _SafeFileHandler)
        # Close the existing stream so we can replace it without a
        # ResourceWarning, and so the handler has a fresh state.
        h.close()

        # Replace the stream with one that always raises on write.
        class _BadStream:
            def write(self, data: str) -> int:
                raise OSError("disk full")

            def flush(self) -> None:
                pass

        h.stream = _BadStream()  # type: ignore[assignment]
        # Replace stderr to capture the warning.
        captured = io.StringIO()
        monkeypatch.setattr("sys.stderr", captured)
        record = _make_record("boom")
        h.emit(record)  # must not raise
        assert "log sink" in captured.getvalue()
        assert "boom" in captured.getvalue()


def test_build_console_handler_attaches_formatter() -> None:
    h = _build_console_handler()
    try:
        assert h.formatter is not None
    finally:
        h.close()


def test_configure_resets_handlers() -> None:
    cfg = _config()
    configure(cfg)
    n1 = len(_get_root_handlers())
    configure(cfg)
    n2 = len(_get_root_handlers())
    assert n1 == n2
