"""``InMemoryNodeMetricStore``: the node metrics, written by the crawler's loop and read on the
webui's thread."""

from collections.abc import Mapping

from p2pwatch.application.ports.driven.node_metric_reader import NodeMetricReader
from p2pwatch.application.ports.driven.node_metric_writer import NodeMetricWriter
from p2pwatch.domain.observability.node_metric import (
    CounterIncrement,
    GaugeSetting,
    NodeCounter,
    NodeGauge,
    NodeMetricSample,
)

type _Series = tuple[NodeCounter | NodeGauge, tuple[tuple[str, str], ...]]


class InMemoryNodeMetricStore(NodeMetricWriter, NodeMetricReader):
    """Its one writer is the crawler's loop, where every dispatch is awaited: a write reads the
    current map and swaps a new one, never a mutation, so a read takes a whole snapshot unlocked."""

    def __init__(self) -> None:
        self._value_by_series: Mapping[_Series, float] = {}

    def record_increment(self, increment: CounterIncrement) -> None:
        series = (increment.counter, increment.labels)
        self._value_by_series = {
            **self._value_by_series,
            series: self._value_by_series.get(series, 0.0) + increment.amount,
        }

    def set_gauge(self, setting: GaugeSetting) -> None:
        series = (setting.gauge, setting.labels)
        if setting.value is None:
            self._value_by_series = {
                kept: kept_value
                for kept, kept_value in self._value_by_series.items()
                if kept != series
            }
        else:
            self._value_by_series = {**self._value_by_series, series: setting.value}

    def read_samples(self) -> tuple[NodeMetricSample, ...]:
        return tuple(
            NodeMetricSample(node_metric, labels, series_value)
            for (node_metric, labels), series_value in self._value_by_series.items()
        )
