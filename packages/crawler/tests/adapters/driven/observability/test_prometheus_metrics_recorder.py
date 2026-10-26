"""The metrics recorder: inc/set/remove on a throwaway CollectorRegistry (get_sample_value)."""

import socket
import socketserver
import threading

import httpx
import pytest
from prometheus_client import CollectorRegistry, start_http_server

from p2pwatch.adapters.driven.observability.prometheus_metrics_recorder import (
    PrometheusMetricsRecorder,
    start_metrics_server,
)
from p2pwatch.domain.observability.events import SearchExecuted, SourceFirstUseful
from p2pwatch.domain.observability.node_metric import (
    CounterIncrement,
    GaugeSetting,
    NodeCounter,
    NodeGauge,
)
from p2pwatch.domain.observability.policy import plan_observability
from tests.domain.observability.test_policy import CASES
from tests.fakes.adapters.driven.fake_metrics_server import FakeMetricsServer


def test_counter_inc_with_label() -> None:
    registry = CollectorRegistry()
    metrics_recorder = PrometheusMetricsRecorder(registry)
    labels = (("client", "amuled"), ("channel", "ed2k"))
    metrics_recorder.apply(CounterIncrement(NodeCounter.OBSERVATIONS, labels))
    metrics_recorder.apply(CounterIncrement(NodeCounter.OBSERVATIONS, labels))
    # counter exposed WITH the _total suffix added by prometheus_client
    assert registry.get_sample_value("p2pwatch_observations_total", dict(labels)) == 2.0


def test_counter_inc_no_label() -> None:
    registry = CollectorRegistry()
    PrometheusMetricsRecorder(registry).apply(CounterIncrement(NodeCounter.DOWNLOADS_COMPLETED))
    assert registry.get_sample_value("p2pwatch_downloads_completed_total") == 1.0


def test_gauge_set_with_label() -> None:
    registry = CollectorRegistry()
    PrometheusMetricsRecorder(registry).apply(
        GaugeSetting(
            NodeGauge.CHANNEL_CONNECTABLE,
            (("client", "amuled"), ("channel", "kad")),
            1.0,
        )
    )
    labels = {"client": "amuled", "channel": "kad"}
    assert registry.get_sample_value("p2pwatch_channel_connectable", labels) == 1.0


def test_gauge_set_no_label() -> None:
    registry = CollectorRegistry()
    PrometheusMetricsRecorder(registry).apply(GaugeSetting(NodeGauge.CRAWLER_UP, (), 1.0))
    assert registry.get_sample_value("p2pwatch_crawler_up") == 1.0


def test_a_channel_series_is_removed_while_unknown_and_only_that_one() -> None:
    registry = CollectorRegistry()
    metrics_recorder = PrometheusMetricsRecorder(registry)
    amuled = (("client", "amuled"), ("channel", "kad"))
    other = (("client", "other"), ("channel", "kad"))
    for labels in (amuled, other):
        metrics_recorder.apply(GaugeSetting(NodeGauge.CHANNEL_CONNECTED, labels, 1.0))
        metrics_recorder.apply(GaugeSetting(NodeGauge.CHANNEL_CONNECTABLE, labels, 0.0))
    metrics_recorder.apply(GaugeSetting(NodeGauge.CHANNEL_CONNECTABLE, amuled, None))
    assert registry.get_sample_value("p2pwatch_channel_connectable", dict(amuled)) is None
    assert registry.get_sample_value("p2pwatch_channel_connectable", dict(other)) == 0.0
    assert registry.get_sample_value("p2pwatch_channel_connected", dict(amuled)) == 1.0


def test_removing_a_series_never_set_is_a_no_op() -> None:
    # A client unreachable from boot has no series yet.
    registry = CollectorRegistry()
    labels = (("client", "amuled"), ("channel", "ed2k"))
    PrometheusMetricsRecorder(registry).apply(
        GaugeSetting(NodeGauge.CHANNEL_CONNECTED, labels, None)
    )
    assert registry.get_sample_value("p2pwatch_channel_connected", dict(labels)) is None


def test_the_search_and_channel_metrics_are_labelled_by_client_and_channel() -> None:
    registry = CollectorRegistry()
    metrics_recorder = PrometheusMetricsRecorder(registry)
    labels = (("client", "amuled"), ("channel", "kad"))
    counters = (
        NodeCounter.SEARCHES,
        NodeCounter.SEARCH_RESULTS_SKIPPED,
        NodeCounter.OBSERVATIONS,
        NodeCounter.SEARCH_FAILURES,
    )
    gauges = (NodeGauge.CHANNEL_CONNECTED, NodeGauge.CHANNEL_CONNECTABLE)
    for counter in counters:
        metrics_recorder.apply(CounterIncrement(counter, labels))
    for gauge in gauges:
        metrics_recorder.apply(GaugeSetting(gauge, labels, 1.0))
    samples = [f"{counter.exposed_name}_total" for counter in counters] + [
        gauge.exposed_name for gauge in gauges
    ]
    assert [registry.get_sample_value(sample, dict(labels)) for sample in samples] == [1.0] * 6


def test_a_search_adds_its_skipped_results_under_its_client_and_channel() -> None:
    registry = CollectorRegistry()
    metrics_recorder = PrometheusMetricsRecorder(registry)
    for channel, skipped_result_count in (("ed2k", 1), ("kad", 0)):
        event = SearchExecuted("amuled", channel, 3, skipped_result_count)
        for instruction in plan_observability(event).node_metrics:
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
    for instruction in plan_observability(event).node_metrics:
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
    PrometheusMetricsRecorder(registry).apply(CounterIncrement(NodeCounter.DOWNLOADS_COMPLETED))
    port = _free_port()

    stop = start_metrics_server(registry, port, start_http_server, join_timeout_seconds=1.0)
    try:
        page = httpx.get(f"http://127.0.0.1:{port}/metrics").text
    finally:
        stop()

    assert "p2pwatch_downloads_completed_total 1.0" in page
    with pytest.raises(httpx.ConnectError):
        httpx.get(f"http://127.0.0.1:{port}/metrics")


def test_no_metrics_server_without_a_port() -> None:
    threads = threading.enumerate()

    stop = start_metrics_server(
        CollectorRegistry(), None, start_http_server, join_timeout_seconds=1.0
    )
    stop()

    assert threading.enumerate() == threads


def test_the_stop_gives_up_on_a_server_thread_that_does_not_end_within_its_join_timeout() -> None:
    released = threading.Event()
    stuck = threading.Thread(target=released.wait, daemon=True)
    stuck.start()
    server = FakeMetricsServer(("127.0.0.1", 9090), socketserver.BaseRequestHandler)
    stop = start_metrics_server(
        CollectorRegistry(),
        9090,
        lambda port, registry: (server, stuck),
        join_timeout_seconds=0.05,
    )

    stopping = threading.Thread(target=stop)
    stopping.start()
    stopping.join(timeout=1.0)
    stopped = not stopping.is_alive()
    released.set()

    assert stopped
