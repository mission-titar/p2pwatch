"""Read-only reads of local.db (webui spec W-D8 §node_state).

``LocalReader`` exposes one read:

- ``node_state()``: full node state: downloads, backoff, node identity.

All SQL lives in module constants, parameterized (no value interpolation).
"""

import sqlite3
from datetime import UTC, datetime, timedelta

from p2pwatch.adapters.driving.webui.views import BackoffRow, DownloadRow, NodeState

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

_SQL_DOWNLOADS = """\
SELECT
    native_id,
    target_id,
    state,
    queued_at,
    completed_at,
    size_bytes,
    last_progress_at,
    waiting_reason,
    failure_reason
FROM downloads
ORDER BY queued_at ASC, native_id ASC
"""

_SQL_BACKOFF = """\
SELECT client_name, channel, attempts, started_at, delay_seconds
FROM backoff_states
ORDER BY client_name ASC, channel ASC
"""

_SQL_NODE_RUNTIME_KEY = """\
SELECT value FROM node_runtime WHERE key = ?
"""


# ---------------------------------------------------------------------------
# LocalReader
# ---------------------------------------------------------------------------


class LocalReader:
    """Read-only access to local.db via a SQLite connection (see ``reader.open_reader``)."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    def node_state(self) -> NodeState:
        """Return the full node state read from local.db."""
        dl_rows = self._conn.execute(_SQL_DOWNLOADS).fetchall()

        node_id_row = self._conn.execute(_SQL_NODE_RUNTIME_KEY, ("node_id",)).fetchone()
        created_at_row = self._conn.execute(_SQL_NODE_RUNTIME_KEY, ("created_at",)).fetchone()

        downloads = tuple(
            DownloadRow(
                native_id=row["native_id"],
                target_id=row["target_id"],
                state=row["state"],
                queued_at=row["queued_at"],
                completed_at=row["completed_at"],
                size_bytes=row["size_bytes"],
                last_progress_at=row["last_progress_at"],
                waiting_reason=row["waiting_reason"],
                failure_reason=row["failure_reason"],
            )
            for row in dl_rows
        )

        backoff_rows = tuple(
            BackoffRow(
                client_name=row["client_name"],
                channel=row["channel"],
                attempts=row["attempts"],
                retry_at=_EPOCH
                + timedelta(microseconds=row["started_at"], seconds=row["delay_seconds"]),
            )
            for row in self._conn.execute(_SQL_BACKOFF)
        )

        node_id: str | None = node_id_row["value"] if node_id_row is not None else None
        created_at: str | None = created_at_row["value"] if created_at_row is not None else None

        return NodeState(
            downloads=downloads,
            backoff_rows=backoff_rows,
            node_id=node_id,
            created_at=created_at,
        )
