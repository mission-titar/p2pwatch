"""The promise of the ``NodeMetricReader`` and ``NodeMetricWriter`` pair; the port promises no
order of the samples, so they are compared as multisets."""

from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass

import pytest

from p2pwatch.application.ports.driven.node_metric_reader import NodeMetricReader
from p2pwatch.application.ports.driven.node_metric_writer import NodeMetricWriter
from p2pwatch.domain.identifiers import Channel, ClientName
from p2pwatch.domain.observability.node_metric import (
    ChannelLabels,
    CounterIncrement,
    GaugeSetting,
    NodeCounter,
    NodeGauge,
    NodeMetricSample,
)

_ED2K = ChannelLabels(client_name=ClientName("amuled"), channel=Channel("ed2k"))
_KAD = ChannelLabels(client_name=ClientName("amuled"), channel=Channel("kad"))
_ED2K_PAIRS = (("client", "amuled"), ("channel", "ed2k"))
_KAD_PAIRS = (("client", "amuled"), ("channel", "kad"))


@dataclass(kw_only=True, frozen=True)
class NodeMetricPorts:
    """The pair's two ports, which one store implements."""

    writer: NodeMetricWriter
    reader: NodeMetricReader


class NodeMetricStoreContract(ABC):
    @pytest.fixture
    @abstractmethod
    def node_metric_ports(self) -> NodeMetricPorts:
        """The ports of a store nothing has written yet."""

    def test_no_series_is_read_before_the_first_write(
        self, node_metric_ports: NodeMetricPorts
    ) -> None:
        assert node_metric_ports.reader.read_samples() == ()

    def test_an_increment_adds_its_amount_to_its_series(
        self, node_metric_ports: NodeMetricPorts
    ) -> None:
        node_metric_ports.writer.record_increment(
            CounterIncrement(counter=NodeCounter.SEARCHES, labels=_ED2K)
        )
        node_metric_ports.writer.record_increment(
            CounterIncrement(counter=NodeCounter.SEARCHES, labels=_ED2K, amount=2.0)
        )
        assert node_metric_ports.reader.read_samples() == (
            NodeMetricSample(node_metric=NodeCounter.SEARCHES, labels=_ED2K_PAIRS, value=3.0),
        )

    def test_an_increment_of_zero_creates_its_series_at_zero(
        self, node_metric_ports: NodeMetricPorts
    ) -> None:
        node_metric_ports.writer.record_increment(
            CounterIncrement(counter=NodeCounter.SEARCHES, labels=_ED2K, amount=0.0)
        )
        assert node_metric_ports.reader.read_samples() == (
            NodeMetricSample(node_metric=NodeCounter.SEARCHES, labels=_ED2K_PAIRS, value=0.0),
        )

    def test_a_setting_replaces_its_series(self, node_metric_ports: NodeMetricPorts) -> None:
        node_metric_ports.writer.set_gauge(
            GaugeSetting(gauge=NodeGauge.CHANNEL_CONNECTED, labels=_ED2K, value=1.0)
        )
        node_metric_ports.writer.set_gauge(
            GaugeSetting(gauge=NodeGauge.CHANNEL_CONNECTED, labels=_ED2K, value=0.0)
        )
        assert node_metric_ports.reader.read_samples() == (
            NodeMetricSample(
                node_metric=NodeGauge.CHANNEL_CONNECTED, labels=_ED2K_PAIRS, value=0.0
            ),
        )

    def test_a_setting_of_none_removes_its_series(self, node_metric_ports: NodeMetricPorts) -> None:
        node_metric_ports.writer.set_gauge(
            GaugeSetting(gauge=NodeGauge.CHANNEL_CONNECTED, labels=_ED2K, value=1.0)
        )
        node_metric_ports.writer.set_gauge(
            GaugeSetting(gauge=NodeGauge.CHANNEL_CONNECTED, labels=_ED2K, value=None)
        )
        assert node_metric_ports.reader.read_samples() == ()

    def test_a_setting_of_none_leaves_the_store_as_it_was_when_its_series_is_absent(
        self, node_metric_ports: NodeMetricPorts
    ) -> None:
        node_metric_ports.writer.set_gauge(
            GaugeSetting(gauge=NodeGauge.CHANNEL_CONNECTED, labels=_ED2K, value=1.0)
        )
        node_metric_ports.writer.set_gauge(
            GaugeSetting(gauge=NodeGauge.CHANNEL_CONNECTED, labels=_KAD, value=None)
        )
        assert node_metric_ports.reader.read_samples() == (
            NodeMetricSample(
                node_metric=NodeGauge.CHANNEL_CONNECTED, labels=_ED2K_PAIRS, value=1.0
            ),
        )

    def test_series_of_one_node_metric_are_apart_by_their_labels(
        self, node_metric_ports: NodeMetricPorts
    ) -> None:
        node_metric_ports.writer.record_increment(
            CounterIncrement(counter=NodeCounter.SEARCHES, labels=_ED2K)
        )
        node_metric_ports.writer.record_increment(
            CounterIncrement(counter=NodeCounter.SEARCHES, labels=_KAD, amount=2.0)
        )
        node_metric_ports.writer.set_gauge(
            GaugeSetting(gauge=NodeGauge.CHANNEL_CONNECTED, labels=_ED2K, value=1.0)
        )
        node_metric_ports.writer.set_gauge(
            GaugeSetting(gauge=NodeGauge.CHANNEL_CONNECTED, labels=_KAD, value=None)
        )
        assert Counter(node_metric_ports.reader.read_samples()) == Counter(
            [
                NodeMetricSample(node_metric=NodeCounter.SEARCHES, labels=_ED2K_PAIRS, value=1.0),
                NodeMetricSample(node_metric=NodeCounter.SEARCHES, labels=_KAD_PAIRS, value=2.0),
                NodeMetricSample(
                    node_metric=NodeGauge.CHANNEL_CONNECTED, labels=_ED2K_PAIRS, value=1.0
                ),
            ]
        )
