"""Hot-reload cache for a `Workflow` source.

The store holds the current effective `Workflow` and watches the
source path for changes via `watchfiles.awatch`. Per SPEC §6.2:

- Invalid reloads MUST NOT crash; the last-known-good effective
  workflow is kept.
- The store SHOULD re-validate defensively before each dispatch
  (the orchestrator calls `reload()` per dispatch tick).

The store is async because the watcher is an async task. The
loader itself is sync (file I/O is fast and avoids event-loop
contention).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from pathlib import Path

from watchfiles import awatch

from symphony.errors import SymphonyError, WorkflowMissingFile
from symphony.workflow.loader import Workflow, load

_LOGGER = logging.getLogger(__name__)

Loader = Callable[[Path], Workflow]


class WorkflowStore:
    """Async workflow cache with file watcher."""

    def __init__(
        self,
        source: Path,
        *,
        loader: Loader | None = None,
        watch_step: int = 10,
    ) -> None:
        self._source = source
        self._loader: Loader = loader or (lambda p: load(str(p)))
        self._watch_step = watch_step
        self._current: Workflow | None = None
        self._last_error: SymphonyError | None = None
        self._task: asyncio.Task[None] | None = None

    @property
    def last_error(self) -> SymphonyError | None:
        return self._last_error

    @property
    def source(self) -> Path:
        return self._source

    def set_loaded(self, workflow: Workflow) -> None:
        """Inject a pre-loaded workflow (e.g. from the orchestrator's
        startup sequence). Does not start the watcher."""
        self._current = workflow
        self._last_error = None

    async def start(self) -> None:
        """Load the initial workflow and spawn the watcher task.

        Safe to call multiple times; only the first call has effect.
        """
        if self._task is not None:
            return
        self._try_reload()
        self._task = asyncio.create_task(self._watch(), name=f"workflow-store:{self._source}")

    async def stop(self) -> None:
        """Cancel the watcher task. Idempotent."""
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def reload(self) -> None:
        """Synchronously attempt a reload; update `current` on success
        and `last_error` on failure. The orchestrator calls this on
        every dispatch tick as a defensive revalidation."""
        self._try_reload()

    async def get(self) -> Workflow:
        """Return the current effective workflow.

        Raises:
            RuntimeError: if the store has not been started (or no
                workflow has been injected) and the initial load
                failed.
        """
        if self._current is None:
            raise RuntimeError(
                f"WorkflowStore for {self._source} has no current workflow"
                + (f" (last error: {self._last_error!r})" if self._last_error else "")
            )
        return self._current

    def _try_reload(self) -> None:
        try:
            new_wf = self._loader(self._source)
        except SymphonyError as e:
            self._last_error = e
            _LOGGER.warning(
                "workflow reload failed; keeping last-known-good",
                extra={"source": str(self._source), "error": str(e)},
            )
            return
        except OSError as e:
            self._last_error = WorkflowMissingFile(
                f"cannot read workflow source {self._source}: {e}",
                code="workflow_missing_file",
            )
            _LOGGER.warning(
                "workflow reload OS error; keeping last-known-good",
                extra={"source": str(self._source), "error": str(e)},
            )
            return
        self._current = new_wf
        self._last_error = None

    async def _watch(self) -> None:
        try:
            async for _changes in awatch(str(self._source), step=self._watch_step):
                self._try_reload()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            _LOGGER.exception(
                "watcher crashed",
                extra={"source": str(self._source), "error": str(exc)},
            )


__all__ = ["Loader", "WorkflowStore"]
