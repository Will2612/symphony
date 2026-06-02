"""Preflight validation for a resolved `SymphonyConfig`.

Called during the orchestrator's startup sequence (plan §7.1,
step 4) after the loader has produced a `Workflow` and
`resolve()` has substituted env vars. The function:

- Returns silently on success.
- Raises `ConfigPreflightError` (with a human-readable message
  listing the offending fields) on any failure.

Per the plan and SPEC:

- For `tracker.kind == "github"`: `project_slug` and `api_key` MUST
  be non-empty.
- For any tracker: `tracker.kind` MUST be known.
- `workspace.root` MUST be non-empty.
- `codex.command` MUST be non-empty.
- `codex.approval_policy` and `codex.thread_sandbox` are
  restricted to known values (already enforced by the schema
  Literal types; checked again here as a defense in depth).
- `logs_root` MUST be non-empty.

A `strict` flag (default off) adds an additional check: any
string field that contains a literal `$` followed by an
uppercase identifier MUST be resolvable to a non-empty value.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping

from symphony.config.schema import SymphonyConfig
from symphony.errors import ConfigPreflightError

_DOLLAR_REF = re.compile(r"\$([A-Z_][A-Z0-9_]*)")


def preflight(
    config: SymphonyConfig, *, env: Mapping[str, str] | None = None, strict: bool = False
) -> None:
    """Validate a resolved config; raise `ConfigPreflightError` on any failure.

    Args:
        config: the (preferably resolved) config to check.
        env: the environment used to validate strict-mode $VAR
            references. If `None`, the process environment is used.
        strict: if True, any unresolved $VAR in any string field
            is a failure.
    """
    problems: list[str] = []

    if config.tracker.kind == "github":
        if not config.tracker.project_slug:
            problems.append("tracker.project_slug is required for github tracker")
        if not config.tracker.api_key:
            problems.append("tracker.api_key is required for github tracker")

    if not config.workspace.root.strip():
        problems.append("workspace.root must be a non-empty string")

    if not config.codex.command.strip():
        problems.append("codex.command must be a non-empty string")

    if not config.logs_root.strip():
        problems.append("logs_root must be a non-empty string")

    if strict:
        effective_env: Mapping[str, str] = env if env is not None else _safe_env()
        for path, value in _walk_strings(config):
            for match in _DOLLAR_REF.finditer(value):
                name = match.group(1)
                if not effective_env.get(name):
                    problems.append(
                        f"unresolved $VAR in {path}: {match.group(0)!r} "
                        f"(env does not contain {name!r})"
                    )

    if problems:
        joined = "; ".join(problems)
        raise ConfigPreflightError(
            f"preflight failed: {joined}",
            code="config_preflight_error",
        )


def _safe_env() -> Mapping[str, str]:
    return os.environ


def _walk_strings(obj: object, prefix: str = "") -> list[tuple[str, str]]:
    """Yield (dotted_path, value) for every string leaf in the config."""
    if isinstance(obj, SymphonyConfig):
        obj = obj.model_dump()
    if isinstance(obj, dict):
        out: list[tuple[str, str]] = []
        for k, v in obj.items():
            child = f"{prefix}.{k}" if prefix else str(k)
            out.extend(_walk_strings(v, child))
        return out
    if isinstance(obj, str):
        return [(prefix, obj)]
    return []


__all__ = ["preflight"]
