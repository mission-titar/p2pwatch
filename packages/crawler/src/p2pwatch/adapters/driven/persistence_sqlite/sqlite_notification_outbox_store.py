"""``SqliteNotificationOutboxStore``: the notification outbox's ports on ``local.db``'s
``pending_notifications``, one row per entry, replaced whole at each save."""

import json
import sqlite3
from collections.abc import Sequence
from datetime import timedelta
from typing import Any, assert_never

from p2pwatch.adapters.driven.persistence_sqlite.errors import (
    PersistenceError,
    wrap_sqlite_errors,
    wrap_stored_value_errors,
)
from p2pwatch.adapters.driven.persistence_sqlite.immediate_transaction import immediate_transaction
from p2pwatch.adapters.driven.persistence_sqlite.named_row import NamedRow
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
    UnreadableNotification,
)
from p2pwatch.domain.observability.policy import Audience
from p2pwatch.domain.observability.severity import Severity
from p2pwatch.domain.source import SourceKey

_SELECT = """
SELECT service_scheme, service_audience, service_ordinal, kind, notification
FROM pending_notifications
ORDER BY id
"""

_INSERT = """
INSERT INTO pending_notifications
(id, service_scheme, service_audience, service_ordinal, kind, notification)
VALUES (?, ?, ?, ?, ?, ?)
"""

_MICROSECOND = timedelta(microseconds=1)

type _Fields = dict[str, Any]


class SqliteNotificationOutboxStore(NotificationOutboxReader, NotificationOutboxWriter):
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def read_pending_notifications(
        self,
    ) -> tuple[PendingNotification | UnreadableNotification, ...]:
        with wrap_sqlite_errors():
            rows = self._connection.execute(_SELECT).fetchall()
        return tuple(map(_entry_or_unreadable, rows))

    def set_pending_notifications(self, entries: Sequence[PendingNotification]) -> None:
        """Replaces the whole table in one transaction, the oldest entry the lowest id."""
        rows = [
            (
                entry_id,
                entry.service.scheme,
                entry.service.audience.value,
                entry.service.ordinal,
                *_kind_and_fields(entry.notification),
            )
            for entry_id, entry in enumerate(entries, start=1)
        ]
        with wrap_sqlite_errors(), immediate_transaction(self._connection):
            self._connection.execute("DELETE FROM pending_notifications")
            self._connection.executemany(_INSERT, rows)


def _kind_and_fields(notification: Notification) -> tuple[str, str]:
    """The kind of ``notification`` and its fields as the text of a JSON object."""
    match notification:
        case RelayedLogLine():
            kind = "relayed_log_line"
            fields: _Fields = {
                "message": notification.message,
                "severity": notification.severity.name,
            }
        case TierRise():
            kind = "tier_rise"
            fields = {
                "tier": notification.tier.value,
                "target_titles": _target_titles_fields(notification.target_titles),
                "network": notification.file.network.value,
                "native_id": notification.file.native_id,
                "filename": notification.filename,
                "size_bytes": notification.size_bytes,
            }
        case SourceAlert():
            kind = "source_alert"
            absent_for = notification.absent_for
            fields = {
                "kind": notification.kind.value,
                "network": notification.source.network.value,
                "native_id": notification.source.native_id,
                "source_name": notification.source_name,
                "absent_for_micros": None if absent_for is None else absent_for // _MICROSECOND,
                "target_titles": _target_titles_fields(notification.target_titles),
                "filename": notification.filename,
            }
        case CompletedDownload():
            kind = "completed_download"
            fields = {
                "target_titles": _target_titles_fields(notification.target_titles),
                "filename": notification.filename,
            }
        case _:  # pragma: no cover
            assert_never(notification)
    return kind, json.dumps(fields | {"node_id": notification.node_id})


def _target_titles_fields(target_titles: tuple[TargetTitle, ...]) -> list[_Fields]:
    return [{"target_id": title.target_id, "title": title.title} for title in target_titles]


def _target_titles(fields: _Fields) -> tuple[TargetTitle, ...]:
    return tuple(
        TargetTitle(target_id=TargetId(title["target_id"]), title=title["title"])
        for title in fields["target_titles"]
    )


def _relayed_log_line(fields: _Fields) -> RelayedLogLine:
    return RelayedLogLine(
        message=fields["message"],
        severity=Severity[fields["severity"]],
        node_id=NodeId(fields["node_id"]),
    )


def _tier_rise(fields: _Fields) -> TierRise:
    return TierRise(
        tier=DecisionTier(fields["tier"]),
        target_titles=_target_titles(fields),
        file=FileKey(network=Network(fields["network"]), native_id=fields["native_id"]),
        filename=fields["filename"],
        size_bytes=fields["size_bytes"],
        node_id=NodeId(fields["node_id"]),
    )


def _source_alert(fields: _Fields) -> SourceAlert:
    absent_for_micros = fields["absent_for_micros"]
    return SourceAlert(
        kind=SourceAlertKind(fields["kind"]),
        source=SourceKey(network=Network(fields["network"]), native_id=fields["native_id"]),
        source_name=fields["source_name"],
        absent_for=None if absent_for_micros is None else absent_for_micros * _MICROSECOND,
        target_titles=_target_titles(fields),
        filename=fields["filename"],
        node_id=NodeId(fields["node_id"]),
    )


def _completed_download(fields: _Fields) -> CompletedDownload:
    return CompletedDownload(
        target_titles=_target_titles(fields),
        filename=fields["filename"],
        node_id=NodeId(fields["node_id"]),
    )


def _notification(kind: str, *, fields: _Fields) -> Notification:
    match kind:
        case "relayed_log_line":
            return _relayed_log_line(fields)
        case "tier_rise":
            return _tier_rise(fields)
        case "source_alert":
            return _source_alert(fields)
        case "completed_download":
            return _completed_download(fields)
        case _:
            raise ValueError(f"no notification is of the kind {kind!r}")


@wrap_stored_value_errors()
def _entry_from_row(row: NamedRow) -> PendingNotification:
    service = NotificationService(
        scheme=row["service_scheme"],
        audience=Audience(row["service_audience"]),
        ordinal=row["service_ordinal"],
    )
    try:
        notification = _notification(row["kind"], fields=json.loads(row["notification"]))
    except (KeyError, TypeError) as error:  # a field missing, or of a type no save writes
        raise ValueError(f"a stored notification is malformed: {error!r}") from error
    return PendingNotification(notification=notification, service=service)


def _entry_or_unreadable(row: NamedRow) -> PendingNotification | UnreadableNotification:
    try:
        return _entry_from_row(row)
    except PersistenceError as error:  # a row an earlier version left, without a field added since
        return UnreadableNotification(reason=str(error))
