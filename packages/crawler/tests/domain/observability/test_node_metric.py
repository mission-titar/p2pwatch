"""The node counters and gauges, and the instructions they refuse at construction."""

import pytest

from p2pwatch.domain.observability.node_metric import (
    CounterIncrement,
    GaugeSetting,
    NodeCounter,
    NodeGauge,
)

_CLIENT_CHANNEL = ("client", "channel")


def test_each_counter_has_the_label_names_dashboards_query() -> None:
    assert {counter: counter.label_names for counter in NodeCounter} == {
        NodeCounter.SEARCHES: _CLIENT_CHANNEL,
        NodeCounter.SEARCH_RESULTS_SKIPPED: _CLIENT_CHANNEL,
        NodeCounter.OBSERVATIONS: _CLIENT_CHANNEL,
        NodeCounter.SEARCH_FAILURES: _CLIENT_CHANNEL,
        NodeCounter.CLIENT_UNREACHABLE: ("client",),
        NodeCounter.DECISIONS: ("tier",),
        NodeCounter.DOWNLOADS_QUEUED: (),
        NodeCounter.DOWNLOADS_COMPLETED: (),
        NodeCounter.SOURCE_ALERTS: ("network", "kind"),
    }


def test_each_gauge_has_the_label_names_dashboards_query() -> None:
    assert {gauge: gauge.label_names for gauge in NodeGauge} == {
        NodeGauge.CRAWLER_UP: (),
        NodeGauge.DISK_FREE_BYTES: (),
        NodeGauge.CHANNEL_CONNECTED: _CLIENT_CHANNEL,
        NodeGauge.CHANNEL_CONNECTABLE: _CLIENT_CHANNEL,
    }


def test_a_node_metric_has_its_exposed_name_and_describes_itself() -> None:
    assert (NodeCounter.SEARCHES.exposed_name, NodeCounter.SEARCHES.description) == (
        "p2pwatch_searches",
        "Searches performed",
    )


def test_an_increment_names_a_counter_its_labels_and_its_amount() -> None:
    increment = CounterIncrement(NodeCounter.DECISIONS, (("tier", "notify"),), 2.0)
    assert (increment.labels, increment.amount) == ((("tier", "notify"),), 2.0)


def test_a_setting_of_none_names_a_gauge_series_to_remove() -> None:
    setting = GaugeSetting(NodeGauge.CHANNEL_CONNECTED, (("client", "a"), ("channel", "kad")), None)
    assert setting.value is None


@pytest.mark.parametrize(
    ("counter", "labels"),
    [
        (NodeCounter.SEARCHES, (("client", "amuled"),)),
        (NodeCounter.CLIENT_UNREACHABLE, (("client", "amuled"), ("channel", "kad"))),
        (NodeCounter.DOWNLOADS_COMPLETED, (("client", "amuled"),)),
        (NodeCounter.SEARCHES, (("channel", "kad"), ("client", "amuled"))),
    ],
    ids=["missing", "extra", "on an unlabelled counter", "out of the declared order"],
)
def test_an_increment_whose_label_names_are_not_its_counters_cannot_be_built(
    counter: NodeCounter, labels: tuple[tuple[str, str], ...]
) -> None:
    with pytest.raises(ValueError, match=f"{counter.exposed_name} takes the labels"):
        CounterIncrement(counter, labels)


def test_a_setting_whose_label_names_are_not_its_gauges_cannot_be_built() -> None:
    with pytest.raises(ValueError, match="p2pwatch_crawler_up takes the labels"):
        GaugeSetting(NodeGauge.CRAWLER_UP, (("client", "amuled"),), 1.0)
