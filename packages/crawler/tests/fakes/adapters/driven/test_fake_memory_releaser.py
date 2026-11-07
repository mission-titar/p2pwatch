import pytest

from tests.contracts.application.ports.driven.memory_releaser_contract import (
    MemoryReleaserContract,
)
from tests.fakes.adapters.driven.fake_memory_releaser import FakeMemoryReleaser


class TestFakeMemoryReleaser(MemoryReleaserContract):
    @pytest.fixture
    def memory_releaser(self) -> FakeMemoryReleaser:
        return FakeMemoryReleaser()


def test_counts_its_releases() -> None:
    memory_releaser = FakeMemoryReleaser()
    memory_releaser.release()
    memory_releaser.release()
    assert memory_releaser.release_count == 2
