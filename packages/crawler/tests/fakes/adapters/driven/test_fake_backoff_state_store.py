import pytest

from tests.contracts.application.ports.driven.backoff_state_store_contract import (
    BackoffStatePorts,
    BackoffStateStoreContract,
)
from tests.fakes.adapters.driven.fake_backoff_state_store import FakeBackoffStateStore


class TestFakeBackoffStateStore(BackoffStateStoreContract):
    @pytest.fixture
    def backoff_state_store(self) -> FakeBackoffStateStore:
        return FakeBackoffStateStore()

    @pytest.fixture
    def backoff_state_ports(self, backoff_state_store: FakeBackoffStateStore) -> BackoffStatePorts:
        return BackoffStatePorts(writer=backoff_state_store, reader=backoff_state_store)
