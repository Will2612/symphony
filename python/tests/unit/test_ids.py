"""Unit tests for `symphony.ids` helpers.

Plan ref: §1, §7.1, §14. The workspace key is a sanitized
deterministic string used as the filesystem directory name for an
issue's workspace. It MUST be:

- Deterministic (same input → same output, always).
- Path-safe (no `/`, no `..`, no leading `.`, no NUL, no whitespace).
- Stable across platforms (POSIX-safe characters only).

`session_id()` returns a unique identifier per call.

`normalize_issue_state()` lowercases, trims, and converts spaces
to `-`, matching SPEC §4.1.1 normalization for tracker state names.
"""

from __future__ import annotations

import pytest

from symphony.ids import normalize_issue_state, session_id, workspace_key


def test_workspace_key_is_deterministic() -> None:
    assert workspace_key("owner/repo#42") == workspace_key("owner/repo#42")


def test_workspace_key_replaces_slashes() -> None:
    key = workspace_key("owner/repo#42")
    assert "/" not in key


def test_workspace_key_replaces_hash() -> None:
    key = workspace_key("owner/repo#42")
    assert "#" not in key


def test_workspace_key_rejects_dot_dot() -> None:
    key = workspace_key("../escape")
    assert ".." not in key
    assert "/" not in key


def test_workspace_key_rejects_leading_dot() -> None:
    key = workspace_key(".hidden")
    assert not key.startswith(".")


def test_workspace_key_rejects_whitespace() -> None:
    key = workspace_key("with spaces")
    assert " " not in key


def test_workspace_key_rejects_empty_string() -> None:
    with pytest.raises(ValueError):
        workspace_key("")


def test_workspace_key_rejects_only_special_chars() -> None:
    with pytest.raises(ValueError):
        workspace_key("///")


def test_workspace_key_is_lowercase() -> None:
    key = workspace_key("Owner/Repo#42")
    assert key == key.lower()


def test_workspace_key_includes_a_short_identifier() -> None:
    key = workspace_key("owner/repo#42")
    assert "42" in key or "owner" in key or "repo" in key


def test_session_id_is_unique_per_call() -> None:
    a = session_id()
    b = session_id()
    assert a != b


def test_session_id_is_a_non_empty_string() -> None:
    s = session_id()
    assert isinstance(s, str)
    assert s


def test_normalize_issue_state_lowercases() -> None:
    assert normalize_issue_state("OPEN") == "open"


def test_normalize_issue_state_strips_whitespace() -> None:
    assert normalize_issue_state("  open  ") == "open"


def test_normalize_issue_state_replaces_spaces_with_dash() -> None:
    assert normalize_issue_state("In Progress") == "in-progress"


def test_normalize_issue_state_is_idempotent() -> None:
    once = normalize_issue_state("In Progress")
    twice = normalize_issue_state(once)
    assert once == twice == "in-progress"


def test_normalize_issue_state_handles_empty_string() -> None:
    assert normalize_issue_state("") == ""
