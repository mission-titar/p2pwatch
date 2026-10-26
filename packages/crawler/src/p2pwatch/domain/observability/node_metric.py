"""The catalog of node metrics, and the two instructions the observability policy writes to them.

A counter's name has no ``_total``: its exposition adds it (``p2pwatch_searches_total``).
"""

from dataclasses import dataclass
from enum import Enum, StrEnum


class NodeMetricKind(Enum):
    COUNTER = "counter"
    GAUGE = "gauge"


class NodeMetricName(StrEnum):
    """A node metric, whose kind, description and label names are the catalog's."""

    SEARCHES = "p2pwatch_searches"
    SEARCH_RESULTS_SKIPPED = "p2pwatch_search_results_skipped"
    OBSERVATIONS = "p2pwatch_observations"
    SEARCH_FAILURES = "p2pwatch_search_failures"
    CLIENT_UNREACHABLE = "p2pwatch_client_unreachable"
    DECISIONS = "p2pwatch_decisions"
    DOWNLOADS_QUEUED = "p2pwatch_downloads_queued"
    DOWNLOADS_COMPLETED = "p2pwatch_downloads_completed"
    DISK_FREE_BYTES = "p2pwatch_download_disk_free_bytes"
    CRAWLER_UP = "p2pwatch_crawler_up"
    CHANNEL_CONNECTED = "p2pwatch_channel_connected"
    CHANNEL_CONNECTABLE = "p2pwatch_channel_connectable"
    SOURCE_ALERTS = "p2pwatch_source_alerts"

    @property
    def kind(self) -> NodeMetricKind:
        return _METADATA_BY_NAME[self].kind

    @property
    def description(self) -> str:
        return _METADATA_BY_NAME[self].description

    @property
    def label_names(self) -> tuple[str, ...]:
        """The names of its labels, in the order an instruction gives them."""
        return _METADATA_BY_NAME[self].label_names


@dataclass(frozen=True)
class _NodeMetricMetadata:
    kind: NodeMetricKind
    description: str
    label_names: tuple[str, ...]


_COUNTER = NodeMetricKind.COUNTER
_GAUGE = NodeMetricKind.GAUGE
_CLIENT_CHANNEL = ("client", "channel")
_METADATA_BY_NAME: dict[NodeMetricName, _NodeMetricMetadata] = {
    NodeMetricName.SEARCHES: _NodeMetricMetadata(_COUNTER, "Searches performed", _CLIENT_CHANNEL),
    NodeMetricName.SEARCH_RESULTS_SKIPPED: _NodeMetricMetadata(
        _COUNTER, "Search results the client could not read", _CLIENT_CHANNEL
    ),
    NodeMetricName.OBSERVATIONS: _NodeMetricMetadata(
        _COUNTER, "Observations recorded", _CLIENT_CHANNEL
    ),
    NodeMetricName.SEARCH_FAILURES: _NodeMetricMetadata(
        _COUNTER, "Failed searches", _CLIENT_CHANNEL
    ),
    NodeMetricName.CLIENT_UNREACHABLE: _NodeMetricMetadata(
        _COUNTER, "Client unreachable", ("client",)
    ),
    NodeMetricName.DECISIONS: _NodeMetricMetadata(_COUNTER, "Match decisions recorded", ("tier",)),
    NodeMetricName.DOWNLOADS_QUEUED: _NodeMetricMetadata(_COUNTER, "Downloads queued", ()),
    NodeMetricName.DOWNLOADS_COMPLETED: _NodeMetricMetadata(_COUNTER, "Downloads completed", ()),
    NodeMetricName.SOURCE_ALERTS: _NodeMetricMetadata(
        _COUNTER, "Sources first useful or reappeared", ("network", "kind")
    ),
    NodeMetricName.CRAWLER_UP: _NodeMetricMetadata(_GAUGE, "Crawler running (1)", ()),
    NodeMetricName.DISK_FREE_BYTES: _NodeMetricMetadata(
        _GAUGE, "Free bytes on the download filesystem", ()
    ),
    NodeMetricName.CHANNEL_CONNECTED: _NodeMetricMetadata(
        _GAUGE, "Channel joined its network (1)", _CLIENT_CHANNEL
    ),
    NodeMetricName.CHANNEL_CONNECTABLE: _NodeMetricMetadata(
        _GAUGE, "Peers can connect to the channel (1)", _CLIENT_CHANNEL
    ),
}


def _refuse_unless_it_fits(
    name: NodeMetricName, kind: NodeMetricKind, labels: tuple[tuple[str, str], ...]
) -> None:
    if name.kind is not kind:
        raise ValueError(f"{name} is a {name.kind.value}, not a {kind.value}")
    label_names = tuple(label_name for label_name, _ in labels)
    if label_names != name.label_names:
        raise ValueError(f"{name} takes the labels {name.label_names}, not {label_names}")


@dataclass(frozen=True)
class CounterIncrement:
    """Adds ``amount`` to the series of the counter ``name`` that ``labels`` names; a gauge, or
    label names other than the counter's in its order, raise ``ValueError``."""

    name: NodeMetricName
    labels: tuple[tuple[str, str], ...] = ()
    amount: float = 1.0

    def __post_init__(self) -> None:
        _refuse_unless_it_fits(self.name, NodeMetricKind.COUNTER, self.labels)


@dataclass(frozen=True)
class GaugeSetting:
    """Sets the series of the gauge ``name`` that ``labels`` names to ``value``, or removes it
    when ``value`` is ``None``; a counter, or label names other than the gauge's in its order,
    raise ``ValueError``."""

    name: NodeMetricName
    labels: tuple[tuple[str, str], ...]
    value: float | None

    def __post_init__(self) -> None:
        _refuse_unless_it_fits(self.name, NodeMetricKind.GAUGE, self.labels)
