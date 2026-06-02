"""Unit tests for `symphony.workflow.store`.

Plan ref: §11 step 6. The store holds the current effective
`Workflow` and reacts to file changes via `watchfiles.awatch`.
Invalid reloads MUST NOT crash; last-known-good is kept.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from symphony.errors import WorkflowParseError
from symphony.workflow.loader import FRONT_MATTER_DELIMITER, Workflow, load
from symphony.workflow.store import WorkflowStore


async def test_start_loads_initial_workflow(tmp_path: Path) -> None:
    wf_path = tmp_path / "WORKFLOW.md"
    wf_path.write_text(
        FRONT_MATTER_DELIMITER + "\n" + 'key: "value"\n' + FRONT_MATTER_DELIMITER + "\nbody\n"
    )
    store = WorkflowStore(wf_path)
    await store.start()
    try:
        wf = await store.get()
        assert isinstance(wf, Workflow)
        assert wf.front_matter == {"key": "value"}
        assert wf.body.strip() == "body"
    finally:
        await store.stop()


async def test_get_before_start_raises(tmp_path: Path) -> None:
    wf_path = tmp_path / "WORKFLOW.md"
    wf_path.write_text("body\n")
    store = WorkflowStore(wf_path)
    with pytest.raises(RuntimeError):
        await store.get()


async def test_reload_picks_up_changes(tmp_path: Path) -> None:
    wf_path = tmp_path / "WORKFLOW.md"
    wf_path.write_text(
        FRONT_MATTER_DELIMITER + "\n" + 'key: "v1"\n' + FRONT_MATTER_DELIMITER + "\nbody1\n"
    )
    store = WorkflowStore(wf_path)
    await store.start()
    try:
        wf = await store.get()
        assert wf.front_matter == {"key": "v1"}
        wf_path.write_text(
            FRONT_MATTER_DELIMITER + "\n" + 'key: "v2"\n' + FRONT_MATTER_DELIMITER + "\nbody2\n"
        )
        await store.reload()
        wf = await store.get()
        assert wf.front_matter == {"key": "v2"}
        assert wf.body.strip() == "body2"
    finally:
        await store.stop()


async def test_invalid_reload_keeps_last_known_good(tmp_path: Path) -> None:
    wf_path = tmp_path / "WORKFLOW.md"
    wf_path.write_text(
        FRONT_MATTER_DELIMITER + "\n" + 'key: "good"\n' + FRONT_MATTER_DELIMITER + "\nbody\n"
    )
    store = WorkflowStore(wf_path)
    await store.start()
    try:
        good = await store.get()
        assert good.front_matter == {"key": "good"}
        # Write content that has a front-matter delimiter but bad YAML
        # inside the front matter — that triggers WorkflowParseError.
        wf_path.write_text(
            FRONT_MATTER_DELIMITER + "\nnot: valid: yaml: [\n" + FRONT_MATTER_DELIMITER + "\n"
        )
        await store.reload()
        # Last-known-good is preserved.
        still_good = await store.get()
        assert still_good is good
        assert isinstance(store.last_error, WorkflowParseError)
    finally:
        await store.stop()


async def test_file_deletion_keeps_last_known_good(tmp_path: Path) -> None:
    wf_path = tmp_path / "WORKFLOW.md"
    wf_path.write_text("body\n")
    store = WorkflowStore(wf_path)
    await store.start()
    try:
        good = await store.get()
        wf_path.unlink()
        await store.reload()
        still_good = await store.get()
        assert still_good is good
        assert store.last_error is not None
    finally:
        await store.stop()


async def test_stop_is_idempotent(tmp_path: Path) -> None:
    wf_path = tmp_path / "WORKFLOW.md"
    wf_path.write_text("body\n")
    store = WorkflowStore(wf_path)
    await store.start()
    await store.stop()
    # Second stop should not raise.
    await store.stop()


async def test_set_loaded_allows_get_without_start(tmp_path: Path) -> None:
    """If the caller pre-loads the workflow (e.g. the orchestrator's
    startup sequence), `get()` can return it without starting the
    watcher. This is a non-spawn mode for tests and one-shot scripts."""
    wf_path = tmp_path / "WORKFLOW.md"
    wf_path.write_text("body\n")
    store = WorkflowStore(wf_path)
    store.set_loaded(load(str(wf_path)))
    wf = await store.get()
    assert wf.body.strip() == "body"


async def test_watch_task_observes_file_change(tmp_path: Path) -> None:
    """Integration test: write a new workflow, wait for the watcher
    to pick up the change, then assert the new workflow is current."""
    wf_path = tmp_path / "WORKFLOW.md"
    wf_path.write_text(
        FRONT_MATTER_DELIMITER + "\n" + 'key: "v1"\n' + FRONT_MATTER_DELIMITER + "\nbody1\n"
    )
    store = WorkflowStore(wf_path)
    await store.start()
    try:
        # Initial load is synchronous inside start(); get() returns v1.
        wf = await store.get()
        assert wf.front_matter.get("key") == "v1"

        # Give the watcher time to set up its inotify watch
        # (the watchfiles library can take a moment to register).
        await asyncio.sleep(0.5)

        # Write new content; watcher should pick it up.
        wf_path.write_text(
            FRONT_MATTER_DELIMITER + "\n" + 'key: "v2"\n' + FRONT_MATTER_DELIMITER + "\nbody2\n"
        )
        # Poll up to 5 seconds for the watcher to pick up the change.
        for _ in range(100):
            wf = await store.get()
            if wf.front_matter.get("key") == "v2":
                break
            await asyncio.sleep(0.05)
        assert wf.front_matter.get("key") == "v2", "watcher did not pick up file change"
        assert wf.body.strip() == "body2"
    finally:
        await store.stop()


async def test_custom_loader_is_used(tmp_path: Path) -> None:
    """If the caller provides a custom loader (e.g. for testing
    or in-memory workflows), it is used instead of the default."""
    wf_path = tmp_path / "WORKFLOW.md"
    wf_path.write_text("body\n")

    sentinel = Workflow(front_matter={"sentinel": True}, body="custom", raw="", source="<test>")
    calls: list[Path] = []

    def custom_loader(p: Path) -> Workflow:
        calls.append(p)
        return sentinel

    store = WorkflowStore(wf_path, loader=custom_loader)
    await store.start()
    try:
        wf = await store.get()
        assert wf is sentinel
        assert calls == [wf_path]
    finally:
        await store.stop()


async def test_get_returns_same_object_until_reload(tmp_path: Path) -> None:
    wf_path = tmp_path / "WORKFLOW.md"
    wf_path.write_text("body\n")
    store = WorkflowStore(wf_path)
    await store.start()
    try:
        a = await store.get()
        b = await store.get()
        assert a is b
    finally:
        await store.stop()


async def test_source_property_returns_the_configured_path(tmp_path: Path) -> None:
    wf_path = tmp_path / "WORKFLOW.md"
    store = WorkflowStore(wf_path)
    assert store.source == wf_path


async def test_start_is_idempotent(tmp_path: Path) -> None:
    wf_path = tmp_path / "WORKFLOW.md"
    wf_path.write_text("body\n")
    store = WorkflowStore(wf_path)
    await store.start()
    first_task = store._task
    await store.start()
    second_task = store._task
    try:
        assert first_task is second_task, "start() must not respawn the watcher"
    finally:
        await store.stop()


async def test_loader_os_error_records_missing_file(tmp_path: Path) -> None:
    """If the loader raises OSError (e.g. file deleted mid-flight),
    the store records a WorkflowMissingFile on `last_error` and keeps
    the last-known-good workflow."""
    wf_path = tmp_path / "WORKFLOW.md"
    wf_path.write_text("body\n")
    store = WorkflowStore(wf_path)
    await store.start()
    try:
        good = await store.get()
        wf_path.unlink()

        # The default loader raises WorkflowMissingFile (SymphonyError)
        # on missing files. Force a generic OSError via a custom loader
        # to exercise the OSError branch.
        def oserror_loader(p: Path) -> Workflow:
            raise FileNotFoundError(p)

        store._loader = oserror_loader  # type: ignore[assignment]
        await store.reload()
        assert isinstance(store.last_error, WorkflowParseError) or (
            store.last_error and "cannot read workflow source" in str(store.last_error)
        )
        # Last-known-good preserved.
        assert await store.get() is good
    finally:
        await store.stop()
