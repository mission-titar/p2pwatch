import pytest

from tests.contracts.application.ports.driven.node_id_store_contract import (
    NodeIdPorts,
    NodeIdStoreContract,
)
from tests.fakes.adapters.driven.fake_node_id_store import FakeNodeIdStore


class TestFakeNodeIdStore(NodeIdStoreContract):
    @pytest.fixture
    def node_id_store(self) -> FakeNodeIdStore:
        return FakeNodeIdStore(stored_node_id=None)

    @pytest.fixture
    def node_id_ports(self, node_id_store: FakeNodeIdStore) -> NodeIdPorts:
        return NodeIdPorts(writer=node_id_store, reader=node_id_store)
