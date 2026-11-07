"""``GlibcMemoryReleaser``: ``MemoryReleaser`` over glibc's ``malloc_trim``, which gives back the
free memory its arenas keep."""

import ctypes
from typing import Protocol

from p2pwatch.application.ports.driven.memory_releaser import MemoryReleaser


class _MallocTrim(Protocol):
    def __call__(self, _pad: ctypes.c_size_t, /) -> int: ...


class GlibcMemoryReleaser(MemoryReleaser):
    """Releases nothing where the C library has no ``malloc_trim`` (musl, macOS)."""

    def __init__(self, c_library: ctypes.CDLL) -> None:
        self._malloc_trim: _MallocTrim | None
        try:
            self._malloc_trim = c_library["malloc_trim"]
        except AttributeError:
            self._malloc_trim = None

    def release(self) -> None:
        if self._malloc_trim is not None:
            # A pad of 0: keep nothing free at the top of the heap.
            self._malloc_trim(ctypes.c_size_t(0))
