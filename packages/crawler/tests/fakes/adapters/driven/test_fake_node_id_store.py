import pytest

from tests.contracts.application.ports.driven.node_id_store_contract import NodeIdStoreContract
from tests.fakes.adapters.driven.fake_node_id_store import FakeNodeIdStore


class TestFakeNodeIdStore(NodeIdStoreContract):
    @pytest.fixture
    def node_id_store(self) -> FakeNodeIdStore:
        return FakeNodeIdStore(stored_node_id=None)

    @pytest.fixture
    def writer(self, node_id_store: FakeNodeIdStore) -> FakeNodeIdStore:
        return node_id_store

    @pytest.fixture
    def reader(self, node_id_store: FakeNodeIdStore) -> FakeNodeIdStore:
        return node_id_store
