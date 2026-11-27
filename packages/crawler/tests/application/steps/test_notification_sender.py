"""The notifier's work, one per service: each turn sends the oldest notification left for its
service within the notification timeout and removes it, a refusal or a timeout a failed send
recorded on its service's part, any other error a bug of the turn; a cancelled send keeps its
entry. At the shutdown, every service's is sent at once."""

import asyncio

import pytest

from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.notification_outbox import NotificationOutbox
from p2pwatch.application.steps.notification_sender import NotificationSender, empty_the_outbox
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.matching.identifiers import TargetId
from p2pwatch.domain.observability.events import TargetTitle
from p2pwatch.domain.observability.notification import CompletedDownload, RelayedLogLine
from p2pwatch.domain.observability.notification_sends import (
    NotificationRefusedError,
    NotificationService,
    PendingNotification,
    local_database_dependency,
    notification_service_dependencies,
)
from p2pwatch.domain.observability.policy import Audience
from p2pwatch.domain.observability.severity import Severity
from tests.fakes.adapters.driven.fake_hanging_notifier import FakeHangingNotifier
from tests.fakes.adapters.driven.fake_held_notifier import FakeHeldNotifier
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_notification_outbox_store import FakeNotificationOutboxStore
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
# What the node's health logs once three turns recorded the same on the local database.
_SAVED = LoggedLine(level="info", message="local database, saves failed: unknown to healthy")
_FAILED_SENDS = LoggedLine(
    level="warning", message="notifier fake community, sends failed: unknown to failing"
)


def _sender(
    notifier: Notifier,
    *,
    outbox: NotificationOutbox,
    service: NotificationService = _COMMUNITY,
    logger: FakeLogger | None = None,
    timeout: float = 5.0,
    health_logger: FakeLogger | None = None,
) -> NotificationSender:
    return NotificationSender(
        service=service,
        outbox=outbox,
        notifier=notifier,
        notification_timeout_seconds=timeout,
        node_health=NodeHealth(
            logger=health_logger or FakeLogger(),
            observability_dispatcher=ObservabilityOverFakes().dispatcher,
        ),
        service_dependencies=notification_service_dependencies(notifier.services()),
        local_database=local_database_dependency(node_id=_NODE_ID),
        logger=logger or FakeLogger(),
    )


def _empty_outbox() -> NotificationOutbox:
    store = FakeNotificationOutboxStore()
    return NotificationOutbox(
        writer=store,
        reader=store,
        services=ONE_SERVICE_PER_AUDIENCE,
        waker=FakeWaker(),
        logger=FakeLogger(),
    )


def _completed_left(*, times: int = 1) -> NotificationOutbox:
    outbox = _empty_outbox()
    for _ in range(times):
        outbox.leave(_COMPLETED, services=[_COMMUNITY])
    return outbox


async def test_it_is_named_in_the_log_by_what_it_does_and_its_service() -> None:
    sender = _sender(FakeNotifier(), outbox=_completed_left())

    assert str(sender) == "notification sending fake community"


async def test_its_wait_returns_once_a_notification_is_left() -> None:
    outbox = _empty_outbox()
    waiting = asyncio.create_task(_sender(FakeNotifier(), outbox=outbox).wait_for_next_turn())
    for _ in range(3):
        await asyncio.sleep(0)  # noqa: TID251
    waited_while_empty = not waiting.done()

    outbox.leave(_COMPLETED, services=[_COMMUNITY])
    await asyncio.wait_for(waiting, 1.0)

    assert waited_while_empty


async def test_a_turn_sends_the_oldest_left_for_its_service_then_removes_it_another_s_kept() -> (
    None
):
    notifier, outbox = FakeNotifier(), _empty_outbox()
    outbox.leave(_ONLINE, services=[_OPERATIONS])
    outbox.leave(_COMPLETED, services=[_COMMUNITY])

    await _sender(notifier, outbox=outbox).run_once()

    assert notifier.calls == [(Audience.COMMUNITY, _COMPLETED)]
    assert (outbox.oldest(_COMMUNITY), outbox.oldest(_OPERATIONS)) == (
        None,
        PendingNotification(notification=_ONLINE, service=_OPERATIONS),
    )


async def test_sends_that_worked_record_their_service_s_sends_as_not_failed() -> None:
    health_logger = FakeLogger()
    sender = _sender(FakeNotifier(), outbox=_completed_left(times=3), health_logger=health_logger)

    await sender.send_what_is_left()

    assert health_logger.lines == [
        _SAVED,
        LoggedLine(
            level="info", message="notifier fake community, sends failed: unknown to healthy"
        ),
    ]


async def test_a_turn_records_on_the_local_database_whether_the_outbox_s_latest_save_failed() -> (
    None
):
    health_logger, store = FakeLogger(), FakeNotificationOutboxStore()
    outbox = NotificationOutbox(
        writer=store,
        reader=store,
        services=ONE_SERVICE_PER_AUDIENCE,
        waker=FakeWaker(),
        logger=FakeLogger(),
    )
    for _ in range(3):
        outbox.leave(_COMPLETED, services=[_COMMUNITY])
    store.writes_fail = True

    await _sender(FakeNotifier(), outbox=outbox, health_logger=health_logger).send_what_is_left()

    assert health_logger.lines == [
        LoggedLine(level="warning", message="local database, saves failed: unknown to failing"),
        LoggedLine(
            level="info", message="notifier fake community, sends failed: unknown to healthy"
        ),
    ]


async def test_a_refused_send_is_a_failed_send_logged_in_one_line_and_removed() -> None:
    logger, health_logger, outbox = FakeLogger(), FakeLogger(), _completed_left(times=3)
    refusing = FakeRaisingNotifier(NotificationRefusedError("the service refused it (FAILURE)"))
    sender = _sender(refusing, outbox=outbox, logger=logger, health_logger=health_logger)

    await sender.send_what_is_left()

    refused = "notifier fake community: notification not sent: the service refused it (FAILURE)"
    assert logger.lines == [LoggedLine(level="warning", message=refused)] * 3
    assert health_logger.lines == [_SAVED, _FAILED_SENDS]
    assert outbox.oldest(_COMMUNITY) is None


async def test_a_send_past_its_timeout_is_a_failed_send_logged_in_one_line_and_removed() -> None:
    logger, health_logger, outbox = FakeLogger(), FakeLogger(), _completed_left(times=3)
    sender = _sender(
        FakeHangingNotifier(),
        outbox=outbox,
        logger=logger,
        timeout=0.01,
        health_logger=health_logger,
    )

    await sender.send_what_is_left()

    past = "notifier fake community: notification not sent: past its timeout of 0.01 s"
    assert logger.lines == [LoggedLine(level="warning", message=past)] * 3
    assert health_logger.lines == [_SAVED, _FAILED_SENDS]
    assert outbox.oldest(_COMMUNITY) is None


async def test_any_other_exception_of_the_notifier_is_a_bug_of_the_turn_its_entry_removed() -> None:
    health_logger, outbox, bug = FakeLogger(), _completed_left(times=3), RuntimeError("canal mort")
    sender = _sender(FakeRaisingNotifier(bug), outbox=outbox, health_logger=health_logger)

    for _ in range(3):
        with pytest.raises(RuntimeError) as raised:
            await sender.run_once()

    # A bug tells nothing of whether the service takes the sends, but the removal was saved.
    assert (raised.value, health_logger.lines, outbox.oldest(_COMMUNITY)) == (bug, [_SAVED], None)


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

    assert outbox.oldest(_COMMUNITY) == PendingNotification(
        notification=_COMPLETED, service=_COMMUNITY
    )


async def test_a_turn_with_nothing_left_sends_and_records_nothing() -> None:
    notifier, health_logger = FakeNotifier(), FakeLogger()
    sender = _sender(notifier, outbox=_empty_outbox(), health_logger=health_logger)

    for _ in range(3):  # three records would turn the local database's rule
        await sender.run_once()

    assert (notifier.calls, health_logger.lines) == ([], [])


async def test_what_is_left_for_each_service_is_sent_a_bug_logged_with_its_trace() -> None:
    logger, bug = FakeLogger(), RuntimeError("an embed apprise cannot build")
    notifier = FakeRaisingNotifier(bug)
    outbox = _completed_left()
    outbox.leave(_ONLINE, services=[_OPERATIONS])

    await empty_the_outbox(
        [
            _sender(notifier, outbox=outbox, service=service, logger=logger)
            for service in ONE_SERVICE_PER_AUDIENCE
        ]
    )

    assert notifier.sends == 2
    assert logger.lines == [
        LoggedLine(level="error", message=f"bug in notification sending fake {audience}", error=bug)
        for audience in ("community", "operations")
    ]
    assert (outbox.oldest(_COMMUNITY), outbox.oldest(_OPERATIONS)) == (None, None)


async def test_emptying_the_outbox_sends_each_service_s_at_once_a_held_send_holding_no_other() -> (
    None
):
    held, notifier, outbox = FakeHeldNotifier(), FakeNotifier(), _completed_left()
    outbox.leave(_ONLINE, services=[_OPERATIONS])
    emptying = asyncio.create_task(
        empty_the_outbox(
            [
                _sender(held, outbox=outbox, service=_COMMUNITY),
                _sender(notifier, outbox=outbox, service=_OPERATIONS),
            ]
        )
    )
    await asyncio.wait_for(held.reached.wait(), 1.0)
    for _ in range(3):
        await asyncio.sleep(0)  # noqa: TID251

    # Its community send still held, the operations' already went out.
    assert notifier.calls == [(Audience.OPERATIONS, _ONLINE)]
    emptying.cancel()


async def test_emptying_the_outbox_sends_what_a_send_left_for_a_service_already_emptied() -> None:
    observability, notifier = ObservabilityOverFakes(), FakeNotifier()
    observability.outbox_store.writes_fail = True
    node_health = NodeHealth(logger=FakeLogger(), observability_dispatcher=observability.dispatcher)
    local_database = local_database_dependency(node_id=_NODE_ID)
    senders = [
        NotificationSender(
            service=service,
            outbox=observability.outbox,
            notifier=notifier,
            notification_timeout_seconds=5.0,
            node_health=node_health,
            service_dependencies=notification_service_dependencies(ONE_SERVICE_PER_AUDIENCE),
            local_database=local_database,
            logger=FakeLogger(),
        )
        for service in (_OPERATIONS, _COMMUNITY)
    ]
    for _ in range(3):
        observability.outbox.leave(_COMPLETED, services=[_COMMUNITY])

    await empty_the_outbox(senders)

    # The third community send records the third save refused, once the operations' had none.
    not_saved = RelayedLogLine(
        message="notifications not saved in local.db",
        detail="impact: lost at the next restart",
        severity=Severity.WARNING,
        node_id=_NODE_ID,
    )
    assert notifier.calls == [(Audience.COMMUNITY, _COMPLETED)] * 3 + [
        (Audience.OPERATIONS, not_saved)
    ]


async def test_two_services_one_refusing_the_other_sent_once_the_refused_tried_once() -> None:
    refused = NotificationService(scheme="discord", audience=Audience.OPERATIONS)
    taking = NotificationService(scheme="ntfy", audience=Audience.OPERATIONS)
    notifier, logger = FakeNotifier((refused, taking), refusing=[refused]), FakeLogger()
    outbox = _empty_outbox()
    outbox.leave(_ONLINE, services=[refused, taking])

    await empty_the_outbox(
        [
            _sender(notifier, outbox=outbox, service=service, logger=logger)
            for service in (refused, taking)
        ]
    )

    assert notifier.calls == [(Audience.OPERATIONS, _ONLINE)]
    assert [line.message for line in logger.lines] == [
        "notifier discord operations: notification not sent: the service refused it (FAILURE)"
    ]
    assert (outbox.oldest(refused), outbox.oldest(taking)) == (None, None)


async def test_a_service_refusing_every_send_fails_its_sends_in_the_log_and_alerts_no_one() -> None:
    observability, health_logger = ObservabilityOverFakes(), FakeLogger()
    sender = NotificationSender(
        service=_OPERATIONS,
        outbox=observability.outbox,
        notifier=FakeNotifier(refusing=[_OPERATIONS]),
        notification_timeout_seconds=5.0,
        node_health=NodeHealth(
            logger=health_logger, observability_dispatcher=observability.dispatcher
        ),
        service_dependencies=notification_service_dependencies(ONE_SERVICE_PER_AUDIENCE),
        local_database=local_database_dependency(node_id=_NODE_ID),
        logger=FakeLogger(),
    )
    for _ in range(3):
        observability.outbox.leave(_ONLINE, services=[_OPERATIONS])

    await sender.send_what_is_left()

    assert health_logger.lines == [
        LoggedLine(level="info", message="local database, saves failed: unknown to healthy"),
        LoggedLine(
            level="warning", message="notifier fake operations, sends failed: unknown to failing"
        ),
    ]
    # An alert would go through the service that refuses it: none is left.
    assert (observability.notifications, observability.outbox.oldest(_OPERATIONS)) == ([], None)


async def test_a_local_database_refusing_every_save_still_sends_every_entry_and_its_alert() -> None:
    observability, health_logger, notifier = ObservabilityOverFakes(), FakeLogger(), FakeNotifier()
    observability.outbox_store.writes_fail = True
    sender = NotificationSender(
        service=_OPERATIONS,
        outbox=observability.outbox,
        notifier=notifier,
        notification_timeout_seconds=5.0,
        node_health=NodeHealth(
            logger=health_logger, observability_dispatcher=observability.dispatcher
        ),
        service_dependencies=notification_service_dependencies(ONE_SERVICE_PER_AUDIENCE),
        local_database=local_database_dependency(node_id=_NODE_ID),
        logger=FakeLogger(),
    )
    for _ in range(3):
        observability.outbox.leave(_ONLINE, services=[_OPERATIONS])

    await sender.send_what_is_left()

    not_saved = RelayedLogLine(
        message="notifications not saved in local.db",
        detail="impact: lost at the next restart",
        severity=Severity.WARNING,
        node_id=_NODE_ID,
    )
    assert notifier.calls == [(Audience.OPERATIONS, _ONLINE)] * 3 + [
        (Audience.OPERATIONS, not_saved)
    ]
    assert health_logger.lines == [
        LoggedLine(level="warning", message="local database, saves failed: unknown to failing"),
        LoggedLine(
            level="info", message="notifier fake operations, sends failed: unknown to healthy"
        ),
    ]
