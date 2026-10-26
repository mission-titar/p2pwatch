"""The node counters and gauges, their typed labels, and the two instructions the observability
policy writes to them.

A counter's name has no ``_total``: its exposition adds it (``p2pwatch_searches_total``).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import ClassVar, Literal

from catalog_matching.domain.decision_tier import DecisionTier
from p2pwatch.domain.file_key import Network
from p2pwatch.domain.observability.notification import SourceAlertKind


class NodeMetricLabels(ABC):
    """The labels of one series of a node metric."""

    names: ClassVar[tuple[str, ...]]

    @abstractmethod
    def texts(self) -> tuple[str, ...]:
        """Its labels' values as the exposition writes them, in the order of ``names``."""

    def pairs(self) -> tuple[tuple[str, str], ...]:
        return tuple(zip(self.names, self.texts(), strict=True))


@dataclass(frozen=True)
class ChannelLabels(NodeMetricLabels):
    names = ("client", "channel")
    client_name: str
    channel: str

    def texts(self) -> tuple[str, ...]:
        return (self.client_name, self.channel)


@dataclass(frozen=True)
class ClientLabels(NodeMetricLabels):
    names = ("client",)
    client_name: str

    def texts(self) -> tuple[str, ...]:
        return (self.client_name,)


@dataclass(frozen=True)
class DecisionLabels(NodeMetricLabels):
    names = ("tier",)
    tier: DecisionTier | Literal["retracted"]

    def texts(self) -> tuple[str, ...]:
        return (str(self.tier),)


@dataclass(frozen=True)
class SourceAlertLabels(NodeMetricLabels):
    names = ("network", "kind")
    network: Network
    kind: SourceAlertKind

    def texts(self) -> tuple[str, ...]:
        return (self.network.value, self.kind.value)


@dataclass(frozen=True)
class _Declaration:
    exposed_name: str
    description: str
    label_class: type[NodeMetricLabels] | None


class NodeMetric(Enum):
    """A node metric, declared with the name it is exposed under, its description and the class of
    its labels, ``None`` for an unlabelled one."""

    _value_: _Declaration

    @property
    def exposed_name(self) -> str:
        return self.value.exposed_name

    @property
    def description(self) -> str:
        return self.value.description

    @property
    def label_class(self) -> type[NodeMetricLabels] | None:
        return self.value.label_class

    @property
    def label_names(self) -> tuple[str, ...]:
        return () if self.label_class is None else self.label_class.names


class NodeCounter(NodeMetric):
    SEARCHES = _Declaration("p2pwatch_searches", "Searches performed", ChannelLabels)
    SEARCH_RESULTS_SKIPPED = _Declaration(
        "p2pwatch_search_results_skipped", "Search results the client could not read", ChannelLabels
    )
    OBSERVATIONS = _Declaration("p2pwatch_observations", "Observations recorded", ChannelLabels)
    SEARCH_FAILURES = _Declaration("p2pwatch_search_failures", "Failed searches", ChannelLabels)
    CLIENT_UNREACHABLE = _Declaration(
        "p2pwatch_client_unreachable", "Client unreachable", ClientLabels
    )
    DECISIONS = _Declaration("p2pwatch_decisions", "Match decisions recorded", DecisionLabels)
    DOWNLOADS_QUEUED = _Declaration("p2pwatch_downloads_queued", "Downloads queued", None)
    DOWNLOADS_COMPLETED = _Declaration("p2pwatch_downloads_completed", "Downloads completed", None)
    SOURCE_ALERTS = _Declaration(
        "p2pwatch_source_alerts", "Sources first useful or reappeared", SourceAlertLabels
    )


class NodeGauge(NodeMetric):
    CRAWLER_UP = _Declaration("p2pwatch_crawler_up", "Crawler running (1)", None)
    DISK_FREE_BYTES = _Declaration(
        "p2pwatch_download_disk_free_bytes", "Free bytes on the download filesystem", None
    )
    CHANNEL_CONNECTED = _Declaration(
        "p2pwatch_channel_connected", "Channel joined its network (1)", ChannelLabels
    )
    CHANNEL_CONNECTABLE = _Declaration(
        "p2pwatch_channel_connectable", "Peers can connect to the channel (1)", ChannelLabels
    )


def _labels_name(label_class: type[NodeMetricLabels] | None) -> str:
    return "no labels" if label_class is None else label_class.__name__


def _pairs(labels: NodeMetricLabels | None) -> tuple[tuple[str, str], ...]:
    return () if labels is None else labels.pairs()


def _refuse_unless_it_fits(node_metric: NodeMetric, labels: NodeMetricLabels | None) -> None:
    given = None if labels is None else type(labels)
    if given is not node_metric.label_class:
        raise ValueError(
            f"{node_metric.exposed_name} takes {_labels_name(node_metric.label_class)}, "
            f"given {_labels_name(given)}"
        )


@dataclass(frozen=True)
class CounterIncrement:
    """Adds ``amount`` to the series of ``counter`` that ``labels`` names; labels of another class
    than the counter's raise ``ValueError``."""

    counter: NodeCounter
    labels: NodeMetricLabels | None = None
    amount: float = 1.0

    def __post_init__(self) -> None:
        _refuse_unless_it_fits(self.counter, self.labels)

    def label_pairs(self) -> tuple[tuple[str, str], ...]:
        """Its labels' ``(name, text)`` pairs, none when it has no labels."""
        return _pairs(self.labels)


@dataclass(frozen=True)
class GaugeSetting:
    """Sets the series of ``gauge`` that ``labels`` names to ``value``, or removes it when
    ``value`` is ``None``; labels of another class than the gauge's raise ``ValueError``."""

    gauge: NodeGauge
    labels: NodeMetricLabels | None
    value: float | None

    def __post_init__(self) -> None:
        _refuse_unless_it_fits(self.gauge, self.labels)

    def label_pairs(self) -> tuple[tuple[str, str], ...]:
        """Its labels' ``(name, text)`` pairs, none when it has no labels."""
        return _pairs(self.labels)


@dataclass(frozen=True)
class NodeMetricSample:
    """One series of ``node_metric``, its labels' ``(name, text)`` pairs in the catalog's order, and
    its value."""

    node_metric: NodeCounter | NodeGauge
    labels: tuple[tuple[str, str], ...]
    value: float
