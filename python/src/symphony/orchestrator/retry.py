"""Retry policy (SPEC §8.4).

Two kinds of retry are scheduled by the orchestrator:

1. **Continuation retry** — after a clean worker exit (no error),
   the orchestrator schedules a short fixed 1000 ms retry so
   the issue can be re-checked for another turn.

2. **Failure retry** — after a worker exit with an error, the
   orchestrator schedules an exponential-backoff retry with
   delay = `min(10_000 * 2^(attempt - 1), agent.max_retry_backoff_ms)`.

The `max_retry_backoff_ms` defaults to 300_000 (5 min) per SPEC
§8.4 and is a power-of-2 cap.
"""

from __future__ import annotations

from symphony.config.schema import SymphonyConfig

_CONTINUATION_DELAY_MS = 1000
_BASE_DELAY_MS = 10_000


def compute_continuation_delay_ms() -> int:
    """Fixed delay for a continuation retry after a clean exit."""
    return _CONTINUATION_DELAY_MS


def compute_failure_delay_ms(*, attempt: int, config: SymphonyConfig) -> int:
    """Exponential-backoff delay for a failure-driven retry.

    `attempt` is 1-indexed (the 1st retry uses base * 2^0).
    """
    attempt = max(attempt, 0)
    base = _BASE_DELAY_MS
    shift = max(attempt - 1, 0)
    # Cap the shift to avoid overflow; the resulting delay is
    # still bounded by `max_retry_backoff_ms` below.
    delay = base * (1 << min(shift, 30))
    cap = max(config.agent.max_retry_backoff_ms, 0)
    return min(delay, cap)


def normalize_max_retry_backoff_ms(value: int) -> int:
    """Clamp a non-negative value; treat negative as 0."""
    return max(value, 0)
