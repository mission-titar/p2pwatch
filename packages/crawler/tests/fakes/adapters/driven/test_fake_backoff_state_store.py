import pytest

from tests.contracts.application.ports.driven.backoff_state_store_contract import (
    BackoffStateStoreContract,
)
from tests.fakes.adapters.driven.fake_backoff_state_store import FakeBackoffStateStore
from tests.support.refused_writes import RefuseWrites


class TestFakeBackoffStateStore(BackoffStateStoreContract):
    @pytest.fixture
    def backoff_state_store(self) -> FakeBackoffStateStore:
        return FakeBackoffStateStore()

    @pytest.fixture
    def writer(self, backoff_state_store: FakeBackoffStateStore) -> FakeBackoffStateStore:
        return backoff_state_store

    @pytest.fixture
    def reader(self, backoff_state_store: FakeBackoffStateStore) -> FakeBackoffStateStore:
        return backoff_state_store

    @pytest.fixture
    def refuse_writes(self) -> RefuseWrites:
        pytest.skip("a fake's memory refuses no write")
