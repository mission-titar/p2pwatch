import pytest

from p2pwatch.adapters.driven.in_memory_open_alert_store import InMemoryOpenAlertStore
from tests.contracts.application.ports.driven.open_alert_store_contract import (
    OpenAlertStoreContract,
)


class TestInMemoryOpenAlertStore(OpenAlertStoreContract):
    @pytest.fixture
    def open_alert_store(self) -> InMemoryOpenAlertStore:
        return InMemoryOpenAlertStore()

    @pytest.fixture
    def writer(self, open_alert_store: InMemoryOpenAlertStore) -> InMemoryOpenAlertStore:
        return open_alert_store

    @pytest.fixture
    def reader(self, open_alert_store: InMemoryOpenAlertStore) -> InMemoryOpenAlertStore:
        return open_alert_store
