"""The dispatch step: log + metrics always; a notification left for each service of its audience,
for the notifier's work to send."""

import asyncio
from collections.abc import Sequence
from typing import Literal

import pytest

from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import Channel, ClientName, NodeId
from p2pwatch.domain.matching.decision_tier import DecisionTier
from p2pwatch.domain.matching.engine import DecisionRecord
from p2pwatch.domain.matching.identifiers import TargetId
from p2pwatch.domain.observability import events as ev
from p2pwatch.domain.observability.node_metric import (
    NodeCounter,
    NodeGauge,
    NodeMetricSample,
)
from p2pwatch.domain.observability.notification import (
    CompletedDownload,
    Notification,
    RelayedLogLine,
    TierRise,
)
from p2pwatch.domain.observability.notification_sends import NotificationService
from p2pwatch.domain.observability.policy import Audience
from p2pwatch.domain.observability.severity import Severity
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_node_metric_store import FakeNodeMetricStore
from tests.fakes.adapters.driven.fake_notifier import ONE_SERVICE_PER_AUDIENCE
from tests.fakes.adapters.driven.fake_raising_node_metric_store import FakeRaisingNodeMetricStore

_NODE_ID = NodeId("titar-node-1")
_COMPLETED = ev.DownloadCompleted(
    file=FileKey(network=Network.ED2K, native_id="a" * 32),
    filename="Keroro 062.avi",
    target_titles=(ev.TargetTitle(target_id=TargetId("062A"), title="t"),),
    node_id=_NODE_ID,
)
_COMPLETED_NOTIFICATION = CompletedDownload(
    target_titles=(ev.TargetTitle(target_id=TargetId("062A"), title="t"),),
    filename="Keroro 062.avi",
    node_id=_NODE_ID,
)

_DISCORD = NotificationService(scheme="discord", audience=Audience.COMMUNITY)
_NTFY = NotificationService(scheme="ntfy", audience=Audience.OPERATIONS)
_SECOND_DISCORD = NotificationService(scheme="discord", audience=Audience.COMMUNITY, ordinal=2)


class _Left:
    """Keeps each notification the dispatcher leaves, with the services it is left for."""

    def __init__(self) -> None:
        self.notifications: list[tuple[Notification, tuple[NotificationService, ...]]] = []

    def __call__(
        self, notification: Notification, *, services: Sequence[NotificationService]
    ) -> None:
        self.notifications.append((notification, tuple(services)))


def _dispatcher(
    node_metric_store: FakeNodeMetricStore,
    *,
    left: _Left | None = None,
    logger: FakeLogger | None = None,
    services: Sequence[NotificationService] = ONE_SERVICE_PER_AUDIENCE,
) -> ObservabilityDispatcher:
    return ObservabilityDispatcher(
        logger=logger or FakeLogger(),
        node_metric_writer=node_metric_store,
        leave_notification=left or _Left(),
        services=services,
    )


@pytest.mark.asyncio
async def test_logs_and_writes_node_metrics_no_audience() -> None:
    node_metric_store, left = FakeNodeMetricStore(), _Left()
    await _dispatcher(node_metric_store, left=left).dispatch(
        ev.ObservationRecorded(client_name=ClientName("amuled"), channel=Channel("ed2k"))
    )
    assert node_metric_store.read_samples() == (
        NodeMetricSample(
            node_metric=NodeCounter.OBSERVATIONS,
            labels=(("client", "amuled"), ("channel", "ed2k")),
            value=1.0,
        ),
    )
    assert left.notifications == []  # ObservationRecorded has no audience


@pytest.mark.asyncio
async def test_two_node_metrics_one_event() -> None:
    node_metric_store = FakeNodeMetricStore()
    await _dispatcher(node_metric_store).dispatch(
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
    dispatcher = _dispatcher(node_metric_store)
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
    left = _Left()
    await _dispatcher(FakeNodeMetricStore(), left=left).dispatch(
        ev.CrawlerStarted(download_enabled=True, node_id=_NODE_ID)
    )
    assert left.notifications == [
        (
            RelayedLogLine(
                message="🟢 node online (download on)", severity=Severity.INFO, node_id=_NODE_ID
            ),
            (ONE_SERVICE_PER_AUDIENCE[1],),
        )
    ]


@pytest.mark.asyncio
async def test_logs_the_message_but_notifies_the_plans_notification() -> None:
    logger, left = FakeLogger(), _Left()
    download = DecisionRecord(
        target_id=TargetId("062A"), rule_name="rule", tier=DecisionTier.DOWNLOAD
    )
    change = ev.DecisionChange(
        target_id=TargetId("062A"),
        title="Les demoiselles cambrioleuses",
        previous_decision=None,
        new_decision=download,
    )
    await _dispatcher(FakeNodeMetricStore(), left=left, logger=logger).dispatch(
        ev.DecisionsRecorded(
            file=FileKey(network=Network.ED2K, native_id="a" * 32),
            filename="Keroro 062.avi",
            size_bytes=1024,
            changes=(change,),
            node_id=_NODE_ID,
        )
    )
    assert logger.lines[-1].message.startswith("decisions for Keroro 062.avi")
    assert left.notifications == [
        (
            TierRise(
                tier=DecisionTier.DOWNLOAD,
                target_titles=(
                    ev.TargetTitle(
                        target_id=TargetId("062A"), title="Les demoiselles cambrioleuses"
                    ),
                ),
                file=FileKey(network=Network.ED2K, native_id="a" * 32),
                filename="Keroro 062.avi",
                size_bytes=1024,
                node_id=_NODE_ID,
            ),
            (ONE_SERVICE_PER_AUDIENCE[0],),
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
    await _dispatcher(FakeNodeMetricStore(), logger=logger).dispatch(event)
    assert [line.level for line in logger.lines] == [level]


@pytest.mark.asyncio
async def test_a_notification_is_left_for_each_service_of_its_audience() -> None:
    left = _Left()
    dispatcher = _dispatcher(
        FakeNodeMetricStore(), left=left, services=(_DISCORD, _NTFY, _SECOND_DISCORD)
    )

    await dispatcher.dispatch(_COMPLETED)

    assert left.notifications == [(_COMPLETED_NOTIFICATION, (_DISCORD, _SECOND_DISCORD))]


@pytest.mark.asyncio
async def test_a_notification_whose_audience_has_no_service_is_left_for_none() -> None:
    left = _Left()

    await _dispatcher(FakeNodeMetricStore(), left=left, services=(_NTFY,)).dispatch(_COMPLETED)

    assert left.notifications == [(_COMPLETED_NOTIFICATION, ())]


@pytest.mark.asyncio
async def test_a_shielded_dispatch_whose_caller_is_cancelled_still_leaves_its_notification() -> (
    None
):
    left = _Left()
    dispatcher = _dispatcher(FakeNodeMetricStore(), left=left)
    caller = asyncio.create_task(dispatcher.dispatch_shielded(_COMPLETED))
    await asyncio.sleep(0)  # noqa: TID251  # the caller hands the dispatch to a task, not yet run

    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller

    assert left.notifications == [(_COMPLETED_NOTIFICATION, (ONE_SERVICE_PER_AUDIENCE[0],))]


@pytest.mark.asyncio
async def test_a_bug_in_a_shielded_dispatch_its_caller_left_is_logged_with_its_kind() -> None:
    logger = FakeLogger()
    bug = RuntimeError("a metrics bug")
    dispatcher = _dispatcher(FakeRaisingNodeMetricStore(bug), logger=logger)
    caller = asyncio.create_task(dispatcher.dispatch_shielded(_COMPLETED))
    await asyncio.sleep(0)  # noqa: TID251  # the caller hands the dispatch to a task, not yet run

    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller

    assert logger.lines[-1] == LoggedLine(
        level="error", message="bug in the notification of DownloadCompleted", error=bug
    )


@pytest.mark.asyncio
async def test_finishing_the_shielded_dispatches_waits_for_one_its_caller_left() -> None:
    left = _Left()
    dispatcher = _dispatcher(FakeNodeMetricStore(), left=left)
    caller = asyncio.create_task(dispatcher.dispatch_shielded(_COMPLETED))
    await asyncio.sleep(0)  # noqa: TID251  # the caller hands the dispatch to a task, not yet run
    caller.cancel()
    left_before_the_finish = list(left.notifications)

    await dispatcher.finish_shielded_dispatches()

    assert left_before_the_finish == []
    assert [notification for notification, _ in left.notifications] == [_COMPLETED_NOTIFICATION]


@pytest.mark.asyncio
async def test_finishing_the_shielded_dispatches_logs_a_bug_of_theirs_and_raises_it_not() -> None:
    logger = FakeLogger()
    bug = RuntimeError("a metrics bug")
    dispatcher = _dispatcher(FakeRaisingNodeMetricStore(bug), logger=logger)
    caller = asyncio.create_task(dispatcher.dispatch_shielded(_COMPLETED))
    await asyncio.sleep(0)  # noqa: TID251  # the caller hands the dispatch to a task, not yet run
    caller.cancel()

    await dispatcher.finish_shielded_dispatches()

    assert [line for line in logger.lines if line.level == "error"] == [
        LoggedLine(level="error", message="bug in the notification of DownloadCompleted", error=bug)
    ]
