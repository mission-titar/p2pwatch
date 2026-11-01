import pytest

from tests.contracts.application.ports.driven.run_state_store_contract import RunStateStoreContract
from tests.fakes.adapters.driven.fake_run_state_store import FakeRunStateStore


class TestFakeRunStateStore(RunStateStoreContract):
    @pytest.fixture
    def run_state_store(self) -> FakeRunStateStore:
        return FakeRunStateStore()

    @pytest.fixture
    def writer(self, run_state_store: FakeRunStateStore) -> FakeRunStateStore:
        return run_state_store

    @pytest.fixture
    def reader(self, run_state_store: FakeRunStateStore) -> FakeRunStateStore:
        return run_state_store
