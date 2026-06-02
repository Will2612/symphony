"""NullObserver — a no-op observer used to disable the HTTP server in tests.

Step 1 skeleton: every method returns `None`. The full Observer
Protocol (start, stop, current_snapshot) lands in the observability
work-plan step (plan §11 step 19).
"""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class NullObserver:
    """An observer that records nothing and exposes nothing."""

    name: str = "null"

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def on_snapshot(self, callback: Callable[[object], None]) -> None:
        return None
