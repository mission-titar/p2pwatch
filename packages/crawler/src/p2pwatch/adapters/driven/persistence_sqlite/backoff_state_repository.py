"""``SqliteBackoffStateStore``: the backoff states' ports on ``local.db``'s
``backoff_states``, mutable state that no append-only trigger guards."""

import sqlite3
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from p2pwatch.adapters.driven.persistence_sqlite.connection import utc_iso
from p2pwatch.adapters.driven.persistence_sqlite.errors import wrap_sqlite_errors
from p2pwatch.adapters.driven.persistence_sqlite.variants import iso_to_micros
from p2pwatch.application.ports.driven.backoff_state_reader import BackoffStateReader
from p2pwatch.application.ports.driven.backoff_state_writer import BackoffStateWriter
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

_SELECT = "SELECT client_name, channel, attempts, started_at, delay_seconds FROM backoff_states"

_INSERT = """
INSERT INTO backoff_states (client_name, channel, attempts, started_at, delay_seconds)
VALUES (?, ?, ?, ?, ?)
"""


class SqliteBackoffStateStore(BackoffStateReader, BackoffStateWriter):
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def read_backoff_states(self) -> dict[BackoffKey, BackoffState]:
        with wrap_sqlite_errors():
            rows = self._connection.execute(_SELECT).fetchall()
        return {
            BackoffKey(client_name, channel): BackoffState(
                attempts,
                _EPOCH + timedelta(microseconds=started_at_micros),
                timedelta(seconds=delay_seconds),
            )
            for client_name, channel, attempts, started_at_micros, delay_seconds in rows
        }

    def set_backoff_states(self, backoff_state_by_key: dict[BackoffKey, BackoffState]) -> None:
        """Replaces the whole table in one transaction."""
        rows = [
            (
                backoff_key.client_name,
                backoff_key.channel,
                state.attempts,
                iso_to_micros(utc_iso(state.started_at)),
                state.delay.total_seconds(),
            )
            for backoff_key, state in backoff_state_by_key.items()
        ]
        with wrap_sqlite_errors():
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute("DELETE FROM backoff_states")
                self._connection.executemany(_INSERT, rows)
                self._connection.execute("COMMIT")
            except BaseException:
                with suppress(sqlite3.Error):
                    self._connection.execute("ROLLBACK")
                raise
