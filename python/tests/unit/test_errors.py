"""Unit tests for the `symphony.errors` hierarchy.

Plan ref: §8.1 "Error Category Hierarchy".

Every error in the project is a `SymphonyError` subclass with a
stable, log-friendly `code` string. Catching at any layer catches
only declared subtypes — no broad `except Exception` (per AGENTS.md).
"""

from __future__ import annotations

import pytest

from symphony.errors import (
    CodexNotFound,
    ConfigError,
    ConfigPreflightError,
    GitHubAPIRequest,
    GitHubAPIStatus,
    GitHubForbidden,
    GitHubNotFound,
    GitHubPaginationMissingLink,
    GitHubRateLimited,
    GitHubUnauthorized,
    GitHubUnknownPayload,
    InvalidWorkspaceCwd,
    PortExit,
    ResponseError,
    ResponseTimeout,
    SymphonyError,
    TemplateParseError,
    TemplateRenderError,
    TurnCancelled,
    TurnFailed,
    TurnInputRequired,
    TurnTimeout,
    WorkflowError,
    WorkflowFrontMatterNotAMap,
    WorkflowMissingFile,
    WorkflowParseError,
)


def test_symphony_error_is_an_exception_with_a_code() -> None:
    err = SymphonyError("boom", code="x_boom")
    assert isinstance(err, Exception)
    assert err.code == "x_boom"
    assert str(err) == "boom"


def test_symphony_error_falls_back_to_class_level_code() -> None:
    err = SymphonyError("boom")
    assert err.code == "symphony_error"
    assert str(err) == "boom"


def test_symphony_error_code_kwarg_overrides_class_default() -> None:
    err = SymphonyError("boom", code="custom")
    assert err.code == "custom"


def test_workflow_error_hierarchy() -> None:
    for cls, expected_code in [
        (WorkflowError, "workflow_error"),
        (WorkflowMissingFile, "workflow_missing_file"),
        (WorkflowParseError, "workflow_parse_error"),
        (WorkflowFrontMatterNotAMap, "workflow_front_matter_not_a_map"),
    ]:
        err = cls("hi")
        assert isinstance(err, SymphonyError)
        assert err.code == expected_code


def test_config_error_hierarchy() -> None:
    for cls, expected_code in [
        (ConfigError, "config_error"),
        (ConfigPreflightError, "config_preflight_error"),
    ]:
        err = cls("hi")
        assert isinstance(err, SymphonyError)
        assert err.code == expected_code


def test_template_error_hierarchy() -> None:
    for cls, expected_code in [
        (TemplateParseError, "template_parse_error"),
        (TemplateRenderError, "template_render_error"),
    ]:
        err = cls("hi")
        assert isinstance(err, SymphonyError)
        assert err.code == expected_code


def test_github_error_hierarchy() -> None:
    for cls, expected_code in [
        (GitHubAPIRequest, "github_api_request"),
        (GitHubAPIStatus, "github_api_status"),
        (GitHubUnauthorized, "github_unauthorized"),
        (GitHubForbidden, "github_forbidden"),
        (GitHubRateLimited, "github_rate_limited"),
        (GitHubNotFound, "github_not_found"),
        (GitHubUnknownPayload, "github_unknown_payload"),
        (GitHubPaginationMissingLink, "github_pagination_missing_link"),
    ]:
        err = cls("hi")
        assert isinstance(err, SymphonyError)
        assert err.code == expected_code


def test_github_unauthorized_is_a_github_api_status() -> None:
    assert issubclass(GitHubUnauthorized, GitHubAPIStatus)


def test_github_forbidden_is_a_github_api_status() -> None:
    assert issubclass(GitHubForbidden, GitHubAPIStatus)


def test_github_not_found_is_a_github_api_status() -> None:
    assert issubclass(GitHubNotFound, GitHubAPIStatus)


def test_github_rate_limited_carries_reset_at() -> None:
    err = GitHubRateLimited("throttled", reset_at=12345)
    assert err.code == "github_rate_limited"
    assert err.reset_at == 12345


def test_runner_error_hierarchy() -> None:
    for cls, expected_code in [
        (CodexNotFound, "codex_not_found"),
        (InvalidWorkspaceCwd, "invalid_workspace_cwd"),
        (ResponseTimeout, "response_timeout"),
        (TurnTimeout, "turn_timeout"),
        (PortExit, "port_exit"),
        (ResponseError, "response_error"),
        (TurnFailed, "turn_failed"),
        (TurnCancelled, "turn_cancelled"),
        (TurnInputRequired, "turn_input_required"),
    ]:
        err = cls("hi")
        assert isinstance(err, SymphonyError)
        assert err.code == expected_code


def test_all_named_errors_are_catchable_as_symphony_error() -> None:
    classes = [
        WorkflowError,
        WorkflowMissingFile,
        WorkflowParseError,
        WorkflowFrontMatterNotAMap,
        ConfigError,
        ConfigPreflightError,
        TemplateParseError,
        TemplateRenderError,
        GitHubAPIRequest,
        GitHubAPIStatus,
        GitHubUnauthorized,
        GitHubForbidden,
        GitHubRateLimited,
        GitHubNotFound,
        GitHubUnknownPayload,
        GitHubPaginationMissingLink,
        CodexNotFound,
        InvalidWorkspaceCwd,
        ResponseTimeout,
        TurnTimeout,
        PortExit,
        ResponseError,
        TurnFailed,
        TurnCancelled,
        TurnInputRequired,
    ]
    for cls in classes:
        try:
            raise cls("boom")
        except SymphonyError as caught:
            assert caught.code
        else:
            pytest.fail(f"{cls.__name__} did not raise as SymphonyError")
