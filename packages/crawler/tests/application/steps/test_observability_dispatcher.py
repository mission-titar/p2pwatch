"""The dispatch step: log + metrics always; notification by audience, failure/timeout absorbed."""

from typing import Literal

import pytest

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.engine import DecisionRecord
from catalog_matching.domain.identifiers import TargetId
from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import Channel, ClientName, NodeId
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

_NODE_ID = NodeId("titar-node-1")
_COMPLETED = ev.DownloadCompleted(
    file=FileKey(network=Network.ED2K, native_id="a" * 32),
    filename="Keroro 062.avi",
    target_titles=(ev.TargetTitle(target_id=TargetId("062A"), title="t"),),
    node_id=_NODE_ID,
)


def _dispatcher(
    node_metric_store: FakeNodeMetricStore,
    *,
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
    await _dispatcher(node_metric_store, notifier=notifier).dispatch(
        ev.ObservationRecorded(client_name=ClientName("amuled"), channel=Channel("ed2k"))
    )
    assert node_metric_store.read_samples() == (
        NodeMetricSample(
            node_metric=NodeCounter.OBSERVATIONS,
            labels=(("client", "amuled"), ("channel", "ed2k")),
            value=1.0,
        ),
    )
    assert notifier.calls == []  # ObservationRecorded has no audience


@pytest.mark.asyncio
async def test_two_node_metrics_one_event() -> None:
    node_metric_store = FakeNodeMetricStore()
    await _dispatcher(node_metric_store, notifier=FakeNotifier()).dispatch(
        ev.ChannelStatusSampled(
            client_name=ClientName("amuled"),
            channel=Channel("kad"),
            connected=True,
            connectable=True,
        )
    )
    labels = (("client", "amuled"), ("channel", "kad"))
    assert set(node_metric_store.read_samples()) == {
        NodeMetricSample(node_metric=NodeGauge.CHANNEL_CONNECTED, labels=labels, value=1.0),
        NodeMetricSample(node_metric=NodeGauge.CHANNEL_CONNECTABLE, labels=labels, value=1.0),
    }


@pytest.mark.asyncio
async def test_writes_each_counter_increment_and_gauge_setting_to_the_node_metric_store() -> None:
    node_metric_store = FakeNodeMetricStore()
    dispatcher = _dispatcher(node_metric_store, notifier=FakeNotifier())
    await dispatcher.dispatch(ev.ClientUnreachable(client_name=ClientName("amuled")))
    await dispatcher.dispatch(ev.CrawlerStarted(download_enabled=True, node_id=_NODE_ID))
    assert set(node_metric_store.read_samples()) == {
        NodeMetricSample(
            node_metric=NodeCounter.CLIENT_UNREACHABLE, labels=(("client", "amuled"),), value=1.0
        ),
        NodeMetricSample(node_metric=NodeGauge.CRAWLER_UP, labels=(), value=1.0),
    }


@pytest.mark.asyncio
async def test_relays_the_log_line_under_the_events_node() -> None:
    notifier = FakeNotifier()
    await _dispatcher(FakeNodeMetricStore(), notifier=notifier).dispatch(
        ev.CrawlerStarted(download_enabled=True, node_id=_NODE_ID)
    )
    assert notifier.calls == [
        (
            Audience.OPERATIONS,
            RelayedLogLine(
                message="🟢 node online (download on)", severity=Severity.INFO, node_id=_NODE_ID
            ),
        )
    ]


@pytest.mark.asyncio
async def test_logs_the_message_but_notifies_the_plans_notification() -> None:
    logger, notifier = FakeLogger(), FakeNotifier()
    download = DecisionRecord(
        target_id=TargetId("062A"), rule_name="rule", tier=DecisionTier.DOWNLOAD
    )
    change = ev.DecisionChange(
        target_id=TargetId("062A"),
        title="Les demoiselles cambrioleuses",
        previous_decision=None,
        new_decision=download,
    )
    await _dispatcher(FakeNodeMetricStore(), notifier=notifier, logger=logger).dispatch(
        ev.DecisionsRecorded(
            file=FileKey(network=Network.ED2K, native_id="a" * 32),
            filename="Keroro 062.avi",
            size_bytes=1024,
            changes=(change,),
            node_id=_NODE_ID,
        )
    )
    assert logger.lines[-1].message.startswith("decisions for Keroro 062.avi")
    assert notifier.calls == [
        (
            Audience.COMMUNITY,
            TierRise(
                tier=DecisionTier.DOWNLOAD,
                target_titles=(
                    ev.TargetTitle(
                        target_id=TargetId("062A"), title="Les demoiselles cambrioleuses"
                    ),
                ),
                filename="Keroro 062.avi",
                size_bytes=1024,
                ed2k_link=f"ed2k://|file|Keroro%20062.avi|1024|{'a' * 32}|/",
                node_id=_NODE_ID,
            ),
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event", "level"),
    [
        (
            ev.ObservationRecorded(client_name=ClientName("amuled"), channel=Channel("ed2k")),
            "debug",
        ),
        (ev.CrawlerStarted(download_enabled=True, node_id=_NODE_ID), "info"),
        (_COMPLETED, "info"),  # a success
        (ev.ClientUnreachable(client_name=ClientName("amuled")), "warning"),
    ],
)
async def test_each_severity_logs_at_its_level(
    *, event: ev.Event, level: Literal["debug", "info", "warning"]
) -> None:
    logger = FakeLogger()
    await _dispatcher(FakeNodeMetricStore(), notifier=FakeNotifier(), logger=logger).dispatch(event)
    assert [line.level for line in logger.lines] == [level]


@pytest.mark.asyncio
async def test_notification_failure_is_absorbed() -> None:
    logger, node_metric_store = FakeLogger(), FakeNodeMetricStore()
    await _dispatcher(node_metric_store, notifier=FakeRaisingNotifier(), logger=logger).dispatch(
        _COMPLETED
    )
    assert node_metric_store.read_samples()  # written despite the notification failure
    assert logger.lines[-1] == LoggedLine(
        level="warning", message="notification community failed (canal mort)"
    )


@pytest.mark.asyncio
async def test_notification_timeout_is_absorbed() -> None:
    node_metric_store = FakeNodeMetricStore()
    # short timeout + hanging notifier → wait_for raises TimeoutError, absorbed.
    await _dispatcher(node_metric_store, notifier=FakeHangingNotifier(), timeout=0.01).dispatch(
        _COMPLETED
    )
    assert node_metric_store.read_samples()
