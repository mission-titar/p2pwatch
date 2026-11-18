"""The notifier's work: each turn sends the oldest notification left within the notification
timeout and removes it, a refusal or a timeout a failed send recorded on its service's part, any
other error a bug of the turn; a cancelled send keeps its entry."""

import asyncio
from dataclasses import dataclass

import pytest

from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.application.steps.health_alerter import HealthAlerter
from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.notification_outbox import NotificationOutbox
from p2pwatch.application.steps.notification_sender import NotificationSender
from p2pwatch.domain.health.external_dependency import ExternalDependency
from p2pwatch.domain.health.health_rule import HealthRule
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.matching.identifiers import TargetId
from p2pwatch.domain.observability.events import TargetTitle
from p2pwatch.domain.observability.notification import CompletedDownload, RelayedLogLine
from p2pwatch.domain.observability.notification_sends import (
    SENDS_FAILED,
    NotificationRefusedError,
    NotificationService,
    PendingNotification,
    notification_service_dependencies,
)
from p2pwatch.domain.observability.policy import Audience
from p2pwatch.domain.observability.severity import Severity
from tests.fakes.adapters.driven.fake_hanging_notifier import FakeHangingNotifier
from tests.fakes.adapters.driven.fake_held_notifier import FakeHeldNotifier
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_notifier import ONE_SERVICE_PER_AUDIENCE, FakeNotifier
from tests.fakes.adapters.driven.fake_raising_notifier import FakeRaisingNotifier
from tests.fakes.adapters.driven.fake_waker import FakeWaker
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes

pytestmark = pytest.mark.asyncio

_NODE_ID = NodeId("titar-node-1")
_COMPLETED = CompletedDownload(
    target_titles=(TargetTitle(target_id=TargetId("062A"), title="t"),),
    filename="Keroro 062.avi",
    node_id=_NODE_ID,
)
_ONLINE = RelayedLogLine(message="🟢 node online", severity=Severity.INFO, node_id=_NODE_ID)
# The fakes' one service for the community, which ``_COMPLETED`` is left for.
_COMMUNITY = ONE_SERVICE_PER_AUDIENCE[0]
_OPERATIONS = ONE_SERVICE_PER_AUDIENCE[1]


@dataclass(kw_only=True, frozen=True)
class _Check:
    part: str
    rule: HealthRule
    detected: bool


class _Checks:
    """Keeps each check the sender records, in order."""

    def __init__(self) -> None:
        self.recorded: list[_Check] = []

    async def __call__(self, *, on: ExternalDependency, rule: HealthRule, detected: bool) -> None:
        self.recorded.append(_Check(part=on.name, rule=rule, detected=detected))


def _sender(
    notifier: Notifier,
    *,
    outbox: NotificationOutbox,
    logger: FakeLogger | None = None,
    timeout: float = 5.0,
    checks: _Checks | None = None,
) -> NotificationSender:
    return NotificationSender(
        outbox=outbox,
        notifier=notifier,
        notification_timeout_seconds=timeout,
        record_check=checks or _Checks(),
        service_dependencies=notification_service_dependencies(notifier.services()),
        logger=logger or FakeLogger(),
    )


def _completed_left() -> NotificationOutbox:
    outbox = NotificationOutbox(waker=FakeWaker())
    outbox.leave(_COMPLETED, services=[_COMMUNITY])
    return outbox


async def test_it_is_named_in_the_log_by_what_it_does() -> None:
    sender = _sender(FakeNotifier(), outbox=_completed_left())

    assert str(sender) == "notification sending"


async def test_its_wait_returns_once_a_notification_is_left() -> None:
    outbox = NotificationOutbox(waker=FakeWaker())
    waiting = asyncio.create_task(_sender(FakeNotifier(), outbox=outbox).wait_for_next_turn())
    for _ in range(3):
        await asyncio.sleep(0)  # noqa: TID251
    waited_while_empty = not waiting.done()

    outbox.leave(_COMPLETED, services=[_COMMUNITY])
    await asyncio.wait_for(waiting, 1.0)

    assert waited_while_empty


async def test_a_turn_sends_the_oldest_notification_left_then_removes_it() -> None:
    notifier, outbox = FakeNotifier(), _completed_left()
    outbox.leave(_ONLINE, services=[_OPERATIONS])

    await _sender(notifier, outbox=outbox).run_once()

    assert notifier.calls == [(Audience.COMMUNITY, _COMPLETED)]
    assert outbox.oldest() == PendingNotification(notification=_ONLINE, service=_OPERATIONS)


async def test_a_send_that_worked_records_its_service_s_sends_as_not_failed() -> None:
    checks = _Checks()

    await _sender(FakeNotifier(), outbox=_completed_left(), checks=checks).run_once()

    assert checks.recorded == [
        _Check(part="notifier fake community", rule=SENDS_FAILED, detected=False)
    ]


async def test_a_refused_send_is_a_failed_send_logged_in_one_line_and_removed() -> None:
    logger, checks, outbox = FakeLogger(), _Checks(), _completed_left()
    refusing = FakeRaisingNotifier(NotificationRefusedError("the service refused it (FAILURE)"))

    await _sender(refusing, outbox=outbox, logger=logger, checks=checks).run_once()

    assert logger.lines == [
        LoggedLine(
            level="warning",
            message="notifier fake community: notification not sent: "
            "the service refused it (FAILURE)",
        )
    ]
    assert checks.recorded == [
        _Check(part="notifier fake community", rule=SENDS_FAILED, detected=True)
    ]
    assert outbox.oldest() is None


async def test_a_send_past_its_timeout_is_a_failed_send_logged_in_one_line_and_removed() -> None:
    logger, checks, outbox = FakeLogger(), _Checks(), _completed_left()
    sender = _sender(
        FakeHangingNotifier(), outbox=outbox, logger=logger, timeout=0.01, checks=checks
    )

    await sender.run_once()

    assert logger.lines == [
        LoggedLine(
            level="warning",
            message="notifier fake community: notification not sent: past its timeout of 0.01 s",
        )
    ]
    assert checks.recorded == [
        _Check(part="notifier fake community", rule=SENDS_FAILED, detected=True)
    ]
    assert outbox.oldest() is None


async def test_any_other_exception_of_the_notifier_is_a_bug_of_the_turn_its_entry_removed() -> None:
    checks, outbox, bug = _Checks(), _completed_left(), RuntimeError("canal mort")
    sender = _sender(FakeRaisingNotifier(bug), outbox=outbox, checks=checks)

    with pytest.raises(RuntimeError) as raised:
        await sender.run_once()

    # A bug tells nothing of whether the service takes the sends.
    assert (raised.value, checks.recorded, outbox.oldest()) == (bug, [], None)


async def test_a_timeout_error_the_notifier_raises_itself_is_a_bug_not_a_timeout() -> None:
    sender = _sender(FakeRaisingNotifier(TimeoutError("its own")), outbox=_completed_left())

    with pytest.raises(TimeoutError, match="its own"):
        await sender.run_once()


async def test_a_send_cancelled_mid_send_keeps_its_entry() -> None:
    notifier, outbox = FakeHeldNotifier(), _completed_left()
    turn = asyncio.create_task(_sender(notifier, outbox=outbox).run_once())
    await asyncio.wait_for(notifier.reached.wait(), 1.0)

    turn.cancel()
    with pytest.raises(asyncio.CancelledError):
        await turn

    assert outbox.oldest() == PendingNotification(notification=_COMPLETED, service=_COMMUNITY)


async def test_a_turn_with_nothing_left_sends_and_records_nothing() -> None:
    notifier, checks = FakeNotifier(), _Checks()
    outbox = NotificationOutbox(waker=FakeWaker())

    await _sender(notifier, outbox=outbox, checks=checks).run_once()

    assert (notifier.calls, checks.recorded) == ([], [])


async def test_what_is_left_is_sent_oldest_first_a_bug_logged_with_its_trace() -> None:
    logger, bug = FakeLogger(), RuntimeError("an embed apprise cannot build")
    notifier = FakeRaisingNotifier(bug)
    outbox = _completed_left()
    outbox.leave(_ONLINE, services=[_OPERATIONS])

    await _sender(notifier, outbox=outbox, logger=logger).send_what_is_left()

    assert notifier.sends == 2
    assert (
        logger.lines
        == [LoggedLine(level="error", message="bug in notification sending", error=bug)] * 2
    )
    assert outbox.oldest() is None


async def test_two_services_one_refusing_the_other_sent_once_the_refused_tried_once() -> None:
    refused = NotificationService(scheme="discord", audience=Audience.OPERATIONS)
    taking = NotificationService(scheme="ntfy", audience=Audience.OPERATIONS)
    notifier, logger = FakeNotifier((refused, taking), refusing=[refused]), FakeLogger()
    outbox = NotificationOutbox(waker=FakeWaker())
    outbox.leave(_ONLINE, services=[refused, taking])
    sender = _sender(notifier, outbox=outbox, logger=logger)

    await sender.send_what_is_left()

    assert notifier.calls == [(Audience.OPERATIONS, _ONLINE)]
    assert [line.message for line in logger.lines] == [
        "notifier discord operations: notification not sent: the service refused it (FAILURE)"
    ]
    assert outbox.oldest() is None


async def test_a_service_refusing_every_send_fails_its_sends_in_the_log_and_alerts_no_one() -> None:
    observability, health_logger = ObservabilityOverFakes(), FakeLogger()
    alerter = HealthAlerter(
        observability_dispatcher=observability.dispatcher, node_id=_NODE_ID, min_free_bytes=None
    )
    sender = NotificationSender(
        outbox=observability.outbox,
        notifier=FakeNotifier(refusing=[_OPERATIONS]),
        notification_timeout_seconds=5.0,
        record_check=NodeHealth(logger=health_logger, subscribers=(alerter.send,)).record,
        service_dependencies=notification_service_dependencies(ONE_SERVICE_PER_AUDIENCE),
        logger=FakeLogger(),
    )
    for _ in range(3):
        observability.outbox.leave(_ONLINE, services=[_OPERATIONS])

    await sender.send_what_is_left()

    assert health_logger.lines == [
        LoggedLine(
            level="warning", message="notifier fake operations, sends failed: unknown to failing"
        )
    ]
    # An alert would go through the service that refuses it: none is left.
    assert (observability.notifications, observability.outbox.oldest()) == ([], None)
