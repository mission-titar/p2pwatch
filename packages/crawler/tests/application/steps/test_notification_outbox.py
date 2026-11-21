"""The outbox: one entry per notification and service, the oldest first, each leave waking the
notifier's work, whose wait returns once it holds an entry; saved at each change, read back when
built."""

import asyncio
from contextlib import closing
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.sqlite_notification_outbox_store import (
    SqliteNotificationOutboxStore,
)
from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.notification_outbox import NotificationOutbox
from p2pwatch.application.steps.notification_sender import NotificationSender
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.observability.notification import RelayedLogLine
from p2pwatch.domain.observability.notification_sends import (
    NotificationService,
    PendingNotification,
    local_database_dependency,
    notification_service_dependencies,
)
from p2pwatch.domain.observability.policy import Audience
from p2pwatch.domain.observability.severity import Severity
from p2pwatch.domain.wake_subject import WakeSubject
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_notification_outbox_store import FakeNotificationOutboxStore
from tests.fakes.adapters.driven.fake_notifier import FakeNotifier
from tests.fakes.adapters.driven.fake_waker import FakeWaker
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_local
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes

pytestmark = pytest.mark.asyncio

_ONLINE = RelayedLogLine(message="🟢 node online", severity=Severity.INFO, node_id=NodeId("n1"))
_OFFLINE = RelayedLogLine(message="🔴 node offline", severity=Severity.INFO, node_id=NodeId("n1"))
_DISCORD = NotificationService(scheme="discord", audience=Audience.OPERATIONS)
_NTFY = NotificationService(scheme="ntfy", audience=Audience.OPERATIONS)
_DISCORD_2 = NotificationService(scheme="discord", audience=Audience.OPERATIONS, ordinal=2)


def _outbox(
    *,
    store: FakeNotificationOutboxStore | SqliteNotificationOutboxStore | None = None,
    waker: FakeWaker | None = None,
    logger: FakeLogger | None = None,
    services: tuple[NotificationService, ...] = (_DISCORD, _NTFY),
) -> NotificationOutbox:
    store = store or FakeNotificationOutboxStore()
    return NotificationOutbox(
        writer=store,
        reader=store,
        services=services,
        waker=waker or FakeWaker(),
        logger=logger or FakeLogger(),
    )


def _taken(
    outbox: NotificationOutbox, *, service: NotificationService
) -> list[PendingNotification]:
    """Each entry it holds for ``service``, the oldest first, taken out."""
    taken = []
    while (entry := outbox.oldest(service)) is not None:
        taken.append(entry)
        outbox.remove(entry)
    return taken


async def test_each_notification_is_left_for_each_service_each_one_s_taken_oldest_first() -> None:
    outbox = _outbox()
    outbox.leave(_ONLINE, services=[_DISCORD, _NTFY])
    outbox.leave(_OFFLINE, services=[_DISCORD])

    assert (_taken(outbox, service=_DISCORD), _taken(outbox, service=_NTFY)) == (
        [
            PendingNotification(notification=_ONLINE, service=_DISCORD),
            PendingNotification(notification=_OFFLINE, service=_DISCORD),
        ],
        [PendingNotification(notification=_ONLINE, service=_NTFY)],
    )


async def test_a_notification_left_wakes_the_notifier_s_work() -> None:
    waker = FakeWaker()

    _outbox(waker=waker).leave(_ONLINE, services=[_DISCORD])

    assert waker.woken_subjects == [WakeSubject.NOTIFICATION]


async def test_the_wait_returns_once_a_notification_is_left() -> None:
    outbox = _outbox()
    waiting = asyncio.create_task(outbox.wait_for_an_entry(_DISCORD))
    for _ in range(3):
        await asyncio.sleep(0)  # noqa: TID251
    waited_while_empty = not waiting.done()

    outbox.leave(_ONLINE, services=[_DISCORD])
    await asyncio.wait_for(waiting, 1.0)

    assert waited_while_empty


async def test_the_wait_for_one_service_keeps_waiting_while_only_another_s_entries_are_left() -> (
    None
):
    outbox = _outbox()
    waiting = asyncio.create_task(outbox.wait_for_an_entry(_DISCORD))

    outbox.leave(_ONLINE, services=[_NTFY])
    for _ in range(3):
        await asyncio.sleep(0)  # noqa: TID251

    assert not waiting.done()
    waiting.cancel()


async def test_the_wait_returns_at_once_while_it_holds_an_entry() -> None:
    outbox = _outbox()
    outbox.leave(_ONLINE, services=[_DISCORD])
    await outbox.wait_for_an_entry(_DISCORD)  # the wake, taken by this wait

    waiting = asyncio.create_task(outbox.wait_for_an_entry(_DISCORD))
    for _ in range(3):
        await asyncio.sleep(0)  # noqa: TID251

    assert waiting.done()


async def test_a_wake_with_nothing_left_since_the_entries_were_sent_keeps_waiting() -> None:
    outbox = _outbox()
    outbox.leave(_ONLINE, services=[_DISCORD])
    outbox.remove(PendingNotification(notification=_ONLINE, service=_DISCORD))
    waiting = asyncio.create_task(outbox.wait_for_an_entry(_DISCORD))
    for _ in range(3):
        await asyncio.sleep(0)  # noqa: TID251

    assert not waiting.done()
    waiting.cancel()


async def test_each_change_saves_the_entries_it_holds_the_oldest_first() -> None:
    store = FakeNotificationOutboxStore()
    outbox = _outbox(store=store)

    outbox.leave(_ONLINE, services=[_DISCORD, _NTFY])
    saved_once_left = store.read_pending_notifications()
    outbox.remove(PendingNotification(notification=_ONLINE, service=_DISCORD))

    assert (saved_once_left, store.read_pending_notifications()) == (
        (
            PendingNotification(notification=_ONLINE, service=_DISCORD),
            PendingNotification(notification=_ONLINE, service=_NTFY),
        ),
        (PendingNotification(notification=_ONLINE, service=_NTFY),),
    )


async def test_a_save_its_store_refuses_is_logged_in_one_line_its_entries_kept_in_memory() -> None:
    store, logger = FakeNotificationOutboxStore(), FakeLogger()
    store.writes_fail = True
    outbox = _outbox(store=store, logger=logger)

    outbox.leave(_ONLINE, services=[_DISCORD])

    assert logger.lines == [
        LoggedLine(
            level="warning",
            message="notification outbox not saved (disk I/O error): "
            "saved again at its next change",
        )
    ]
    assert _taken(outbox, service=_DISCORD) == [
        PendingNotification(notification=_ONLINE, service=_DISCORD)
    ]


async def test_it_keeps_whether_its_latest_save_failed() -> None:
    store = FakeNotificationOutboxStore()
    outbox = _outbox(store=store)
    before_any_save = outbox.latest_save_failed

    store.writes_fail = True
    outbox.leave(_ONLINE, services=[_DISCORD])
    once_refused = outbox.latest_save_failed
    store.writes_fail = False
    outbox.leave(_OFFLINE, services=[_DISCORD])

    assert (before_any_save, once_refused, outbox.latest_save_failed) == (False, True, False)


async def test_it_reads_back_the_entries_an_earlier_one_saved_the_oldest_first() -> None:
    store = FakeNotificationOutboxStore()
    earlier = _outbox(store=store)
    earlier.leave(_ONLINE, services=[_NTFY, _DISCORD])
    earlier.leave(_OFFLINE, services=[_NTFY])

    outbox = _outbox(store=store)
    assert (_taken(outbox, service=_NTFY), _taken(outbox, service=_DISCORD)) == (
        [
            PendingNotification(notification=_ONLINE, service=_NTFY),
            PendingNotification(notification=_OFFLINE, service=_NTFY),
        ],
        [PendingNotification(notification=_ONLINE, service=_DISCORD)],
    )


async def test_an_entry_for_a_service_no_longer_configured_is_dropped_in_one_line() -> None:
    store, logger = FakeNotificationOutboxStore(), FakeLogger()
    _outbox(store=store, services=(_DISCORD, _DISCORD_2, _NTFY)).leave(
        _ONLINE, services=[_NTFY, _DISCORD, _DISCORD_2]
    )

    outbox = _outbox(store=store, logger=logger, services=(_DISCORD,))

    assert logger.lines == [
        LoggedLine(
            level="warning",
            message="2 notification(s) dropped, their service no longer configured: "
            "discord operations 2, ntfy operations",
        )
    ]
    kept = (PendingNotification(notification=_ONLINE, service=_DISCORD),)
    assert (store.read_pending_notifications(), outbox.oldest(_DISCORD)) == (kept, kept[0])


async def test_an_entry_it_cannot_read_back_is_dropped_in_one_line(tmp_path: Path) -> None:
    logger = FakeLogger()
    with closing(open_local(tmp_path / "local.db")) as local:
        store = SqliteNotificationOutboxStore(local)
        _outbox(store=store).leave(_ONLINE, services=[_DISCORD])
        # Left by an earlier version, without a field a later one added.
        local.execute(
            "INSERT INTO pending_notifications VALUES "
            "(2, 'discord', 'operations', 1, 'completed_download', '{}')"
        )

        outbox = _outbox(store=store, logger=logger)

        assert logger.lines == [
            LoggedLine(
                level="warning",
                message="1 notification(s) dropped, unreadable: a stored value cannot be read: "
                "a stored notification is malformed: KeyError('target_titles')",
            )
        ]
        kept = (PendingNotification(notification=_ONLINE, service=_DISCORD),)
        assert (store.read_pending_notifications(), outbox.oldest(_DISCORD)) == (kept, kept[0])


async def test_a_notification_for_no_service_is_neither_saved_nor_woken_for() -> None:
    store, waker = FakeNotificationOutboxStore(), FakeWaker()
    store.writes_fail = True
    outbox = _outbox(store=store, waker=waker)

    outbox.leave(_ONLINE, services=[])

    # A node without notifications opens no write of local.db for each of its events.
    assert (outbox.latest_save_failed, waker.woken_subjects) == (False, [])


async def test_a_notification_left_before_a_stop_is_sent_after_the_start(tmp_path: Path) -> None:
    services = (_DISCORD,)
    with closing(open_local(tmp_path / "local.db")) as before_the_stop:
        store = SqliteNotificationOutboxStore(before_the_stop)
        _outbox(store=store, services=services).leave(_ONLINE, services=services)
    notifier = FakeNotifier(services)

    with closing(open_local(tmp_path / "local.db")) as after_the_start:
        store = SqliteNotificationOutboxStore(after_the_start)
        await NotificationSender(
            service=_DISCORD,
            outbox=_outbox(store=store, services=services),
            notifier=notifier,
            notification_timeout_seconds=5.0,
            record_check=NodeHealth(
                logger=FakeLogger(), observability_dispatcher=ObservabilityOverFakes().dispatcher
            ).record,
            service_dependencies=notification_service_dependencies(services),
            local_database=local_database_dependency(node_id=NodeId("n1")),
            logger=FakeLogger(),
        ).run_once()

    assert notifier.calls == [(Audience.OPERATIONS, _ONLINE)]
