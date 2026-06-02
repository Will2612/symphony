"""FakeWorkflowStore — synchronous stand-in for `symphony.workflow.store`.

Step 1 skeleton: holds a current `Workflow` value and supports
`force_reload`. The hot-reload logic via `watchfiles.awatch` lands
in the workflow work-plan step (plan §11 step 6).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeWorkflowStore:
    """In-memory workflow store for tests."""

    current: Any = None
    force_reload_count: int = 0
    _subscribers: list[Callable[[Any], None]] = field(default_factory=list)

    def set(self, workflow: Any) -> None:
        self.current = workflow
        for sub in self._subscribers:
            sub(workflow)

    def force_reload(self) -> None:
        self.force_reload_count += 1

    def subscribe(self, callback: Callable[[Any], None]) -> None:
        self._subscribers.append(callback)
