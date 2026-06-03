"""Unit tests for `symphony.observability.server` (FastAPI HTTP API).

Per SPEC §13.3 the orchestrator MAY expose a JSON HTTP surface
for dashboards. The Elixir reference implements:

- `GET  /api/state` — full snapshot.
- `GET  /api/issues/{identifier}` — one-issue view; 404 if not found.
- `POST /api/refresh` — force a reconcile tick; 202 on success, 503 unavailable.
- `GET  /api/health` — liveness probe.
- `* /<unknown>` — 404 with `{"error": {"code": "not_found", ...}}`.

The HTTP server MUST be bound to `127.0.0.1` by default
(`server.host` is configurable). `server.port = 0` selects an
ephemeral port (so tests can pick it up via the actual bound
socket).
"""

from __future__ import annotations

import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from uvicorn import Server

from symphony.config.schema import SymphonyConfig
from symphony.observability.server import (
    ObservabilityServer,
    _discover_bound_port,
    build_app,
    find_ephemeral_port,
    shutdown,
    start,
)
from symphony.orchestrator.service import OrchestratorService
from symphony.orchestrator.state import LiveSession, OrchestratorState, RetryEntry
from symphony.tracker.normalize import Issue


def _config(**overrides: Any) -> SymphonyConfig:
    base: dict[str, Any] = {
        "agent": {"max_concurrent_agents": 5, "max_retry_backoff_ms": 60_000},
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
        "server": {"host": "127.0.0.1", "port": 0, "log_file": ""},
    }
    for k, v in overrides.items():
        if isinstance(v, dict) and k in base:
            base[k].update(v)
        else:
            base[k] = v
    return SymphonyConfig.model_validate(base)


@dataclass
class _StubTracker:
    """A stub Tracker Protocol for the server (no methods called
    by the HTTP layer in these tests)."""

    async def fetch_candidate_issues(self) -> list[Issue]:
        return []

    async def fetch_issues_by_states(self, state_names: list[str]) -> list[Issue]:
        return []

    async def fetch_issue_states_by_ids(self, issue_ids: list[str]) -> list[Issue]:
        return []

    async def create_comment(self, issue_id: str, body: str) -> None:
        pass

    async def update_issue_state(self, issue_id: str, state_name: str) -> None:
        pass


def _tracker() -> _StubTracker:
    return _StubTracker()


def _service(*, state: OrchestratorState | None = None) -> OrchestratorService:
    cfg = _config()
    return OrchestratorService(
        config=cfg,
        tracker=_tracker(),  # type: ignore[arg-type]
        runner=object(),  # type: ignore[arg-type]
        workspace_manager=object(),  # type: ignore[arg-type]
        state=state or OrchestratorState(),
    )


# ---------------------------------------------------------------------------
# build_app — in-process via httpx.AsyncClient(app=app)
# ---------------------------------------------------------------------------


def test_build_app_returns_fastapi_app() -> None:
    app = build_app(_service())
    assert isinstance(app, FastAPI)


async def test_health_returns_ok() -> None:
    app = build_app(_service())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        r = await c.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_state_returns_full_snapshot() -> None:
    state = OrchestratorState()
    state.running["1"] = LiveSession(
        issue_id="1",
        identifier="#1",
        session_id="s-1",
        started_at=datetime(2024, 1, 1, tzinfo=UTC),
        attempt=1,
        usage={"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
    )
    svc = _service(state=state)
    app = build_app(svc)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        r = await c.get("/api/state")
    assert r.status_code == 200
    body = r.json()
    assert "running" in body
    assert "retrying" in body
    assert "codex_totals" in body
    assert "rate_limits" in body
    assert body["running"][0]["issue_id"] == "1"
    assert body["codex_totals"]["input_tokens"] == 5


async def test_state_returns_empty_when_no_sessions() -> None:
    svc = _service()
    app = build_app(svc)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        r = await c.get("/api/state")
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "running": [],
        "retrying": [],
        "codex_totals": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "seconds_running": 0,
        },
        "rate_limits": None,
    }


async def test_issue_lookup_found() -> None:
    state = OrchestratorState()
    state.running["1"] = LiveSession(
        issue_id="1",
        identifier="#1",
        session_id="s-1",
        started_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    svc = _service(state=state)
    app = build_app(svc)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        r = await c.get("/api/issues/1")
    assert r.status_code == 200
    body = r.json()
    assert body["issue_id"] == "1"
    assert body["identifier"] == "#1"
    assert body["state"] == "running"


async def test_issue_lookup_retry_queue() -> None:
    state = OrchestratorState()
    state.retry_attempts["1"] = RetryEntry(
        issue_id="1",
        identifier="#1",
        attempt=2,
        error="boom",
        due_at_ms=12345,
    )
    svc = _service(state=state)
    app = build_app(svc)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        r = await c.get("/api/issues/1")
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "retrying"
    assert body["attempt"] == 2
    assert body["error"] == "boom"


async def test_issue_lookup_claimed() -> None:
    state = OrchestratorState()
    state.claimed.add("1")
    svc = _service(state=state)
    app = build_app(svc)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        r = await c.get("/api/issues/1")
    assert r.status_code == 200
    assert r.json()["state"] == "claimed"


async def test_issue_lookup_idle() -> None:
    svc = _service()
    app = build_app(svc)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        r = await c.get("/api/issues/99")
    assert r.status_code == 200
    assert r.json() == {"issue_id": "99", "state": "idle"}


async def test_issue_lookup_404_when_missing_and_strict() -> None:
    """Default behavior: unknown issues return 200 with state='idle'.
    With strict=True, return 404."""
    svc = _service()
    app = build_app(svc, strict_issue_lookup=True)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        r = await c.get("/api/issues/99")
    assert r.status_code == 404
    body = r.json()
    assert body == {"error": {"code": "issue_not_found", "message": "Issue not found"}}


async def test_refresh_returns_202() -> None:
    svc = _service()
    app = build_app(svc)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        r = await c.post("/api/refresh")
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "refresh_requested"


async def test_refresh_503_when_lock_contended() -> None:
    """If the state lock is held, /api/refresh returns 503."""
    svc = _service()
    # Acquire the lock; the refresh endpoint tries to acquire it
    # with a 1ms timeout and gives up.
    await svc.state.lock.acquire()
    try:
        app = build_app(svc)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as c:
            r = await c.post("/api/refresh")
        assert r.status_code == 503
        body = r.json()
        assert body["error"]["code"] == "orchestrator_unavailable"
    finally:
        svc.state.lock.release()


async def test_unknown_route_404() -> None:
    svc = _service()
    app = build_app(svc)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        r = await c.get("/api/nonexistent")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "not_found"


async def test_method_not_allowed_405() -> None:
    svc = _service()
    app = build_app(svc)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        r = await c.delete("/api/state")
    assert r.status_code == 405
    body = r.json()
    assert body["error"]["code"] == "method_not_allowed"


# ---------------------------------------------------------------------------
# find_ephemeral_port
# ---------------------------------------------------------------------------


def test_find_ephemeral_port_returns_open_port() -> None:
    """Returns a port that is currently free on 127.0.0.1, then
    closes the listener."""
    port = find_ephemeral_port(host="127.0.0.1")
    # Re-open on the same port: should succeed (TOCTOU is fine
    # for this test).
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", port))
    assert 1024 <= port <= 65_535


# ---------------------------------------------------------------------------
# start / shutdown — real uvicorn on a free port
# ---------------------------------------------------------------------------


async def test_start_uses_configured_port() -> None:
    """start() binds to `config.server.host:port`; shutdown() stops it."""
    cfg = _config(server={"port": 0})
    svc = _service()
    server = await start(cfg, svc)
    try:
        assert server.bound_port > 0
        transport = httpx.AsyncHTTPTransport()
        async with httpx.AsyncClient(transport=transport) as c:
            r = await c.get(f"http://127.0.0.1:{server.bound_port}/api/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}
    finally:
        await shutdown(server)


async def test_start_with_port_zero_picks_ephemeral() -> None:
    """`server.port = 0` triggers the ephemeral-port path; the
    actual bound port is written back to `server.bound_port`."""
    cfg = _config(server={"port": 0})
    svc = _service()
    server = await start(cfg, svc)
    try:
        assert server.bound_port > 0
        transport = httpx.AsyncHTTPTransport()
        async with httpx.AsyncClient(transport=transport) as c:
            r = await c.get(f"http://127.0.0.1:{server.bound_port}/api/state")
        assert r.status_code == 200
    finally:
        await shutdown(server)


async def test_observability_server_dataclass_holds_state() -> None:
    """`ObservabilityServer` is a frozen dataclass that bundles
    the uvicorn Server, the bound host, and the bound port."""
    server = ObservabilityServer(
        server=Server(config=None),  # type: ignore[arg-type]
        host="127.0.0.1",
        bound_port=0,
    )
    assert server.host == "127.0.0.1"
    assert server.bound_port == 0


async def test_http_exception_handler_returns_error_envelope() -> None:
    """Unhandled HTTPException (e.g. 500) returns the
    `{"error": {"code": "http_error", ...}}` envelope."""
    app = build_app(_service())

    @app.get("/boom")
    async def boom() -> None:
        raise HTTPException(status_code=500, detail="kaboom")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        r = await c.get("/boom")
    assert r.status_code == 500
    body = r.json()
    assert body["error"]["code"] == "http_error"
    assert body["error"]["message"] == "kaboom"


# ---------------------------------------------------------------------------
# _discover_bound_port
# ---------------------------------------------------------------------------


def test_discover_bound_port_returns_requested_when_nonzero() -> None:
    """When the requested port is non-zero, _discover_bound_port
    returns it without inspecting the server's sockets."""
    assert _discover_bound_port(server=None, host="127.0.0.1", requested=9999) == 9999


def test_discover_bound_port_returns_zero_when_no_servers() -> None:
    """When port=0 and uvicorn has not yet exposed any server
    objects, we return 0 (best-effort; the caller logs)."""
    server = MagicMock(spec=["servers"])
    server.servers = None
    assert _discover_bound_port(server=server, host="127.0.0.1", requested=0) == 0


def test_discover_bound_port_returns_zero_when_no_sockets() -> None:
    """When uvicorn exposes a server but no listening sockets yet."""
    inner = MagicMock(spec=["sockets"])
    inner.sockets = None
    server = MagicMock(spec=["servers"])
    server.servers = [inner]
    assert _discover_bound_port(server=server, host="127.0.0.1", requested=0) == 0


# ---------------------------------------------------------------------------
# shutdown
# ---------------------------------------------------------------------------
# shutdown
# ---------------------------------------------------------------------------


async def test_shutdown_closes_listening_sockets() -> None:
    """shutdown() closes the underlying listening socket so the
    OS releases the port immediately (no waiting for GC)."""
    cfg = _config(server={"port": 0})
    svc = _service()
    server = await start(cfg, svc)
    inner = server.server.servers[0].sockets[0]._sock
    assert not _is_closed(inner)
    await shutdown(server)
    assert _is_closed(inner)


def _is_closed(sock: object) -> bool:
    """True if `sock` has been closed (works for stdlib `socket.socket`)."""
    fileno = getattr(sock, "fileno", None)
    if fileno is None:
        return True
    try:
        fd = fileno()
    except OSError:
        return True
    return fd < 0


# ---------------------------------------------------------------------------
# start — failure modes
# ---------------------------------------------------------------------------


async def test_start_raises_if_uvicorn_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """If uvicorn's serve() raises during startup, start() re-raises."""
    from symphony.observability import server as srv  # noqa: PLC0415

    class _BrokenServer:
        started = False

        def __init__(self, config: object = None) -> None:
            self.servers: list[object] = []
            self.should_exit = False

        async def serve(self) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr(srv, "Server", _BrokenServer)
    cfg = _config(server={"port": 0})
    svc = _service()
    with pytest.raises(RuntimeError, match="boom"):
        await start(cfg, svc)
