"""Read-only reads of local.db (webui spec W-D8 §node_state).

``SqliteNodeStateReader`` exposes one read:

- ``read_node_state()``: full node state: downloads, backoff, node identity.

All SQL lives in module constants, parameterized (no value interpolation).
"""

from datetime import UTC, datetime, timedelta

from p2pwatch.adapters.driven.persistence_sqlite.reader import ReaderProvider
from p2pwatch.domain.download.states import DownloadState
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.node_state import NodeState, TrackedDownload
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState
from p2pwatch.ports.driven.node_state_reader import NodeStateReader

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

_SQL_DOWNLOADS = """\
SELECT
    network,
    native_id,
    target_id,
    state,
    queued_at,
    completed_at,
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


def _instant(iso: str | None) -> datetime | None:
    return None if iso is None else datetime.fromisoformat(iso)


# ---------------------------------------------------------------------------
# SqliteNodeStateReader
# ---------------------------------------------------------------------------


class SqliteNodeStateReader(NodeStateReader):
    """Read-only access to local.db through the calling thread's connection."""

    def __init__(self, reader_provider: ReaderProvider) -> None:
        self._reader_provider = reader_provider

    def read_node_state(self) -> NodeState:
        connection = self._reader_provider.connection()
        dl_rows = connection.execute(_SQL_DOWNLOADS).fetchall()

        node_id_row = connection.execute(_SQL_NODE_RUNTIME_KEY, ("node_id",)).fetchone()
        created_at_row = connection.execute(_SQL_NODE_RUNTIME_KEY, ("created_at",)).fetchone()

        downloads = tuple(
            TrackedDownload(
                file=FileKey(Network(row["network"]), row["native_id"]),
                target_id=row["target_id"],
                state=DownloadState(row["state"]),
                queued_at=datetime.fromisoformat(row["queued_at"]),
                completed_at=_instant(row["completed_at"]),
                last_progress_at=_instant(row["last_progress_at"]),
                waiting_reason=row["waiting_reason"],
                failure_reason=row["failure_reason"],
            )
            for row in dl_rows
        )

        backoff_state_by_key = {
            BackoffKey(row["client_name"], row["channel"]): BackoffState(
                row["attempts"],
                _EPOCH + timedelta(microseconds=row["started_at"]),
                timedelta(seconds=row["delay_seconds"]),
            )
            for row in connection.execute(_SQL_BACKOFF)
        }

        node_id: str | None = node_id_row["value"] if node_id_row is not None else None
        created_at = _instant(created_at_row["value"]) if created_at_row is not None else None

        return NodeState(
            node_id=node_id,
            created_at=created_at,
            downloads=downloads,
            backoff_state_by_key=backoff_state_by_key,
        )
