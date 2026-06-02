"""Typed error hierarchy for the Symphony service.

Every error in the project inherits from `SymphonyError` and carries
a stable, log-friendly `code` string (per plan §8.1 and SPEC §10.6,
§11.4, §14). Catching at any layer catches only declared subtypes
— no broad `except Exception` (per `python/AGENTS.md`).
"""

from __future__ import annotations


class SymphonyError(Exception):
    """Base class for every error raised by the Symphony service.

    Subclasses MUST set a stable `code` so log lines and snapshot
    payloads can be matched without parsing the human message.
    """

    code: str = "symphony_error"

    def __init__(self, message: str = "", *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class WorkflowError(SymphonyError):
    code = "workflow_error"


class WorkflowMissingFile(WorkflowError):
    code = "workflow_missing_file"


class WorkflowParseError(WorkflowError):
    code = "workflow_parse_error"


class WorkflowFrontMatterNotAMap(WorkflowError):
    code = "workflow_front_matter_not_a_map"


class ConfigError(SymphonyError):
    code = "config_error"


class ConfigPreflightError(ConfigError):
    code = "config_preflight_error"


class TemplateParseError(SymphonyError):
    code = "template_parse_error"


class TemplateRenderError(SymphonyError):
    code = "template_render_error"


class GitHubAPIRequest(SymphonyError):
    code = "github_api_request"


class GitHubAPIStatus(SymphonyError):
    code = "github_api_status"


class GitHubUnauthorized(GitHubAPIStatus):
    code = "github_unauthorized"


class GitHubForbidden(GitHubAPIStatus):
    code = "github_forbidden"


class GitHubRateLimited(GitHubAPIStatus):
    code = "github_rate_limited"

    def __init__(
        self,
        message: str = "",
        *,
        reset_at: int | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message, code=code)
        self.reset_at = reset_at


class GitHubNotFound(GitHubAPIStatus):
    code = "github_not_found"


class GitHubUnknownPayload(SymphonyError):
    code = "github_unknown_payload"


class GitHubPaginationMissingLink(SymphonyError):
    code = "github_pagination_missing_link"


class CodexNotFound(SymphonyError):
    code = "codex_not_found"


class InvalidWorkspaceCwd(SymphonyError):
    code = "invalid_workspace_cwd"


class ResponseTimeout(SymphonyError):
    code = "response_timeout"


class TurnTimeout(SymphonyError):
    code = "turn_timeout"


class PortExit(SymphonyError):
    code = "port_exit"


class ResponseError(SymphonyError):
    code = "response_error"


class TurnFailed(SymphonyError):
    code = "turn_failed"


class TurnCancelled(SymphonyError):
    code = "turn_cancelled"


class TurnInputRequired(SymphonyError):
    code = "turn_input_required"


class HookError(SymphonyError):
    """Base class for workspace-hook failures."""


class HookFailed(HookError):
    """A hook command exited with a non-zero status."""

    code = "hook_failed"

    def __init__(
        self,
        message: str = "",
        *,
        hook_name: str,
        status: int,
        output: str,
        code: str | None = None,
    ) -> None:
        super().__init__(message, code=code)
        self.hook_name = hook_name
        self.status = status
        self.output = output


class HookTimeout(HookError):
    """A hook command did not complete within the configured timeout."""

    code = "hook_timeout"

    def __init__(
        self,
        message: str = "",
        *,
        hook_name: str,
        timeout_ms: int,
        code: str | None = None,
    ) -> None:
        super().__init__(message, code=code)
        self.hook_name = hook_name
        self.timeout_ms = timeout_ms


class WorkspaceOutsideRoot(SymphonyError):
    """A computed workspace path is outside the configured workspace root."""

    code = "workspace_outside_root"

    def __init__(
        self,
        message: str = "",
        *,
        workspace: str,
        root: str,
        code: str | None = None,
    ) -> None:
        super().__init__(message, code=code)
        self.workspace = workspace
        self.root = root


__all__ = [
    "CodexNotFound",
    "ConfigError",
    "ConfigPreflightError",
    "GitHubAPIRequest",
    "GitHubAPIStatus",
    "GitHubForbidden",
    "GitHubNotFound",
    "GitHubPaginationMissingLink",
    "GitHubRateLimited",
    "GitHubUnauthorized",
    "GitHubUnknownPayload",
    "HookError",
    "HookFailed",
    "HookTimeout",
    "InvalidWorkspaceCwd",
    "PortExit",
    "ResponseError",
    "ResponseTimeout",
    "SymphonyError",
    "TemplateParseError",
    "TemplateRenderError",
    "TurnCancelled",
    "TurnFailed",
    "TurnInputRequired",
    "TurnTimeout",
    "WorkflowError",
    "WorkflowFrontMatterNotAMap",
    "WorkflowMissingFile",
    "WorkflowParseError",
    "WorkspaceOutsideRoot",
]
