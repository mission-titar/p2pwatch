from p2pwatch.application.ports.driven.node_metric_reader import NodeMetricReader
from p2pwatch.application.ports.driven.node_metric_writer import NodeMetricWriter
from p2pwatch.domain.observability.node_metric import (
    CounterIncrement,
    GaugeSetting,
    NodeCounter,
    NodeGauge,
    NodeMetricSample,
)


class FakeNodeMetricStore(NodeMetricWriter, NodeMetricReader):
    """Series in a dict, written and read on one thread."""

    def __init__(self) -> None:
        self._value_by_series: dict[
            tuple[NodeCounter | NodeGauge, tuple[tuple[str, str], ...]], float
        ] = {}

    def record_increment(self, increment: CounterIncrement) -> None:
        series = (increment.counter, increment.label_pairs())
        self._value_by_series[series] = self._value_by_series.get(series, 0.0) + increment.amount

    def set_gauge(self, setting: GaugeSetting) -> None:
        series = (setting.gauge, setting.label_pairs())
        if setting.value is None:
            self._value_by_series.pop(series, None)
        else:
            self._value_by_series[series] = setting.value

    def read_samples(self) -> tuple[NodeMetricSample, ...]:
        return tuple(
            NodeMetricSample(node_metric, labels, series_value)
            for (node_metric, labels), series_value in self._value_by_series.items()
        )
