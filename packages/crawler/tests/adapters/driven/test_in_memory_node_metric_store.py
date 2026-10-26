import pytest

from p2pwatch.adapters.driven.in_memory_node_metric_store import InMemoryNodeMetricStore
from tests.contracts.application.ports.driven.node_metric_store_contract import (
    NodeMetricStoreContract,
)


class TestInMemoryNodeMetricStore(NodeMetricStoreContract):
    @pytest.fixture
    def node_metric_store(self) -> InMemoryNodeMetricStore:
        return InMemoryNodeMetricStore()
