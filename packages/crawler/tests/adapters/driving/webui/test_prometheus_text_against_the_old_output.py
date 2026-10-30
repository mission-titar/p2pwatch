"""The text the store, the use case and the writer give, against the fixtures that
the 4.x recorder wrote for the same instructions, ``_created`` lines stripped."""

import re
from pathlib import Path

import pytest

from catalog_matching.domain.decision_tier import DecisionTier
from p2pwatch.adapters.driven.in_memory_node_metric_store import InMemoryNodeMetricStore
from p2pwatch.adapters.driving.webui.prometheus_text import prometheus_text
from p2pwatch.application.use_cases.list_node_metrics import ListNodeMetrics
from p2pwatch.domain.file_key import Network
from p2pwatch.domain.identifiers import Channel, ClientName
from p2pwatch.domain.observability.node_metric import (
    ChannelLabels,
    ClientLabels,
    CounterIncrement,
    DecisionLabels,
    GaugeSetting,
    NodeCounter,
    NodeGauge,
    SourceAlertLabels,
)
from p2pwatch.domain.observability.notification import SourceAlertKind

_FIXTURES = Path(__file__).parents[3] / "fixtures"
_AMULED_ED2K = ChannelLabels(client_name=ClientName("amuled"), channel=Channel("ed2k"))
_AMULED_KAD = ChannelLabels(client_name=ClientName("amuled"), channel=Channel("kad"))

# Every node metric, and each instruction test_policy's cases write: increments that add up, an
# increment of 0, a gauge replaced, a series removed, an absent one removed, a label to escape.
INSTRUCTIONS: tuple[CounterIncrement | GaugeSetting, ...] = (
    CounterIncrement(counter=NodeCounter.SEARCHES, labels=_AMULED_ED2K),
    CounterIncrement(counter=NodeCounter.SEARCH_RESULTS_SKIPPED, labels=_AMULED_ED2K, amount=2.0),
    CounterIncrement(counter=NodeCounter.SEARCHES, labels=_AMULED_KAD),
    CounterIncrement(counter=NodeCounter.SEARCH_RESULTS_SKIPPED, labels=_AMULED_KAD, amount=0.0),
    CounterIncrement(counter=NodeCounter.SEARCHES, labels=_AMULED_ED2K),
    CounterIncrement(
        counter=NodeCounter.CLIENT_UNREACHABLE, labels=ClientLabels(client_name=ClientName("slskd"))
    ),
    CounterIncrement(
        counter=NodeCounter.CLIENT_UNREACHABLE,
        labels=ClientLabels(client_name=ClientName('a\\b"c\nd')),
    ),
    CounterIncrement(counter=NodeCounter.SEARCH_FAILURES, labels=_AMULED_KAD),
    CounterIncrement(counter=NodeCounter.OBSERVATIONS, labels=_AMULED_KAD),
    CounterIncrement(
        counter=NodeCounter.DECISIONS, labels=DecisionLabels(tier=DecisionTier.DOWNLOAD)
    ),
    CounterIncrement(
        counter=NodeCounter.DECISIONS, labels=DecisionLabels(tier=DecisionTier.NOTIFY)
    ),
    CounterIncrement(counter=NodeCounter.DOWNLOADS_QUEUED),
    CounterIncrement(counter=NodeCounter.DOWNLOADS_COMPLETED),
    GaugeSetting(gauge=NodeGauge.CHANNEL_CONNECTED, labels=_AMULED_KAD, value=1.0),
    GaugeSetting(gauge=NodeGauge.CHANNEL_CONNECTABLE, labels=_AMULED_KAD, value=0.0),
    GaugeSetting(gauge=NodeGauge.CHANNEL_CONNECTED, labels=_AMULED_ED2K, value=1.0),
    GaugeSetting(gauge=NodeGauge.CHANNEL_CONNECTABLE, labels=_AMULED_ED2K, value=1.0),
    GaugeSetting(gauge=NodeGauge.CHANNEL_CONNECTED, labels=_AMULED_KAD, value=None),
    GaugeSetting(gauge=NodeGauge.CHANNEL_CONNECTABLE, labels=_AMULED_KAD, value=None),
    GaugeSetting(
        gauge=NodeGauge.CHANNEL_CONNECTED,
        labels=ChannelLabels(client_name=ClientName("slskd"), channel=Channel("ed2k")),
        value=None,
    ),
    GaugeSetting(gauge=NodeGauge.DISK_FREE_BYTES, labels=None, value=5_000.0),
    GaugeSetting(gauge=NodeGauge.DISK_FREE_BYTES, labels=None, value=500_000_000_000.0),
    GaugeSetting(gauge=NodeGauge.CRAWLER_UP, labels=None, value=1.0),
    CounterIncrement(
        counter=NodeCounter.SOURCE_ALERTS,
        labels=SourceAlertLabels(network=Network.ED2K, kind=SourceAlertKind.FIRST_USEFUL),
    ),
    CounterIncrement(
        counter=NodeCounter.SOURCE_ALERTS,
        labels=SourceAlertLabels(network=Network.ED2K, kind=SourceAlertKind.REAPPEARED),
    ),
)

_SAMPLE_LINE = re.compile(r"(?P<name>\w+)(?:\{(?P<labels>.*)\})? (?P<value>\S+)")
_LABEL = re.compile(r'(\w+)="((?:[^"\\]|\\.)*)"')

type _Sample = tuple[str, frozenset[tuple[str, str]], float]


def _sample(line: str) -> _Sample:
    """A sample line as its name, its labels with their values as escaped, and its value."""
    match = _SAMPLE_LINE.fullmatch(line)
    assert match is not None, line
    labels = frozenset(_LABEL.findall(match["labels"] or ""))
    return match["name"], labels, float(match["value"])


def _metadata(text: str) -> frozenset[str]:
    return frozenset(line for line in text.splitlines() if line.startswith("#"))


def _samples(text: str) -> frozenset[_Sample]:
    return frozenset(_sample(line) for line in text.splitlines() if not line.startswith("#"))


@pytest.mark.parametrize(
    ("fixture", "instructions"),
    [("old_prometheus_text_unwritten.txt", ()), ("old_prometheus_text_written.txt", INSTRUCTIONS)],
)
def test_the_text_holds_the_metadata_and_samples_the_4x_recorder_wrote(
    fixture: str, instructions: tuple[CounterIncrement | GaugeSetting, ...]
) -> None:
    store = InMemoryNodeMetricStore()
    for instruction in instructions:
        if isinstance(instruction, CounterIncrement):
            store.record_increment(instruction)
        else:
            store.set_gauge(instruction)
    text = prometheus_text(ListNodeMetrics(store).list_node_metrics())
    old_text = (_FIXTURES / fixture).read_text(encoding="utf-8")
    assert _metadata(text) == _metadata(old_text)
    assert _samples(text) == _samples(old_text)
