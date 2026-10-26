from p2pwatch.adapters.driven.in_memory_node_metric_store import InMemoryNodeMetricStore
from p2pwatch.domain.observability.node_metric import (
    CounterIncrement,
    GaugeSetting,
    NodeCounter,
    NodeGauge,
    NodeMetricSample,
)

_ED2K = (("client", "amuled"), ("channel", "ed2k"))
_KAD = (("client", "amuled"), ("channel", "kad"))


def test_increments_add_up_in_their_series() -> None:
    node_metric_store = InMemoryNodeMetricStore()
    node_metric_store.record_increment(CounterIncrement(NodeCounter.SEARCHES, _ED2K))
    node_metric_store.record_increment(CounterIncrement(NodeCounter.SEARCHES, _ED2K, 2.0))
    node_metric_store.record_increment(CounterIncrement(NodeCounter.SEARCHES, _KAD, 0.0))
    assert node_metric_store.read_samples() == (
        NodeMetricSample(NodeCounter.SEARCHES, _ED2K, 3.0),
        NodeMetricSample(NodeCounter.SEARCHES, _KAD, 0.0),
    )


def test_a_setting_replaces_its_series_and_none_removes_it() -> None:
    node_metric_store = InMemoryNodeMetricStore()
    node_metric_store.set_gauge(GaugeSetting(NodeGauge.CHANNEL_CONNECTED, _ED2K, 1.0))
    node_metric_store.set_gauge(GaugeSetting(NodeGauge.CHANNEL_CONNECTED, _KAD, 1.0))
    node_metric_store.set_gauge(GaugeSetting(NodeGauge.CHANNEL_CONNECTED, _ED2K, 0.0))
    node_metric_store.set_gauge(GaugeSetting(NodeGauge.CHANNEL_CONNECTED, _KAD, None))
    node_metric_store.set_gauge(GaugeSetting(NodeGauge.CRAWLER_UP, (), None))
    assert node_metric_store.read_samples() == (
        NodeMetricSample(NodeGauge.CHANNEL_CONNECTED, _ED2K, 0.0),
    )


def test_a_later_write_never_changes_the_samples_already_read() -> None:
    node_metric_store = InMemoryNodeMetricStore()
    before = node_metric_store.read_samples()
    node_metric_store.set_gauge(GaugeSetting(NodeGauge.CRAWLER_UP, (), 1.0))
    assert before == ()
