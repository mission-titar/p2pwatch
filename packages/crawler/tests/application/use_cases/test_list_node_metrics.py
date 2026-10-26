"""``ListNodeMetrics``: every node metric of the catalog, with the samples the store holds."""

from p2pwatch.application.use_cases.list_node_metrics import ListNodeMetrics
from p2pwatch.domain.observability.node_metric import (
    CounterIncrement,
    NodeCounter,
    NodeGauge,
    NodeMetricSample,
)
from tests.fakes.adapters.driven.fake_node_metric_store import FakeNodeMetricStore

_DOWNLOAD_TIER = (("tier", "download"),)


def test_lists_every_node_metric_once_in_the_catalogs_order() -> None:
    node_metric_listing = ListNodeMetrics(FakeNodeMetricStore()).list_node_metrics()
    assert tuple(node_metric_listing.samples_by_node_metric) == (*NodeCounter, *NodeGauge)


def test_an_unlabelled_metric_never_written_has_one_sample_at_zero() -> None:
    node_metric_listing = ListNodeMetrics(FakeNodeMetricStore()).list_node_metrics()
    assert node_metric_listing.samples_by_node_metric[NodeCounter.DOWNLOADS_QUEUED] == (
        NodeMetricSample(NodeCounter.DOWNLOADS_QUEUED, (), 0.0),
    )


def test_a_labelled_metric_lists_the_samples_written_and_none_before() -> None:
    node_metric_store = FakeNodeMetricStore()
    node_metric_store.record_increment(CounterIncrement(NodeCounter.DECISIONS, _DOWNLOAD_TIER))
    samples_by_node_metric = (
        ListNodeMetrics(node_metric_store).list_node_metrics().samples_by_node_metric
    )
    assert samples_by_node_metric[NodeCounter.DECISIONS] == (
        NodeMetricSample(NodeCounter.DECISIONS, _DOWNLOAD_TIER, 1.0),
    )
    assert samples_by_node_metric[NodeCounter.SEARCHES] == ()
