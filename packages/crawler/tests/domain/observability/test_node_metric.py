"""The node counters and gauges, their typed labels, and the instructions they refuse."""

import pytest

from catalog_matching.domain.decision_tier import DecisionTier
from p2pwatch.domain.file_key import Network
from p2pwatch.domain.identifiers import Channel, ClientName
from p2pwatch.domain.observability.node_metric import (
    ChannelLabels,
    ClientLabels,
    CounterIncrement,
    DecisionLabels,
    GaugeSetting,
    NodeCounter,
    NodeGauge,
    NodeMetricLabels,
    SourceAlertLabels,
)
from p2pwatch.domain.observability.notification import SourceAlertKind

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


@pytest.mark.parametrize(
    ("labels", "pairs"),
    [
        (
            ChannelLabels(client_name=ClientName("amuled"), channel=Channel("kad")),
            (("client", "amuled"), ("channel", "kad")),
        ),
        (ClientLabels(client_name=ClientName("amuled")), (("client", "amuled"),)),
        (DecisionLabels(tier=DecisionTier.NOTIFY), (("tier", "notify"),)),
        (DecisionLabels(tier="retracted"), (("tier", "retracted"),)),
        (
            SourceAlertLabels(network=Network.ED2K, kind=SourceAlertKind.FIRST_USEFUL),
            (("network", "ed2k"), ("kind", "first_useful")),
        ),
    ],
)
def test_labels_write_their_pairs_in_the_order_of_their_names(
    *, labels: NodeMetricLabels, pairs: tuple[tuple[str, str], ...]
) -> None:
    assert labels.pairs() == pairs
    assert tuple(name for name, _ in pairs) == labels.names


def test_an_increment_names_a_counter_its_labels_and_its_amount() -> None:
    increment = CounterIncrement(
        counter=NodeCounter.DECISIONS, labels=DecisionLabels(tier=DecisionTier.NOTIFY), amount=2.0
    )
    assert (increment.labels, increment.amount) == (DecisionLabels(tier=DecisionTier.NOTIFY), 2.0)


def test_a_setting_of_none_names_a_gauge_series_to_remove() -> None:
    setting = GaugeSetting(
        gauge=NodeGauge.CHANNEL_CONNECTED,
        labels=ChannelLabels(client_name=ClientName("amuled"), channel=Channel("kad")),
        value=None,
    )
    assert setting.value is None


@pytest.mark.parametrize(
    ("counter", "labels", "message"),
    [
        (
            NodeCounter.SEARCHES,
            ClientLabels(client_name=ClientName("amuled")),
            "p2pwatch_searches takes ChannelLabels, given ClientLabels",
        ),
        (NodeCounter.SEARCHES, None, "p2pwatch_searches takes ChannelLabels, given no labels"),
        (
            NodeCounter.DOWNLOADS_COMPLETED,
            ClientLabels(client_name=ClientName("amuled")),
            "p2pwatch_downloads_completed takes no labels, given ClientLabels",
        ),
    ],
    ids=["other labels", "missing labels", "labels on an unlabelled counter"],
)
def test_an_increment_whose_labels_are_not_its_counters_cannot_be_built(
    *, counter: NodeCounter, labels: NodeMetricLabels | None, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        CounterIncrement(counter=counter, labels=labels)


def test_a_setting_whose_labels_are_not_its_gauges_cannot_be_built() -> None:
    with pytest.raises(
        ValueError, match="p2pwatch_crawler_up takes no labels, given ChannelLabels"
    ):
        GaugeSetting(
            gauge=NodeGauge.CRAWLER_UP,
            labels=ChannelLabels(client_name=ClientName("amuled"), channel=Channel("kad")),
            value=1.0,
        )


def test_an_instruction_gives_the_pairs_of_its_labels_or_none_unlabelled() -> None:
    labelled = GaugeSetting(
        gauge=NodeGauge.CHANNEL_CONNECTED,
        labels=ChannelLabels(client_name=ClientName("amuled"), channel=Channel("kad")),
        value=1.0,
    )
    unlabelled = CounterIncrement(counter=NodeCounter.DOWNLOADS_QUEUED)
    assert labelled.label_pairs() == (("client", "amuled"), ("channel", "kad"))
    assert unlabelled.label_pairs() == ()


def test_an_increment_of_a_negative_amount_cannot_be_built() -> None:
    with pytest.raises(
        ValueError, match="p2pwatch_searches takes an amount of 0 or more, not -1.0"
    ):
        CounterIncrement(
            counter=NodeCounter.SEARCHES,
            labels=ChannelLabels(client_name=ClientName("amuled"), channel=Channel("kad")),
            amount=-1.0,
        )
