import pytest

from tests.contracts.application.ports.driven.node_metric_store_contract import (
    NodeMetricPorts,
    NodeMetricStoreContract,
)
from tests.fakes.adapters.driven.fake_node_metric_store import FakeNodeMetricStore


class TestFakeNodeMetricStore(NodeMetricStoreContract):
    @pytest.fixture
    def node_metric_store(self) -> FakeNodeMetricStore:
        return FakeNodeMetricStore()

    @pytest.fixture
    def node_metric_ports(self, node_metric_store: FakeNodeMetricStore) -> NodeMetricPorts:
        return NodeMetricPorts(writer=node_metric_store, reader=node_metric_store)
