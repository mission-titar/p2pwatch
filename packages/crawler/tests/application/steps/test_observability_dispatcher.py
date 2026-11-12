"""The dispatch step: log + metrics always; notification by audience, each one's outcome recorded on
the notifier's component, a refusal or a timeout declared, any other exception a bug."""

from dataclasses import dataclass
from typing import Literal

import pytest

from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.application.steps.health_event_translator import HealthEventTranslator
from p2pwatch.application.steps.health_recorder import HealthRecorder
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.application.steps.restart_policy import RestartPolicy
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.health.component import Component
from p2pwatch.domain.health.health_condition import BUGS, Health
from p2pwatch.domain.health.outcome import TURNS, Bug, Outcome, OutcomeSource
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
    NotificationRefused,
    NotificationTimedOut,
    notifier_component,
)
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


_NOTIFIER = notifier_component()


def _dispatcher(
    node_metric_store: FakeNodeMetricStore,
    *,
    notifier: Notifier,
    logger: FakeLogger | None = None,
    timeout: float = 5.0,
    outcomes: _OutcomeSpy | None = None,
) -> ObservabilityDispatcher:
    return ObservabilityDispatcher(
        logger=logger or FakeLogger(),
        node_metric_writer=node_metric_store,
        notifier=notifier,
        notification_timeout_seconds=timeout,
        record_outcome=outcomes or _OutcomeSpy(),
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
async def test_a_sent_notification_records_a_success_on_the_notifier_s_component() -> None:
    outcomes = _OutcomeSpy()
    await _dispatcher(FakeNodeMetricStore(), notifier=FakeNotifier(), outcomes=outcomes).dispatch(
        _COMPLETED
    )
    assert outcomes.recorded == [_Recorded(outcome=Outcome.success(), on=_NOTIFIER, by=TURNS)]


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
    refusal = NotificationRefused("a service refused it (FAILURE)")
    await _dispatcher(
        node_metric_store, notifier=FakeRaisingNotifier(refusal), logger=logger, outcomes=outcomes
    ).dispatch(_COMPLETED)
    assert node_metric_store.read_samples()  # written despite the refusal
    assert logger.lines[-1] == LoggedLine(
        level="warning", message="notification community: a service refused it (FAILURE)"
    )
    assert outcomes.recorded == [
        _Recorded(outcome=Outcome.declared(refusal), on=_NOTIFIER, by=TURNS)
    ]


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
        level="warning", message="notification community: past its timeout of 0.01 s"
    )
    [recorded] = outcomes.recorded
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
        level="error", message="bug in notification community", error=error
    )
    assert outcomes.recorded == [
        _Recorded(
            outcome=Outcome(reason=Bug(description="RuntimeError('canal mort')")),
            on=_NOTIFIER,
            by=TURNS,
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "health"),
    [
        (NotificationRefused("403"), Health.HEALTHY),
        (KeyError("embeds"), Health.FAILING),
    ],
)
async def test_three_bugs_fail_the_notifier_s_bugs_condition_three_refusals_do_not(
    *, error: Exception, health: Health
) -> None:
    component = notifier_component()
    dispatcher = ObservabilityDispatcher(
        logger=FakeLogger(),
        node_metric_writer=FakeNodeMetricStore(),
        notifier=FakeRaisingNotifier(error),
        notification_timeout_seconds=5.0,
        record_outcome=HealthRecorder(logger=FakeLogger(), subscribers=()).record,
        notifier_component=component,
    )
    for _ in range(3):
        await dispatcher.dispatch(_COMPLETED)
    assert component.health_of(BUGS) is health


@pytest.mark.asyncio
async def test_the_notifier_failing_on_its_bugs_notifies_nothing_and_is_only_logged() -> None:
    # The cycle the composition builds: the translator, a subscriber, dispatches through the
    # dispatcher recording on the same recorder. The notifier's transitions dispatch no event.
    component, policy_logger = notifier_component(), FakeLogger()
    notifier = FakeRaisingNotifier(KeyError("embeds"))
    recorder: HealthRecorder
    dispatcher = ObservabilityDispatcher(
        logger=FakeLogger(),
        node_metric_writer=FakeNodeMetricStore(),
        notifier=notifier,
        notification_timeout_seconds=5.0,
        record_outcome=lambda outcome, *, on, by: recorder.record(outcome, on=on, by=by),
        notifier_component=component,
    )
    recorder = HealthRecorder(
        logger=FakeLogger(),
        subscribers=(
            HealthEventTranslator(observability_dispatcher=dispatcher, node_id=_NODE_ID).translate,
            RestartPolicy(owners={}, logger=policy_logger),
        ),
    )
    for _ in range(4):
        await dispatcher.dispatch(_COMPLETED)
    assert component.health_of(BUGS) is Health.FAILING
    assert notifier.calls == 4  # one per event, none for the notifier's own transitions
    assert policy_logger.lines == [
        LoggedLine(level="warning", message="notifier, bugs failing: no owner, not restarted")
    ]
