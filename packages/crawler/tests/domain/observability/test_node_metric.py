"""The catalog of node metrics, and the instructions it refuses at construction."""

import pytest

from p2pwatch.domain.observability.node_metric import (
    CounterIncrement,
    GaugeSetting,
    NodeMetricKind,
    NodeMetricName,
)

_COUNTER = NodeMetricKind.COUNTER
_GAUGE = NodeMetricKind.GAUGE
_CLIENT_CHANNEL = ("client", "channel")


def test_each_node_metric_has_the_kind_and_label_names_dashboards_query() -> None:
    assert {name: (name.kind, name.label_names) for name in NodeMetricName} == {
        NodeMetricName.SEARCHES: (_COUNTER, _CLIENT_CHANNEL),
        NodeMetricName.SEARCH_RESULTS_SKIPPED: (_COUNTER, _CLIENT_CHANNEL),
        NodeMetricName.OBSERVATIONS: (_COUNTER, _CLIENT_CHANNEL),
        NodeMetricName.SEARCH_FAILURES: (_COUNTER, _CLIENT_CHANNEL),
        NodeMetricName.CLIENT_UNREACHABLE: (_COUNTER, ("client",)),
        NodeMetricName.DECISIONS: (_COUNTER, ("tier",)),
        NodeMetricName.DOWNLOADS_QUEUED: (_COUNTER, ()),
        NodeMetricName.DOWNLOADS_COMPLETED: (_COUNTER, ()),
        NodeMetricName.SOURCE_ALERTS: (_COUNTER, ("network", "kind")),
        NodeMetricName.CRAWLER_UP: (_GAUGE, ()),
        NodeMetricName.DISK_FREE_BYTES: (_GAUGE, ()),
        NodeMetricName.CHANNEL_CONNECTED: (_GAUGE, _CLIENT_CHANNEL),
        NodeMetricName.CHANNEL_CONNECTABLE: (_GAUGE, _CLIENT_CHANNEL),
    }


def test_a_node_metric_describes_itself() -> None:
    assert NodeMetricName.SEARCHES.description == "Searches performed"


def test_an_increment_names_a_counter_and_its_labels() -> None:
    increment = CounterIncrement(NodeMetricName.DECISIONS, (("tier", "notify"),), 2.0)
    assert (increment.labels, increment.amount) == ((("tier", "notify"),), 2.0)


def test_a_setting_names_a_gauge_and_its_labels() -> None:
    setting = GaugeSetting(
        NodeMetricName.CHANNEL_CONNECTED, (("client", "a"), ("channel", "kad")), None
    )
    assert setting.value is None


def test_an_increment_of_a_gauge_cannot_be_built() -> None:
    with pytest.raises(ValueError, match="p2pwatch_crawler_up is a gauge, not a counter"):
        CounterIncrement(NodeMetricName.CRAWLER_UP)


def test_a_setting_of_a_counter_cannot_be_built() -> None:
    with pytest.raises(ValueError, match="p2pwatch_downloads_queued is a counter, not a gauge"):
        GaugeSetting(NodeMetricName.DOWNLOADS_QUEUED, (), 1.0)


@pytest.mark.parametrize(
    ("name", "labels"),
    [
        (NodeMetricName.SEARCHES, (("client", "amuled"),)),
        (NodeMetricName.CLIENT_UNREACHABLE, (("client", "amuled"), ("channel", "kad"))),
        (NodeMetricName.DOWNLOADS_COMPLETED, (("client", "amuled"),)),
        (NodeMetricName.SEARCHES, (("channel", "kad"), ("client", "amuled"))),
    ],
    ids=["missing", "extra", "on an unlabelled metric", "out of the catalog's order"],
)
def test_an_increment_whose_label_names_are_not_its_counters_cannot_be_built(
    name: NodeMetricName, labels: tuple[tuple[str, str], ...]
) -> None:
    with pytest.raises(ValueError, match=f"{name} takes the labels"):
        CounterIncrement(name, labels)


def test_a_setting_whose_label_names_are_not_its_gauges_cannot_be_built() -> None:
    with pytest.raises(ValueError, match="p2pwatch_channel_connected takes the labels"):
        GaugeSetting(NodeMetricName.CHANNEL_CONNECTED, (("client", "amuled"),), 1.0)
