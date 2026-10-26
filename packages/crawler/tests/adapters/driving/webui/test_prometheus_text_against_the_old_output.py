"""The text the store, the use case and the writer give, against the fixtures that
the 4.x recorder wrote for the same instructions, ``_created`` lines stripped."""

import re
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.in_memory_node_metric_store import InMemoryNodeMetricStore
from p2pwatch.adapters.driving.webui.prometheus_text import prometheus_text
from p2pwatch.application.use_cases.list_node_metrics import ListNodeMetrics
from p2pwatch.domain.observability.node_metric import (
    CounterIncrement,
    GaugeSetting,
    NodeCounter,
    NodeGauge,
)

_FIXTURES = Path(__file__).parents[3] / "fixtures"
_AMULED_ED2K = (("client", "amuled"), ("channel", "ed2k"))
_AMULED_KAD = (("client", "amuled"), ("channel", "kad"))

# Every node metric, and each instruction test_policy's cases write: increments that add up, an
# increment of 0, a gauge replaced, a series removed, an absent one removed, a label to escape.
INSTRUCTIONS: tuple[CounterIncrement | GaugeSetting, ...] = (
    CounterIncrement(NodeCounter.SEARCHES, _AMULED_ED2K),
    CounterIncrement(NodeCounter.SEARCH_RESULTS_SKIPPED, _AMULED_ED2K, 2.0),
    CounterIncrement(NodeCounter.SEARCHES, _AMULED_KAD),
    CounterIncrement(NodeCounter.SEARCH_RESULTS_SKIPPED, _AMULED_KAD, 0.0),
    CounterIncrement(NodeCounter.SEARCHES, _AMULED_ED2K),
    CounterIncrement(NodeCounter.CLIENT_UNREACHABLE, (("client", "slskd"),)),
    CounterIncrement(NodeCounter.CLIENT_UNREACHABLE, (("client", 'a\\b"c\nd'),)),
    CounterIncrement(NodeCounter.SEARCH_FAILURES, _AMULED_KAD),
    CounterIncrement(NodeCounter.OBSERVATIONS, _AMULED_KAD),
    CounterIncrement(NodeCounter.DECISIONS, (("tier", "download"),)),
    CounterIncrement(NodeCounter.DECISIONS, (("tier", "notify"),)),
    CounterIncrement(NodeCounter.DOWNLOADS_QUEUED),
    CounterIncrement(NodeCounter.DOWNLOADS_COMPLETED),
    GaugeSetting(NodeGauge.CHANNEL_CONNECTED, _AMULED_KAD, 1.0),
    GaugeSetting(NodeGauge.CHANNEL_CONNECTABLE, _AMULED_KAD, 0.0),
    GaugeSetting(NodeGauge.CHANNEL_CONNECTED, _AMULED_ED2K, 1.0),
    GaugeSetting(NodeGauge.CHANNEL_CONNECTABLE, _AMULED_ED2K, 1.0),
    GaugeSetting(NodeGauge.CHANNEL_CONNECTED, _AMULED_KAD, None),
    GaugeSetting(NodeGauge.CHANNEL_CONNECTABLE, _AMULED_KAD, None),
    GaugeSetting(NodeGauge.CHANNEL_CONNECTED, (("client", "slskd"), ("channel", "ed2k")), None),
    GaugeSetting(NodeGauge.DISK_FREE_BYTES, (), 5_000.0),
    GaugeSetting(NodeGauge.DISK_FREE_BYTES, (), 500_000_000_000.0),
    GaugeSetting(NodeGauge.CRAWLER_UP, (), 1.0),
    CounterIncrement(NodeCounter.SOURCE_ALERTS, (("network", "ed2k"), ("kind", "first_useful"))),
    CounterIncrement(NodeCounter.SOURCE_ALERTS, (("network", "ed2k"), ("kind", "reappeared"))),
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
