"""Applies a ``MetricInstruction`` to a DEDICATED Prometheus ``CollectorRegistry`` (E-D9).

ADAPTER layer (implements ``MetricsRecorder``). Catalog declared on the INJECTED registry (never
the global registry) → testable on a throwaway registry, no shared state. Two HOMOGENEOUS maps
(counters/gauges) indexed by ``MetricName`` → ``apply`` routes on ``kind``. GOTCHA: counters
are named WITHOUT ``_total`` (added by the lib at exposition time)."""

from collections.abc import Callable
from socketserver import BaseServer
from threading import Thread

from prometheus_client import CollectorRegistry, Counter, Gauge

from p2pwatch.domain.observability.policy import MetricInstruction, MetricName
from p2pwatch.ports.driven.telemetry import MetricsRecorder

# The stop runs on the event loop, where no shutdown deadline can cut a blocking call.
_JOIN_TIMEOUT_SECONDS = 1.0

# (name, doc, labels) of the counters.
_COUNTERS: tuple[tuple[MetricName, str, tuple[str, ...]], ...] = (
    (MetricName.SEARCHES, "Searches performed", ("client", "channel")),
    (
        MetricName.SEARCH_RESULTS_SKIPPED,
        "Search results the client could not read",
        ("client", "channel"),
    ),
    (MetricName.OBSERVATIONS, "Observations recorded", ("client", "channel")),
    (MetricName.SEARCH_FAILURES, "Failed searches", ("client", "channel")),
    (MetricName.CLIENT_UNREACHABLE, "Client unreachable", ("client",)),
    (MetricName.DECISIONS, "Match decisions recorded", ("tier",)),
    (MetricName.DOWNLOADS_QUEUED, "Downloads queued", ()),
    (MetricName.DOWNLOADS_COMPLETED, "Downloads completed", ()),
    (MetricName.SOURCE_ALERTS, "Sources first useful or reappeared", ("network", "kind")),
)
_GAUGES: tuple[tuple[MetricName, str, tuple[str, ...]], ...] = (
    (MetricName.CRAWLER_UP, "Crawler running (1)", ()),
    (MetricName.DISK_FREE_BYTES, "Free bytes on the download filesystem", ()),
    (MetricName.CHANNEL_CONNECTED, "Channel joined its network (1)", ("client", "channel")),
    (MetricName.CHANNEL_CONNECTABLE, "Peers can connect to the channel (1)", ("client", "channel")),
)


class PrometheusMetricsRecorder(MetricsRecorder):
    """``MetricsRecorder`` adapter over an injected dedicated registry."""

    def __init__(self, registry: CollectorRegistry) -> None:
        self._counters = {
            name: Counter(name.value, doc, labels, registry=registry)
            for name, doc, labels in _COUNTERS
        }
        self._gauges = {
            name: Gauge(name.value, doc, labels, registry=registry) for name, doc, labels in _GAUGES
        }

    def apply(self, instruction: MetricInstruction) -> None:
        labels = dict(instruction.labels)
        if instruction.operation == "inc":
            counter = self._counters[instruction.name]
            (counter.labels(**labels) if labels else counter).inc(instruction.value)
        elif instruction.operation == "set":
            gauge = self._gauges[instruction.name]
            (gauge.labels(**labels) if labels else gauge).set(instruction.value)
        else:
            self._gauges[instruction.name].remove_by_labels(labels)


def start_metrics_server(
    registry: CollectorRegistry,
    port: int | None,
    start_http_server: Callable[..., tuple[BaseServer, Thread]],
) -> Callable[[], None]:
    """Serves ``registry`` on ``/metrics`` from the daemon thread ``start_http_server`` starts,
    or nothing when ``port`` is ``None``; returns what stops it."""
    if port is None:
        return lambda: None
    server, thread = start_http_server(port, registry=registry)

    def stop() -> None:
        server.shutdown()
        server.server_close()
        thread.join(_JOIN_TIMEOUT_SECONDS)

    return stop
