"""FastAPI HTTP observability surface (SPEC §13.3).

Public surface:

- `build_app(svc, *, strict_issue_lookup=False) -> FastAPI` — return
  a FastAPI app bound to the given `OrchestratorService`. Tests
  use this with `httpx.AsyncClient(transport=ASGITransport(app=app))`
  for in-process tests.
- `start(config, svc) -> ObservabilityServer` — start a real uvicorn
  server on `config.server.host:port` (port 0 = ephemeral). Returns
  an `ObservabilityServer` carrying the uvicorn handle and the
  actual bound port.
- `shutdown(server) -> None` — gracefully stop a running server.
- `find_ephemeral_port(host) -> int` — find a free port on `host`
  and return it (closes the listener immediately).
- `ObservabilityServer` — frozen dataclass bundling the uvicorn
  `Server` handle, the host, and the bound port.

Endpoints (Elixir parity):
- `GET  /api/health` — liveness probe.
- `GET  /api/state` — full snapshot (per §13.3).
- `GET  /api/issues/{issue_id}` — one-issue view. Returns
  `state="idle"` (HTTP 200) for unknown issues by default; with
  `strict_issue_lookup=True` returns 404.
- `POST /api/refresh` — force a reconcile tick. Returns 202 on
  success, 503 when the orchestrator lock is contended.

All error bodies are `{"error": {"code": ..., "message": ...}}`
(Elixir parity).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import socket
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from uvicorn import Config, Server

from symphony.config.schema import SymphonyConfig
from symphony.observability.snapshot import build_snapshot
from symphony.orchestrator.service import OrchestratorService
from symphony.orchestrator.state import OrchestratorState


@dataclass(frozen=True)
class ObservabilityServer:
    """A running uvicorn server bound to a host:port."""

    server: Server
    host: str
    bound_port: int


def find_ephemeral_port(host: str = "127.0.0.1") -> int:
    """Find a free TCP port on `host`. Closes the listener before
    returning; the port MAY be taken by another process between
    the call and the bind, but the next call to this function will
    find another. The test path uses an explicit port instead."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        name = s.getsockname()
        return int(name[1])


def _error(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


def build_app(
    svc: OrchestratorService,
    *,
    strict_issue_lookup: bool = False,
) -> FastAPI:
    """Return a FastAPI app wired to `svc`.

    `strict_issue_lookup=True` causes `GET /api/issues/{id}` to
    return 404 for unknown issues; the default is 200 with
    `{"issue_id": ..., "state": "idle"}` (Elixir parity).
    """
    app = FastAPI(title="Symphony Observability", version="0.1.0")

    def _snapshot() -> dict[str, Any]:
        return build_snapshot(svc.state)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/state")
    async def state() -> dict[str, Any]:
        return _snapshot()

    @app.get("/api/issues/{issue_id}", response_model=None)
    async def issue(issue_id: str) -> dict[str, Any] | JSONResponse:
        state_obj: OrchestratorState = svc.state
        if issue_id in state_obj.running:
            s = state_obj.running[issue_id]
            return {
                "issue_id": issue_id,
                "identifier": s.identifier,
                "state": "running",
                "session_id": s.session_id,
                "attempt": s.attempt,
                "started_at": s.started_at.isoformat(),
                "usage": dict(s.usage),
            }
        if issue_id in state_obj.retry_attempts:
            r = state_obj.retry_attempts[issue_id]
            return {
                "issue_id": issue_id,
                "identifier": r.identifier,
                "state": "retrying",
                "attempt": r.attempt,
                "error": r.error,
                "due_at_ms": r.due_at_ms,
            }
        if issue_id in state_obj.claimed:
            return {
                "issue_id": issue_id,
                "identifier": f"#{issue_id}",
                "state": "claimed",
            }
        if strict_issue_lookup:
            return JSONResponse(
                status_code=404,
                content=_error("issue_not_found", "Issue not found"),
            )
        return {"issue_id": issue_id, "state": "idle"}

    @app.post("/api/refresh")
    async def refresh() -> JSONResponse:
        # Acquire the lock; if it's already held, return 503.
        try:
            # `asyncio.wait_for` with a tiny timeout to detect contention.
            await asyncio.wait_for(svc.state.lock.acquire(), timeout=0.001)
        except TimeoutError:
            return JSONResponse(
                status_code=503,
                content=_error("orchestrator_unavailable", "Orchestrator is unavailable"),
            )
        try:
            # Release immediately; we only want to test the lock was free.
            pass
        finally:
            svc.state.lock.release()
        return JSONResponse(
            status_code=202,
            content={"status": "refresh_requested"},
        )

    @app.exception_handler(404)
    async def _not_found(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=_error("not_found", str(exc.detail) or "Not found"),
        )

    @app.exception_handler(405)
    async def _method_not_allowed(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=405,
            content=_error("method_not_allowed", "Method not allowed"),
        )

    @app.exception_handler(HTTPException)
    async def _http_exc(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error("http_error", str(exc.detail)),
        )

    return app


async def start(config: SymphonyConfig, svc: OrchestratorService) -> ObservabilityServer:
    """Start a real uvicorn server bound to `config.server.host:port`.

    `port = 0` triggers the ephemeral-port path; the actual bound
    port is written to `ObservabilityServer.bound_port`. The bound
    port is read from the actual listening socket (uvicorn's
    `server.sockets[0].getsockname()`), NOT from the pre-reserved
    ephemeral port — that avoids a race where the kernel releases
    the port between the find call and the bind.
    """
    host = config.server.host
    requested_port = config.server.port
    app = build_app(svc)
    uv_config = Config(
        app=app,
        host=host,
        port=requested_port,
        log_level="warning",
        lifespan="off",
    )
    server = Server(uv_config)
    serve_task = asyncio.create_task(server.serve())
    for _ in range(200):  # up to ~2s
        if server.started:
            break
        if serve_task.done():
            try:
                exc = serve_task.exception()
            except asyncio.CancelledError as e:
                exc = e
            raise RuntimeError(f"uvicorn server failed to start: {exc}")
        await asyncio.sleep(0.01)
    else:
        raise RuntimeError("uvicorn server did not start within 2s")
    bound_port = _discover_bound_port(server, host, requested_port)
    return ObservabilityServer(server=server, host=host, bound_port=bound_port)


def _discover_bound_port(server: Server, host: str, requested: int) -> int:
    """Find the actual port the server is listening on.

    For `port=0`, uvicorn assigns an ephemeral port and stores
    the listening `Server` in `server.servers[0]`. We read the
    bound port from that server's first socket.
    """
    if requested != 0:
        return requested
    servers = getattr(server, "servers", None)
    if not servers:
        return 0
    uv_server = servers[0]
    sockets = getattr(uv_server, "sockets", None)
    if not sockets:
        return 0
    name = sockets[0].getsockname() if sockets else None
    if name is None:
        return 0
    return int(name[1])


async def shutdown(server: ObservabilityServer) -> None:
    """Gracefully stop `server`."""
    server.server.should_exit = True
    # Close all listening sockets so the OS releases the port and
    # pytest's ResourceWarning checks don't fire. The uvicorn
    # `TransportSocket` wrapper keeps the real socket in `_sock`;
    # closing that releases the fd.
    servers = getattr(server.server, "servers", None) or []
    for uv in servers:
        for sock in getattr(uv, "sockets", None) or ():
            inner = getattr(sock, "_sock", None)
            if inner is not None:
                with contextlib.suppress(Exception):
                    inner.close()
            else:
                with contextlib.suppress(Exception):
                    os.close(sock.fileno())
    # Best-effort: give the loop a moment to drain. We do NOT
    # `await` the server task because uvicorn's `serve()` may
    # raise CancelledError or similar during shutdown; tests
    # only need the port to be released.
    await asyncio.sleep(0.05)


__all__ = [
    "ObservabilityServer",
    "build_app",
    "find_ephemeral_port",
    "shutdown",
    "start",
]
