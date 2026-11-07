import ctypes
from typing import NoReturn, cast

import pytest

from p2pwatch.adapters.driven.glibc_memory_releaser import GlibcMemoryReleaser
from tests.contracts.application.ports.driven.memory_releaser_contract import (
    MemoryReleaserContract,
)


class TestGlibcMemoryReleaser(MemoryReleaserContract):
    @pytest.fixture
    def memory_releaser(self) -> GlibcMemoryReleaser:
        return GlibcMemoryReleaser(ctypes.CDLL(None))


class _ResolvingCLibrary(ctypes.CDLL):
    """The process's C library, keeping the name of each function looked up in it."""

    def __init__(self) -> None:
        super().__init__(None)
        self.looked_up: list[str] = []

    def __getitem__(self, name: str) -> "ctypes._NamedFuncPointer":
        self.looked_up.append(name)
        return super().__getitem__(name)


_MallocTrimType = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_size_t)


class _RecordingCLibrary(ctypes.CDLL):
    """A C library whose ``malloc_trim`` keeps each pad it is called with."""

    def __init__(self) -> None:
        super().__init__(None)
        self.pads: list[int] = []
        self._malloc_trim = _MallocTrimType(self._record)

    def _record(self, pad: int) -> int:
        self.pads.append(pad)
        return 1

    def __getitem__(self, name: str) -> "ctypes._NamedFuncPointer":
        assert name == "malloc_trim"
        return cast("ctypes._NamedFuncPointer", self._malloc_trim)


class _CLibraryWithoutMallocTrim(ctypes.CDLL):
    """A C library lacking ``malloc_trim``, as musl does."""

    def __init__(self) -> None:
        super().__init__(None)

    def __getitem__(self, name: str) -> NoReturn:
        raise AttributeError(name)


def test_resolves_malloc_trim_in_the_process_s_c_library() -> None:
    c_library = _ResolvingCLibrary()
    GlibcMemoryReleaser(c_library).release()
    assert c_library.looked_up == ["malloc_trim"]


def test_release_calls_malloc_trim_once_with_a_pad_of_0() -> None:
    c_library = _RecordingCLibrary()
    GlibcMemoryReleaser(c_library).release()
    assert c_library.pads == [0]


def test_releases_nothing_from_a_c_library_without_malloc_trim() -> None:
    GlibcMemoryReleaser(_CLibraryWithoutMallocTrim()).release()
