"""Read-only reads of local.db (webui spec W-D8 §node_state).

``SqliteNodeStateReader`` exposes one read:

- ``read_node_state()``: full node state: downloads, backoff, node identity.

All SQL lives in module constants, parameterized (no value interpolation).
"""

from datetime import datetime, timedelta
from enum import StrEnum

from catalog_matching.domain.identifiers import TargetId
from p2pwatch.adapters.driven.persistence_sqlite.micros import micros_to_instant
from p2pwatch.adapters.driven.persistence_sqlite.thread_read_connections import (
    ThreadReadConnections,
)
from p2pwatch.application.ports.driven.node_state_reader import NodeStateReader
from p2pwatch.domain.download.states import DownloadState, FailureReason, WaitingReason
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.node_state import NodeState, TrackedDownload
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState

# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

_SQL_DOWNLOADS = """\
SELECT
    network,
    native_id,
    target_id,
    state,
    queued_at_micros,
    completed_at_micros,
    latest_progress_at_micros,
    waiting_reason,
    failure_reason
FROM downloads
ORDER BY queued_at_micros ASC, native_id ASC
"""

_SQL_BACKOFF = """\
SELECT client_name, channel, attempts, started_at_micros, delay_seconds
FROM backoff_states
ORDER BY client_name ASC, channel ASC
"""

_SQL_NODE_IDENTITY = """\
SELECT node_id, created_at_micros FROM node_identity
"""


def _instant(micros: int | None) -> datetime | None:
    return None if micros is None else micros_to_instant(micros)


def _optional[Reason: StrEnum](reason_type: type[Reason], stored: str | None) -> Reason | None:
    return None if stored is None else reason_type(stored)


# ---------------------------------------------------------------------------
# SqliteNodeStateReader
# ---------------------------------------------------------------------------


class SqliteNodeStateReader(NodeStateReader):
    """Read-only access to local.db through the calling thread's connection."""

    def __init__(self, thread_read_connections: ThreadReadConnections) -> None:
        self._thread_read_connections = thread_read_connections

    def read_node_state(self) -> NodeState:
        connection = self._thread_read_connections.connection()
        dl_rows = connection.execute(_SQL_DOWNLOADS).fetchall()

        identity_row = connection.execute(_SQL_NODE_IDENTITY).fetchone()

        downloads = tuple(
            TrackedDownload(
                file=FileKey(Network(row["network"]), row["native_id"]),
                target_id=TargetId(row["target_id"]),
                state=DownloadState(row["state"]),
                queued_at=micros_to_instant(row["queued_at_micros"]),
                completed_at=_instant(row["completed_at_micros"]),
                latest_progress_at=_instant(row["latest_progress_at_micros"]),
                waiting_reason=_optional(WaitingReason, row["waiting_reason"]),
                failure_reason=_optional(FailureReason, row["failure_reason"]),
            )
            for row in dl_rows
        )

        backoff_state_by_key = {
            BackoffKey(row["client_name"], row["channel"]): BackoffState(
                row["attempts"],
                micros_to_instant(row["started_at_micros"]),
                timedelta(seconds=row["delay_seconds"]),
            )
            for row in connection.execute(_SQL_BACKOFF)
        }

        return NodeState(
            node_id=identity_row["node_id"] if identity_row is not None else None,
            created_at=(
                micros_to_instant(identity_row["created_at_micros"])
                if identity_row is not None
                else None
            ),
            downloads=downloads,
            backoff_state_by_key=backoff_state_by_key,
        )
