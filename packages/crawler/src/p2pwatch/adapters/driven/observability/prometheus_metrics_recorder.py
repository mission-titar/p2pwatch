"""Applies a ``CounterIncrement`` or a ``GaugeSetting`` to a DEDICATED Prometheus
``CollectorRegistry`` (E-D9).

ADAPTER ring (implements ``MetricsRecorder``). The domain's catalog of node metrics is declared on
the INJECTED registry (never the global registry) → testable on a throwaway registry, no shared
state."""

from collections.abc import Callable
from socketserver import BaseServer
from threading import Thread

from prometheus_client import CollectorRegistry, Counter, Gauge

from p2pwatch.application.ports.driven.metrics_recorder import MetricsRecorder
from p2pwatch.domain.observability.node_metric import (
    CounterIncrement,
    GaugeSetting,
    NodeMetricKind,
    NodeMetricName,
)


class PrometheusMetricsRecorder(MetricsRecorder):
    """``MetricsRecorder`` adapter over an injected dedicated registry."""

    def __init__(self, registry: CollectorRegistry) -> None:
        self._counters = {
            name: Counter(name.value, name.description, name.label_names, registry=registry)
            for name in NodeMetricName
            if name.kind is NodeMetricKind.COUNTER
        }
        self._gauges = {
            name: Gauge(name.value, name.description, name.label_names, registry=registry)
            for name in NodeMetricName
            if name.kind is NodeMetricKind.GAUGE
        }

    def apply(self, instruction: CounterIncrement | GaugeSetting) -> None:
        labels = dict(instruction.labels)
        if isinstance(instruction, CounterIncrement):
            counter = self._counters[instruction.name]
            (counter.labels(**labels) if labels else counter).inc(instruction.amount)
        elif instruction.value is None:
            self._gauges[instruction.name].remove_by_labels(labels)
        else:
            gauge = self._gauges[instruction.name]
            (gauge.labels(**labels) if labels else gauge).set(instruction.value)


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
