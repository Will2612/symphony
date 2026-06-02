"""Unit tests for `symphony.config.resolution`.

Plan ref: §3, §15, §17.1. The resolver expands `$VAR` and `~` only
on whitelisted fields:

- $VAR: tracker.api_key, workspace.root, logs_root.
- ~: workspace.root, logs_root.
- NEVER: tracker.endpoint, codex.command, GraphQL host names.

`$UNKNOWN` resolves to the empty string by default.
"""

from __future__ import annotations

import os

from symphony.config.resolution import PATH_FIELDS, resolve
from symphony.config.schema import SymphonyConfig


def test_resolve_expands_dollar_var_in_workspace_root() -> None:
    cfg = SymphonyConfig.model_validate({"workspace": {"root": "$WS_ROOT/sub"}})
    out = resolve(cfg, env={"WS_ROOT": "/var/ws"})
    assert out.workspace.root == "/var/ws/sub"


def test_resolve_expands_dollar_var_in_logs_root() -> None:
    cfg = SymphonyConfig.model_validate({"logs_root": "$LOGS_DIR/symphony"})
    out = resolve(cfg, env={"LOGS_DIR": "/var/log"})
    assert out.logs_root == "/var/log/symphony"


def test_resolve_expands_dollar_var_in_api_key() -> None:
    cfg = SymphonyConfig.model_validate({"tracker": {"api_key": "$GH_TOKEN"}})
    out = resolve(cfg, env={"GH_TOKEN": "secret123"})
    assert out.tracker.api_key == "secret123"


def test_resolve_expands_home_in_workspace_root() -> None:
    cfg = SymphonyConfig.model_validate({"workspace": {"root": "~/work"}})
    out = resolve(cfg)
    assert "work" in out.workspace.root
    assert "~" not in out.workspace.root


def test_resolve_expands_home_in_logs_root() -> None:
    cfg = SymphonyConfig.model_validate({"logs_root": "~/logs/symphony"})
    out = resolve(cfg)
    assert "~" not in out.logs_root


def test_resolve_does_not_touch_endpoint() -> None:
    cfg = SymphonyConfig.model_validate({"tracker": {"endpoint": "https://$HOST.example.com"}})
    out = resolve(cfg, env={"HOST": "shouldnt-apply"})
    assert out.tracker.endpoint == "https://$HOST.example.com"


def test_resolve_does_not_touch_codex_command() -> None:
    cfg = SymphonyConfig.model_validate({"codex": {"command": "$BIN acp"}})
    out = resolve(cfg, env={"BIN": "shouldnt-apply"})
    assert out.codex.command == "$BIN acp"


def test_resolve_does_not_touch_active_states() -> None:
    cfg = SymphonyConfig.model_validate({"tracker": {"active_states": ["$STATE"]}})
    out = resolve(cfg, env={"STATE": "shouldnt-apply"})
    assert out.tracker.active_states == ["$STATE"]


def test_resolve_unknown_dollar_var_resolves_to_empty() -> None:
    cfg = SymphonyConfig.model_validate({"workspace": {"root": "$MISSING/x"}})
    out = resolve(cfg)
    assert out.workspace.root == "/x"


def test_resolve_returns_a_new_config_value() -> None:
    cfg = SymphonyConfig.model_validate({"workspace": {"root": "$WS"}})
    out = resolve(cfg, env={"WS": "/var/ws"})
    assert out is not cfg
    assert cfg.workspace.root == "$WS"  # original unchanged
    assert out.workspace.root == "/var/ws"


def test_resolve_no_substitutions_returns_same_view() -> None:
    cfg = SymphonyConfig.model_validate({})
    out = resolve(cfg)
    # No substitutable fields with $ or ~; should return a value
    # with identical content.
    assert out.workspace.root == cfg.workspace.root
    assert out.logs_root == cfg.logs_root


def test_resolve_with_explicit_empty_env() -> None:
    cfg = SymphonyConfig.model_validate({"workspace": {"root": "$WS"}})
    out = resolve(cfg, env={})
    assert out.workspace.root == ""


def test_resolve_combined_dollar_and_home() -> None:
    cfg = SymphonyConfig.model_validate({"workspace": {"root": "~$WS_ROOT"}})
    out = resolve(cfg, env={"WS_ROOT": "/inner"})
    home = os.path.expanduser("~")
    assert out.workspace.root == f"{home}/inner"


def test_path_fields_constant_includes_workspace_and_logs() -> None:
    assert "workspace.root" in PATH_FIELDS
    assert "logs_root" in PATH_FIELDS
