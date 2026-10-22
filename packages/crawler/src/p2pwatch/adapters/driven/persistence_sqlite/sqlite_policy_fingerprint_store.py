"""``SqlitePolicyFingerprintStore``: the policy fingerprint of the latest reevaluation (§7.1)."""

import sqlite3

from p2pwatch.adapters.driven.persistence_sqlite.errors import wrap_sqlite_errors
from p2pwatch.application.ports.driven.policy_fingerprint_reader import PolicyFingerprintReader
from p2pwatch.application.ports.driven.policy_fingerprint_writer import PolicyFingerprintWriter

_SELECT_POLICY_FINGERPRINT = "SELECT policy_fingerprint FROM reevaluation_state WHERE id = 1"

_UPSERT_POLICY_FINGERPRINT = """
INSERT INTO reevaluation_state (id, policy_fingerprint)
VALUES (1, ?)
ON CONFLICT (id) DO UPDATE SET policy_fingerprint = excluded.policy_fingerprint
"""


class SqlitePolicyFingerprintStore(PolicyFingerprintReader, PolicyFingerprintWriter):
    """SQLite implementation of the policy fingerprint's ports."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def read_policy_fingerprint(self) -> str | None:
        """The stored policy fingerprint, or ``None`` if no re-evaluation ever ran."""
        with wrap_sqlite_errors():
            row = self._connection.execute(_SELECT_POLICY_FINGERPRINT).fetchone()
        return str(row[0]) if row is not None else None

    def set_policy_fingerprint(self, fingerprint: str) -> None:
        """Upserts the single-row marker (called only AFTER a full re-evaluation pass)."""
        with wrap_sqlite_errors():
            self._connection.execute(_UPSERT_POLICY_FINGERPRINT, (fingerprint,))
