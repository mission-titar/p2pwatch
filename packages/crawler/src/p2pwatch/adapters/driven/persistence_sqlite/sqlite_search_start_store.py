"""``SqliteSearchStartStore``: the search starts' ports on ``local.db``'s
``latest_search_starts``, mutable state that no append-only trigger guards."""

import sqlite3

from p2pwatch.adapters.driven.persistence_sqlite.errors import (
    wrap_sqlite_errors,
    wrap_stored_value_errors,
)
from p2pwatch.adapters.driven.persistence_sqlite.immediate_transaction import immediate_transaction
from p2pwatch.adapters.driven.persistence_sqlite.micros import instant_to_micros, micros_to_instant
from p2pwatch.adapters.driven.persistence_sqlite.named_row import NamedRow
from p2pwatch.application.ports.driven.search_start_reader import SearchStartReader
from p2pwatch.application.ports.driven.search_start_writer import SearchStartWriter
from p2pwatch.domain.identifiers import Channel, ClientName
from p2pwatch.domain.search.latest_search_start import LatestSearchStart

_SELECT = """
SELECT channel, scope, started_at_micros FROM latest_search_starts
WHERE client_name = ?
"""

_UPSERT = """
INSERT INTO latest_search_starts (client_name, channel, scope, started_at_micros)
VALUES (?, ?, ?, ?)
ON CONFLICT (client_name, channel, scope) DO UPDATE SET
started_at_micros = excluded.started_at_micros
"""


class SqliteSearchStartStore(SearchStartReader, SearchStartWriter):
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def read_latest_starts(self, client_name: ClientName) -> tuple[LatestSearchStart, ...]:
        with wrap_sqlite_errors():
            rows = self._connection.execute(_SELECT, (client_name,)).fetchall()
        return tuple(map(_start_from_row, rows))

    def set_latest_start(self, client_name: ClientName, *, start: LatestSearchStart) -> None:
        row = (client_name, start.channel, start.scope, instant_to_micros(start.started_at))
        with wrap_sqlite_errors(), immediate_transaction(self._connection):
            self._connection.execute(_UPSERT, row)


@wrap_stored_value_errors()
def _start_from_row(row: NamedRow) -> LatestSearchStart:
    return LatestSearchStart(
        channel=Channel(row["channel"]),
        scope=row["scope"],
        started_at=micros_to_instant(row["started_at_micros"]),
    )
