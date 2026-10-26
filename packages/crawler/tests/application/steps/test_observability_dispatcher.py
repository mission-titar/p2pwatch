"""The dispatch step: log + metrics always; notification by audience, failure/timeout absorbed."""

from typing import Literal

import pytest

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.engine import DecisionRecord
from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.observability import events as ev
from p2pwatch.domain.observability.node_metric import (
    NodeCounter,
    NodeGauge,
    NodeMetricSample,
)
from p2pwatch.domain.observability.notification import RelayedLogLine, TierRise
from p2pwatch.domain.observability.policy import Audience
from p2pwatch.domain.observability.severity import Severity
from tests.fakes.adapters.driven.fake_hanging_notifier import FakeHangingNotifier
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_node_metric_store import FakeNodeMetricStore
from tests.fakes.adapters.driven.fake_notifier import FakeNotifier
from tests.fakes.adapters.driven.fake_raising_notifier import FakeRaisingNotifier

_NODE = "titar-node-1"
_COMPLETED = ev.DownloadCompleted(
    FileKey(Network.ED2K, "a" * 32), "Keroro 062.avi", (ev.TargetTitle("062A", "t"),), _NODE
)


def _dispatcher(
    node_metric_store: FakeNodeMetricStore,
    notifier: Notifier,
    logger: FakeLogger | None = None,
    timeout: float = 5.0,
) -> ObservabilityDispatcher:
    return ObservabilityDispatcher(
        logger=logger or FakeLogger(),
        node_metric_writer=node_metric_store,
        notifier=notifier,
        notification_timeout_seconds=timeout,
    )


@pytest.mark.asyncio
async def test_logs_and_writes_node_metrics_no_audience() -> None:
    node_metric_store, notifier = FakeNodeMetricStore(), FakeNotifier()
    await _dispatcher(node_metric_store, notifier).dispatch(
        ev.ObservationRecorded(client_name="amuled", channel="ed2k")
    )
    assert node_metric_store.read_samples() == (
        NodeMetricSample(
            NodeCounter.OBSERVATIONS, (("client", "amuled"), ("channel", "ed2k")), 1.0
        ),
    )
    assert notifier.calls == []  # ObservationRecorded has no audience


@pytest.mark.asyncio
async def test_two_node_metrics_one_event() -> None:
    node_metric_store = FakeNodeMetricStore()
    await _dispatcher(node_metric_store, FakeNotifier()).dispatch(
        ev.ChannelStatusSampled(
            client_name="amuled", channel="kad", connected=True, connectable=True
        )
    )
    labels = (("client", "amuled"), ("channel", "kad"))
    assert set(node_metric_store.read_samples()) == {
        NodeMetricSample(NodeGauge.CHANNEL_CONNECTED, labels, 1.0),
        NodeMetricSample(NodeGauge.CHANNEL_CONNECTABLE, labels, 1.0),
    }


@pytest.mark.asyncio
async def test_writes_each_counter_increment_and_gauge_setting_to_the_node_metric_store() -> None:
    node_metric_store = FakeNodeMetricStore()
    dispatcher = _dispatcher(node_metric_store, FakeNotifier())
    await dispatcher.dispatch(ev.ClientUnreachable("amuled"))
    await dispatcher.dispatch(ev.CrawlerStarted(download_enabled=True, node_id=_NODE))
    assert set(node_metric_store.read_samples()) == {
        NodeMetricSample(NodeCounter.CLIENT_UNREACHABLE, (("client", "amuled"),), 1.0),
        NodeMetricSample(NodeGauge.CRAWLER_UP, (), 1.0),
    }


@pytest.mark.asyncio
async def test_relays_the_log_line_under_the_events_node() -> None:
    notifier = FakeNotifier()
    await _dispatcher(FakeNodeMetricStore(), notifier).dispatch(
        ev.CrawlerStarted(download_enabled=True, node_id=_NODE)
    )
    assert notifier.calls == [
        (Audience.OPERATIONS, RelayedLogLine("🟢 node online (download on)", Severity.INFO, _NODE))
    ]


@pytest.mark.asyncio
async def test_logs_the_message_but_notifies_the_plans_notification() -> None:
    logger, notifier = FakeLogger(), FakeNotifier()
    download = DecisionRecord("062A", "rule", DecisionTier.DOWNLOAD)
    change = ev.DecisionChange("062A", "Les demoiselles cambrioleuses", None, download)
    await _dispatcher(FakeNodeMetricStore(), notifier, logger).dispatch(
        ev.DecisionsRecorded(
            FileKey(Network.ED2K, "a" * 32), "Keroro 062.avi", 1024, (change,), _NODE
        )
    )
    assert logger.lines[-1].message.startswith("decisions for Keroro 062.avi")
    assert notifier.calls == [
        (
            Audience.COMMUNITY,
            TierRise(
                DecisionTier.DOWNLOAD,
                (ev.TargetTitle("062A", "Les demoiselles cambrioleuses"),),
                "Keroro 062.avi",
                1024,
                f"ed2k://|file|Keroro%20062.avi|1024|{'a' * 32}|/",
                _NODE,
            ),
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event", "level"),
    [
        (ev.ObservationRecorded(client_name="amuled", channel="ed2k"), "debug"),
        (ev.CrawlerStarted(download_enabled=True, node_id=_NODE), "info"),
        (_COMPLETED, "info"),  # a success
        (ev.ClientUnreachable("amuled"), "warning"),
    ],
)
async def test_each_severity_logs_at_its_level(
    event: ev.Event, level: Literal["debug", "info", "warning"]
) -> None:
    logger = FakeLogger()
    await _dispatcher(FakeNodeMetricStore(), FakeNotifier(), logger).dispatch(event)
    assert [line.level for line in logger.lines] == [level]


@pytest.mark.asyncio
async def test_notification_failure_is_absorbed() -> None:
    logger, node_metric_store = FakeLogger(), FakeNodeMetricStore()
    await _dispatcher(node_metric_store, FakeRaisingNotifier(), logger).dispatch(_COMPLETED)
    assert node_metric_store.read_samples()  # written despite the notification failure
    assert logger.lines[-1] == LoggedLine("warning", "notification community failed (canal mort)")


@pytest.mark.asyncio
async def test_notification_timeout_is_absorbed() -> None:
    node_metric_store = FakeNodeMetricStore()
    # short timeout + hanging notifier → wait_for raises TimeoutError, absorbed.
    await _dispatcher(node_metric_store, FakeHangingNotifier(), timeout=0.01).dispatch(_COMPLETED)
    assert node_metric_store.read_samples()
