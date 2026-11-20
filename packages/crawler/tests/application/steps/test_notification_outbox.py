"""The outbox: one entry per notification and service, the oldest first, each leave waking the
notifier's work, whose wait returns once it holds an entry."""

import asyncio

import pytest

from p2pwatch.application.steps.notification_outbox import NotificationOutbox
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.observability.notification import RelayedLogLine
from p2pwatch.domain.observability.notification_sends import (
    NotificationService,
    PendingNotification,
)
from p2pwatch.domain.observability.policy import Audience
from p2pwatch.domain.observability.severity import Severity
from p2pwatch.domain.wake_subject import WakeSubject
from tests.fakes.adapters.driven.fake_waker import FakeWaker

pytestmark = pytest.mark.asyncio

_ONLINE = RelayedLogLine(message="🟢 node online", severity=Severity.INFO, node_id=NodeId("n1"))
_OFFLINE = RelayedLogLine(message="🔴 node offline", severity=Severity.INFO, node_id=NodeId("n1"))
_DISCORD = NotificationService(scheme="discord", audience=Audience.OPERATIONS)
_NTFY = NotificationService(scheme="ntfy", audience=Audience.OPERATIONS)


async def test_each_notification_is_left_for_each_service_and_taken_out_oldest_first() -> None:
    outbox = NotificationOutbox(waker=FakeWaker())
    outbox.leave(_ONLINE, services=[_DISCORD, _NTFY])
    outbox.leave(_OFFLINE, services=[_DISCORD])

    taken = []
    while (entry := outbox.oldest()) is not None:
        taken.append(entry)
        outbox.remove(entry)

    assert taken == [
        PendingNotification(notification=_ONLINE, service=_DISCORD),
        PendingNotification(notification=_ONLINE, service=_NTFY),
        PendingNotification(notification=_OFFLINE, service=_DISCORD),
    ]


async def test_a_notification_left_wakes_the_notifier_s_work() -> None:
    waker = FakeWaker()

    NotificationOutbox(waker=waker).leave(_ONLINE, services=[_DISCORD])

    assert waker.woken_subjects == [WakeSubject.NOTIFICATION]


async def test_the_wait_returns_once_a_notification_is_left() -> None:
    outbox = NotificationOutbox(waker=FakeWaker())
    waiting = asyncio.create_task(outbox.wait_for_an_entry())
    for _ in range(3):
        await asyncio.sleep(0)  # noqa: TID251
    waited_while_empty = not waiting.done()

    outbox.leave(_ONLINE, services=[_DISCORD])
    await asyncio.wait_for(waiting, 1.0)

    assert waited_while_empty


async def test_the_wait_returns_at_once_while_it_holds_an_entry() -> None:
    outbox = NotificationOutbox(waker=FakeWaker())
    outbox.leave(_ONLINE, services=[_DISCORD])
    await outbox.wait_for_an_entry()  # the wake, taken by this wait

    waiting = asyncio.create_task(outbox.wait_for_an_entry())
    for _ in range(3):
        await asyncio.sleep(0)  # noqa: TID251

    assert waiting.done()


async def test_a_wake_with_nothing_left_since_the_entries_were_sent_keeps_waiting() -> None:
    outbox = NotificationOutbox(waker=FakeWaker())
    outbox.leave(_ONLINE, services=[_DISCORD])
    outbox.remove(PendingNotification(notification=_ONLINE, service=_DISCORD))
    waiting = asyncio.create_task(outbox.wait_for_an_entry())
    for _ in range(3):
        await asyncio.sleep(0)  # noqa: TID251

    assert not waiting.done()
    waiting.cancel()
