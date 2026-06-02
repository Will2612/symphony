"""Unit tests for `symphony.orchestrator.retry`.

Plan ref: §11 step 16, SPEC §8.4 (retry backoff formula).

Retry semantics:
- Normal continuation retries after a clean worker exit use a
  fixed 1000 ms delay.
- Failure-driven retries use
  `delay = min(10000 * 2^(attempt - 1), agent.max_retry_backoff_ms)`.
- Power is capped by `agent.max_retry_backoff_ms` (default
  `300_000` / 5 min).
"""

from __future__ import annotations

from symphony.config.schema import SymphonyConfig
from symphony.orchestrator.retry import (
    compute_continuation_delay_ms,
    compute_failure_delay_ms,
    normalize_max_retry_backoff_ms,
)


def _config(**overrides: object) -> SymphonyConfig:
    base = {
        "agent": {
            "max_retry_backoff_ms": 300_000,
        }
    }
    for k, v in overrides.items():
        if isinstance(v, dict) and k in base:
            base[k].update(v)  # type: ignore[union-attr]
        else:
            base[k] = v
    return SymphonyConfig.model_validate(base)


# ---------------------------------------------------------------------------
# compute_continuation_delay_ms
# ---------------------------------------------------------------------------


def test_continuation_delay_is_1000ms() -> None:
    assert compute_continuation_delay_ms() == 1000


# ---------------------------------------------------------------------------
# compute_failure_delay_ms
# ---------------------------------------------------------------------------


def test_failure_delay_attempt_1() -> None:
    cfg = _config()
    # 10000 * 2^0 = 10_000
    assert compute_failure_delay_ms(attempt=1, config=cfg) == 10_000


def test_failure_delay_attempt_2() -> None:
    cfg = _config()
    # 10000 * 2^1 = 20_000
    assert compute_failure_delay_ms(attempt=2, config=cfg) == 20_000


def test_failure_delay_attempt_3() -> None:
    cfg = _config()
    # 10000 * 2^2 = 40_000
    assert compute_failure_delay_ms(attempt=3, config=cfg) == 40_000


def test_failure_delay_capped_by_max_backoff() -> None:
    cfg = _config(agent={"max_retry_backoff_ms": 50_000})
    # attempt 3 would be 40_000 (under cap)
    assert compute_failure_delay_ms(attempt=3, config=cfg) == 40_000
    # attempt 4 would be 80_000 (over cap)
    assert compute_failure_delay_ms(attempt=4, config=cfg) == 50_000


def test_failure_delay_attempt_zero_is_base() -> None:
    """attempt 0 is not a real attempt; we floor the exponent at
    0 and return the base delay 10_000 ms. Callers should pass
    attempt >= 1; this is documented as defensive behavior."""
    cfg = _config()
    assert compute_failure_delay_ms(attempt=0, config=cfg) == 10_000


def test_failure_delay_huge_attempt_capped() -> None:
    cfg = _config()
    # 10000 * 2^30 is astronomical; should be capped at 300_000
    assert compute_failure_delay_ms(attempt=30, config=cfg) == 300_000


def test_failure_delay_zero_max_backoff_clamps_to_zero() -> None:
    """If max_retry_backoff_ms is 0, the delay is 0."""
    cfg = _config(agent={"max_retry_backoff_ms": 0})
    assert compute_failure_delay_ms(attempt=1, config=cfg) == 0


# ---------------------------------------------------------------------------
# normalize_max_retry_backoff_ms
# ---------------------------------------------------------------------------


def test_normalize_zero_clamps_to_zero() -> None:
    assert normalize_max_retry_backoff_ms(0) == 0


def test_normalize_negative_clamps_to_zero() -> None:
    """Negative values are treated as 0 (defensive)."""
    assert normalize_max_retry_backoff_ms(-100) == 0


def test_normalize_positive_unchanged() -> None:
    assert normalize_max_retry_backoff_ms(60_000) == 60_000
