import pytest

from tests.contracts.application.ports.driven.node_metric_store_contract import (
    NodeMetricStoreContract,
)
from tests.fakes.adapters.driven.fake_node_metric_store import FakeNodeMetricStore


class TestFakeNodeMetricStore(NodeMetricStoreContract):
    @pytest.fixture
    def node_metric_store(self) -> FakeNodeMetricStore:
        return FakeNodeMetricStore()

    @pytest.fixture
    def writer(self, node_metric_store: FakeNodeMetricStore) -> FakeNodeMetricStore:
        return node_metric_store

    @pytest.fixture
    def reader(self, node_metric_store: FakeNodeMetricStore) -> FakeNodeMetricStore:
        return node_metric_store
