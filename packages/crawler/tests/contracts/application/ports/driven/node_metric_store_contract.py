"""The promise of the ``NodeMetricReader`` and ``NodeMetricWriter`` pair; the port promises no
order of the samples, so they are compared as multisets."""

from abc import ABC, abstractmethod
from collections import Counter
from typing import Protocol

import pytest

from p2pwatch.domain.identifiers import Channel, ClientName
from p2pwatch.domain.observability.node_metric import (
    ChannelLabels,
    CounterIncrement,
    GaugeSetting,
    NodeCounter,
    NodeGauge,
    NodeMetricSample,
)

_ED2K = ChannelLabels(ClientName("amuled"), Channel("ed2k"))
_KAD = ChannelLabels(ClientName("amuled"), Channel("kad"))
_ED2K_PAIRS = (("client", "amuled"), ("channel", "ed2k"))
_KAD_PAIRS = (("client", "amuled"), ("channel", "kad"))


class NodeMetricStore(Protocol):
    """Both ports of the pair, which one store implements."""

    def record_increment(self, increment: CounterIncrement) -> None: ...

    def set_gauge(self, setting: GaugeSetting) -> None: ...

    def read_samples(self) -> tuple[NodeMetricSample, ...]: ...


class NodeMetricStoreContract(ABC):
    @pytest.fixture
    @abstractmethod
    def node_metric_store(self) -> NodeMetricStore:
        """A store nothing has written yet."""

    def test_no_series_is_read_before_the_first_write(
        self, node_metric_store: NodeMetricStore
    ) -> None:
        assert node_metric_store.read_samples() == ()

    def test_an_increment_adds_its_amount_to_its_series(
        self, node_metric_store: NodeMetricStore
    ) -> None:
        node_metric_store.record_increment(CounterIncrement(NodeCounter.SEARCHES, _ED2K))
        node_metric_store.record_increment(CounterIncrement(NodeCounter.SEARCHES, _ED2K, 2.0))
        assert node_metric_store.read_samples() == (
            NodeMetricSample(NodeCounter.SEARCHES, _ED2K_PAIRS, 3.0),
        )

    def test_an_increment_of_zero_creates_its_series_at_zero(
        self, node_metric_store: NodeMetricStore
    ) -> None:
        node_metric_store.record_increment(CounterIncrement(NodeCounter.SEARCHES, _ED2K, 0.0))
        assert node_metric_store.read_samples() == (
            NodeMetricSample(NodeCounter.SEARCHES, _ED2K_PAIRS, 0.0),
        )

    def test_a_setting_replaces_its_series(self, node_metric_store: NodeMetricStore) -> None:
        node_metric_store.set_gauge(GaugeSetting(NodeGauge.CHANNEL_CONNECTED, _ED2K, 1.0))
        node_metric_store.set_gauge(GaugeSetting(NodeGauge.CHANNEL_CONNECTED, _ED2K, 0.0))
        assert node_metric_store.read_samples() == (
            NodeMetricSample(NodeGauge.CHANNEL_CONNECTED, _ED2K_PAIRS, 0.0),
        )

    def test_a_setting_of_none_removes_its_series(self, node_metric_store: NodeMetricStore) -> None:
        node_metric_store.set_gauge(GaugeSetting(NodeGauge.CHANNEL_CONNECTED, _ED2K, 1.0))
        node_metric_store.set_gauge(GaugeSetting(NodeGauge.CHANNEL_CONNECTED, _ED2K, None))
        assert node_metric_store.read_samples() == ()

    def test_a_setting_of_none_leaves_the_store_as_it_was_when_its_series_is_absent(
        self, node_metric_store: NodeMetricStore
    ) -> None:
        node_metric_store.set_gauge(GaugeSetting(NodeGauge.CHANNEL_CONNECTED, _ED2K, 1.0))
        node_metric_store.set_gauge(GaugeSetting(NodeGauge.CHANNEL_CONNECTED, _KAD, None))
        assert node_metric_store.read_samples() == (
            NodeMetricSample(NodeGauge.CHANNEL_CONNECTED, _ED2K_PAIRS, 1.0),
        )

    def test_series_of_one_node_metric_are_apart_by_their_labels(
        self, node_metric_store: NodeMetricStore
    ) -> None:
        node_metric_store.record_increment(CounterIncrement(NodeCounter.SEARCHES, _ED2K))
        node_metric_store.record_increment(CounterIncrement(NodeCounter.SEARCHES, _KAD, 2.0))
        node_metric_store.set_gauge(GaugeSetting(NodeGauge.CHANNEL_CONNECTED, _ED2K, 1.0))
        node_metric_store.set_gauge(GaugeSetting(NodeGauge.CHANNEL_CONNECTED, _KAD, None))
        assert Counter(node_metric_store.read_samples()) == Counter(
            [
                NodeMetricSample(NodeCounter.SEARCHES, _ED2K_PAIRS, 1.0),
                NodeMetricSample(NodeCounter.SEARCHES, _KAD_PAIRS, 2.0),
                NodeMetricSample(NodeGauge.CHANNEL_CONNECTED, _ED2K_PAIRS, 1.0),
            ]
        )
