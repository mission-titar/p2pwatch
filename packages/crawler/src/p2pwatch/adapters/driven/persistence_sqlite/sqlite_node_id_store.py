"""``SqliteNodeIdStore``: the node id and its ``created_at``, in ``node_identity``'s one row."""

import sqlite3
from datetime import datetime

from p2pwatch.adapters.driven.persistence_sqlite.errors import wrap_sqlite_errors
from p2pwatch.adapters.driven.persistence_sqlite.micros import instant_to_micros
from p2pwatch.application.ports.driven.node_id_reader import NodeIdReader
from p2pwatch.application.ports.driven.node_id_writer import NodeIdWriter
from p2pwatch.domain.identifiers import NodeId

_SELECT_NODE_ID = "SELECT node_id FROM node_identity"

_INSERT_NODE_IDENTITY = """
INSERT INTO node_identity (id, node_id, created_at_micros)
VALUES (1, ?, ?)
"""


class SqliteNodeIdStore(NodeIdReader, NodeIdWriter):
    """SQLite implementation of the node id's ports."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def read_node_id(self) -> NodeId | None:
        """The stored node id, ``None`` before one is recorded."""
        with wrap_sqlite_errors():
            row = self._connection.execute(_SELECT_NODE_ID).fetchone()
        return NodeId(row[0]) if row is not None else None

    def record_node_id(self, node_id: NodeId, created_at: datetime) -> None:
        """Persists ``node_id`` with ``created_at``, in one row."""
        created_at_micros = instant_to_micros(created_at)
        with wrap_sqlite_errors():
            self._connection.execute(_INSERT_NODE_IDENTITY, (node_id, created_at_micros))
