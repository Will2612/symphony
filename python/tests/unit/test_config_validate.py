"""Unit tests for `symphony.config.validate`.

Plan ref: §11 step 5. The preflight checks a resolved
SymphonyConfig and raises `ConfigPreflightError` if anything
required is missing or out-of-range.
"""

from __future__ import annotations

import pytest

from symphony.config.resolution import resolve
from symphony.config.schema import SymphonyConfig
from symphony.config.validate import preflight
from symphony.errors import ConfigPreflightError


def test_preflight_passes_for_default_memory_tracker() -> None:
    cfg = SymphonyConfig.model_validate(
        {"tracker": {"kind": "memory"}, "workspace": {"root": "/tmp/ws"}}
    )
    preflight(cfg)


def test_preflight_passes_for_fully_specified_github_config() -> None:
    raw = {
        "tracker": {
            "kind": "github",
            "project_slug": "owner/repo",
            "api_key": "secret",
        },
        "workspace": {"root": "/tmp/ws"},
        "codex": {"command": "opencode acp"},
    }
    cfg = SymphonyConfig.model_validate(raw)
    preflight(cfg)


def test_preflight_fails_when_github_has_no_project_slug() -> None:
    cfg = SymphonyConfig.model_validate({"tracker": {"kind": "github"}})
    with pytest.raises(ConfigPreflightError):
        preflight(cfg)


def test_preflight_fails_when_github_has_no_api_key() -> None:
    cfg = SymphonyConfig.model_validate(
        {"tracker": {"kind": "github", "project_slug": "owner/repo"}}
    )
    with pytest.raises(ConfigPreflightError):
        preflight(cfg)


def test_preflight_fails_when_workspace_root_empty() -> None:
    cfg = SymphonyConfig.model_validate(
        {
            "tracker": {"kind": "memory"},
            "workspace": {"root": "/tmp/ws"},
        }
    )
    # Bypass the schema's non-empty validator to construct a config
    # with an empty root, then assert preflight catches it.
    empty = cfg.model_copy(update={"workspace": cfg.workspace.model_copy(update={"root": ""})})
    with pytest.raises(ConfigPreflightError):
        preflight(empty)


def test_preflight_fails_when_codex_command_empty() -> None:
    cfg = SymphonyConfig.model_validate(
        {
            "tracker": {"kind": "memory"},
            "workspace": {"root": "/tmp/ws"},
            "codex": {"command": ""},
        }
    )
    with pytest.raises(ConfigPreflightError):
        preflight(cfg)


def test_preflight_includes_the_offending_field_in_the_error() -> None:
    cfg = SymphonyConfig.model_validate({"tracker": {"kind": "github"}})
    with pytest.raises(ConfigPreflightError) as exc:
        preflight(cfg)
    assert "project_slug" in str(exc.value) or "tracker" in str(exc.value)


def test_preflight_resolved_config_passes() -> None:
    raw = {
        "tracker": {
            "kind": "github",
            "project_slug": "owner/repo",
            "api_key": "$GH_TOKEN",
        },
        "workspace": {"root": "$WS_ROOT"},
    }
    cfg = SymphonyConfig.model_validate(raw)
    resolved = resolve(cfg, env={"GH_TOKEN": "secret", "WS_ROOT": "/var/ws"})
    preflight(resolved)


def test_preflight_resolved_config_with_missing_var_uses_strict() -> None:
    raw = {
        "tracker": {
            "kind": "github",
            "project_slug": "owner/repo",
            "api_key": "$MISSING_TOKEN",
        },
        "workspace": {"root": "/tmp/ws"},
    }
    cfg = SymphonyConfig.model_validate(raw)
    resolved = resolve(cfg, env={})  # MISSING_TOKEN not set
    # Without strict mode, missing $VAR yields empty api_key,
    # which then fails the github preflight check.
    with pytest.raises(ConfigPreflightError):
        preflight(resolved)


def test_preflight_strict_mode_passes_when_all_vars_resolved() -> None:
    raw = {
        "tracker": {
            "kind": "github",
            "project_slug": "owner/repo",
            "api_key": "$GH_TOKEN",
        },
        "workspace": {"root": "/tmp/ws"},
    }
    cfg = SymphonyConfig.model_validate(raw)
    preflight(cfg, env={"GH_TOKEN": "secret"}, strict=True)


def test_preflight_strict_mode_fails_on_unresolved_var() -> None:
    raw = {
        "tracker": {"kind": "memory"},
        "workspace": {"root": "/tmp/ws/$MISSING"},
    }
    cfg = SymphonyConfig.model_validate(raw)
    with pytest.raises(ConfigPreflightError) as exc:
        preflight(cfg, env={}, strict=True)
    assert "MISSING" in str(exc.value)


def test_preflight_strict_mode_fails_on_unresolved_var_in_logs_root() -> None:
    raw = {
        "tracker": {"kind": "memory"},
        "workspace": {"root": "/tmp/ws"},
        "logs_root": "/var/log/$X",
    }
    cfg = SymphonyConfig.model_validate(raw)
    with pytest.raises(ConfigPreflightError):
        preflight(cfg, env={}, strict=True)


def test_preflight_strict_mode_uses_process_env_by_default() -> None:
    raw = {
        "tracker": {"kind": "memory"},
        "workspace": {"root": "/tmp/ws"},
    }
    cfg = SymphonyConfig.model_validate(raw)
    preflight(cfg, strict=True)
