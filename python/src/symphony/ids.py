"""Identifier and normalization helpers.

`workspace_key` returns a deterministic, POSIX-safe filesystem
name for an issue's workspace (SPEC §7). It must be:

- deterministic (same input → same output)
- path-safe (no `/`, no `..`, no leading dot, no whitespace, no NUL)
- lowercase (POSIX-portable)

`session_id` returns a fresh unique identifier per call (used for
runner session ids and similar ephemeral values).

`normalize_issue_state` is the SPEC §4.1.1 normalization: lower
case, strip, replace spaces with `-`. The function is idempotent.
"""

from __future__ import annotations

import re
import uuid

_DISALLOWED = re.compile(r"[^a-z0-9._-]+")
_MULTI_DASH = re.compile(r"-{2,}")


def workspace_key(issue_id: str) -> str:
    """Return a deterministic, POSIX-safe filesystem name for `issue_id`.

    Raises:
        ValueError: if the input is empty or contains no usable
            characters after sanitization.
    """
    if not issue_id:
        raise ValueError("workspace_key requires a non-empty issue_id")
    lowered = issue_id.lower().strip()
    replaced = _DISALLOWED.sub("-", lowered)
    cleaned = _MULTI_DASH.sub("-", replaced).strip("._-")
    if not cleaned:
        raise ValueError(f"workspace_key: no usable characters in {issue_id!r}")
    return cleaned


def session_id() -> str:
    """Return a fresh unique session identifier."""
    return uuid.uuid4().hex


def normalize_issue_state(raw: str) -> str:
    """Lower-case, strip, and replace internal whitespace with `-`.

    Matches the SPEC §4.1.1 tracker-state normalization. Idempotent.
    """
    return _MULTI_DASH.sub("-", _DISALLOWED.sub("-", raw.lower().strip()).strip("-"))


__all__ = ["normalize_issue_state", "session_id", "workspace_key"]
