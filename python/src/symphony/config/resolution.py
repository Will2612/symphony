"""Resolution helpers: $VAR and ~ expansion.

Per the plan and SPEC §15.2 / §17.1:

- `$VAR` indirection is gated to a whitelist: path-typed fields
  (workspace.root, logs_root) and tracker.api_key.
- URI / command strings (tracker.endpoint, codex.command,
  GraphQL host names) are NEVER rewritten.
- `~` is expanded only on path-typed fields.
- `api_key` is never logged (it is replaced with the literal
  string `redacted` when it appears in any log payload — the
  logging layer enforces this; resolution just substitutes it).

Resolution returns a NEW `SymphonyConfig` value (Pydantic models
are immutable in our config layer via `model_copy(update=...)`).
Unknown `$VAR` references resolve to the empty string by default
and yield a `ConfigPreflightError` if strict mode is on (the
strict mode flag is wired in the preflight step).
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping

from symphony.config.schema import SymphonyConfig

PATH_FIELDS: frozenset[str] = frozenset(
    {
        "workspace.root",
        "logs_root",
        "server.log_file",
    }
)

_API_KEY_FIELDS: frozenset[str] = frozenset({"tracker.api_key"})

_SUBSTITUTABLE_FIELDS: frozenset[str] = PATH_FIELDS | _API_KEY_FIELDS

_DOLLAR_VAR = re.compile(r"\$([A-Z_][A-Z0-9_]*)")
_HOME = re.compile(r"(?<![\w])~(?![\w])")


def _expand_dollar(value: str, env: Mapping[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        return env.get(name, "")

    return _DOLLAR_VAR.sub(repl, value)


def _expand_home(value: str) -> str:
    return _HOME.sub(os.path.expanduser("~"), value)


def _is_substitutable(field_path: str) -> bool:
    return field_path in _SUBSTITUTABLE_FIELDS


def _walk(obj: object, prefix: str = "") -> list[tuple[str, str]]:
    """Yield (dotted_path, value) pairs for every leaf string in `obj`."""
    if isinstance(obj, SymphonyConfig):
        dumped: object = obj.model_dump()
        return _walk(dumped, prefix)
    if isinstance(obj, dict):
        out: list[tuple[str, str]] = []
        for k, v in obj.items():
            child_prefix = f"{prefix}.{k}" if prefix else str(k)
            out.extend(_walk(v, child_prefix))
        return out
    if isinstance(obj, str):
        return [(prefix, obj)]
    return []


def resolve(config: SymphonyConfig, env: Mapping[str, str] | None = None) -> SymphonyConfig:
    """Return a new config with `$VAR` and `~` expansion applied to
    whitelisted fields.

    The whitelisted fields are:

    - `workspace.root` — both $VAR and ~
    - `logs_root` — both $VAR and ~
    - `tracker.api_key` — $VAR only (it's a secret; `~` is not meaningful)

    URI / command strings (`tracker.endpoint`, `codex.command`, etc.)
    are preserved verbatim.
    """
    effective_env: Mapping[str, str] = env if env is not None else os.environ
    changed_paths: list[tuple[str, str]] = []
    for path, value in _walk(config):
        if not isinstance(value, str) or value == "":
            continue
        if not _is_substitutable(path):
            continue
        new_value = value
        if path in PATH_FIELDS:
            new_value = _expand_home(new_value)
        new_value = _expand_dollar(new_value, effective_env)
        if new_value != value:
            changed_paths.append((path, new_value))

    if not changed_paths:
        return config

    return _apply_updates(config, changed_paths)


def _apply_updates(config: SymphonyConfig, updates: list[tuple[str, str]]) -> SymphonyConfig:
    """Build a new SymphonyConfig with the given path/value updates.

    Each update targets a single dotted path. Nested models are
    rebuilt via `model_copy(update=...)` so their validators are
    skipped for fields the user did not change.
    """
    # Group updates by top-level section
    sections: dict[str, dict[str, str]] = {}
    top_level: dict[str, str] = {}
    for path, new_value in updates:
        if "." in path:
            section, key = path.split(".", 1)
            sections.setdefault(section, {})[key] = new_value
        else:
            top_level[path] = new_value

    new = config
    for section, fields in sections.items():
        sub = getattr(new, section)
        new_sub = sub.model_copy(update=fields)
        new = new.model_copy(update={section: new_sub})
    if top_level:
        new = new.model_copy(update=top_level)
    return new


__all__ = ["PATH_FIELDS", "resolve"]
