"""The notifier as the node rebuilds it: built anew with the work sending the outbox's
notifications through it, one send's timeout and the margin its time limit."""

from collections.abc import Sequence
from datetime import timedelta

import pytest

from p2pwatch.adapters.driven.observability.apprise_notifier import AppriseNotifier
from p2pwatch.application.ports.driven.restartable import Restartable
from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.notification_outbox import NotificationOutbox
from p2pwatch.application.steps.notification_sender import NotificationSender
from p2pwatch.application.steps.work import SupervisedWork, Work
from p2pwatch.composition.notifier_restartable import NotifierRestartable, notification_sending
from p2pwatch.domain.observability.notification_sends import (
    local_database_dependency,
    notification_service_dependencies,
)
from tests.contracts.application.ports.driven.restartable_contract import RestartableContract
from tests.fakes.adapters.driven.fake_apprise import FakeApprise
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_notification_outbox_store import FakeNotificationOutboxStore
from tests.fakes.adapters.driven.fake_notifier import ONE_SERVICE_PER_AUDIENCE, FakeNotifier
from tests.fakes.adapters.driven.fake_waker import FakeWaker


class _Notifiers:
    """Builds apprise notifiers with no service, keeping each, as the composition builds them."""

    def __init__(self) -> None:
        self.built: list[AppriseNotifier] = []

    def build(self) -> AppriseNotifier:
        self.built.append(AppriseNotifier((), apprise_factory=FakeApprise))
        return self.built[-1]


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
    return [SupervisedWork(work=_Over(notifier), time_limit=timedelta(minutes=5), dependencies=())]


class TestNotifierRestartable(RestartableContract):
    @pytest.fixture
    def restartable(self) -> NotifierRestartable:
        self._notifiers = _Notifiers()
        self._notifiers.build()  # the first, which the composition builds
        return NotifierRestartable(build_notifier=self._notifiers.build, works_over=_works_over)

    def state_of(self, restartable: Restartable[object]) -> object:
        return self._notifiers.built[-1]

    def state_under(self, works: Sequence[object]) -> object:
        [supervised] = works
        assert isinstance(supervised, SupervisedWork)
        assert isinstance(supervised.work, _Over)
        return supervised.work.notifier


def test_it_is_named_as_the_notifier_s_part_is() -> None:
    notifier = NotifierRestartable(build_notifier=_Notifiers().build, works_over=_works_over)

    assert str(notifier) == "notifier"


def _sender() -> NotificationSender:
    notifier, store = FakeNotifier(), FakeNotificationOutboxStore()
    return NotificationSender(
        outbox=NotificationOutbox(
            writer=store,
            reader=store,
            services=notifier.services(),
            waker=FakeWaker(),
            logger=FakeLogger(),
        ),
        notifier=notifier,
        notification_timeout_seconds=5.0,
        record_check=NodeHealth(logger=FakeLogger(), subscribers=()).record,
        service_dependencies=notification_service_dependencies(notifier.services()),
        local_database=local_database_dependency(),
        logger=FakeLogger(),
    )


def test_the_sending_takes_one_send_s_timeout_and_the_margin_on_each_service_s_part() -> None:
    sender = _sender()
    parts = tuple(notification_service_dependencies(ONE_SERVICE_PER_AUDIENCE).values())

    works = notification_sending(sender, notification_timeout_seconds=5.0, dependencies=parts)

    assert works == [
        SupervisedWork(work=sender, time_limit=timedelta(minutes=5, seconds=5), dependencies=parts)
    ]


def test_no_service_has_nothing_to_send_and_so_no_sending() -> None:
    assert notification_sending(_sender(), notification_timeout_seconds=5.0, dependencies=()) == ()
