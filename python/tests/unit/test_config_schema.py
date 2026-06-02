"""Unit tests for `symphony.config.schema`.

Plan ref: §3, §5, §11 step 4.

Pydantic typed view over a parsed WORKFLOW.md front-matter. The
schema enforces:

- tracker.kind must be one of {"github", "memory"} (or a custom
  adapter kind registered elsewhere).
- tracker.endpoint defaults to https://api.github.com.
- tracker.active_states defaults to ["open"]; tracker.terminal_states
  defaults to ["closed"].
- polling.interval_ms must be positive.
- workspace.root must be a non-empty string.
- agent.max_retry_backoff_ms must be non-negative.
- codex.command is preserved verbatim (not subject to $VAR
  indirection).
- worker.ssh_hosts is parsed but not used in v1.
- server.host defaults to "127.0.0.1", server.port is 0..65535.
- logs_root has a default of "./logs".
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from symphony.config.schema import (
    SymphonyConfig,
)


def test_minimal_valid_config() -> None:
    cfg = SymphonyConfig.model_validate({})
    assert cfg.tracker.kind == "github"
    assert cfg.tracker.endpoint == "https://api.github.com"
    assert cfg.tracker.active_states == ["open"]
    assert cfg.tracker.terminal_states == ["closed"]


def test_tracker_kind_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError):
        SymphonyConfig.model_validate({"tracker": {"kind": "jira"}})


def test_tracker_kind_accepts_github() -> None:
    cfg = SymphonyConfig.model_validate({"tracker": {"kind": "github"}})
    assert cfg.tracker.kind == "github"


def test_tracker_kind_accepts_memory() -> None:
    cfg = SymphonyConfig.model_validate({"tracker": {"kind": "memory"}})
    assert cfg.tracker.kind == "memory"


def test_tracker_endpoint_default() -> None:
    cfg = SymphonyConfig.model_validate({"tracker": {"kind": "github"}})
    assert cfg.tracker.endpoint == "https://api.github.com"


def test_tracker_endpoint_accepts_custom_enterprise_url() -> None:
    cfg = SymphonyConfig.model_validate(
        {"tracker": {"kind": "github", "endpoint": "https://gh.example.com"}}
    )
    assert cfg.tracker.endpoint == "https://gh.example.com"


def test_tracker_active_states_default() -> None:
    cfg = SymphonyConfig.model_validate({})
    assert cfg.tracker.active_states == ["open"]


def test_tracker_active_states_can_be_overridden() -> None:
    cfg = SymphonyConfig.model_validate(
        {"tracker": {"kind": "github", "active_states": ["Todo", "In Progress"]}}
    )
    assert cfg.tracker.active_states == ["Todo", "In Progress"]


def test_tracker_terminal_states_default() -> None:
    cfg = SymphonyConfig.model_validate({})
    assert cfg.tracker.terminal_states == ["closed"]


def test_polling_interval_ms_default_is_30000() -> None:
    cfg = SymphonyConfig.model_validate({})
    assert cfg.polling.interval_ms == 30_000


def test_polling_interval_ms_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        SymphonyConfig.model_validate({"polling": {"interval_ms": 0}})


def test_workspace_root_required() -> None:
    cfg = SymphonyConfig.model_validate({"workspace": {"root": "/tmp/ws"}})
    assert cfg.workspace.root == "/tmp/ws"


def test_workspace_root_must_be_non_empty() -> None:
    with pytest.raises(ValidationError):
        SymphonyConfig.model_validate({"workspace": {"root": ""}})


def test_hooks_default_is_empty_dict() -> None:
    cfg = SymphonyConfig.model_validate({})
    assert cfg.hooks.after_create is None
    assert cfg.hooks.before_run is None
    assert cfg.hooks.after_run is None
    assert cfg.hooks.before_remove is None


def test_hooks_accepts_command_strings() -> None:
    cfg = SymphonyConfig.model_validate({"hooks": {"after_create": "echo hi", "timeout_ms": 5000}})
    assert cfg.hooks.after_create == "echo hi"
    assert cfg.hooks.timeout_ms == 5_000


def test_agent_max_retry_backoff_ms_default() -> None:
    cfg = SymphonyConfig.model_validate({})
    assert cfg.agent.max_retry_backoff_ms == 600_000


def test_agent_max_retry_backoff_ms_must_be_non_negative() -> None:
    with pytest.raises(ValidationError):
        SymphonyConfig.model_validate({"agent": {"max_retry_backoff_ms": -1}})


def test_codex_command_default() -> None:
    cfg = SymphonyConfig.model_validate({})
    assert cfg.codex.command == "opencode acp"


def test_codex_command_preserved_verbatim() -> None:
    cfg = SymphonyConfig.model_validate({"codex": {"command": "/usr/local/bin/opencode acp --foo"}})
    assert cfg.codex.command == "/usr/local/bin/opencode acp --foo"


def test_codex_approval_policy_default() -> None:
    cfg = SymphonyConfig.model_validate({})
    assert cfg.codex.approval_policy == "auto-approve"


def test_codex_thread_sandbox_default() -> None:
    cfg = SymphonyConfig.model_validate({})
    assert cfg.codex.thread_sandbox == "workspace-write"


def test_codex_stall_timeout_ms_zero_disables_stall_detection() -> None:
    cfg = SymphonyConfig.model_validate({"codex": {"stall_timeout_ms": 0}})
    assert cfg.codex.stall_timeout_ms == 0


def test_server_host_default_is_loopback() -> None:
    cfg = SymphonyConfig.model_validate({})
    assert cfg.server.host == "127.0.0.1"


def test_server_port_can_be_zero_for_ephemeral() -> None:
    cfg = SymphonyConfig.model_validate({"server": {"port": 0}})
    assert cfg.server.port == 0


def test_server_port_must_be_in_range() -> None:
    with pytest.raises(ValidationError):
        SymphonyConfig.model_validate({"server": {"port": 70_000}})


def test_worker_ssh_hosts_parsed_but_unused() -> None:
    cfg = SymphonyConfig.model_validate(
        {"worker": {"ssh_hosts": ["a@host1", "b@host2"], "max_concurrent_agents_per_host": 2}}
    )
    assert cfg.worker.ssh_hosts == ["a@host1", "b@host2"]
    assert cfg.worker.max_concurrent_agents_per_host == 2


def test_logs_root_default() -> None:
    cfg = SymphonyConfig.model_validate({})
    assert cfg.logs_root == "./logs"


def test_full_config_round_trip() -> None:
    raw = {
        "tracker": {
            "kind": "github",
            "project_slug": "owner/repo",
            "api_key": "$GITHUB_TOKEN",
            "active_states": ["open"],
            "terminal_states": ["closed"],
            "endpoint": "https://api.github.com",
        },
        "polling": {"interval_ms": 30_000},
        "workspace": {"root": "$WORKSPACE_ROOT"},
        "agent": {"max_turns": 50, "max_retry_backoff_ms": 60_000},
        "codex": {"command": "opencode acp"},
        "server": {"host": "127.0.0.1", "port": 7842},
        "logs_root": "./logs",
    }
    cfg = SymphonyConfig.model_validate(raw)
    assert cfg.tracker.api_key == "$GITHUB_TOKEN"
    assert cfg.tracker.project_slug == "owner/repo"
    assert cfg.workspace.root == "$WORKSPACE_ROOT"
    assert cfg.agent.max_turns == 50
    assert cfg.server.port == 7842
