"""The notifier as the node builds it, at its start and at each rebuild: built anew with the work
sending the outbox's notifications through it, one send's timeout and the margin its time limit."""

from collections.abc import Sequence
from datetime import timedelta

import pytest

from p2pwatch.adapters.driven.observability.apprise_notifier import AppriseNotifier
from p2pwatch.application.ports.driven.restartable import Restartable
from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.notification_outbox import NotificationOutbox
from p2pwatch.application.steps.notification_sender import NotificationSender
from p2pwatch.application.steps.work import SupervisedWork, Work
from p2pwatch.composition.notifier_restartable import (
    NotifierRestartable,
    NotifierRestartableBuilder,
    notification_sending,
)
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.observability.notification_sends import (
    local_database_dependency,
    notification_service_dependencies,
)
from tests.contracts.application.ports.driven.restartable_builder_contract import (
    RestartableBuilderContract,
)
from tests.fakes.adapters.driven.fake_apprise import FakeApprise
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_notification_outbox_store import FakeNotificationOutboxStore
from tests.fakes.adapters.driven.fake_notifier import ONE_SERVICE_PER_AUDIENCE, FakeNotifier
from tests.fakes.adapters.driven.fake_waker import FakeWaker
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes


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
    return [SupervisedWork(work=_Over(notifier), time_limit=timedelta(minutes=5))]


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
        record_check=NodeHealth(
            logger=FakeLogger(), observability_dispatcher=ObservabilityOverFakes().dispatcher
        ).record,
        service_dependencies=notification_service_dependencies(notifier.services()),
        local_database=local_database_dependency(node_id=NodeId("n1")),
        logger=FakeLogger(),
    )


def test_the_sending_takes_one_send_s_timeout_and_the_margin() -> None:
    sender = _sender()

    works = notification_sending(
        sender, notification_timeout_seconds=5.0, services=ONE_SERVICE_PER_AUDIENCE
    )

    assert works == [SupervisedWork(work=sender, time_limit=timedelta(minutes=5, seconds=5))]


def test_no_service_has_nothing_to_send_and_so_no_sending() -> None:
    assert notification_sending(_sender(), notification_timeout_seconds=5.0, services=()) == ()
