"""``SqliteSchedulerStateRepository``: scheduler state as KV (orchestration spec §4/§7).

STRUCTURALLY implements the ``SchedulerStateRepository`` port. Stores one key in the
``scheduler_state`` table of ``local.db``: ``backoff_states`` (JSON map of
:class:`BackoffState`, each :class:`BackoffKey` written ``client`` or ``client:channel``).
``save_backoff_states`` replaces the map ENTIRELY (registry snapshot); ``load_backoff_states``
returns an empty dict if the key is absent.

``scheduler_state`` is NOT append-only (mutable state, not the catalog): no
triggers: the ``ON CONFLICT … DO UPDATE`` UPSERT is allowed.
"""

import json
import sqlite3
from contextlib import suppress
from typing import Any

from p2pwatch.adapters.persistence_sqlite.errors import wrap_sqlite_errors
from p2pwatch.ports.scheduler_state_repository import BackoffKey, BackoffState

_SELECT_BACKOFF = "SELECT value FROM scheduler_state WHERE key = 'backoff_states'"

_UPSERT = """
INSERT INTO scheduler_state (key, value) VALUES (?, ?)
ON CONFLICT (key) DO UPDATE SET value = excluded.value
"""


def _json_key(backoff_key: BackoffKey) -> str:
    if backoff_key.channel is None:
        return backoff_key.client_name
    return f"{backoff_key.client_name}:{backoff_key.channel}"


def _backoff_key(json_key: str) -> BackoffKey:
    client_name, separator, channel = json_key.partition(":")
    return BackoffKey(client_name, channel if separator else None)


class SqliteSchedulerStateRepository:
    """SQLite implementation of the ``SchedulerStateRepository`` port (STRUCTURAL satisfaction)."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def load_backoff_states(self) -> dict[BackoffKey, BackoffState]:
        """Re-reads the persisted backoff map, ``{}`` if never written (first startup).

        Each JSON entry ``{"attempts": int, "retry_after": str}`` is reconstructed into a
        :class:`BackoffState`. Harmless read: no explicit transaction.
        """
        with wrap_sqlite_errors():
            row = self._connection.execute(_SELECT_BACKOFF).fetchone()
        if row is None:
            return {}
        raw: dict[str, dict[str, Any]] = json.loads(row[0])
        return {
            _backoff_key(json_key): BackoffState(
                attempts=int(entry["attempts"]), retry_after=str(entry["retry_after"])
            )
            for json_key, entry in raw.items()
        }

    def save_backoff_states(self, backoff: dict[BackoffKey, BackoffState]) -> None:
        """Replaces the persisted map ENTIRELY (registry snapshot, at each change).

        Serialized as sorted JSON (``sort_keys`` → stable diff, determinism). Atomic UPSERT
        under ``BEGIN IMMEDIATE``.
        """
        blob = json.dumps(
            {
                _json_key(backoff_key): {
                    "attempts": state.attempts,
                    "retry_after": state.retry_after,
                }
                for backoff_key, state in backoff.items()
            },
            sort_keys=True,
        )
        with wrap_sqlite_errors():
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute(_UPSERT, ("backoff_states", blob))
                self._connection.execute("COMMIT")
            except BaseException:
                with suppress(sqlite3.Error):
                    self._connection.execute("ROLLBACK")
                raise
