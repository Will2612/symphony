"""Unit tests for `symphony.tracker.normalize`.

Plan ref: §11 step 10, SPEC §4.1.1, §11.3.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from typing import Any

import pytest

from symphony.tracker.normalize import (
    BlockerRef,
    Issue,
    normalize_issue,
    parse_iso8601,
)


def _raw(**fields: Any) -> Mapping[str, Any]:
    base: dict[str, Any] = {
        "id": "iss-1",
        "identifier": "ABC-1",
        "title": "Fix the thing",
        "state": "open",
        "description": "It's broken.",
        "priority": 1,
        "branch_name": None,
        "url": "https://example.com/issue/1",
        "labels": ["bug", "P1"],
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T12:34:56+00:00",
    }
    base.update(fields)
    return base


def test_normalize_issue_basic_fields() -> None:
    issue = normalize_issue(_raw())
    assert isinstance(issue, Issue)
    assert issue.id == "iss-1"
    assert issue.identifier == "ABC-1"
    assert issue.title == "Fix the thing"
    assert issue.state == "open"
    assert issue.description == "It's broken."
    assert issue.priority == 1
    assert issue.branch_name is None
    assert issue.url == "https://example.com/issue/1"


def test_normalize_issue_lowercases_labels() -> None:
    issue = normalize_issue(_raw(labels=["Bug", "P1", "READY"]))
    assert issue.labels == ("bug", "p1", "ready")


def test_normalize_issue_handles_label_dicts() -> None:
    issue = normalize_issue(_raw(labels=[{"name": "Bug"}, {"name": "P1"}]))
    assert issue.labels == ("bug", "p1")


def test_normalize_issue_handles_mixed_label_formats() -> None:
    issue = normalize_issue(_raw(labels=["Bug", {"name": "P1"}, "ready"]))
    assert issue.labels == ("bug", "p1", "ready")


def test_normalize_issue_empty_labels() -> None:
    issue = normalize_issue(_raw(labels=[]))
    assert issue.labels == ()


def test_normalize_issue_strips_label_whitespace() -> None:
    issue = normalize_issue(_raw(labels=["  bug  ", "p1"]))
    assert issue.labels == ("bug", "p1")


def test_normalize_issue_filters_empty_label_strings() -> None:
    issue = normalize_issue(_raw(labels=["bug", "", "  ", "p1"]))
    assert issue.labels == ("bug", "p1")


def test_normalize_issue_blocked_by_from_inverse_relations() -> None:
    raw = _raw(
        inverse_relations={
            "nodes": [
                {
                    "type": "blocks",
                    "issue": {
                        "id": "iss-99",
                        "identifier": "ABC-99",
                        "state": "open",
                    },
                }
            ]
        }
    )
    issue = normalize_issue(raw)
    assert len(issue.blocked_by) == 1
    ref = issue.blocked_by[0]
    assert isinstance(ref, BlockerRef)
    assert ref.id == "iss-99"
    assert ref.identifier == "ABC-99"
    assert ref.state == "open"


def test_normalize_issue_blocked_by_ignores_non_blocks_relations() -> None:
    raw = _raw(
        inverse_relations={
            "nodes": [
                {
                    "type": "duplicate",
                    "issue": {
                        "id": "iss-99",
                        "identifier": "ABC-99",
                        "state": "open",
                    },
                },
                {
                    "type": "blocks",
                    "issue": {
                        "id": "iss-100",
                        "identifier": "ABC-100",
                        "state": "closed",
                    },
                },
            ]
        }
    )
    issue = normalize_issue(raw)
    assert len(issue.blocked_by) == 1
    assert issue.blocked_by[0].identifier == "ABC-100"


def test_normalize_issue_blocked_by_handles_list_format() -> None:
    """Some trackers expose inverse_relations as a list, not {nodes: [...]}."""
    raw = _raw(
        inverse_relations=[
            {
                "type": "blocks",
                "issue": {
                    "id": "iss-99",
                    "identifier": "ABC-99",
                    "state": "open",
                },
            }
        ]
    )
    issue = normalize_issue(raw)
    assert len(issue.blocked_by) == 1


def test_normalize_issue_blocked_by_handles_blocker_as_dict() -> None:
    """Some trackers (GitHub) use a flat blocker dict, not a nested 'issue'."""
    raw = _raw(
        inverse_relations=[
            {
                "type": "blocks",
                "id": "iss-99",
                "identifier": "ABC-99",
                "state": "open",
            }
        ]
    )
    issue = normalize_issue(raw)
    assert len(issue.blocked_by) == 1
    assert issue.blocked_by[0].identifier == "ABC-99"


def test_normalize_issue_blocked_by_empty_when_no_relations() -> None:
    issue = normalize_issue(_raw())
    assert issue.blocked_by == ()


def test_normalize_issue_priority_zero() -> None:
    issue = normalize_issue(_raw(priority=0))
    assert issue.priority == 0


def test_normalize_issue_priority_string_int() -> None:
    issue = normalize_issue(_raw(priority="2"))
    assert issue.priority == 2


def test_normalize_issue_priority_garbage_becomes_none() -> None:
    issue = normalize_issue(_raw(priority="not-a-number"))
    assert issue.priority is None


def test_normalize_issue_priority_float_becomes_none() -> None:
    issue = normalize_issue(_raw(priority=1.5))
    assert issue.priority is None


def test_normalize_issue_priority_missing_is_none() -> None:
    raw = _raw()
    del raw["priority"]
    issue = normalize_issue(raw)
    assert issue.priority is None


def test_normalize_issue_created_at_parsed() -> None:
    issue = normalize_issue(_raw())
    assert issue.created_at == datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)


def test_normalize_issue_updated_at_parsed() -> None:
    issue = normalize_issue(_raw())
    assert issue.updated_at == datetime(2024, 1, 2, 12, 34, 56, tzinfo=UTC)


def test_normalize_issue_invalid_timestamps_become_none() -> None:
    issue = normalize_issue(_raw(created_at="not a date", updated_at=None))
    assert issue.created_at is None
    assert issue.updated_at is None


def test_normalize_issue_missing_timestamps_are_none() -> None:
    raw = _raw()
    del raw["created_at"]
    del raw["updated_at"]
    issue = normalize_issue(raw)
    assert issue.created_at is None
    assert issue.updated_at is None


def test_normalize_issue_dataclass_is_frozen() -> None:
    issue = normalize_issue(_raw())
    with pytest.raises(FrozenInstanceError):
        issue.title = "New title"  # type: ignore[misc]


def test_blocker_ref_dataclass() -> None:
    ref = BlockerRef(id="x", identifier="X-1", state="open")
    assert ref.id == "x"
    assert ref.identifier == "X-1"
    assert ref.state == "open"


def test_parse_iso8601_z_suffix() -> None:
    dt = parse_iso8601("2024-01-01T00:00:00Z")
    assert dt == datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)


def test_parse_iso8601_with_offset() -> None:
    dt = parse_iso8601("2024-01-01T00:00:00+05:00")
    assert dt is not None
    assert dt.utcoffset().total_seconds() == 5 * 3600


def test_parse_iso8601_none() -> None:
    assert parse_iso8601(None) is None


def test_parse_iso8601_garbage() -> None:
    assert parse_iso8601("not a date") is None


def test_parse_iso8601_naive_assumes_utc() -> None:
    """A naive ISO-8601 timestamp is interpreted as UTC."""
    dt = parse_iso8601("2024-01-01T00:00:00")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.utcoffset().total_seconds() == 0


def test_parse_iso8601_datetime_input_returned_as_aware() -> None:
    """If a datetime is passed in, it's returned as-is (or made aware)."""
    dt = parse_iso8601(datetime(2024, 1, 1, 0, 0, 0))
    assert dt is not None
    assert dt.tzinfo is not None


def test_parse_iso8601_non_string_non_datetime() -> None:
    """Non-string, non-datetime input returns None."""
    assert parse_iso8601(42) is None
    assert parse_iso8601([]) is None
    assert parse_iso8601({}) is None


def test_normalize_priority_bool_becomes_none() -> None:
    """Bool (subclass of int) is rejected for priority."""
    issue = normalize_issue(_raw(priority=True))
    assert issue.priority is None


def test_blocker_ref_with_non_string_id_uses_str_coercion() -> None:
    """If a tracker returns a non-string id, we coerce to str."""
    issue = normalize_issue(
        _raw(
            inverse_relations=[
                {
                    "type": "blocks",
                    "issue": {"id": 123, "identifier": "X-1", "state": "open"},
                }
            ]
        )
    )
    assert issue.blocked_by[0].id == "123"


def test_normalize_blocked_by_with_non_list_nodes() -> None:
    """If `nodes` is not a list, return empty."""
    issue = normalize_issue(_raw(inverse_relations={"nodes": "not a list"}))
    assert issue.blocked_by == ()


def test_normalize_blocked_by_skips_non_mapping_nodes() -> None:
    issue = normalize_issue(_raw(inverse_relations=[None, "string", 42]))
    assert issue.blocked_by == ()


def test_normalize_blocked_by_skips_non_string_relation_type() -> None:
    issue = normalize_issue(
        _raw(
            inverse_relations=[
                {"type": None, "issue": {"id": "1", "identifier": "A", "state": "open"}},
                {"issue": {"id": "2", "identifier": "B", "state": "open"}},
            ]
        )
    )
    assert issue.blocked_by == ()


def test_blocker_ref_with_none_id() -> None:
    """None id/identifier/state are preserved as None."""
    issue = normalize_issue(
        _raw(
            inverse_relations=[
                {
                    "type": "blocks",
                    "issue": {"id": None, "identifier": None, "state": None},
                }
            ]
        )
    )
    assert issue.blocked_by[0].id is None
    assert issue.blocked_by[0].identifier is None
    assert issue.blocked_by[0].state is None


def test_parse_iso8601_empty_string() -> None:
    """An empty or whitespace-only string returns None."""
    assert parse_iso8601("") is None
    assert parse_iso8601("   ") is None
