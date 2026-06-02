"""Workspace path-safety primitives.

Mirrors the Elixir `SymphonyElixir.PathSafety` module. Two
public functions:

- `canonicalize(path)`: lstat-based symlink resolver. Returns an
  absolute, fully-resolved path. Missing leaf segments are kept
  verbatim (the function stops resolving at the first non-existent
  component and returns the rest as-is). Permission errors and
  other `OSError` subclasses bubble up.

- `is_within(child, root)`: returns True iff `child` is `root` or
  a subdirectory of `root`. Both paths are canonicalized first,
  so the comparison is robust to symlinks.

This module implements SPEC §9.5 invariants 1-2. Invariant 3
(workspace-key sanitization) lives in `symphony.ids.workspace_key`.
"""

from __future__ import annotations

import os

PathLike = os.PathLike[str] | str


def canonicalize(path: PathLike) -> str:
    """Return the canonicalized absolute path, following symlinks.

    Algorithm (mirrors the Elixir reference):
    1. Expand `~` and resolve `.` / `..` via `os.path.abspath`.
    2. Walk each segment of the path. For each, do `os.lstat`:
       - If the segment is a symlink, read its target with
         `os.readlink`, expand it relative to the resolved prefix,
         and recurse on the (now possibly absolute) target plus the
         remaining segments.
       - If the segment does not exist (ENOENT), return the
         resolved prefix + the remaining segments verbatim.
       - If the segment exists and is not a symlink, append it to
         the resolved prefix and continue.
    """
    expanded = os.path.abspath(os.path.expanduser(os.fspath(path)))
    if not expanded.startswith("/"):
        # On non-POSIX this would differ; we only target POSIX for v1.
        raise OSError(  # pragma: no cover - POSIX-only guard
            f"canonicalize requires an absolute path; got {expanded!r}"
        )
    if expanded == "/":
        return "/"
    # Split into ["tmp", "foo", "bar"] for "/tmp/foo/bar".
    # Skip the leading empty string from the first "/".
    raw_segments = [s for s in expanded.split("/") if s != ""]
    return _resolve("/" + raw_segments[0], raw_segments[1:])


def _resolve(prefix: str, segments: list[str]) -> str:
    """Recursively resolve `segments` under `prefix`."""
    if not segments:
        return prefix
    head, *rest = segments
    candidate = os.path.join(prefix, head)
    try:
        st = os.lstat(candidate)
    except FileNotFoundError:
        # Missing component: stop resolving; return the prefix +
        # the remaining segments verbatim.
        return os.path.join(candidate, *rest) if rest else candidate
    if _is_symlink(st):
        # Symlink: read target, expand relative to current dir, recurse.
        target = os.readlink(candidate)
        if os.path.isabs(target):
            expanded = os.path.abspath(target)
        else:
            expanded = os.path.abspath(os.path.join(prefix, target))
        # Build a fresh segments list from the expanded path.
        if expanded.startswith("/"):
            new_segs = [s for s in expanded.split("/") if s != ""]
        else:  # pragma: no cover - we always pass abs paths
            new_segs = [s for s in expanded.split("/") if s != ""]
        new_prefix = "/" + new_segs[0] if new_segs else "/"
        return _resolve(new_prefix, new_segs[1:] + list(rest))
    # Regular entry: recurse with the new prefix.
    return _resolve(candidate, list(rest))


def _is_symlink(st: os.stat_result) -> bool:
    """Return True if the lstat result indicates a symlink."""
    return bool(st and (st.st_mode & 0o170000) == 0o120000)


def is_within(child: PathLike, root: PathLike) -> bool:
    """Return True iff `child` is `root` or a subdirectory of `root`.

    Both paths are canonicalized first, so symlink trickery cannot
    escape the boundary. The comparison uses a path-separator
    sentinel to avoid partial-name collisions (e.g. `/tmp/ab` is
    NOT inside `/tmp/abc`).
    """
    child_canon = canonicalize(child)
    root_canon = canonicalize(root)
    if child_canon == root_canon:
        return True
    prefix = root_canon.rstrip("/") + "/"
    return child_canon.startswith(prefix)


__all__ = ["PathLike", "canonicalize", "is_within"]
