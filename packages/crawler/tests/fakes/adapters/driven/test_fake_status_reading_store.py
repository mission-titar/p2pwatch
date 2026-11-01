import pytest

from tests.contracts.application.ports.driven.status_reading_store_contract import (
    CLIENT_NAMES,
    StatusReadingStoreContract,
)
from tests.fakes.adapters.driven.fake_status_reading_store import FakeStatusReadingStore


class TestFakeStatusReadingStore(StatusReadingStoreContract):
    @pytest.fixture
    def status_reading_store(self) -> FakeStatusReadingStore:
        return FakeStatusReadingStore(CLIENT_NAMES)

    @pytest.fixture
    def writer(self, status_reading_store: FakeStatusReadingStore) -> FakeStatusReadingStore:
        return status_reading_store

    @pytest.fixture
    def reader(self, status_reading_store: FakeStatusReadingStore) -> FakeStatusReadingStore:
        return status_reading_store
