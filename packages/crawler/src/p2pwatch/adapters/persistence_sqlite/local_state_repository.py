"""``SqliteLocalStateRepository``: node identity + reevaluated policy fingerprint (spec §4/§6).

``get_or_create_node_id`` (spec §3): UUID generated on the first call, persisted in ``node_runtime``
with ``created_at``, stable thereafter (scheduler seed §6 MVP + observation tag).
"""

import sqlite3
import uuid
from contextlib import suppress
from datetime import datetime

from p2pwatch.adapters.persistence_sqlite.connection import utc_iso
from p2pwatch.adapters.persistence_sqlite.errors import wrap_sqlite_errors

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


class SqliteLocalStateRepository:
    """SQLite implementation of the ``LocalStateRepository`` port (STRUCTURAL satisfaction)."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def get_or_create_node_id(self, created_at: datetime) -> str:
        """UUID created (and persisted with ``created_at``) on the first call, stable after."""
        with wrap_sqlite_errors():
            row = self._connection.execute(_SELECT_NODE_ID).fetchone()
            if row is not None:
                return str(row[0])
            node_id = str(uuid.uuid4())
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
        return node_id

    def reevaluated_policy_fingerprint(self) -> str | None:
        """The stored policy fingerprint, or ``None`` if no re-evaluation ever ran (spec §7.1)."""
        with wrap_sqlite_errors():
            row = self._connection.execute(_SELECT_POLICY_FINGERPRINT).fetchone()
        return str(row[0]) if row is not None else None

    def set_reevaluated_policy_fingerprint(self, fingerprint: str) -> None:
        """Upserts the single-row marker (called only AFTER a full re-evaluation pass)."""
        with wrap_sqlite_errors():
            self._connection.execute(_UPSERT_POLICY_FINGERPRINT, (fingerprint,))
