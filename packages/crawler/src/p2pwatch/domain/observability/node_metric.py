"""The node counters and gauges, and the two instructions the observability policy writes to them.

A counter's name has no ``_total``: its exposition adds it (``p2pwatch_searches_total``).
"""

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class _Declaration:
    exposed_name: str
    description: str
    label_names: tuple[str, ...]


class NodeMetric(Enum):
    """A node metric, declared with the name it is exposed under, its description and the names of
    its labels, in the order an instruction gives them."""

    _value_: _Declaration

    @property
    def exposed_name(self) -> str:
        return self.value.exposed_name

    @property
    def description(self) -> str:
        return self.value.description

    @property
    def label_names(self) -> tuple[str, ...]:
        return self.value.label_names


_CLIENT_CHANNEL = ("client", "channel")


class NodeCounter(NodeMetric):
    SEARCHES = _Declaration("p2pwatch_searches", "Searches performed", _CLIENT_CHANNEL)
    SEARCH_RESULTS_SKIPPED = _Declaration(
        "p2pwatch_search_results_skipped",
        "Search results the client could not read",
        _CLIENT_CHANNEL,
    )
    OBSERVATIONS = _Declaration("p2pwatch_observations", "Observations recorded", _CLIENT_CHANNEL)
    SEARCH_FAILURES = _Declaration("p2pwatch_search_failures", "Failed searches", _CLIENT_CHANNEL)
    CLIENT_UNREACHABLE = _Declaration(
        "p2pwatch_client_unreachable", "Client unreachable", ("client",)
    )
    DECISIONS = _Declaration("p2pwatch_decisions", "Match decisions recorded", ("tier",))
    DOWNLOADS_QUEUED = _Declaration("p2pwatch_downloads_queued", "Downloads queued", ())
    DOWNLOADS_COMPLETED = _Declaration("p2pwatch_downloads_completed", "Downloads completed", ())
    SOURCE_ALERTS = _Declaration(
        "p2pwatch_source_alerts", "Sources first useful or reappeared", ("network", "kind")
    )


class NodeGauge(NodeMetric):
    CRAWLER_UP = _Declaration("p2pwatch_crawler_up", "Crawler running (1)", ())
    DISK_FREE_BYTES = _Declaration(
        "p2pwatch_download_disk_free_bytes", "Free bytes on the download filesystem", ()
    )
    CHANNEL_CONNECTED = _Declaration(
        "p2pwatch_channel_connected", "Channel joined its network (1)", _CLIENT_CHANNEL
    )
    CHANNEL_CONNECTABLE = _Declaration(
        "p2pwatch_channel_connectable", "Peers can connect to the channel (1)", _CLIENT_CHANNEL
    )


def _refuse_unless_it_fits(node_metric: NodeMetric, labels: tuple[tuple[str, str], ...]) -> None:
    label_names = tuple(label_name for label_name, _ in labels)
    if label_names != node_metric.label_names:
        raise ValueError(
            f"{node_metric.exposed_name} takes the labels {node_metric.label_names}, "
            f"not {label_names}"
        )


@dataclass(frozen=True)
class CounterIncrement:
    """Adds ``amount`` to the series of ``counter`` that ``labels`` names; label names other than
    the counter's, in its order, raise ``ValueError``."""

    counter: NodeCounter
    labels: tuple[tuple[str, str], ...] = ()
    amount: float = 1.0

    def __post_init__(self) -> None:
        _refuse_unless_it_fits(self.counter, self.labels)


@dataclass(frozen=True)
class GaugeSetting:
    """Sets the series of ``gauge`` that ``labels`` names to ``value``, or removes it when
    ``value`` is ``None``; label names other than the gauge's, in its order, raise
    ``ValueError``."""

    gauge: NodeGauge
    labels: tuple[tuple[str, str], ...]
    value: float | None

    def __post_init__(self) -> None:
        _refuse_unless_it_fits(self.gauge, self.labels)
