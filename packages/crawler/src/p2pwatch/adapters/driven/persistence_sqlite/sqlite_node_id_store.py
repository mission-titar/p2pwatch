"""``SqliteNodeIdStore``: the node id, in ``node_runtime`` beside its ``created_at`` (spec §3)."""

import sqlite3
from contextlib import suppress
from datetime import datetime

from p2pwatch.adapters.driven.persistence_sqlite.connection import utc_iso
from p2pwatch.adapters.driven.persistence_sqlite.errors import wrap_sqlite_errors
from p2pwatch.application.ports.driven.node_id_reader import NodeIdReader
from p2pwatch.application.ports.driven.node_id_writer import NodeIdWriter

_SELECT_NODE_ID = "SELECT value FROM node_runtime WHERE key = 'node_id'"

_INSERT_NODE_IDENTITY = """
INSERT INTO node_runtime (key, value)
VALUES ('node_id', ?), ('created_at', ?)
"""


class SqliteNodeIdStore(NodeIdReader, NodeIdWriter):
    """SQLite implementation of the node id's ports."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def read_node_id(self) -> str | None:
        """The stored node id, ``None`` before one is recorded."""
        with wrap_sqlite_errors():
            row = self._connection.execute(_SELECT_NODE_ID).fetchone()
        return str(row[0]) if row is not None else None

    def record_node_id(self, node_id: str, created_at: datetime) -> None:
        """Persists ``node_id`` with ``created_at``, both rows or neither."""
        with wrap_sqlite_errors():
            # Formatted BEFORE the BEGIN: a naive instant must not raise inside the transaction.
            created_at_iso = utc_iso(created_at)
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute(_INSERT_NODE_IDENTITY, (node_id, created_at_iso))
                self._connection.execute("COMMIT")
            except BaseException:
                # A NON-sqlite failure must not leave the connection in_transaction for good.
                with suppress(sqlite3.Error):
                    self._connection.execute("ROLLBACK")
                raise
