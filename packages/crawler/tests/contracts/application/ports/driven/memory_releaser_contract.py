"""The promise of the ``MemoryReleaser`` port."""

from abc import ABC, abstractmethod

import pytest

from p2pwatch.application.ports.driven.memory_releaser import MemoryReleaser


class MemoryReleaserContract(ABC):
    @pytest.fixture
    @abstractmethod
    def memory_releaser(self) -> MemoryReleaser:
        """A releaser over the process's own allocator."""

    def test_release_returns_however_often_it_is_called(
        self, memory_releaser: MemoryReleaser
    ) -> None:
        memory_releaser.release()
        memory_releaser.release()
