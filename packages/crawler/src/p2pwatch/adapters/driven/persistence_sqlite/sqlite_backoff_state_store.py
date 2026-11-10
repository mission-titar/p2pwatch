"""``SqliteBackoffStateStore``: the backoff states' ports on ``local.db``'s
``backoff_states``, mutable state that no append-only trigger guards."""

import sqlite3
from datetime import timedelta

from p2pwatch.adapters.driven.persistence_sqlite.errors import (
    wrap_sqlite_errors,
    wrap_stored_value_errors,
)
from p2pwatch.adapters.driven.persistence_sqlite.immediate_transaction import immediate_transaction
from p2pwatch.adapters.driven.persistence_sqlite.micros import instant_to_micros, micros_to_instant
from p2pwatch.adapters.driven.persistence_sqlite.named_row import NamedRow
from p2pwatch.application.ports.driven.backoff_state_reader import BackoffStateReader
from p2pwatch.application.ports.driven.backoff_state_writer import BackoffStateWriter
from p2pwatch.domain.identifiers import Channel, ClientName
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState

_SELECT = (
    "SELECT client_name, channel, attempts, started_at_micros, delay_seconds FROM backoff_states"
)

_INSERT = """
INSERT INTO backoff_states (client_name, channel, attempts, started_at_micros, delay_seconds)
VALUES (?, ?, ?, ?, ?)
"""


@wrap_stored_value_errors()
def backoff_from_row(row: NamedRow) -> tuple[BackoffKey, BackoffState]:
    """A row of ``backoff_states`` as its key and its state."""
    backoff_key = BackoffKey(
        client_name=ClientName(row["client_name"]),
        channel=None if row["channel"] is None else Channel(row["channel"]),
    )
    return backoff_key, BackoffState(
        attempts=row["attempts"],
        started_at=micros_to_instant(row["started_at_micros"]),
        delay=timedelta(seconds=row["delay_seconds"]),
    )


class SqliteBackoffStateStore(BackoffStateReader, BackoffStateWriter):
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def read_backoff_states(self) -> dict[BackoffKey, BackoffState]:
        with wrap_sqlite_errors():
            rows = self._connection.execute(_SELECT).fetchall()
        return dict(map(backoff_from_row, rows))

    def set_backoff_states(self, backoff_state_by_key: dict[BackoffKey, BackoffState]) -> None:
        """Replaces the whole table in one transaction."""
        rows = [
            (
                backoff_key.client_name,
                backoff_key.channel,
                state.attempts,
                instant_to_micros(state.started_at),
                state.delay.total_seconds(),
            )
            for backoff_key, state in backoff_state_by_key.items()
        ]
        with wrap_sqlite_errors(), immediate_transaction(self._connection):
            self._connection.execute("DELETE FROM backoff_states")
            self._connection.executemany(_INSERT, rows)
