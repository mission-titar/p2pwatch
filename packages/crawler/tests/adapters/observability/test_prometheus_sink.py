"""Prometheus sink: inc/set/remove on a throwaway CollectorRegistry (get_sample_value)."""

from prometheus_client import CollectorRegistry

from p2pwatch.adapters.observability.prometheus_sink import PrometheusSink
from p2pwatch.domain.observability.events import SourceFirstUseful
from p2pwatch.domain.observability.policy import MetricInstruction, MetricName, describe
from tests.domain.observability.test_policy import CASES


def test_counter_inc_with_label() -> None:
    registry = CollectorRegistry()
    sink = PrometheusSink(registry)
    labels = (("client", "amuled"), ("channel", "ed2k"))
    sink.apply(MetricInstruction(MetricName.OBSERVATIONS, "inc", labels))
    sink.apply(MetricInstruction(MetricName.OBSERVATIONS, "inc", labels))
    # counter exposed WITH the _total suffix added by prometheus_client
    assert registry.get_sample_value("p2pwatch_observations_total", dict(labels)) == 2.0


def test_counter_inc_no_label() -> None:
    registry = CollectorRegistry()
    PrometheusSink(registry).apply(MetricInstruction(MetricName.DOWNLOADS_COMPLETED, "inc"))
    assert registry.get_sample_value("p2pwatch_downloads_completed_total") == 1.0


def test_gauge_set_with_label() -> None:
    registry = CollectorRegistry()
    PrometheusSink(registry).apply(
        MetricInstruction(
            MetricName.CHANNEL_CONNECTABLE, "set", (("client", "amuled"), ("channel", "kad")), 1.0
        )
    )
    labels = {"client": "amuled", "channel": "kad"}
    assert registry.get_sample_value("p2pwatch_channel_connectable", labels) == 1.0


def test_gauge_set_no_label() -> None:
    registry = CollectorRegistry()
    PrometheusSink(registry).apply(MetricInstruction(MetricName.CRAWLER_UP, "set", (), 1.0))
    assert registry.get_sample_value("p2pwatch_crawler_up") == 1.0


def test_a_channel_series_is_removed_while_unknown_and_only_that_one() -> None:
    registry = CollectorRegistry()
    sink = PrometheusSink(registry)
    amuled = (("client", "amuled"), ("channel", "kad"))
    other = (("client", "other"), ("channel", "kad"))
    for labels in (amuled, other):
        sink.apply(MetricInstruction(MetricName.CHANNEL_CONNECTED, "set", labels, 1.0))
        sink.apply(MetricInstruction(MetricName.CHANNEL_CONNECTABLE, "set", labels, 0.0))
    sink.apply(MetricInstruction(MetricName.CHANNEL_CONNECTABLE, "remove", amuled))
    assert registry.get_sample_value("p2pwatch_channel_connectable", dict(amuled)) is None
    assert registry.get_sample_value("p2pwatch_channel_connectable", dict(other)) == 0.0
    assert registry.get_sample_value("p2pwatch_channel_connected", dict(amuled)) == 1.0


def test_removing_a_series_never_set_is_a_no_op() -> None:
    # A client unreachable from boot has no series yet.
    registry = CollectorRegistry()
    labels = (("client", "amuled"), ("channel", "ed2k"))
    PrometheusSink(registry).apply(
        MetricInstruction(MetricName.CHANNEL_CONNECTED, "remove", labels)
    )
    assert registry.get_sample_value("p2pwatch_channel_connected", dict(labels)) is None


def test_every_emitted_metric_is_declared_in_the_sink() -> None:
    """STRUCTURAL guardrail: every metric that ``describe`` emits for EACH variant of the
    ``Event`` union must be declared in the sink (otherwise ``apply`` raises ``KeyError``). Closes
    the policy→sink loop, which no pure test covered: a future event adding an undeclared metric
    makes this test fail."""
    registry = CollectorRegistry()
    sink = PrometheusSink(registry)
    for event, _ in CASES:
        for instruction in describe(event).metrics:
            sink.apply(instruction)  # must NEVER raise (declared metric)


def test_the_search_and_channel_metrics_are_labelled_by_client_and_channel() -> None:
    registry = CollectorRegistry()
    sink = PrometheusSink(registry)
    labels = (("client", "amuled"), ("channel", "kad"))
    counters = (MetricName.SEARCHES, MetricName.OBSERVATIONS, MetricName.SEARCH_FAILURES)
    gauges = (MetricName.CHANNEL_CONNECTED, MetricName.CHANNEL_CONNECTABLE)
    for name in counters:
        sink.apply(MetricInstruction(name, "inc", labels))
    for name in gauges:
        sink.apply(MetricInstruction(name, "set", labels, 1.0))
    samples = [f"{name}_total" for name in counters] + [name.value for name in gauges]
    assert [registry.get_sample_value(sample, dict(labels)) for sample in samples] == [1.0] * 5


def test_exposed_names() -> None:
    # Dashboards query these names.
    registry = CollectorRegistry()
    PrometheusSink(registry)
    assert {m.name for m in registry.collect()} == {
        "p2pwatch_searches",
        "p2pwatch_observations",
        "p2pwatch_search_failures",
        "p2pwatch_client_unreachable",
        "p2pwatch_decisions",
        "p2pwatch_downloads_queued",
        "p2pwatch_downloads_completed",
        "p2pwatch_download_disk_free_bytes",
        "p2pwatch_crawler_up",
        "p2pwatch_channel_connected",
        "p2pwatch_channel_connectable",
        "p2pwatch_source_alerts",
    }


def test_a_first_useful_alert_counts_under_its_network_and_kind() -> None:
    registry = CollectorRegistry()
    sink = PrometheusSink(registry)
    event = next(event for event, _ in CASES if isinstance(event, SourceFirstUseful))
    for instruction in describe(event).metrics:
        sink.apply(instruction)
    labels = {"network": "ed2k", "kind": "first_useful"}
    assert registry.get_sample_value("p2pwatch_source_alerts_total", labels) == 1.0
