"""Runtime snapshot for the optional observability HTTP endpoint
(SPEC §13.3 + §13.5).

Public surface:

- `build_snapshot(state, *, now=None) -> dict` — return a JSON-safe
  dict with the snapshot fields per SPEC §13.3:
  - `running`: list of running session rows (each with `turn_count`).
  - `retrying`: list of retry queue rows.
  - `codex_totals`: aggregate input_tokens, output_tokens,
    total_tokens, seconds_running.
  - `rate_limits`: latest rate-limit payload (none if never seen).
- `RunningSnapshotRow`, `RetrySnapshotRow` — dataclasses for the
  rows (used by tests; the public API is the dict form).
- `aggregate_token_usage(state)` — sum input_tokens, output_tokens,
  total_tokens across all running + retry sessions, ignoring
  non-integer values.
- `aggregate_runtime_seconds(state, now)` — sum of `seconds_running`
  = cumulative ended session runtime + active session elapsed.
- `extract_token_counts(usage)` — lenient extraction of
  (input, output, total) from a usage dict (SPEC §13.5).
- `extract_rate_limit(event_payload)` — extract rate-limit
  payload from an event payload, or `None`.

Token accounting rules per SPEC §13.5:
- Prefer absolute thread totals; ignore delta-style maps.
- For absolute totals, callers should pass deltas; this module
  treats `usage` maps as cumulative only when the field name is
  one of `total_token_usage.input_tokens`,
  `total_token_usage.output_tokens`, `total_token_usage.total_tokens`,
  or the equivalent shorthand. Otherwise, values are summed
  additively.

Runtime accounting per SPEC §13.5:
- Cumulative ended-session runtime is tracked in `state.runtime_seconds`.
- Active-session elapsed = `(now - session.started_at).total_seconds()`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from symphony.orchestrator.state import OrchestratorState

_TOKEN_KEY_INPUT = "input_tokens"
_TOKEN_KEY_OUTPUT = "output_tokens"
_TOKEN_KEY_TOTAL = "total_tokens"

# Field names that signal an *absolute* (not delta) usage payload.
# When ANY of these is present in a usage dict, we use the absolute
# values directly (clamped at 0). Otherwise, we add the values to
# the running aggregate.
_ABSOLUTE_KEYS = frozenset(
    {
        "total_token_usage",
        "thread/tokenUsage/updated",
        "total_input_tokens",
        "total_output_tokens",
    }
)

_RATE_LIMIT_KEYS = frozenset({"codex_rate_limits", "rate_limits", "rateLimit", "rate_limit"})


@dataclass(frozen=True)
class RunningSnapshotRow:
    """One running session for the snapshot."""

    issue_id: str
    identifier: str
    session_id: str
    started_at: datetime
    attempt: int
    turn_count: int
    usage: dict[str, int]


@dataclass(frozen=True)
class RetrySnapshotRow:
    """One queued retry for the snapshot."""

    issue_id: str
    identifier: str
    attempt: int
    error: str
    due_at_ms: int


def extract_token_counts(usage: Any) -> tuple[int, int, int]:  # noqa: ANN401
    """Extract (input, output, total) from a usage dict.

    Lenient: missing fields are treated as 0. Non-int values are
    skipped. Recognises both short (`input_tokens`/`output_tokens`)
    and long-form (`total_token_usage.input_tokens`) names.
    """
    if not isinstance(usage, dict):
        return (0, 0, 0)
    inp = max(_coerce_int(usage.get(_TOKEN_KEY_INPUT)), 0)
    out = max(_coerce_int(usage.get(_TOKEN_KEY_OUTPUT)), 0)
    total = max(_coerce_int(usage.get(_TOKEN_KEY_TOTAL)), 0)
    if total == 0:
        total = inp + out
    # If the dict has a nested total_token_usage, prefer that for
    # absolute totals.
    nested = usage.get("total_token_usage")
    if isinstance(nested, dict):
        abs_in = max(_coerce_int(nested.get(_TOKEN_KEY_INPUT)), 0)
        abs_out = max(_coerce_int(nested.get(_TOKEN_KEY_OUTPUT)), 0)
        abs_total = max(_coerce_int(nested.get(_TOKEN_KEY_TOTAL)), 0)
        if abs_in or abs_out or abs_total:
            inp, out, total = abs_in or inp, abs_out or out, abs_total or (inp + out)
    return (inp, out, total)


def _coerce_int(value: Any) -> int:  # noqa: ANN401
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return 0


def extract_rate_limit(event_payload: Any) -> dict[str, Any] | None:  # noqa: ANN401
    """Extract a rate-limit payload from a runner event, or None."""
    if not isinstance(event_payload, dict):
        return None
    for k in _RATE_LIMIT_KEYS:
        v = event_payload.get(k)
        if isinstance(v, dict):
            return v
        if isinstance(v, list) and v:
            return {"entries": v}
    return None


def aggregate_token_usage(
    state: OrchestratorState,
) -> dict[str, int]:
    """Sum `input_tokens` / `output_tokens` / `total_tokens` across
    all running + queued-retry sessions.

    Each session's `usage` is a `dict[str, int]`. We sum each key
    independently. Sessions with no usage contribute 0.

    For `total_tokens` specifically, if any session reported it,
    we use the sum of those reports; otherwise we fall back to
    `sum(input_tokens) + sum(output_tokens)`.
    """
    totals: dict[str, int] = {}
    for session in state.running.values():
        for k, v in session.usage.items():
            if isinstance(v, int) and not isinstance(v, bool):
                totals[k] = totals.get(k, 0) + v
    # Retry entries don't carry usage (only issue_id, attempt, error,
    # due_at_ms), so we don't add from `retry_attempts`.
    if _TOKEN_KEY_TOTAL not in totals:
        totals[_TOKEN_KEY_TOTAL] = totals.get(_TOKEN_KEY_INPUT, 0) + totals.get(
            _TOKEN_KEY_OUTPUT, 0
        )
    return totals


def aggregate_runtime_seconds(
    state: OrchestratorState,
    *,
    now: datetime | None = None,
) -> int:
    """Cumulative ended-session runtime + active-session elapsed.

    Returned as an integer number of seconds.
    """
    when = now or datetime.now(UTC)
    ended = int(getattr(state, "runtime_seconds", 0))
    active = 0
    for session in state.running.values():
        elapsed = (when - session.started_at).total_seconds()
        if elapsed > 0:
            active += int(elapsed)
    return ended + active


def _running_rows(state: OrchestratorState) -> list[RunningSnapshotRow]:
    rows: list[RunningSnapshotRow] = []
    for s in state.running.values():
        rows.append(
            RunningSnapshotRow(
                issue_id=s.issue_id,
                identifier=s.identifier,
                session_id=s.session_id,
                started_at=s.started_at,
                attempt=s.attempt,
                turn_count=s.turn_count,
                usage=dict(s.usage),
            )
        )
    return rows


def _retrying_rows(state: OrchestratorState) -> list[RetrySnapshotRow]:
    rows: list[RetrySnapshotRow] = []
    for entry in state.retry_attempts.values():
        rows.append(
            RetrySnapshotRow(
                issue_id=entry.issue_id,
                identifier=entry.identifier,
                attempt=entry.attempt,
                error=entry.error,
                due_at_ms=entry.due_at_ms,
            )
        )
    return rows


def build_snapshot(
    state: OrchestratorState,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a JSON-safe snapshot per SPEC §13.3.

    Returns a dict with the keys: `running`, `retrying`,
    `codex_totals`, `rate_limits`.
    """
    when = now or datetime.now(UTC)
    usage = aggregate_token_usage(state)
    inp = usage.get(_TOKEN_KEY_INPUT, 0)
    out = usage.get(_TOKEN_KEY_OUTPUT, 0)
    total = usage.get(_TOKEN_KEY_TOTAL, inp + out)
    codex_totals = {
        _TOKEN_KEY_INPUT: inp,
        _TOKEN_KEY_OUTPUT: out,
        _TOKEN_KEY_TOTAL: total,
        "seconds_running": aggregate_runtime_seconds(state, now=when),
    }
    return {
        "running": [_row_to_dict(r) for r in _running_rows(state)],
        "retrying": [_retry_to_dict(r) for r in _retrying_rows(state)],
        "codex_totals": codex_totals,
        "rate_limits": _latest_rate_limit(state),
    }


def _row_to_dict(row: RunningSnapshotRow) -> dict[str, Any]:
    return {
        "issue_id": row.issue_id,
        "identifier": row.identifier,
        "session_id": row.session_id,
        "started_at": row.started_at.isoformat(),
        "attempt": row.attempt,
        "turn_count": row.turn_count,
        "usage": dict(row.usage),
    }


def _retry_to_dict(row: RetrySnapshotRow) -> dict[str, Any]:
    return {
        "issue_id": row.issue_id,
        "identifier": row.identifier,
        "attempt": row.attempt,
        "error": row.error,
        "due_at_ms": row.due_at_ms,
    }


def _latest_rate_limit(state: OrchestratorState) -> dict[str, Any] | None:
    """Return the latest rate-limit payload seen, or None.

    `state` is expected to have a `latest_rate_limit` attribute
    (defaulting to None). Sessions may also carry rate-limit
    information; we prefer the orchestrator-level cache.
    """
    return getattr(state, "latest_rate_limit", None)


def record_rate_limit(state: OrchestratorState, payload: dict[str, Any]) -> None:
    """Cache `payload` as the latest rate-limit seen."""
    state.latest_rate_limit = dict(payload)


__all__ = [
    "RetrySnapshotRow",
    "RunningSnapshotRow",
    "aggregate_runtime_seconds",
    "aggregate_token_usage",
    "build_snapshot",
    "extract_rate_limit",
    "extract_token_counts",
    "record_rate_limit",
]
