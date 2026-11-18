"""The promise of the ``NotificationOutboxReader`` and ``NotificationOutboxWriter`` pair."""

from abc import ABC, abstractmethod
from datetime import timedelta
from random import Random

import pytest

from p2pwatch.application.ports.driven.notification_outbox_reader import NotificationOutboxReader
from p2pwatch.application.ports.driven.notification_outbox_writer import NotificationOutboxWriter
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.matching.decision_tier import DecisionTier
from p2pwatch.domain.matching.identifiers import TargetId
from p2pwatch.domain.observability.events import TargetTitle
from p2pwatch.domain.observability.notification import (
    CompletedDownload,
    Notification,
    RelayedLogLine,
    SourceAlert,
    SourceAlertKind,
    TierRise,
)
from p2pwatch.domain.observability.notification_sends import (
    NotificationService,
    PendingNotification,
)
from p2pwatch.domain.observability.policy import Audience
from p2pwatch.domain.observability.severity import Severity
from p2pwatch.domain.source import SourceKey
from p2pwatch.domain.store_error import StoreError
from tests.support.draws import draw_quantity, draw_text
from tests.support.refused_writes import RefuseWrites, draw_long_text


def _draw_hash(randomness: Random) -> str:
    return "".join(randomness.choices("0123456789abcdef", k=32))


def _draw_target_titles(randomness: Random) -> tuple[TargetTitle, ...]:
    return tuple(
        TargetTitle(target_id=TargetId(draw_text(randomness)), title=draw_text(randomness))
        for _ in range(2)
    )


def _draw_source_alert(randomness: Random, *, first: bool) -> SourceAlert:
    """A first useful source, its name unknown, or one reappeared after a drawn absence."""
    return SourceAlert(
        kind=SourceAlertKind.FIRST_USEFUL if first else SourceAlertKind.REAPPEARED,
        source=SourceKey(network=Network.ED2K, native_id=_draw_hash(randomness)),
        source_name=None if first else draw_text(randomness),
        absent_for=None if first else timedelta(microseconds=draw_quantity(randomness)),
        target_titles=_draw_target_titles(randomness),
        filename=draw_text(randomness),
        node_id=NodeId(draw_text(randomness)),
    )


def _draw_notifications(randomness: Random) -> tuple[Notification, ...]:
    """One notification of each kind, a source alert of each kind."""
    return (
        RelayedLogLine(
            message=draw_text(randomness),
            severity=randomness.choice(list(Severity)),
            node_id=NodeId(draw_text(randomness)),
        ),
        TierRise(
            tier=randomness.choice(list(DecisionTier)),
            target_titles=_draw_target_titles(randomness),
            file=FileKey(network=Network.ED2K, native_id=_draw_hash(randomness)),
            filename=draw_text(randomness),
            size_bytes=draw_quantity(randomness),
            node_id=NodeId(draw_text(randomness)),
        ),
        _draw_source_alert(randomness, first=True),
        _draw_source_alert(randomness, first=False),
        CompletedDownload(
            target_titles=_draw_target_titles(randomness),
            filename=draw_text(randomness),
            node_id=NodeId(draw_text(randomness)),
        ),
    )


def _draw_service(randomness: Random) -> NotificationService:
    return NotificationService(
        scheme=draw_text(randomness),
        audience=randomness.choice(list(Audience)),
        ordinal=draw_quantity(randomness) + 1,
    )


def _draw_entries(randomness: Random) -> tuple[PendingNotification, ...]:
    """An entry per notification drawn, each for a drawn service."""
    return tuple(
        PendingNotification(notification=notification, service=_draw_service(randomness))
        for notification in _draw_notifications(randomness)
    )


class NotificationOutboxStoreContract(ABC):
    @pytest.fixture
    @abstractmethod
    def writer(self) -> NotificationOutboxWriter:
        """The writer of a store holding no entry yet."""

    @pytest.fixture
    @abstractmethod
    def reader(self) -> NotificationOutboxReader:
        """The reader of the writer's store."""

    @pytest.fixture
    @abstractmethod
    def refuse_writes(self) -> RefuseWrites:
        """Makes the writer's store refuse every write."""

    def test_a_save_its_store_refuses_raises_store_error_and_keeps_none(
        self,
        *,
        randomness: Random,
        writer: NotificationOutboxWriter,
        reader: NotificationOutboxReader,
        refuse_writes: RefuseWrites,
    ) -> None:
        notification = CompletedDownload(
            target_titles=(), filename=draw_long_text(randomness), node_id=NodeId("n")
        )
        entry = PendingNotification(notification=notification, service=_draw_service(randomness))
        refuse_writes()

        with pytest.raises(StoreError):
            writer.set_pending_notifications([entry])

        assert reader.read_pending_notifications() == ()

    def test_no_entry_is_read_before_the_first_save(self, reader: NotificationOutboxReader) -> None:
        assert reader.read_pending_notifications() == ()

    def test_every_kind_of_notification_saved_is_read_back_the_oldest_first(
        self,
        *,
        randomness: Random,
        writer: NotificationOutboxWriter,
        reader: NotificationOutboxReader,
    ) -> None:
        entries = _draw_entries(randomness)
        # One notification left twice for one service is two entries.
        entries_twice = (*entries, entries[0])

        writer.set_pending_notifications(entries_twice)

        assert reader.read_pending_notifications() == entries_twice

    def test_a_save_replaces_every_entry_saved_before(
        self,
        *,
        randomness: Random,
        writer: NotificationOutboxWriter,
        reader: NotificationOutboxReader,
    ) -> None:
        earlier, latest = _draw_entries(randomness), _draw_entries(randomness)
        writer.set_pending_notifications(earlier)

        writer.set_pending_notifications(latest[1:3])

        assert reader.read_pending_notifications() == latest[1:3]

    def test_a_save_of_no_entry_leaves_none(
        self,
        *,
        randomness: Random,
        writer: NotificationOutboxWriter,
        reader: NotificationOutboxReader,
    ) -> None:
        writer.set_pending_notifications(_draw_entries(randomness))

        writer.set_pending_notifications(())

        assert reader.read_pending_notifications() == ()
