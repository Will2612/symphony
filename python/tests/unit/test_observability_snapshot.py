"""Unit tests for `symphony.observability.snapshot`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from symphony.observability.snapshot import (
    aggregate_runtime_seconds,
    aggregate_token_usage,
    build_snapshot,
    extract_rate_limit,
    extract_token_counts,
    record_rate_limit,
)
from symphony.orchestrator.state import LiveSession, OrchestratorState, RetryEntry


def _session(
    id: str = "1",
    *,
    started_at: datetime | None = None,
    attempt: int = 1,
    usage: dict[str, int] | None = None,
) -> LiveSession:
    return LiveSession(
        issue_id=id,
        identifier=f"#{id}",
        session_id=f"s-{id}",
        started_at=started_at or datetime(2024, 1, 1, tzinfo=UTC),
        attempt=attempt,
        usage=usage or {},
    )


def _retry(
    id: str = "1",
    *,
    attempt: int = 1,
    error: str = "",
    due_at_ms: int = 0,
) -> RetryEntry:
    return RetryEntry(
        issue_id=id,
        identifier=f"#{id}",
        attempt=attempt,
        error=error,
        due_at_ms=due_at_ms,
    )


# ---------------------------------------------------------------------------
# extract_token_counts
# ---------------------------------------------------------------------------


def test_extract_token_counts_short_form() -> None:
    inp, out, total = extract_token_counts(
        {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
    )
    assert inp == 10
    assert out == 5
    assert total == 15


def test_extract_token_counts_derives_total() -> None:
    inp, out, total = extract_token_counts({"input_tokens": 4, "output_tokens": 6})
    assert inp == 4 and out == 6 and total == 10


def test_extract_token_counts_prefers_nested_total() -> None:
    inp, out, total = extract_token_counts(
        {
            "input_tokens": 1,
            "output_tokens": 2,
            "total_token_usage": {
                "input_tokens": 100,
                "output_tokens": 200,
                "total_tokens": 300,
            },
        }
    )
    assert (inp, out, total) == (100, 200, 300)


def test_extract_token_counts_missing_keys_are_zero() -> None:
    assert extract_token_counts({}) == (0, 0, 0)


def test_extract_token_counts_non_int_skipped() -> None:
    assert extract_token_counts({"input_tokens": "x", "output_tokens": None}) == (0, 0, 0)


def test_extract_token_counts_non_dict() -> None:
    assert extract_token_counts(None) == (0, 0, 0)
    assert extract_token_counts("foo") == (0, 0, 0)


def test_extract_token_counts_negative_clamped() -> None:
    assert extract_token_counts({"input_tokens": -5, "output_tokens": 3}) == (0, 3, 3)


# ---------------------------------------------------------------------------
# extract_rate_limit
# ---------------------------------------------------------------------------


def test_extract_rate_limit_dict() -> None:
    payload = {"codex_rate_limits": {"primary": {"window": 60}}}
    assert extract_rate_limit(payload) == {"primary": {"window": 60}}


def test_extract_rate_limit_list() -> None:
    payload = {"rate_limits": [{"window": 60}]}
    assert extract_rate_limit(payload) == {"entries": [{"window": 60}]}


def test_extract_rate_limit_missing() -> None:
    assert extract_rate_limit({"foo": "bar"}) is None


def test_extract_rate_limit_non_dict() -> None:
    assert extract_rate_limit(None) is None
    assert extract_rate_limit("x") is None


# ---------------------------------------------------------------------------
# aggregate_token_usage
# ---------------------------------------------------------------------------


def test_aggregate_token_usage_sums_sessions() -> None:
    state = OrchestratorState()
    state.running["1"] = _session("1", usage={"input_tokens": 10, "output_tokens": 5})
    state.running["2"] = _session("2", usage={"input_tokens": 20})
    totals = aggregate_token_usage(state)
    # total_tokens derived as 30+5 = 35.
    assert totals == {"input_tokens": 30, "output_tokens": 5, "total_tokens": 35}


def test_aggregate_token_usage_empty() -> None:
    state = OrchestratorState()
    assert aggregate_token_usage(state) == {"total_tokens": 0}


def test_aggregate_token_usage_skips_non_int() -> None:
    state = OrchestratorState()
    state.running["1"] = _session("1", usage={"input_tokens": "x", "output_tokens": 5})
    totals = aggregate_token_usage(state)
    assert totals == {"output_tokens": 5, "total_tokens": 5}


# ---------------------------------------------------------------------------
# aggregate_runtime_seconds
# ---------------------------------------------------------------------------


def test_aggregate_runtime_seconds_includes_active() -> None:
    now = datetime(2024, 1, 1, 1, 0, 0, tzinfo=UTC)
    state = OrchestratorState()
    state.running["1"] = _session("1", started_at=now - timedelta(seconds=30))
    state.running["2"] = _session("2", started_at=now - timedelta(seconds=15))
    secs = aggregate_runtime_seconds(state, now=now)
    assert secs == 45


def test_aggregate_runtime_seconds_includes_ended() -> None:
    now = datetime(2024, 1, 1, 1, 0, 0, tzinfo=UTC)
    state = OrchestratorState(runtime_seconds=120)
    secs = aggregate_runtime_seconds(state, now=now)
    assert secs == 120


def test_aggregate_runtime_seconds_ended_plus_active() -> None:
    now = datetime(2024, 1, 1, 1, 0, 0, tzinfo=UTC)
    state = OrchestratorState(runtime_seconds=60)
    state.running["1"] = _session("1", started_at=now - timedelta(seconds=10))
    secs = aggregate_runtime_seconds(state, now=now)
    assert secs == 70


def test_aggregate_runtime_seconds_now_default() -> None:
    state = OrchestratorState()
    secs = aggregate_runtime_seconds(state)
    assert secs >= 0


# ---------------------------------------------------------------------------
# build_snapshot — full structure
# ---------------------------------------------------------------------------


def test_build_snapshot_running_rows_have_turn_count() -> None:
    now = datetime(2024, 1, 1, 1, 0, 0, tzinfo=UTC)
    state = OrchestratorState()
    s = _session("1", started_at=now - timedelta(seconds=20), usage={"input_tokens": 7})
    s.turn_count = 3
    state.running["1"] = s
    snap = build_snapshot(state, now=now)
    assert len(snap["running"]) == 1
    row = snap["running"][0]
    assert row["issue_id"] == "1"
    assert row["identifier"] == "#1"
    assert row["turn_count"] == 3
    assert row["usage"] == {"input_tokens": 7}


def test_build_snapshot_retrying_rows() -> None:
    state = OrchestratorState()
    state.retry_attempts["1"] = _retry("1", attempt=2, error="boom", due_at_ms=12345)
    snap = build_snapshot(state)
    assert len(snap["retrying"]) == 1
    row = snap["retrying"][0]
    assert row == {
        "issue_id": "1",
        "identifier": "#1",
        "attempt": 2,
        "error": "boom",
        "due_at_ms": 12345,
    }


def test_build_snapshot_codex_totals() -> None:
    now = datetime(2024, 1, 1, 1, 0, 0, tzinfo=UTC)
    state = OrchestratorState(runtime_seconds=100)
    state.running["1"] = _session(
        "1",
        started_at=now - timedelta(seconds=10),
        usage={"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
    )
    state.running["2"] = _session(
        "2", started_at=now - timedelta(seconds=5), usage={"input_tokens": 2}
    )
    snap = build_snapshot(state, now=now)
    totals = snap["codex_totals"]
    assert totals["input_tokens"] == 7
    assert totals["output_tokens"] == 3
    # Session 1 reported total_tokens=8; session 2 didn't, so the
    # sum of per-session totals is 8. (The fallback to inputs+outputs
    # only kicks in when NO session reports total_tokens.)
    assert totals["total_tokens"] == 8
    assert totals["seconds_running"] == 115  # 100 + 10 + 5


def test_build_snapshot_rate_limits_none_by_default() -> None:
    state = OrchestratorState()
    snap = build_snapshot(state)
    assert snap["rate_limits"] is None


def test_build_snapshot_rate_limits_cached() -> None:
    state = OrchestratorState(latest_rate_limit={"primary": {"window": 60}})
    snap = build_snapshot(state)
    assert snap["rate_limits"] == {"primary": {"window": 60}}


def test_build_snapshot_empty() -> None:
    snap = build_snapshot(OrchestratorState())
    assert snap == {
        "running": [],
        "retrying": [],
        "codex_totals": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "seconds_running": 0,
        },
        "rate_limits": None,
    }


# ---------------------------------------------------------------------------
# record_rate_limit
# ---------------------------------------------------------------------------


def test_record_rate_limit_caches_payload() -> None:
    state = OrchestratorState()
    record_rate_limit(state, {"primary": {"limit": 100}})
    assert state.latest_rate_limit == {"primary": {"limit": 100}}
    # A second call replaces the first.
    record_rate_limit(state, {"primary": {"limit": 200}})
    assert state.latest_rate_limit == {"primary": {"limit": 200}}


def test_record_rate_limit_copies_payload() -> None:
    """Mutating the original dict does not affect the cached copy."""
    state = OrchestratorState()
    payload: dict[str, object] = {"primary": {"limit": 100}}
    record_rate_limit(state, payload)
    payload["secondary"] = {"limit": 50}  # type: ignore[assignment]
    assert state.latest_rate_limit == {"primary": {"limit": 100}}
