"""The notifier as the node builds it, at its start and at each rebuild: built anew with the works
sending the outbox's notifications through it, one per service, one send's timeout and the margin
their time limit."""

from collections.abc import Sequence
from datetime import timedelta

import pytest

from p2pwatch.adapters.driven.observability.apprise_notifier import AppriseNotifier
from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.application.ports.driven.restartable import Restartable
from p2pwatch.application.steps.notification_outbox import NotificationOutbox
from p2pwatch.application.steps.notification_sender import NotificationSender
from p2pwatch.application.steps.supervisor import Supervisor
from p2pwatch.application.steps.work import SupervisedWork, Work
from p2pwatch.composition.notifier_restartable import (
    NotifierRestartable,
    NotifierRestartableBuilder,
    notification_sending,
)
from p2pwatch.domain.crawler_function import CrawlerFunction
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.observability.notification import RelayedLogLine
from p2pwatch.domain.observability.notification_sends import (
    NotificationService,
    local_database_dependency,
    notification_service_dependencies,
)
from p2pwatch.domain.observability.policy import Audience
from p2pwatch.domain.observability.severity import Severity
from tests.contracts.application.ports.driven.restartable_builder_contract import (
    RestartableBuilderContract,
)
from tests.fakes.adapters.driven.fake_apprise import FakeApprise
from tests.fakes.adapters.driven.fake_hanging_notifier import FakeHangingNotifier
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_loop_monotonic_clock import FakeLoopMonotonicClock
from tests.fakes.adapters.driven.fake_notification_outbox_store import FakeNotificationOutboxStore
from tests.fakes.adapters.driven.fake_notifier import ONE_SERVICE_PER_AUDIENCE, FakeNotifier
from tests.fakes.adapters.driven.fake_run_state_store import FakeRunStateStore
from tests.fakes.adapters.driven.fake_waker import FakeWaker
from tests.fakes.composition.fake_restartable_builder import FakeRestartableBuilder
from tests.support.application.steps.node_health import build_node_health
from tests.support.virtual_time import VirtualLoop

_COMMUNITY, _OPERATIONS = ONE_SERVICE_PER_AUDIENCE


def _build_notifier() -> AppriseNotifier:
    """An apprise notifier with no service, as the composition builds them."""
    return AppriseNotifier((), apprise_factory=FakeApprise)


class _Over(Work):
    """A work over one notifier, never run."""

    def __init__(self, notifier: AppriseNotifier) -> None:
        self.notifier = notifier

    def __str__(self) -> str:
        return "notification sending"

    async def wait_for_next_turn(self) -> None:
        """Never awaited."""

    async def run_once(self) -> None:
        """Never awaited."""


def _works_over(notifier: AppriseNotifier, /) -> Sequence[SupervisedWork]:
    return [SupervisedWork(work=_Over(notifier), time_limit=timedelta(minutes=5), function=None)]


class TestNotifierRestartableBuilder(RestartableBuilderContract):
    @pytest.fixture
    def restartable_builder(self) -> NotifierRestartableBuilder:
        return NotifierRestartableBuilder(build_notifier=_build_notifier, works_over=_works_over)

    def state_of(self, restartable: Restartable[object]) -> object:
        assert isinstance(restartable, NotifierRestartable)
        return restartable.notifier

    def state_reached(self, restartable: Restartable[object]) -> object:
        [supervised] = restartable.works()
        assert isinstance(supervised, SupervisedWork)
        assert isinstance(supervised.work, _Over)
        return supervised.work.notifier


def test_it_names_its_notifiers_as_the_notifier_s_part_is() -> None:
    builder = NotifierRestartableBuilder(build_notifier=_build_notifier, works_over=_works_over)

    assert str(builder) == "notifier"


def _outbox() -> NotificationOutbox:
    store = FakeNotificationOutboxStore()
    return NotificationOutbox(
        writer=store,
        reader=store,
        services=ONE_SERVICE_PER_AUDIENCE,
        waker=FakeWaker(),
        logger=FakeLogger(),
    )


def _sender(
    service: NotificationService, *, outbox: NotificationOutbox, notifier: Notifier
) -> NotificationSender:
    return NotificationSender(
        service=service,
        outbox=outbox,
        notifier=notifier,
        notification_timeout_seconds=5.0,
        node_health=build_node_health(),
        service_dependencies=notification_service_dependencies(
            ONE_SERVICE_PER_AUDIENCE, node_id=NodeId("n1")
        ),
        local_database=local_database_dependency(node_id=NodeId("n1")),
        logger=FakeLogger(),
    )


def test_each_service_s_sending_is_a_work_of_its_own_one_send_s_timeout_and_the_margin() -> None:
    outbox, notifier = _outbox(), FakeNotifier()
    senders = [_sender(s, outbox=outbox, notifier=notifier) for s in ONE_SERVICE_PER_AUDIENCE]

    works = notification_sending(senders, notification_timeout_seconds=5.0)

    assert works == [
        SupervisedWork(
            work=sender,
            time_limit=timedelta(minutes=5, seconds=5),
            function=CrawlerFunction.NOTIFICATIONS,
        )
        for sender in senders
    ]


def test_a_service_past_its_timeout_at_every_send_holds_none_of_another_service_s_entries(
    virtual_loop: VirtualLoop,
) -> None:
    outbox, notifier = _outbox(), FakeNotifier()
    online = RelayedLogLine(message="🟢 node online", severity=Severity.INFO, node_id=NodeId("n1"))
    for _ in range(10):  # 50 s of sends past their 5 s timeout, one after the other
        outbox.leave(online, services=[_COMMUNITY])
    outbox.leave(online, services=[_OPERATIONS])
    works = notification_sending(
        [
            _sender(_COMMUNITY, outbox=outbox, notifier=FakeHangingNotifier()),
            _sender(_OPERATIONS, outbox=outbox, notifier=notifier),
        ],
        notification_timeout_seconds=5.0,
    )
    run_state = FakeRunStateStore()
    virtual_loop.call_later(1.0, run_state.set_shutdown_requested)
    supervisor = Supervisor(
        run_state_reader=run_state,
        monotonic_clock=FakeLoopMonotonicClock(virtual_loop),
        node_health=build_node_health(),
        node_id=NodeId("n1"),
        logger=FakeLogger(),
    )

    async def supervise() -> None:
        await supervisor.build_first(FakeRestartableBuilder("notifier", works_over=lambda _: works))
        await supervisor.supervise(arm_shutdown_bound=lambda: None)

    virtual_loop.run_until_complete(supervise())

    assert notifier.calls == [(Audience.OPERATIONS, online)]
