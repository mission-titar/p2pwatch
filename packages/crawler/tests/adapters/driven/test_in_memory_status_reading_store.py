from datetime import UTC, datetime

import pytest

from p2pwatch.adapters.driven.in_memory_status_reading_store import InMemoryStatusReadingStore
from p2pwatch.domain.identifiers import ClientName
from p2pwatch.domain.monotonic_instant import MonotonicInstant
from p2pwatch.domain.status_reading import ClientStatus, StatusReading
from tests.contracts.application.ports.driven.status_reading_store_contract import (
    CLIENT_NAMES,
    StatusReadingStoreContract,
)

_READING = StatusReading(
    read_at=datetime(2026, 6, 12, tzinfo=UTC), status=ClientStatus(version="3.0.1", channels=())
)


class TestInMemoryStatusReadingStore(StatusReadingStoreContract):
    @pytest.fixture
    def status_reading_store(self) -> InMemoryStatusReadingStore:
        return InMemoryStatusReadingStore(CLIENT_NAMES)

    @pytest.fixture
    def writer(
        self, status_reading_store: InMemoryStatusReadingStore
    ) -> InMemoryStatusReadingStore:
        return status_reading_store

    @pytest.fixture
    def reader(
        self, status_reading_store: InMemoryStatusReadingStore
    ) -> InMemoryStatusReadingStore:
        return status_reading_store


def test_publishing_replaces_the_snapshot_and_never_changes_one_already_read() -> None:
    status_reading_store = InMemoryStatusReadingStore((ClientName("amuled"),))
    before = status_reading_store.read_readings()
    status_reading_store.set_reading(
        ClientName("amuled"), reading=_READING, published_at=MonotonicInstant(nanoseconds=7)
    )
    assert before == {"amuled": None}
