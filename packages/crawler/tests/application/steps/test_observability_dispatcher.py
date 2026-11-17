"""The dispatch step: log + metrics always; notification by audience, each send recorded on the
notifier's part once it has ended: a refusal or a timeout a failed send, any other error a bug."""

import asyncio
from dataclasses import dataclass
from typing import Literal

import pytest

from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.health.component import Component
from p2pwatch.domain.health.health_rule import HealthRule, HealthState
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
    RelayedLogLine,
    TierRise,
)
from p2pwatch.domain.observability.notification_sends import (
    SENDS_FAILED,
    NotificationRefusedError,
    notifier_component,
)
from p2pwatch.domain.observability.policy import Audience
from p2pwatch.domain.observability.severity import Severity
from p2pwatch.domain.work_components import BUGS
from tests.fakes.adapters.driven.fake_hanging_notifier import FakeHangingNotifier
from tests.fakes.adapters.driven.fake_held_notifier import FakeHeldNotifier
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_node_metric_store import FakeNodeMetricStore
from tests.fakes.adapters.driven.fake_notifier import FakeNotifier
from tests.fakes.adapters.driven.fake_raising_node_metric_store import FakeRaisingNodeMetricStore
from tests.fakes.adapters.driven.fake_raising_notifier import FakeRaisingNotifier

_NODE_ID = NodeId("titar-node-1")
_COMPLETED = ev.DownloadCompleted(
    file=FileKey(network=Network.ED2K, native_id="a" * 32),
    filename="Keroro 062.avi",
    target_titles=(ev.TargetTitle(target_id=TargetId("062A"), title="t"),),
    node_id=_NODE_ID,
)


@dataclass(kw_only=True, frozen=True)
class _Check:
    component: Component
    rule: HealthRule
    detected: bool


class _Checks:
    """Keeps each check the dispatcher records, in order."""

    def __init__(self) -> None:
        self.recorded: list[_Check] = []

    async def __call__(self, *, on: Component, rule: HealthRule, detected: bool) -> None:
        self.recorded.append(_Check(component=on, rule=rule, detected=detected))


_NOTIFIER = notifier_component()


def _dispatcher(
    node_metric_store: FakeNodeMetricStore,
    *,
    notifier: Notifier,
    logger: FakeLogger | None = None,
    timeout: float = 5.0,
    checks: _Checks | None = None,
) -> ObservabilityDispatcher:
    return ObservabilityDispatcher(
        logger=logger or FakeLogger(),
        node_metric_writer=node_metric_store,
        current_notifier=lambda: notifier,
        notification_timeout_seconds=timeout,
        record_check=checks or _Checks(),
        notifier_component=_NOTIFIER,
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
                file=FileKey(network=Network.ED2K, native_id="a" * 32),
                filename="Keroro 062.avi",
                size_bytes=1024,
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
async def test_a_send_that_worked_records_not_detected_on_both_rules_once_it_has_ended() -> None:
    notifier, checks = FakeHeldNotifier(), _Checks()
    dispatcher = _dispatcher(FakeNodeMetricStore(), notifier=notifier, checks=checks)
    sending = asyncio.create_task(dispatcher.dispatch(_COMPLETED))
    await notifier.reached.wait()
    recorded_while_held = list(checks.recorded)

    notifier.released.set()
    await sending

    assert recorded_while_held == []
    assert checks.recorded == [
        _Check(component=_NOTIFIER, rule=BUGS, detected=False),
        _Check(component=_NOTIFIER, rule=SENDS_FAILED, detected=False),
    ]


@pytest.mark.asyncio
async def test_an_event_without_a_notification_records_no_check() -> None:
    checks = _Checks()

    await _dispatcher(FakeNodeMetricStore(), notifier=FakeNotifier(), checks=checks).dispatch(
        ev.ObservationRecorded(client_name=ClientName("amuled"), channel=Channel("ed2k"))
    )

    assert checks.recorded == []


@pytest.mark.asyncio
async def test_a_refused_send_is_a_failed_send_logged_in_one_line_and_no_bug() -> None:
    logger, node_metric_store, checks = FakeLogger(), FakeNodeMetricStore(), _Checks()
    refusal = NotificationRefusedError("a service refused it (FAILURE)")
    dispatcher = _dispatcher(
        node_metric_store, notifier=FakeRaisingNotifier(refusal), logger=logger, checks=checks
    )

    await dispatcher.dispatch(_COMPLETED)

    assert node_metric_store.read_samples()  # written despite the refusal
    assert logger.lines[-1] == LoggedLine(
        level="warning",
        message="notifier: community notification not sent: a service refused it (FAILURE)",
    )
    assert checks.recorded == [
        _Check(component=_NOTIFIER, rule=BUGS, detected=False),
        _Check(component=_NOTIFIER, rule=SENDS_FAILED, detected=True),
    ]


@pytest.mark.asyncio
async def test_a_send_past_its_timeout_is_a_failed_send_logged_in_one_line_and_no_bug() -> None:
    logger, node_metric_store, checks = FakeLogger(), FakeNodeMetricStore(), _Checks()
    dispatcher = _dispatcher(
        node_metric_store,
        notifier=FakeHangingNotifier(),
        logger=logger,
        timeout=0.01,
        checks=checks,
    )

    await dispatcher.dispatch(_COMPLETED)

    assert node_metric_store.read_samples()  # written despite the timeout
    assert logger.lines[-1] == LoggedLine(
        level="warning",
        message="notifier: community notification not sent: past its timeout of 0.01 s",
    )
    assert checks.recorded == [
        _Check(component=_NOTIFIER, rule=BUGS, detected=False),
        _Check(component=_NOTIFIER, rule=SENDS_FAILED, detected=True),
    ]


@pytest.mark.asyncio
async def test_any_other_exception_of_the_notifier_is_a_bug_logged_with_its_trace() -> None:
    logger, checks = FakeLogger(), _Checks()
    bug = RuntimeError("canal mort")
    dispatcher = _dispatcher(
        FakeNodeMetricStore(), notifier=FakeRaisingNotifier(bug), logger=logger, checks=checks
    )

    await dispatcher.dispatch(_COMPLETED)

    assert logger.lines[-1] == LoggedLine(
        level="error", message="bug in notifier, sending a community notification", error=bug
    )
    # A bug tells nothing of whether the services take the sends.
    assert checks.recorded == [_Check(component=_NOTIFIER, rule=BUGS, detected=True)]


@pytest.mark.asyncio
async def test_a_timeout_error_the_notifier_raises_itself_is_a_bug_not_a_timeout() -> None:
    checks = _Checks()
    dispatcher = _dispatcher(
        FakeNodeMetricStore(), notifier=FakeRaisingNotifier(TimeoutError("its own")), checks=checks
    )

    await dispatcher.dispatch(_COMPLETED)

    assert checks.recorded == [_Check(component=_NOTIFIER, rule=BUGS, detected=True)]


@pytest.mark.asyncio
async def test_refused_sends_and_sends_past_their_timeout_fail_the_notifier_s_sends() -> None:
    refusing = FakeRaisingNotifier(NotificationRefusedError("a service refused it (FAILURE)"))
    notifiers: list[Notifier] = [refusing, FakeHangingNotifier(), refusing]
    notifier = notifier_component()
    dispatcher = ObservabilityDispatcher(
        logger=FakeLogger(),
        node_metric_writer=FakeNodeMetricStore(),
        current_notifier=lambda: notifiers.pop(0),
        notification_timeout_seconds=0.01,
        record_check=NodeHealth(logger=FakeLogger(), subscribers=()).record,
        notifier_component=notifier,
    )

    for _ in range(3):
        await dispatcher.dispatch(_COMPLETED)

    assert (notifier.state(SENDS_FAILED), notifier.state(BUGS)) == (
        HealthState.FAILING,
        HealthState.HEALTHY,
    )


@pytest.mark.asyncio
async def test_each_send_goes_to_the_notifier_current_when_it_starts() -> None:
    old, rebuilt = FakeHeldNotifier(), FakeNotifier()
    current: Notifier = old
    dispatcher = ObservabilityDispatcher(
        logger=FakeLogger(),
        node_metric_writer=FakeNodeMetricStore(),
        current_notifier=lambda: current,
        notification_timeout_seconds=5.0,
        record_check=_Checks(),
        notifier_component=_NOTIFIER,
    )
    in_flight = asyncio.create_task(dispatcher.dispatch(_COMPLETED))
    await old.reached.wait()

    current = rebuilt
    await dispatcher.dispatch(_COMPLETED)
    old.released.set()
    await in_flight

    # The send in flight finishes on the old notifier, the next goes to the new one.
    assert (len(old.calls), len(rebuilt.calls)) == (1, 1)


@pytest.mark.asyncio
async def test_a_shielded_dispatch_whose_caller_is_cancelled_mid_send_still_sends() -> None:
    notifier = FakeHeldNotifier()
    dispatcher = _dispatcher(FakeNodeMetricStore(), notifier=notifier)
    caller = asyncio.create_task(dispatcher.dispatch_shielded(_COMPLETED))
    await notifier.reached.wait()

    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    notifier.released.set()
    await notifier.wait_until_sent(timeout_seconds=1.0)

    assert notifier.calls == [
        (
            Audience.COMMUNITY,
            CompletedDownload(
                target_titles=(ev.TargetTitle(target_id=TargetId("062A"), title="t"),),
                filename="Keroro 062.avi",
                node_id=_NODE_ID,
            ),
        )
    ]


@pytest.mark.asyncio
async def test_a_bug_in_a_shielded_dispatch_its_caller_left_is_logged_with_its_kind() -> None:
    logger = FakeLogger()
    bug = RuntimeError("a metrics bug")
    dispatcher = _dispatcher(
        FakeRaisingNodeMetricStore(bug), notifier=FakeNotifier(), logger=logger
    )
    caller = asyncio.create_task(dispatcher.dispatch_shielded(_COMPLETED))
    await asyncio.sleep(0)  # noqa: TID251  # the caller hands the dispatch to a task, not yet run

    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller

    assert logger.lines[-1] == LoggedLine(
        level="error", message="bug in the notification of DownloadCompleted", error=bug
    )


@pytest.mark.asyncio
async def test_finishing_the_shielded_dispatches_waits_for_a_send_its_caller_left() -> None:
    notifier = FakeHeldNotifier()
    dispatcher = _dispatcher(FakeNodeMetricStore(), notifier=notifier)
    caller = asyncio.create_task(dispatcher.dispatch_shielded(_COMPLETED))
    await notifier.reached.wait()
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller

    finishing = asyncio.create_task(dispatcher.finish_shielded_dispatches())
    await asyncio.sleep(0)  # noqa: TID251  # the finish starts waiting for the send
    finished_while_held = finishing.done()
    notifier.released.set()
    await asyncio.wait_for(finishing, 1.0)

    assert not finished_while_held
    assert [notification for _, notification in notifier.calls] == [
        CompletedDownload(
            target_titles=(ev.TargetTitle(target_id=TargetId("062A"), title="t"),),
            filename="Keroro 062.avi",
            node_id=_NODE_ID,
        )
    ]


@pytest.mark.asyncio
async def test_finishing_the_shielded_dispatches_logs_a_bug_of_theirs_and_raises_it_not() -> None:
    logger = FakeLogger()
    bug = RuntimeError("a metrics bug")
    dispatcher = _dispatcher(
        FakeRaisingNodeMetricStore(bug), notifier=FakeNotifier(), logger=logger
    )
    caller = asyncio.create_task(dispatcher.dispatch_shielded(_COMPLETED))
    await asyncio.sleep(0)  # noqa: TID251  # the caller hands the dispatch to a task, not yet run
    caller.cancel()

    await dispatcher.finish_shielded_dispatches()

    assert [line for line in logger.lines if line.level == "error"] == [
        LoggedLine(level="error", message="bug in the notification of DownloadCompleted", error=bug)
    ]
