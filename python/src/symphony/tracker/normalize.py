"""Tracker-agnostic issue normalization.

A tracker adapter (GitHub, Linear, memory, ...) returns raw issues
in its own JSON shape. The orchestrator works with a single
canonical `Issue` dataclass per SPEC §4.1.1. This module is
the boundary: it accepts the raw shape and emits the canonical one.

Normalization rules (per SPEC §11.3):

- `labels` -> lowercase strings; strings are stripped; dicts with
  `name` key are unwrapped.
- `blocked_by` -> derived from inverse relations where relation
  type is `blocks`. Accepts `inverse_relations` in either
  `{nodes: [...]}` (Linear) or list (GitHub-style) format.
- `priority` -> integer; non-integer values become `None`.
- `created_at` and `updated_at` -> ISO-8601 timestamps parsed via
  `datetime.fromisoformat` (handles Z and offset suffixes on 3.12+).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class BlockerRef:
    """A normalized reference to a blocking issue (SPEC §4.1.1)."""

    id: str | None
    identifier: str | None
    state: str | None


@dataclass(frozen=True)
class Issue:
    """Canonical normalized issue used by orchestration, prompt
    rendering, and observability (SPEC §4.1.1).

    `labels` is a tuple of lowercase strings. `blocked_by` is a
    tuple of `BlockerRef`s. Timestamps are timezone-aware UTC
    datetimes (or `None` if missing / unparseable)."""

    id: str
    identifier: str
    title: str
    state: str
    description: str | None
    priority: int | None
    branch_name: str | None
    url: str | None
    labels: tuple[str, ...] = field(default_factory=tuple)
    blocked_by: tuple[BlockerRef, ...] = field(default_factory=tuple)
    created_at: datetime | None = None
    updated_at: datetime | None = None


_BLOCKS_RELATION = "blocks"


def normalize_issue(raw: Mapping[str, Any]) -> Issue:
    """Convert a raw issue mapping into a canonical `Issue`.

    See module docstring for normalization rules.
    """
    return Issue(
        id=str(raw.get("id", "")),
        identifier=str(raw.get("identifier", "")),
        title=str(raw.get("title", "")),
        state=str(raw.get("state", "")),
        description=raw.get("description"),
        priority=_normalize_priority(raw.get("priority")),
        branch_name=raw.get("branch_name"),
        url=raw.get("url"),
        labels=_normalize_labels(raw.get("labels")),
        blocked_by=_normalize_blocked_by(raw.get("inverse_relations")),
        created_at=parse_iso8601(raw.get("created_at")),
        updated_at=parse_iso8601(raw.get("updated_at")),
    )


def _normalize_priority(value: Any) -> int | None:  # noqa: ANN401 - raw JSON
    if value is None:
        return None
    if isinstance(value, bool):  # bool is a subclass of int — reject
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _normalize_labels(value: Any) -> tuple[str, ...]:  # noqa: ANN401 - raw JSON
    if value is None:
        return ()
    out: list[str] = []
    if isinstance(value, Mapping):
        value = list(value.values())
    for item in value:
        name = item.get("name") if isinstance(item, Mapping) else item
        if not isinstance(name, str):
            continue
        cleaned = name.strip().lower()
        if cleaned:
            out.append(cleaned)
    return tuple(out)


def _normalize_blocked_by(value: Any) -> tuple[BlockerRef, ...]:  # noqa: ANN401 - raw JSON
    if value is None:
        return ()
    # Accept either a list of relations or a {nodes: [...]} wrapper.
    if isinstance(value, Mapping):
        nodes = value.get("nodes", [])
    elif isinstance(value, list):
        nodes = value
    else:
        return ()
    if not isinstance(nodes, list):
        return ()
    out: list[BlockerRef] = []
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        rel_type = node.get("type")
        if not isinstance(rel_type, str):
            continue
        if rel_type.strip().lower() != _BLOCKS_RELATION:
            continue
        blocker = _extract_blocker(node)
        if blocker is not None:
            out.append(blocker)
    return tuple(out)


def _extract_blocker(node: Mapping[str, Any]) -> BlockerRef | None:
    """Extract a BlockerRef from a relation node. Handles both
    nested (`{issue: {id, identifier, state}}`) and flat
    (`{id, identifier, state}`) shapes."""
    nested = node.get("issue")
    if isinstance(nested, Mapping):
        return BlockerRef(
            id=_as_str_or_none(nested.get("id")),
            identifier=_as_str_or_none(nested.get("identifier")),
            state=_as_str_or_none(nested.get("state")),
        )
    return BlockerRef(
        id=_as_str_or_none(node.get("id")),
        identifier=_as_str_or_none(node.get("identifier")),
        state=_as_str_or_none(node.get("state")),
    )


def _as_str_or_none(value: Any) -> str | None:  # noqa: ANN401 - raw JSON
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def parse_iso8601(value: Any) -> datetime | None:  # noqa: ANN401 - raw JSON
    """Parse an ISO-8601 timestamp into a timezone-aware `datetime`.

    Accepts strings with a `Z` suffix (Python 3.11+ translates to
    `+00:00`). Returns `None` for `None` or unparseable values.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return _ensure_aware(value)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    # Python 3.11+ handles the trailing 'Z' in fromisoformat directly.
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return _ensure_aware(dt)


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt
    # Naive datetimes are assumed to be UTC.
    return dt.replace(tzinfo=UTC)


__all__ = ["BlockerRef", "Issue", "normalize_issue", "parse_iso8601"]
