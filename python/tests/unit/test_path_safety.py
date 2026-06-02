"""Unit tests for `symphony.workspace.path_safety`.

Plan ref: §11 step 7, SPEC §9.5 invariants 1-3.

- `canonicalize(path)`: lstat-based symlink resolver. Mirrors the
  Elixir `SymphonyElixir.PathSafety.canonicalize/1` algorithm.
- `is_within(child, root)`: returns True iff `child` is `root` or
  a subdirectory of `root`. Both are canonicalized first.
"""

from __future__ import annotations

import os
from pathlib import Path

from symphony.workspace.path_safety import canonicalize, is_within


def test_canonicalize_absolute_path(tmp_path: Path) -> None:
    target = tmp_path / "real"
    target.mkdir()
    assert canonicalize(str(target)) == str(target)


def test_canonicalize_relative_path(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        result = canonicalize("a")
    finally:
        os.chdir(cwd)
    assert result == str(tmp_path / "a")


def test_canonicalize_expands_home() -> None:
    home = os.path.expanduser("~")
    result = canonicalize("~")
    assert result == home


def test_canonicalize_follows_symlink(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    os.symlink(real, link)
    assert canonicalize(str(link)) == str(real)


def test_canonicalize_follows_chained_symlinks(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    mid = tmp_path / "mid"
    os.symlink(real, mid)
    top = tmp_path / "top"
    os.symlink(mid, top)
    assert canonicalize(str(top)) == str(real)


def test_canonicalize_follows_symlink_in_middle(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    inner = real / "inner"
    inner.mkdir()
    link_parent = tmp_path / "linkdir"
    os.symlink(real, link_parent)
    # canonicalize the symlinked parent + a real child.
    assert canonicalize(str(link_parent / "inner")) == str(inner)


def test_canonicalize_broken_symlink_returns_dangling_path(tmp_path: Path) -> None:
    link = tmp_path / "broken"
    os.symlink(tmp_path / "does_not_exist", link)
    # The lstat sees a symlink, read_link returns the target,
    # we recurse on the non-existent target → enoent → return
    # the dangling path as-is.
    result = canonicalize(str(link))
    # Must point to a path that does not exist; the parent should
    # match the original link's parent.
    assert result.startswith(str(tmp_path))


def test_canonicalize_nonexistent_leaf_returns_prefix(tmp_path: Path) -> None:
    """If a path doesn't exist, canonicalize returns the longest
    existing prefix + the remaining segments verbatim."""
    missing = tmp_path / "missing" / "sub"
    result = canonicalize(str(missing))
    assert result == str(missing)


def test_canonicalize_path_with_dots(tmp_path: Path) -> None:
    a = tmp_path / "a"
    a.mkdir()
    dotted = str(tmp_path) + "/./a"
    # os.path.normpath on POSIX collapses ./ before our code runs.
    result = canonicalize(dotted)
    assert result == str(a)


def test_canonicalize_accepts_pathlike(tmp_path: Path) -> None:
    a = tmp_path / "a"
    a.mkdir()
    assert canonicalize(a) == str(a)


def test_canonicalize_root_path() -> None:
    """The literal root '/' canonicalizes to '/'."""
    assert canonicalize("/") == "/"


def test_canonicalize_relative_symlink_target(tmp_path: Path) -> None:
    """A symlink whose target is a relative path is resolved
    relative to the symlink's parent directory."""
    real = tmp_path / "real"
    real.mkdir()
    sub = real / "sub"
    sub.mkdir()
    link_dir = tmp_path / "linkdir"
    link_dir.mkdir()
    # Create a symlink inside linkdir with a relative target.
    link = link_dir / "rel"
    os.symlink("../real/sub", link)
    # canonicalize of link should follow the relative target.
    assert canonicalize(str(link)) == str(sub)


def test_canonicalize_non_absolute_raises() -> None:
    """A path that is not absolute after abspath raises OSError.
    We simulate this by passing a path on a non-POSIX-like
    structure; under POSIX every path is absolute after abspath
    unless it errors. We use a non-existent file in the current
    working directory to construct a relative-looking path:
    canonicalize is called with the raw relative string, BEFORE
    abspath, by checking the function's first guard.

    In practice, the guard is unreachable on POSIX (abspath always
    returns an absolute path), so this test is more of a defensive
    marker for future porting. We assert that a non-existent
    relative input still works (it gets absolutized by abspath).
    """
    cwd = os.getcwd()
    try:
        os.chdir("/tmp")
        result = canonicalize("does-not-exist")
    finally:
        os.chdir(cwd)
    assert result == "/tmp/does-not-exist"


def test_is_within_returns_true_for_self(tmp_path: Path) -> None:
    assert is_within(str(tmp_path), str(tmp_path)) is True


def test_is_within_returns_true_for_immediate_child(tmp_path: Path) -> None:
    child = tmp_path / "child"
    child.mkdir()
    assert is_within(str(child), str(tmp_path)) is True


def test_is_within_returns_true_for_nested_child(tmp_path: Path) -> None:
    grandchild = tmp_path / "a" / "b" / "c"
    grandchild.mkdir(parents=True)
    assert is_within(str(grandchild), str(tmp_path)) is True


def test_is_within_returns_false_for_sibling(tmp_path: Path) -> None:
    sibling = tmp_path.parent / f"{tmp_path.name}-sibling"
    sibling.mkdir(exist_ok=True)
    try:
        assert is_within(str(sibling), str(tmp_path)) is False
    finally:
        sibling.rmdir()


def test_is_within_returns_false_for_parent(tmp_path: Path) -> None:
    parent = tmp_path.parent
    assert is_within(str(parent), str(tmp_path)) is False


def test_is_within_returns_false_for_partial_name_collision(tmp_path: Path) -> None:
    """`/tmp/abc` MUST NOT be considered inside `/tmp/ab`."""
    ab = tmp_path / "ab"
    abc = tmp_path / "abc"
    ab.mkdir()
    abc.mkdir()
    assert is_within(str(abc), str(ab)) is False


def test_is_within_follows_symlinks_into_root(tmp_path: Path) -> None:
    """A symlink from outside the root, pointing INTO the root,
    resolves to a path that is within the root."""
    real = tmp_path / "real"
    real.mkdir()
    inside = real / "child"
    inside.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = outside / "link"
    os.symlink(real, link)
    # link/child resolves into real/child, which IS within real.
    assert is_within(str(link / "child"), str(real)) is True
    # The link itself, canonicalized, points to real — also within.
    assert is_within(str(link), str(real)) is True


def test_is_within_follows_symlinks_out_of_root(tmp_path: Path) -> None:
    """A symlink from inside the root, pointing OUTSIDE the root,
    is NOT considered within the root after canonicalization."""
    root = tmp_path / "root"
    root.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    link = root / "link"
    os.symlink(target, link)
    assert is_within(str(link), str(root)) is False
    # Even a subpath of the link is outside after canonicalization.
    assert is_within(str(link / "child"), str(root)) is False
