"""``SqliteLocalStateRepository``: node identity + reevaluated policy fingerprint (spec §4/§6).

The node id lives in ``node_runtime`` with its ``created_at``, recorded once (spec §3).
"""

import sqlite3
from contextlib import suppress
from datetime import datetime

from p2pwatch.adapters.driven.persistence_sqlite.connection import utc_iso
from p2pwatch.adapters.driven.persistence_sqlite.errors import wrap_sqlite_errors
from p2pwatch.ports.driven.node_id import NodeIdReader, NodeIdWriter
from p2pwatch.ports.driven.policy_fingerprint import (
    PolicyFingerprintReader,
    PolicyFingerprintWriter,
)

_SELECT_NODE_ID = "SELECT value FROM node_runtime WHERE key = 'node_id'"

_INSERT_NODE_IDENTITY = """
INSERT INTO node_runtime (key, value)
VALUES ('node_id', ?), ('created_at', ?)
"""

_SELECT_POLICY_FINGERPRINT = "SELECT policy_fingerprint FROM reevaluation_state WHERE id = 1"

_UPSERT_POLICY_FINGERPRINT = """
INSERT INTO reevaluation_state (id, policy_fingerprint)
VALUES (1, ?)
ON CONFLICT (id) DO UPDATE SET policy_fingerprint = excluded.policy_fingerprint
"""


class SqliteLocalStateRepository(
    NodeIdReader, NodeIdWriter, PolicyFingerprintReader, PolicyFingerprintWriter
):
    """SQLite implementation of the node id's ports and of the policy fingerprint's."""

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
            # Formatted BEFORE the BEGIN (same hygiene as the catalog repo): a naive
            # instant must not raise in the middle of a transaction.
            created_at_iso = utc_iso(created_at)
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute(_INSERT_NODE_IDENTITY, (node_id, created_at_iso))
                self._connection.execute("COMMIT")
            except BaseException:
                # Rollback on BaseException (same discipline as catalog_repository):
                # a NON-sqlite failure must not leave the connection in_transaction,
                # otherwise the repository would be permanently broken.
                with suppress(sqlite3.Error):
                    self._connection.execute("ROLLBACK")
                raise

    def read_policy_fingerprint(self) -> str | None:
        """The stored policy fingerprint, or ``None`` if no re-evaluation ever ran (spec §7.1)."""
        with wrap_sqlite_errors():
            row = self._connection.execute(_SELECT_POLICY_FINGERPRINT).fetchone()
        return str(row[0]) if row is not None else None

    def set_policy_fingerprint(self, fingerprint: str) -> None:
        """Upserts the single-row marker (called only AFTER a full re-evaluation pass)."""
        with wrap_sqlite_errors():
            self._connection.execute(_UPSERT_POLICY_FINGERPRINT, (fingerprint,))
