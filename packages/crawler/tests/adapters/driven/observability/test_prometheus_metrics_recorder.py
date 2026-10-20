"""The metrics recorder: inc/set/remove on a throwaway CollectorRegistry (get_sample_value)."""

import socket
import threading

import httpx
import pytest
from prometheus_client import CollectorRegistry

from p2pwatch.adapters.driven.observability import prometheus_metrics_recorder
from p2pwatch.adapters.driven.observability.prometheus_metrics_recorder import (
    PrometheusMetricsRecorder,
    start_metrics_server,
)
from p2pwatch.domain.observability.events import SearchExecuted, SourceFirstUseful
from p2pwatch.domain.observability.policy import MetricInstruction, MetricName, describe
from tests.domain.observability.test_policy import CASES


def test_counter_inc_with_label() -> None:
    registry = CollectorRegistry()
    metrics_recorder = PrometheusMetricsRecorder(registry)
    labels = (("client", "amuled"), ("channel", "ed2k"))
    metrics_recorder.apply(MetricInstruction(MetricName.OBSERVATIONS, "inc", labels))
    metrics_recorder.apply(MetricInstruction(MetricName.OBSERVATIONS, "inc", labels))
    # counter exposed WITH the _total suffix added by prometheus_client
    assert registry.get_sample_value("p2pwatch_observations_total", dict(labels)) == 2.0


def test_counter_inc_no_label() -> None:
    registry = CollectorRegistry()
    PrometheusMetricsRecorder(registry).apply(
        MetricInstruction(MetricName.DOWNLOADS_COMPLETED, "inc")
    )
    assert registry.get_sample_value("p2pwatch_downloads_completed_total") == 1.0


def test_gauge_set_with_label() -> None:
    registry = CollectorRegistry()
    PrometheusMetricsRecorder(registry).apply(
        MetricInstruction(
            MetricName.CHANNEL_CONNECTABLE, "set", (("client", "amuled"), ("channel", "kad")), 1.0
        )
    )
    labels = {"client": "amuled", "channel": "kad"}
    assert registry.get_sample_value("p2pwatch_channel_connectable", labels) == 1.0


def test_gauge_set_no_label() -> None:
    registry = CollectorRegistry()
    PrometheusMetricsRecorder(registry).apply(
        MetricInstruction(MetricName.CRAWLER_UP, "set", (), 1.0)
    )
    assert registry.get_sample_value("p2pwatch_crawler_up") == 1.0


def test_a_channel_series_is_removed_while_unknown_and_only_that_one() -> None:
    registry = CollectorRegistry()
    metrics_recorder = PrometheusMetricsRecorder(registry)
    amuled = (("client", "amuled"), ("channel", "kad"))
    other = (("client", "other"), ("channel", "kad"))
    for labels in (amuled, other):
        metrics_recorder.apply(MetricInstruction(MetricName.CHANNEL_CONNECTED, "set", labels, 1.0))
        metrics_recorder.apply(
            MetricInstruction(MetricName.CHANNEL_CONNECTABLE, "set", labels, 0.0)
        )
    metrics_recorder.apply(MetricInstruction(MetricName.CHANNEL_CONNECTABLE, "remove", amuled))
    assert registry.get_sample_value("p2pwatch_channel_connectable", dict(amuled)) is None
    assert registry.get_sample_value("p2pwatch_channel_connectable", dict(other)) == 0.0
    assert registry.get_sample_value("p2pwatch_channel_connected", dict(amuled)) == 1.0


def test_removing_a_series_never_set_is_a_no_op() -> None:
    # A client unreachable from boot has no series yet.
    registry = CollectorRegistry()
    labels = (("client", "amuled"), ("channel", "ed2k"))
    PrometheusMetricsRecorder(registry).apply(
        MetricInstruction(MetricName.CHANNEL_CONNECTED, "remove", labels)
    )
    assert registry.get_sample_value("p2pwatch_channel_connected", dict(labels)) is None


def test_every_emitted_metric_is_declared_in_the_metrics_recorder() -> None:
    """STRUCTURAL guardrail: every metric that ``describe`` emits for EACH variant of the
    ``Event`` union must be declared in the metrics recorder (otherwise ``apply`` raises
    ``KeyError``). Closes the policy→recorder loop, which no pure test covered: a future event
    adding an undeclared metric makes this test fail."""
    registry = CollectorRegistry()
    metrics_recorder = PrometheusMetricsRecorder(registry)
    for event, _ in CASES:
        for instruction in describe(event).metrics:
            metrics_recorder.apply(instruction)  # must NEVER raise (declared metric)


def test_the_search_and_channel_metrics_are_labelled_by_client_and_channel() -> None:
    registry = CollectorRegistry()
    metrics_recorder = PrometheusMetricsRecorder(registry)
    labels = (("client", "amuled"), ("channel", "kad"))
    counters = (
        MetricName.SEARCHES,
        MetricName.SEARCH_RESULTS_SKIPPED,
        MetricName.OBSERVATIONS,
        MetricName.SEARCH_FAILURES,
    )
    gauges = (MetricName.CHANNEL_CONNECTED, MetricName.CHANNEL_CONNECTABLE)
    for name in counters:
        metrics_recorder.apply(MetricInstruction(name, "inc", labels))
    for name in gauges:
        metrics_recorder.apply(MetricInstruction(name, "set", labels, 1.0))
    samples = [f"{name}_total" for name in counters] + [name.value for name in gauges]
    assert [registry.get_sample_value(sample, dict(labels)) for sample in samples] == [1.0] * 6


def test_a_search_adds_its_skipped_results_under_its_client_and_channel() -> None:
    registry = CollectorRegistry()
    metrics_recorder = PrometheusMetricsRecorder(registry)
    for channel, skipped_result_count in (("ed2k", 1), ("kad", 0)):
        event = SearchExecuted("amuled", channel, 3, skipped_result_count)
        for instruction in describe(event).metrics:
            metrics_recorder.apply(instruction)
    sample = "p2pwatch_search_results_skipped_total"
    assert registry.get_sample_value(sample, {"client": "amuled", "channel": "ed2k"}) == 1.0
    assert registry.get_sample_value(sample, {"client": "amuled", "channel": "kad"}) == 0.0


def test_exposed_names() -> None:
    # Dashboards query these names.
    registry = CollectorRegistry()
    PrometheusMetricsRecorder(registry)
    assert {m.name for m in registry.collect()} == {
        "p2pwatch_searches",
        "p2pwatch_search_results_skipped",
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
    metrics_recorder = PrometheusMetricsRecorder(registry)
    event = next(event for event, _ in CASES if isinstance(event, SourceFirstUseful))
    for instruction in describe(event).metrics:
        metrics_recorder.apply(instruction)
    labels = {"network": "ed2k", "kind": "first_useful"}
    assert registry.get_sample_value("p2pwatch_source_alerts_total", labels) == 1.0


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


def test_the_metrics_server_serves_the_registry_on_its_port_until_stopped() -> None:
    registry = CollectorRegistry()
    PrometheusMetricsRecorder(registry).apply(
        MetricInstruction(MetricName.DOWNLOADS_COMPLETED, "inc")
    )
    port = _free_port()

    stop = start_metrics_server(registry, port)
    try:
        page = httpx.get(f"http://127.0.0.1:{port}/metrics").text
    finally:
        stop()

    assert "p2pwatch_downloads_completed_total 1.0" in page
    with pytest.raises(httpx.ConnectError):
        httpx.get(f"http://127.0.0.1:{port}/metrics")


def test_no_metrics_server_without_a_port() -> None:
    threads = threading.enumerate()

    stop = start_metrics_server(CollectorRegistry(), None)
    stop()

    assert threading.enumerate() == threads


class _ShutDownServer:
    def shutdown(self) -> None: ...

    def server_close(self) -> None: ...


def test_the_stop_gives_up_on_a_server_thread_that_does_not_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    released = threading.Event()
    stuck = threading.Thread(target=released.wait, daemon=True)
    stuck.start()
    monkeypatch.setattr(
        prometheus_metrics_recorder,
        "start_http_server",
        lambda port, registry: (_ShutDownServer(), stuck),
    )
    stop = start_metrics_server(CollectorRegistry(), 9090)

    stopping = threading.Thread(target=stop)
    stopping.start()
    stopping.join(timeout=5.0)
    stopped = not stopping.is_alive()
    released.set()

    assert stopped
