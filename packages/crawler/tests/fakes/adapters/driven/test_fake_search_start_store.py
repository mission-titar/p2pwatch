import pytest

from p2pwatch.domain.identifiers import ClientName
from p2pwatch.domain.store_error import StoreError
from tests.contracts.application.ports.driven.search_start_store_contract import (
    SearchStartStoreContract,
)
from tests.fakes.adapters.driven.fake_search_start_store import FakeSearchStartStore
from tests.support.refused_writes import RefuseWrites


class TestFakeSearchStartStore(SearchStartStoreContract):
    @pytest.fixture
    def search_start_store(self) -> FakeSearchStartStore:
        return FakeSearchStartStore()

    @pytest.fixture
    def writer(self, search_start_store: FakeSearchStartStore) -> FakeSearchStartStore:
        return search_start_store

    @pytest.fixture
    def reader(self, search_start_store: FakeSearchStartStore) -> FakeSearchStartStore:
        return search_start_store

    @pytest.fixture
    def refuse_writes(self, search_start_store: FakeSearchStartStore) -> RefuseWrites:
        def refuse_writes() -> None:
            search_start_store.writes_fail = True

        return refuse_writes


def test_a_store_failing_its_reads_raises_store_error() -> None:
    search_start_store = FakeSearchStartStore()
    search_start_store.reads_fail = True
    with pytest.raises(StoreError):
        search_start_store.read_latest_starts(ClientName("amuled"))
