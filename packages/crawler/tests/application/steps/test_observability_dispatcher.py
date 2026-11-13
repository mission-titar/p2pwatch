"""The dispatch step: log + metrics always; a notification sent to each service of its audience
together, each send's outcome recorded on its service's component, a refusal or a timeout
declared, any other exception a bug."""

from dataclasses import dataclass
from typing import Literal

import pytest

from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.application.steps.health_recorder import HealthRecorder
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.health.component import Component
from p2pwatch.domain.health.health_condition import BUGS, Health
from p2pwatch.domain.health.outcome import UNITS_OF_WORK, Bug, Outcome, OutcomeSource
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
from p2pwatch.domain.observability.notification import RelayedLogLine, TierRise
from p2pwatch.domain.observability.notifier_outcomes import (
    SENDS,
    SENDS_FAILED,
    NotificationRefused,
    NotificationService,
    NotificationTimedOut,
    notifier_components,
)
from p2pwatch.domain.observability.policy import Audience
from p2pwatch.domain.observability.severity import Severity
from tests.fakes.adapters.driven.fake_hanging_notifier import FakeHangingNotifier
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_node_metric_store import FakeNodeMetricStore
from tests.fakes.adapters.driven.fake_notifier import ONE_SERVICE_PER_AUDIENCE, FakeNotifier
from tests.fakes.adapters.driven.fake_raising_notifier import FakeRaisingNotifier
from tests.support.virtual_time import VirtualLoop

_NODE_ID = NodeId("titar-node-1")
_COMPLETED = ev.DownloadCompleted(
    file=FileKey(network=Network.ED2K, native_id="a" * 32),
    filename="Keroro 062.avi",
    target_titles=(ev.TargetTitle(target_id=TargetId("062A"), title="t"),),
    node_id=_NODE_ID,
)


@dataclass(kw_only=True, frozen=True)
class _Recorded:
    outcome: Outcome
    on: Component
    by: OutcomeSource


class _OutcomeSpy:
    def __init__(self) -> None:
        self.recorded: list[_Recorded] = []

    async def __call__(self, outcome: Outcome, *, on: Component, by: OutcomeSource) -> None:
        self.recorded.append(_Recorded(outcome=outcome, on=on, by=by))


_COMPONENTS = notifier_components(ONE_SERVICE_PER_AUDIENCE)
_COMMUNITY = _COMPONENTS[ONE_SERVICE_PER_AUDIENCE[0]]
_DISCORD, _DISCORD_2, _NTFY = (
    NotificationService(scheme="discord", audience=Audience.COMMUNITY),
    NotificationService(scheme="discord", audience=Audience.COMMUNITY, ordinal=2),
    NotificationService(scheme="ntfy", audience=Audience.OPERATIONS),
)


def _dispatcher(
    node_metric_store: FakeNodeMetricStore,
    *,
    notifier: Notifier,
    logger: FakeLogger | None = None,
    timeout: float = 5.0,
    outcomes: _OutcomeSpy | None = None,
    components: dict[NotificationService, Component] = _COMPONENTS,
) -> ObservabilityDispatcher:
    return ObservabilityDispatcher(
        logger=logger or FakeLogger(),
        node_metric_writer=node_metric_store,
        current_notifier=lambda: notifier,
        notification_timeout_seconds=timeout,
        record_outcome=outcomes or _OutcomeSpy(),
        service_components=components,
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


def _both(outcome: Outcome, *, on: Component = _COMMUNITY) -> list[_Recorded]:
    """A send's outcome as the dispatcher records it: by the bugs' source, then by the sends'."""
    return [
        _Recorded(outcome=outcome, on=on, by=UNITS_OF_WORK),
        _Recorded(outcome=outcome, on=on, by=SENDS),
    ]


@pytest.mark.asyncio
async def test_a_sent_notification_records_a_success_on_its_service_s_component() -> None:
    outcomes = _OutcomeSpy()
    await _dispatcher(FakeNodeMetricStore(), notifier=FakeNotifier(), outcomes=outcomes).dispatch(
        _COMPLETED
    )
    assert outcomes.recorded == _both(Outcome.success())


@pytest.mark.asyncio
async def test_a_notification_reaches_each_service_of_its_audience_alone() -> None:
    notifier, outcomes = FakeNotifier((_DISCORD, _NTFY, _DISCORD_2)), _OutcomeSpy()
    components = notifier_components(notifier.services())
    await _dispatcher(
        FakeNodeMetricStore(), notifier=notifier, outcomes=outcomes, components=components
    ).dispatch(_COMPLETED)
    assert [audience for audience, _ in notifier.calls] == [Audience.COMMUNITY] * 2
    assert outcomes.recorded == [
        *_both(Outcome.success(), on=components[_DISCORD]),
        *_both(Outcome.success(), on=components[_DISCORD_2]),
    ]


def test_the_services_of_an_audience_are_sent_to_together(virtual_loop: VirtualLoop) -> None:
    notifier = FakeHangingNotifier((_DISCORD, _DISCORD_2))
    dispatcher = _dispatcher(
        FakeNodeMetricStore(),
        notifier=notifier,
        components=notifier_components(notifier.services()),
    )
    virtual_loop.run_until_complete(dispatcher.dispatch(_COMPLETED))
    assert virtual_loop.time() == 5.0  # one timeout, not one per service


@pytest.mark.asyncio
async def test_an_event_without_a_notification_records_no_outcome() -> None:
    outcomes = _OutcomeSpy()
    await _dispatcher(FakeNodeMetricStore(), notifier=FakeNotifier(), outcomes=outcomes).dispatch(
        ev.ObservationRecorded(client_name=ClientName("amuled"), channel=Channel("ed2k"))
    )
    assert outcomes.recorded == []


@pytest.mark.asyncio
async def test_a_refused_notification_is_a_declared_outcome_logged_in_one_line() -> None:
    logger, node_metric_store, outcomes = FakeLogger(), FakeNodeMetricStore(), _OutcomeSpy()
    refusal = NotificationRefused("refused (FAILURE)")
    await _dispatcher(
        node_metric_store, notifier=FakeRaisingNotifier(refusal), logger=logger, outcomes=outcomes
    ).dispatch(_COMPLETED)
    assert node_metric_store.read_samples()  # written despite the refusal
    assert logger.lines[-1] == LoggedLine(
        level="warning", message="notifier fake community: refused (FAILURE)"
    )
    assert outcomes.recorded == _both(Outcome.declared(refusal))


@pytest.mark.asyncio
async def test_a_send_past_its_timeout_is_a_declared_outcome_logged_in_one_line() -> None:
    logger, node_metric_store, outcomes = FakeLogger(), FakeNodeMetricStore(), _OutcomeSpy()
    # short timeout + hanging notifier: the send is cut at its timeout.
    await _dispatcher(
        node_metric_store,
        notifier=FakeHangingNotifier(),
        logger=logger,
        timeout=0.01,
        outcomes=outcomes,
    ).dispatch(_COMPLETED)
    assert node_metric_store.read_samples()
    assert logger.lines[-1] == LoggedLine(
        level="warning", message="notifier fake community: past its timeout of 0.01 s"
    )
    assert [recorded.by for recorded in outcomes.recorded] == [UNITS_OF_WORK, SENDS]
    for recorded in outcomes.recorded:
        assert isinstance(recorded.outcome.reason, NotificationTimedOut)
        assert str(recorded.outcome.reason) == "past its timeout of 0.01 s"


@pytest.mark.asyncio
async def test_any_other_exception_of_the_notifier_is_a_bug_logged_with_its_trace() -> None:
    logger, outcomes = FakeLogger(), _OutcomeSpy()
    error = RuntimeError("canal mort")
    await _dispatcher(
        FakeNodeMetricStore(), notifier=FakeRaisingNotifier(error), logger=logger, outcomes=outcomes
    ).dispatch(_COMPLETED)
    assert logger.lines[-1] == LoggedLine(
        level="error", message="bug in notifier fake community", error=error
    )
    assert outcomes.recorded == [  # a bug records nothing by the sends' source
        _Recorded(
            outcome=Outcome(reason=Bug(description="RuntimeError('canal mort')")),
            on=_COMMUNITY,
            by=UNITS_OF_WORK,
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "bugs", "sends_failed", "failing"),
    [
        (NotificationRefused("403"), Health.HEALTHY, Health.FAILING, "sends failed"),
        (KeyError("embeds"), Health.FAILING, Health.UNKNOWN, "bugs"),
    ],
)
async def test_three_bugs_fail_a_service_s_bugs_condition_three_refusals_its_sends_failed(
    *, error: Exception, bugs: Health, sends_failed: Health, failing: str
) -> None:
    notifier, health_logger = FakeRaisingNotifier(error), FakeLogger()
    components = notifier_components(notifier.services())
    dispatcher = ObservabilityDispatcher(
        logger=FakeLogger(),
        node_metric_writer=FakeNodeMetricStore(),
        current_notifier=lambda: notifier,
        notification_timeout_seconds=5.0,
        record_outcome=HealthRecorder(logger=health_logger, subscribers=()).record,
        service_components=components,
    )
    for _ in range(3):
        await dispatcher.dispatch(_COMPLETED)
    component = components[ONE_SERVICE_PER_AUDIENCE[0]]
    assert (component.health_of(BUGS), component.health_of(SENDS_FAILED)) == (bugs, sends_failed)
    # The log line, the conditions' one reader in lot 4b.
    assert health_logger.lines[-1] == LoggedLine(
        level="warning", message=f"notifier fake community, {failing}: unknown to failing"
    )


@pytest.mark.asyncio
async def test_each_send_reaches_the_notifier_current_then() -> None:
    first, rebuilt = FakeNotifier(), FakeNotifier()
    current = first
    dispatcher = ObservabilityDispatcher(
        logger=FakeLogger(),
        node_metric_writer=FakeNodeMetricStore(),
        current_notifier=lambda: current,
        notification_timeout_seconds=5.0,
        record_outcome=_OutcomeSpy(),
        service_components=_COMPONENTS,
    )
    await dispatcher.dispatch(_COMPLETED)
    current = rebuilt
    await dispatcher.dispatch(_COMPLETED)
    assert (len(first.calls), len(rebuilt.calls)) == (1, 1)
