"""Workspace manager.

Creates and reuses per-issue workspaces under `workspace.root` per
SPEC §9.1-§9.5. The manager owns:

- Workspace path computation and safety validation (invariant 2).
- Directory creation, reuse, and removal.
- Lifecycle hooks (after_create, before_run, after_run, before_remove).

This module depends on:
- `symphony.config.schema.SymphonyConfig` for paths and hook commands.
- `symphony.ids.workspace_key` for invariant 3 (sanitized key).
- `symphony.workspace.path_safety` for invariant 2 (path is within root).
- `symphony.workspace.hooks` for hook execution.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass

from symphony.config.schema import SymphonyConfig
from symphony.errors import WorkspaceOutsideRoot
from symphony.ids import workspace_key
from symphony.workspace.hooks import (
    HookResult,
    HookRunner,
    SubprocessHookRunner,
    invoke_hook,
)
from symphony.workspace.path_safety import canonicalize, is_within

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Workspace:
    """A created or reused per-issue workspace directory."""

    path: str
    key: str
    created_now: bool

    def __post_init__(self) -> None:
        # Defensive: a workspace path must always be absolute.
        if not self.path.startswith("/"):
            raise ValueError(f"workspace path must be absolute; got {self.path!r}")


class WorkspaceManager:
    """Creates, reuses, and removes per-issue workspaces."""

    def __init__(
        self,
        config: SymphonyConfig,
        *,
        hook_runner: HookRunner | None = None,
    ) -> None:
        self._config = config
        self._hook_runner: HookRunner = hook_runner or SubprocessHookRunner()
        self._root = canonicalize(config.workspace.root)
        if self._root == "/":
            raise ValueError("workspace.root cannot be '/'")

    @property
    def root(self) -> str:
        return self._root

    async def create_for_issue(
        self,
        identifier: str,
        *,
        issue_id: str | None = None,
    ) -> Workspace:
        """Create (or reuse) the workspace for the given issue identifier.

        Raises:
            WorkspaceOutsideRoot: if the computed path is not within the
                configured workspace root.
            HookFailed / HookTimeout: if the after_create hook is
                configured and fails.
        """
        key = workspace_key(identifier)
        candidate = os.path.join(self._root, key)
        workspace_path = canonicalize(candidate)
        if not is_within(workspace_path, self._root):
            raise WorkspaceOutsideRoot(  # pragma: no cover - defensive
                f"computed workspace {workspace_path!r} is outside root {self._root!r}",
                workspace=workspace_path,
                root=self._root,
            )
        # ensure directory
        if os.path.isdir(workspace_path):
            created_now = False
        else:
            # If a non-directory file exists at this path, remove it.
            if os.path.lexists(workspace_path):
                if os.path.islink(workspace_path) or os.path.isfile(workspace_path):
                    os.unlink(workspace_path)
                else:
                    shutil.rmtree(workspace_path)  # pragma: no cover - defensive
            os.makedirs(workspace_path, exist_ok=False)
            created_now = True
        workspace = Workspace(path=workspace_path, key=key, created_now=created_now)
        # Run after_create hook if this is a brand-new workspace.
        if created_now:
            command = self._config.hooks.after_create
            if command:
                await invoke_hook(
                    self._hook_runner,
                    hook_name="after_create",
                    command=command,
                    workspace=workspace_path,
                    timeout_ms=self._config.hooks.timeout_ms,
                    fatal=True,
                )
        return workspace

    async def remove(self, workspace: Workspace) -> None:
        """Remove a workspace directory. Failures of the before_remove
        hook are logged and ignored (per SPEC §9.4)."""
        if not os.path.isdir(workspace.path):
            return
        command = self._config.hooks.before_remove
        if command:
            await invoke_hook(
                self._hook_runner,
                hook_name="before_remove",
                command=command,
                workspace=workspace.path,
                timeout_ms=self._config.hooks.timeout_ms,
                fatal=False,
            )
        shutil.rmtree(workspace.path, ignore_errors=True)

    async def run_before_run_hook(
        self,
        workspace: Workspace,
        identifier: str,
        *,
        issue_id: str | None = None,
    ) -> HookResult:
        """Run the before_run hook (fatal on failure/timeout per §9.4)."""
        command = self._config.hooks.before_run
        if not command:
            return HookResult(status=0, output="")
        return await invoke_hook(
            self._hook_runner,
            hook_name="before_run",
            command=command,
            workspace=workspace.path,
            timeout_ms=self._config.hooks.timeout_ms,
            fatal=True,
        )

    async def run_after_run_hook(
        self,
        workspace: Workspace,
        identifier: str,
        *,
        issue_id: str | None = None,
    ) -> HookResult:
        """Run the after_run hook (logged and ignored on failure/timeout)."""
        command = self._config.hooks.after_run
        if not command:
            return HookResult(status=0, output="")
        return await invoke_hook(
            self._hook_runner,
            hook_name="after_run",
            command=command,
            workspace=workspace.path,
            timeout_ms=self._config.hooks.timeout_ms,
            fatal=False,
        )


def make_workspace_key(identifier: str) -> str:
    """Module-level alias for `symphony.ids.workspace_key`. Re-exported
    so callers don't need to import both `ids` and `workspace`."""
    return workspace_key(identifier)


__all__ = [
    "Workspace",
    "WorkspaceManager",
    "make_workspace_key",
]
