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
from p2pwatch.domain.identifiers import Channel, ClientName
from p2pwatch.domain.observability.notification import SourceAlertKind


class NodeMetricLabels(ABC):
    """The labels of one series of a node metric."""

    names: ClassVar[tuple[str, ...]]

    @abstractmethod
    def texts(self) -> tuple[str, ...]:
        """Its labels' values as the exposition writes them, in the order of ``names``."""

    def pairs(self) -> tuple[tuple[str, str], ...]:
        return tuple(zip(self.names, self.texts(), strict=True))


@dataclass(kw_only=True, frozen=True)
class ChannelLabels(NodeMetricLabels):
    names = ("client", "channel")
    client_name: ClientName
    channel: Channel

    def texts(self) -> tuple[str, ...]:
        return (self.client_name, self.channel)


@dataclass(kw_only=True, frozen=True)
class ClientLabels(NodeMetricLabels):
    names = ("client",)
    client_name: ClientName

    def texts(self) -> tuple[str, ...]:
        return (self.client_name,)


@dataclass(kw_only=True, frozen=True)
class DecisionLabels(NodeMetricLabels):
    names = ("tier",)
    tier: DecisionTier | Literal["retracted"]

    def texts(self) -> tuple[str, ...]:
        return (str(self.tier),)


@dataclass(kw_only=True, frozen=True)
class SourceAlertLabels(NodeMetricLabels):
    names = ("network", "kind")
    network: Network
    kind: SourceAlertKind

    def texts(self) -> tuple[str, ...]:
        return (self.network.value, self.kind.value)


@dataclass(kw_only=True, frozen=True)
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
    SEARCHES = _Declaration(
        exposed_name="p2pwatch_searches",
        description="Searches performed",
        label_class=ChannelLabels,
    )
    SEARCH_RESULTS_SKIPPED = _Declaration(
        exposed_name="p2pwatch_search_results_skipped",
        description="Search results the client could not read",
        label_class=ChannelLabels,
    )
    OBSERVATIONS = _Declaration(
        exposed_name="p2pwatch_observations",
        description="Observations recorded",
        label_class=ChannelLabels,
    )
    SEARCH_FAILURES = _Declaration(
        exposed_name="p2pwatch_search_failures",
        description="Failed searches",
        label_class=ChannelLabels,
    )
    CLIENT_UNREACHABLE = _Declaration(
        exposed_name="p2pwatch_client_unreachable",
        description="Client unreachable",
        label_class=ClientLabels,
    )
    DECISIONS = _Declaration(
        exposed_name="p2pwatch_decisions",
        description="Match decisions recorded",
        label_class=DecisionLabels,
    )
    DOWNLOADS_QUEUED = _Declaration(
        exposed_name="p2pwatch_downloads_queued", description="Downloads queued", label_class=None
    )
    DOWNLOADS_COMPLETED = _Declaration(
        exposed_name="p2pwatch_downloads_completed",
        description="Downloads completed",
        label_class=None,
    )
    SOURCE_ALERTS = _Declaration(
        exposed_name="p2pwatch_source_alerts",
        description="Sources first useful or reappeared",
        label_class=SourceAlertLabels,
    )


class NodeGauge(NodeMetric):
    CRAWLER_UP = _Declaration(
        exposed_name="p2pwatch_crawler_up", description="Crawler running (1)", label_class=None
    )
    DISK_FREE_BYTES = _Declaration(
        exposed_name="p2pwatch_download_disk_free_bytes",
        description="Free bytes on the download filesystem",
        label_class=None,
    )
    CHANNEL_CONNECTED = _Declaration(
        exposed_name="p2pwatch_channel_connected",
        description="Channel joined its network (1)",
        label_class=ChannelLabels,
    )
    CHANNEL_CONNECTABLE = _Declaration(
        exposed_name="p2pwatch_channel_connectable",
        description="Peers can connect to the channel (1)",
        label_class=ChannelLabels,
    )


def _labels_name(label_class: type[NodeMetricLabels] | None) -> str:
    return "no labels" if label_class is None else label_class.__name__


def _pairs(labels: NodeMetricLabels | None) -> tuple[tuple[str, str], ...]:
    return () if labels is None else labels.pairs()


def _refuse_unless_it_fits(node_metric: NodeMetric, *, labels: NodeMetricLabels | None) -> None:
    given = None if labels is None else type(labels)
    if given is not node_metric.label_class:
        raise ValueError(
            f"{node_metric.exposed_name} takes {_labels_name(node_metric.label_class)}, "
            f"given {_labels_name(given)}"
        )


@dataclass(kw_only=True, frozen=True)
class CounterIncrement:
    """Adds ``amount`` to the series of ``counter`` that ``labels`` names; labels of another class
    than the counter's, or a negative amount, raise ``ValueError``."""

    counter: NodeCounter
    labels: NodeMetricLabels | None = None
    amount: float = 1.0

    def __post_init__(self) -> None:
        _refuse_unless_it_fits(self.counter, labels=self.labels)
        if self.amount < 0:
            raise ValueError(
                f"{self.counter.exposed_name} takes an amount of 0 or more, not {self.amount}"
            )

    def label_pairs(self) -> tuple[tuple[str, str], ...]:
        """Its labels' ``(name, text)`` pairs, none when it has no labels."""
        return _pairs(self.labels)


@dataclass(kw_only=True, frozen=True)
class GaugeSetting:
    """Sets the series of ``gauge`` that ``labels`` names to ``value``, or removes it when
    ``value`` is ``None``; labels of another class than the gauge's raise ``ValueError``."""

    gauge: NodeGauge
    labels: NodeMetricLabels | None
    value: float | None

    def __post_init__(self) -> None:
        _refuse_unless_it_fits(self.gauge, labels=self.labels)

    def label_pairs(self) -> tuple[tuple[str, str], ...]:
        """Its labels' ``(name, text)`` pairs, none when it has no labels."""
        return _pairs(self.labels)


@dataclass(kw_only=True, frozen=True)
class NodeMetricSample:
    """One series of ``node_metric``, its labels' ``(name, text)`` pairs in the catalog's order, and
    its value."""

    node_metric: NodeCounter | NodeGauge
    labels: tuple[tuple[str, str], ...]
    value: float
