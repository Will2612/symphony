"""FakeClock — controllable monotonic clock for tests.

Step 1 skeleton: provides a stable `now()` and `advance()` interface.
Scheduling, monotonicity guarantees, and asyncio integration land in
the orchestrator step (plan §11 step 17).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


@dataclass
class FakeClock:
    """A clock whose `now()` is under test control.

    Time is stored as a `datetime` (UTC, tz-aware) so equality and
    arithmetic are well-defined. `advance(ms)` moves the clock forward
    by the given number of milliseconds without sleeping.
    """

    _now: datetime = field(default_factory=lambda: datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC))
    _pending: list[tuple[datetime, Callable[[], None]]] = field(default_factory=list)

    def now(self) -> datetime:
        return self._now

    def advance(self, ms: int) -> None:
        if ms < 0:
            raise ValueError("FakeClock.advance only accepts non-negative ms")
        self._now = self._now + timedelta(milliseconds=ms)
        self._fire_due()

    def schedule(self, callback: Callable[[], None], at: datetime) -> None:
        self._pending.append((at, callback))

    def _fire_due(self) -> None:
        still_pending: list[tuple[datetime, Callable[[], None]]] = []
        for at, callback in self._pending:
            if at <= self._now:
                callback()
            else:
                still_pending.append((at, callback))
        self._pending = still_pending
