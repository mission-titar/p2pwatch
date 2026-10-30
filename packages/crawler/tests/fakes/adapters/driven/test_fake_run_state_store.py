import pytest

from tests.contracts.application.ports.driven.run_state_store_contract import (
    RunStatePorts,
    RunStateStoreContract,
)
from tests.fakes.adapters.driven.fake_run_state_store import FakeRunStateStore


class TestFakeRunStateStore(RunStateStoreContract):
    @pytest.fixture
    def run_state_store(self) -> FakeRunStateStore:
        return FakeRunStateStore()

    @pytest.fixture
    def run_state_ports(self, run_state_store: FakeRunStateStore) -> RunStatePorts:
        return RunStatePorts(writer=run_state_store, reader=run_state_store)
