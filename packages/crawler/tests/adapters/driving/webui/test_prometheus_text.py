from p2pwatch.adapters.driving.webui.prometheus_text import prometheus_text
from p2pwatch.application.ports.driving.node_metric_lister import NodeMetricListing
from p2pwatch.domain.observability.node_metric import NodeCounter, NodeGauge, NodeMetricSample

_SEARCHES = NodeCounter.SEARCHES


def _lines(
    samples_by_node_metric: dict[NodeCounter | NodeGauge, tuple[NodeMetricSample, ...]],
) -> list[str]:
    return prometheus_text(
        NodeMetricListing(samples_by_node_metric=samples_by_node_metric)
    ).splitlines(keepends=True)


def test_a_counter_takes_total_on_every_line_and_writes_its_labels() -> None:
    ed2k = NodeMetricSample(
        node_metric=_SEARCHES, labels=(("client", "amuled"), ("channel", "ed2k")), value=3.0
    )
    kad = NodeMetricSample(
        node_metric=_SEARCHES, labels=(("client", "amuled"), ("channel", "kad")), value=0.0
    )
    assert _lines({_SEARCHES: (ed2k, kad)}) == [
        "# HELP p2pwatch_searches_total Searches performed\n",
        "# TYPE p2pwatch_searches_total counter\n",
        'p2pwatch_searches_total{client="amuled",channel="ed2k"} 3.0\n',
        'p2pwatch_searches_total{client="amuled",channel="kad"} 0.0\n',
    ]


def test_a_gauge_without_labels_keeps_its_name() -> None:
    free_bytes = NodeMetricSample(
        node_metric=NodeGauge.DISK_FREE_BYTES, labels=(), value=500_000_000_000.0
    )
    assert _lines({NodeGauge.DISK_FREE_BYTES: (free_bytes,)}) == [
        "# HELP p2pwatch_download_disk_free_bytes Free bytes on the download filesystem\n",
        "# TYPE p2pwatch_download_disk_free_bytes gauge\n",
        "p2pwatch_download_disk_free_bytes 500000000000.0\n",
    ]


def test_a_label_value_escapes_its_backslashes_quotes_and_newlines() -> None:
    client = NodeMetricSample(
        node_metric=NodeCounter.CLIENT_UNREACHABLE, labels=(("client", 'a\\b"c\nd'),), value=1.0
    )
    assert _lines({NodeCounter.CLIENT_UNREACHABLE: (client,)})[2] == (
        'p2pwatch_client_unreachable_total{client="a\\\\b\\"c\\nd"} 1.0\n'
    )


def test_a_metric_without_samples_writes_its_help_and_type_alone() -> None:
    assert _lines({_SEARCHES: (), NodeGauge.CRAWLER_UP: ()}) == [
        "# HELP p2pwatch_searches_total Searches performed\n",
        "# TYPE p2pwatch_searches_total counter\n",
        "# HELP p2pwatch_crawler_up Crawler running (1)\n",
        "# TYPE p2pwatch_crawler_up gauge\n",
    ]
