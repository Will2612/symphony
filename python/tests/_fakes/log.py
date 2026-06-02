"""CapturingLogHandler — a `logging.Handler` that records emitted records.

Step 1 skeleton: stores every `LogRecord` it sees. Whitelisted
field handling and the kv formatter land in the observability
work-plan step (plan §11 step 18).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator


class CapturingLogHandler(logging.Handler):
    """A logging handler that captures every emitted LogRecord."""

    def __init__(self, level: int = logging.DEBUG) -> None:
        super().__init__(level=level)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def by_level(self, level: int) -> list[logging.LogRecord]:
        return [r for r in self.records if r.levelno == level]

    def __iter__(self) -> Iterator[logging.LogRecord]:
        return iter(self.records)
