import pytest

from tests.contracts.application.ports.driven.status_reading_store_contract import (
    CLIENT_NAMES,
    StatusReadingPorts,
    StatusReadingStoreContract,
)
from tests.fakes.adapters.driven.fake_status_reading_store import FakeStatusReadingStore


class TestFakeStatusReadingStore(StatusReadingStoreContract):
    @pytest.fixture
    def status_reading_store(self) -> FakeStatusReadingStore:
        return FakeStatusReadingStore(CLIENT_NAMES)

    @pytest.fixture
    def status_reading_ports(
        self, status_reading_store: FakeStatusReadingStore
    ) -> StatusReadingPorts:
        return StatusReadingPorts(writer=status_reading_store, reader=status_reading_store)
