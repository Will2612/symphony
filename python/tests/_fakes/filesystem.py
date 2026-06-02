"""FakeFileSystem — in-memory FS preserving lstat semantics for symlinks.

Step 1 skeleton: a dict-backed path tree. Real lstat / symlink
resolution arrives in the workspace step (plan §11 step 7).
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import PurePosixPath


@dataclass
class _Entry:
    kind: str
    target: str | None = None


@dataclass
class FakeFileSystem:
    """An in-memory POSIX-like filesystem.

    Paths are stored as canonical strings. The `lstat` semantics for
    symlink resolution land when Workspace.path_safety lands.
    """

    _entries: dict[str, _Entry] = field(default_factory=dict)

    def reset(self) -> None:
        self._entries.clear()

    def mkdir(self, path: str | PurePosixPath) -> None:
        key = self._key(path)
        if key in self._entries and self._entries[key].kind == "dir":
            return
        self._entries[key] = _Entry(kind="dir")

    def write(self, path: str | PurePosixPath, content: str) -> None:
        key = self._key(path)
        parent = self._key(PurePosixPath(key).parent)
        if parent and parent not in self._entries:
            self._entries[parent] = _Entry(kind="dir")
        self._entries[key] = _Entry(kind="file")

    def symlink(self, link: str | PurePosixPath, target: str) -> None:
        self._entries[self._key(link)] = _Entry(kind="symlink", target=target)

    def exists(self, path: str | PurePosixPath) -> bool:
        return self._key(path) in self._entries

    def is_dir(self, path: str | PurePosixPath) -> bool:
        entry = self._entries.get(self._key(path))
        return entry is not None and entry.kind == "dir"

    def is_file(self, path: str | PurePosixPath) -> bool:
        entry = self._entries.get(self._key(path))
        return entry is not None and entry.kind == "file"

    def lstat(self, path: str | PurePosixPath) -> _Entry:
        key = self._key(path)
        if key not in self._entries:
            raise FileNotFoundError(key)
        return self._entries[key]

    def walk(self) -> Iterator[str]:
        return iter(sorted(self._entries))

    @staticmethod
    def _key(path: str | PurePosixPath) -> str:
        if isinstance(path, PurePosixPath):
            return str(path)
        return str(PurePosixPath(path))
