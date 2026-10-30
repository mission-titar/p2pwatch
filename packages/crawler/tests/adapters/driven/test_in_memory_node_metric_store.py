import pytest

from p2pwatch.adapters.driven.in_memory_node_metric_store import InMemoryNodeMetricStore
from tests.contracts.application.ports.driven.node_metric_store_contract import (
    NodeMetricPorts,
    NodeMetricStoreContract,
)


class TestInMemoryNodeMetricStore(NodeMetricStoreContract):
    @pytest.fixture
    def node_metric_store(self) -> InMemoryNodeMetricStore:
        return InMemoryNodeMetricStore()

    @pytest.fixture
    def node_metric_ports(self, node_metric_store: InMemoryNodeMetricStore) -> NodeMetricPorts:
        return NodeMetricPorts(writer=node_metric_store, reader=node_metric_store)
