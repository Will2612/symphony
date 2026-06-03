"""Typed Pydantic view over a parsed WORKFLOW.md front-matter.

The schema is the single source of truth for what a valid config
looks like. Defaults are applied here so the rest of the codebase
can rely on every field being populated.

Per the plan and SPEC:

- `tracker.kind` is restricted to known adapter values; "github"
  and "memory" are first-class, with room for future kinds.
- `tracker.endpoint` defaults to https://api.github.com.
- `codex.command` is preserved verbatim (never subject to $VAR
  indirection).
- `worker.ssh_hosts` is parsed but unused in v1.
- `server.host` defaults to the loopback 127.0.0.1.
- `server.port` accepts 0 for an ephemeral port.
- `codex.stall_timeout_ms` accepts 0 to disable stall detection.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

TrackerKind = Literal["github", "memory"]
ApprovalPolicy = Literal["auto-approve", "reject", "prompt"]
ThreadSandbox = Literal["workspace-write", "read-only", "full-disk"]


class Tracker(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: TrackerKind = "github"
    project_slug: str = ""
    api_key: str = ""
    active_states: list[str] = Field(default_factory=lambda: ["open"])
    terminal_states: list[str] = Field(default_factory=lambda: ["closed"])
    endpoint: str = "https://api.github.com"


class Polling(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interval_ms: int = 30_000

    @field_validator("interval_ms")
    @classmethod
    def _positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("polling.interval_ms must be > 0")
        return v


class Workspace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root: str = ""

    @field_validator("root")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if v == "":
            raise ValueError("workspace.root must be a non-empty string")
        return v


class Hooks(BaseModel):
    model_config = ConfigDict(extra="forbid")

    after_create: str | None = None
    before_run: str | None = None
    after_run: str | None = None
    before_remove: str | None = None
    timeout_ms: int = 60_000


class Agent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_turns: int = 50
    max_retry_backoff_ms: int = 600_000
    max_concurrent_agents: int = 5

    @field_validator("max_retry_backoff_ms")
    @classmethod
    def _non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("agent.max_retry_backoff_ms must be >= 0")
        return v

    @field_validator("max_concurrent_agents")
    @classmethod
    def _positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("agent.max_concurrent_agents must be > 0")
        return v


class Codex(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str = "opencode acp"
    approval_policy: ApprovalPolicy = "auto-approve"
    thread_sandbox: ThreadSandbox = "workspace-write"
    turn_sandbox_policy: dict[str, object] = Field(default_factory=dict)
    read_timeout_ms: int = 30_000
    turn_timeout_ms: int = 3_600_000
    stall_timeout_ms: int = 300_000


class Server(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = "127.0.0.1"
    port: int = 7842
    log_file: str = ""

    @field_validator("port")
    @classmethod
    def _port_range(cls, v: int) -> int:
        if not 0 <= v <= 65_535:
            raise ValueError("server.port must be in 0..65535")
        return v


class Worker(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ssh_hosts: list[str] = Field(default_factory=list)
    max_concurrent_agents_per_host: int = 1


class SymphonyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tracker: Tracker = Field(default_factory=Tracker)
    polling: Polling = Field(default_factory=Polling)
    workspace: Workspace = Field(default_factory=Workspace)
    hooks: Hooks = Field(default_factory=Hooks)
    agent: Agent = Field(default_factory=Agent)
    codex: Codex = Field(default_factory=Codex)
    server: Server = Field(default_factory=Server)
    worker: Worker = Field(default_factory=Worker)
    logs_root: str = "./logs"
