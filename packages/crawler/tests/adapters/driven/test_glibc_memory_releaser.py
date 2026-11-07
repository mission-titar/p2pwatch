import ctypes
from typing import NoReturn

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


def test_releases_nothing_from_a_c_library_without_malloc_trim() -> None:
    GlibcMemoryReleaser(_CLibraryWithoutMallocTrim()).release()
