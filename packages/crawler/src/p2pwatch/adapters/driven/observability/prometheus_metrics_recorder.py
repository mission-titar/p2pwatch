"""Applies a ``MetricInstruction`` to a DEDICATED Prometheus ``CollectorRegistry`` (E-D9).

ADAPTER ring (implements ``MetricsRecorder``). Catalog declared on the INJECTED registry (never
the global registry) → testable on a throwaway registry, no shared state. Two HOMOGENEOUS maps
(counters/gauges) indexed by ``NodeMetricName`` → ``apply`` routes on ``kind``. GOTCHA: counters
are named WITHOUT ``_total`` (added by the lib at exposition time)."""

from collections.abc import Callable
from socketserver import BaseServer
from threading import Thread

from prometheus_client import CollectorRegistry, Counter, Gauge

from p2pwatch.application.ports.driven.metrics_recorder import MetricsRecorder
from p2pwatch.domain.observability.policy import MetricInstruction, NodeMetricName

# (name, doc, labels) of the counters.
_COUNTERS: tuple[tuple[NodeMetricName, str, tuple[str, ...]], ...] = (
    (NodeMetricName.SEARCHES, "Searches performed", ("client", "channel")),
    (
        NodeMetricName.SEARCH_RESULTS_SKIPPED,
        "Search results the client could not read",
        ("client", "channel"),
    ),
    (NodeMetricName.OBSERVATIONS, "Observations recorded", ("client", "channel")),
    (NodeMetricName.SEARCH_FAILURES, "Failed searches", ("client", "channel")),
    (NodeMetricName.CLIENT_UNREACHABLE, "Client unreachable", ("client",)),
    (NodeMetricName.DECISIONS, "Match decisions recorded", ("tier",)),
    (NodeMetricName.DOWNLOADS_QUEUED, "Downloads queued", ()),
    (NodeMetricName.DOWNLOADS_COMPLETED, "Downloads completed", ()),
    (NodeMetricName.SOURCE_ALERTS, "Sources first useful or reappeared", ("network", "kind")),
)
_GAUGES: tuple[tuple[NodeMetricName, str, tuple[str, ...]], ...] = (
    (NodeMetricName.CRAWLER_UP, "Crawler running (1)", ()),
    (NodeMetricName.DISK_FREE_BYTES, "Free bytes on the download filesystem", ()),
    (NodeMetricName.CHANNEL_CONNECTED, "Channel joined its network (1)", ("client", "channel")),
    (
        NodeMetricName.CHANNEL_CONNECTABLE,
        "Peers can connect to the channel (1)",
        ("client", "channel"),
    ),
)


class PrometheusMetricsRecorder(MetricsRecorder):
    """``MetricsRecorder`` adapter over an injected dedicated registry."""

    def __init__(self, registry: CollectorRegistry) -> None:
        self._counters = {
            name: Counter(name.value, documentation, labels, registry=registry)
            for name, documentation, labels in _COUNTERS
        }
        self._gauges = {
            name: Gauge(name.value, documentation, labels, registry=registry)
            for name, documentation, labels in _GAUGES
        }

    def apply(self, instruction: MetricInstruction) -> None:
        labels = dict(instruction.labels)
        if instruction.operation == "inc":
            counter = self._counters[instruction.name]
            (counter.labels(**labels) if labels else counter).inc(instruction.amount)
        elif instruction.operation == "set":
            gauge = self._gauges[instruction.name]
            (gauge.labels(**labels) if labels else gauge).set(instruction.amount)
        else:
            self._gauges[instruction.name].remove_by_labels(labels)


def start_metrics_server(
    registry: CollectorRegistry,
    port: int | None,
    start_http_server: Callable[..., tuple[BaseServer, Thread]],
    *,
    join_timeout_seconds: float,
) -> Callable[[], None]:
    """Serves ``registry`` on ``/metrics`` from the daemon thread ``start_http_server`` starts,
    or nothing when ``port`` is ``None``; returns what stops it."""
    if port is None:
        return lambda: None
    server, thread = start_http_server(port, registry=registry)

    def stop() -> None:
        server.shutdown()
        server.server_close()
        thread.join(join_timeout_seconds)

    return stop
