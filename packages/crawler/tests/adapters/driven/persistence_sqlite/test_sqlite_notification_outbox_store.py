import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.sqlite_notification_outbox_store import (
    SqliteNotificationOutboxStore,
)
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.matching.identifiers import TargetId
from p2pwatch.domain.observability.events import TargetTitle
from p2pwatch.domain.observability.notification import CompletedDownload, RelayedLogLine
from p2pwatch.domain.observability.notification_sends import (
    NotificationService,
    PendingNotification,
    UnreadableNotification,
)
from p2pwatch.domain.observability.policy import Audience
from p2pwatch.domain.observability.severity import Severity
from tests.contracts.application.ports.driven.notification_outbox_store_contract import (
    NotificationOutboxStoreContract,
)
from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.refused_writes import (
    StorageRefusal,
    refusing,
)
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_local
from tests.support.refused_writes import RefuseWrites

_COMPLETED = PendingNotification(
    notification=CompletedDownload(
        target_titles=(TargetTitle(target_id=TargetId("062A"), title="Les demoiselles"),),
        filename="Keroro 062.avi",
        node_id=NodeId("titar-node-1"),
    ),
    service=NotificationService(scheme="discord", audience=Audience.COMMUNITY, ordinal=2),
)


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    local = open_local(tmp_path / "local.db")
    yield local
    local.close()


@pytest.fixture
def outbox_store(connection: sqlite3.Connection) -> SqliteNotificationOutboxStore:
    return SqliteNotificationOutboxStore(connection)


class TestSqliteNotificationOutboxStore(NotificationOutboxStoreContract):
    @pytest.fixture
    def writer(self, outbox_store: SqliteNotificationOutboxStore) -> SqliteNotificationOutboxStore:
        return outbox_store

    @pytest.fixture
    def reader(self, outbox_store: SqliteNotificationOutboxStore) -> SqliteNotificationOutboxStore:
        return outbox_store

    @pytest.fixture(params=list(StorageRefusal), ids=str)
    def refuse_writes(
        self, *, request: pytest.FixtureRequest, connection: sqlite3.Connection
    ) -> RefuseWrites:
        return refusing(connection, refusal=request.param)


def test_the_entries_saved_are_read_by_a_store_built_later_on_the_same_database(
    *, outbox_store: SqliteNotificationOutboxStore, connection: sqlite3.Connection
) -> None:
    outbox_store.set_pending_notifications([_COMPLETED])

    store_built_later = SqliteNotificationOutboxStore(connection)

    assert store_built_later.read_pending_notifications() == (_COMPLETED,)


def test_an_entry_is_one_row_its_service_in_columns_its_notification_a_json_object(
    *, outbox_store: SqliteNotificationOutboxStore, connection: sqlite3.Connection
) -> None:
    outbox_store.set_pending_notifications([_COMPLETED])

    stored = rows(connection, sql="SELECT * FROM pending_notifications")
    assert [row | {"notification": json.loads(row["notification"])} for row in stored] == [
        {
            "id": 1,
            "service_scheme": "discord",
            "service_audience": "community",
            "service_ordinal": 2,
            "kind": "completed_download",
            "notification": {
                "target_titles": [{"target_id": "062A", "title": "Les demoiselles"}],
                "filename": "Keroro 062.avi",
                "node_id": "titar-node-1",
            },
        }
    ]


def test_a_relayed_log_line_saved_without_a_second_line_is_read_back_with_none(
    *, outbox_store: SqliteNotificationOutboxStore, connection: sqlite3.Connection
) -> None:
    # As the version before the second line saved it.
    fields = '{"message": "amuled reachable again", "severity": "INFO", "node_id": "n1"}'
    connection.execute(
        "INSERT INTO pending_notifications VALUES (1, 'ntfy', 'operations', 1, ?, ?)",
        ("relayed_log_line", fields),
    )

    assert outbox_store.read_pending_notifications() == (
        PendingNotification(
            notification=RelayedLogLine(
                message="amuled reachable again", severity=Severity.INFO, node_id=NodeId("n1")
            ),
            service=NotificationService(scheme="ntfy", audience=Audience.OPERATIONS),
        ),
    )


@pytest.mark.parametrize(
    ("kind", "fields", "reason"),
    [
        (
            "completed_download",
            '{"filename": "x"}',
            "a stored notification is malformed: KeyError('target_titles')",
        ),
        ("a_kind_no_save_writes", "{}", "no notification is of the kind 'a_kind_no_save_writes'"),
    ],
    ids=["lacking a field", "of no kind"],
)
def test_a_stored_notification_no_save_writes_is_read_back_unreadable_and_why(
    *,
    outbox_store: SqliteNotificationOutboxStore,
    connection: sqlite3.Connection,
    kind: str,
    fields: str,
    reason: str,
) -> None:
    outbox_store.set_pending_notifications([_COMPLETED])
    connection.execute(
        "INSERT INTO pending_notifications VALUES (2, 'discord', 'community', 1, ?, ?)",
        (kind, fields),
    )

    assert outbox_store.read_pending_notifications() == (
        _COMPLETED,
        UnreadableNotification(reason=f"a stored value cannot be read: {reason}"),
    )
