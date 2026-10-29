"""Read-only tests of local.db via SqliteNodeStateReader (Task 8, W-D8 §node_state)."""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from catalog_matching.domain.identifiers import TargetId
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_node_id_store import SqliteNodeIdStore
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_node_state_reader import (
    SqliteNodeStateReader,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_tracked_download_store import (
    SqliteTrackedDownloadStore,
)
from p2pwatch.adapters.driven.persistence_sqlite.thread_read_connections import (
    ThreadReadConnections,
)
from p2pwatch.domain.download.states import DownloadState, FailureReason, WaitingReason
from p2pwatch.domain.download.status import DownloadStatus
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import Channel, ClientName, NodeId
from p2pwatch.domain.node_state import NodeState, TrackedDownload
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_reader

_STARTED_AT_MICROS = 1_781_258_400_000_000  # 2026-06-12T10:00:00Z
_QUEUED_AT_MICROS = 1_782_122_400_000_000  # 2026-06-22T10:00:00Z

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_node_state(path: Path) -> NodeState:
    """Read local.db through the webui's read-only connection."""
    with ThreadReadConnections(path, open_reader) as thread_read_connections:
        return SqliteNodeStateReader(thread_read_connections).read_node_state()


# ---------------------------------------------------------------------------
# Populated DB
# ---------------------------------------------------------------------------


def test_node_state_populated(local_db: Path) -> None:
    """Populated DB: downloads, backoff_states, node_identity."""
    # --- populate ---
    with closing(sqlite3.connect(local_db)) as w, w:
        w.execute(
            "INSERT INTO downloads (file_id, network, native_id, target_id, state,"
            " queued_at_micros, size_bytes, latest_progress_at_micros, waiting_reason,"
            " failure_reason) VALUES (x'00', 'ed2k', ?, '062A', 'failed', ?, ?, ?, ?, ?)",
            (
                "aabbccdd" * 4,
                _QUEUED_AT_MICROS,
                1024,
                _QUEUED_AT_MICROS + 86_400_000_000,
                "no_source",
                "error",
            ),
        )
        w.executemany(
            "INSERT INTO backoff_states VALUES (?, ?, ?, ?, ?)",
            [("amuled", "kad", 1, _STARTED_AT_MICROS, 2.5), ("amuled", None, 3, 0, 120.0)],
        )
        w.execute(
            "INSERT INTO node_identity VALUES (1, ?, ?)",
            ("test-node-42", 1_782_086_400_000_000),
        )
        w.commit()

    state = _read_node_state(local_db)

    # downloads
    assert state.downloads == (
        TrackedDownload(
            file=FileKey(Network.ED2K, "aabbccdd" * 4),
            target_id=TargetId("062A"),
            state=DownloadState.FAILED,
            queued_at=datetime(2026, 6, 22, 10, tzinfo=UTC),
            completed_at=None,
            latest_progress_at=datetime(2026, 6, 23, 10, tzinfo=UTC),
            waiting_reason=WaitingReason.NO_SOURCE,
            failure_reason=FailureReason.ERROR,
        ),
    )
    # The domain's members, not their text: a StrEnum compares equal to its value.
    (download,) = state.downloads
    assert download.waiting_reason is WaitingReason.NO_SOURCE
    assert download.failure_reason is FailureReason.ERROR

    # backoff, the whole client first, each with its start and its delay
    assert list(state.backoff_state_by_key.items()) == [
        (
            BackoffKey(ClientName("amuled"), None),
            BackoffState(3, datetime(1970, 1, 1, tzinfo=UTC), timedelta(seconds=120)),
        ),
        (
            BackoffKey(ClientName("amuled"), Channel("kad")),
            BackoffState(1, datetime(2026, 6, 12, 10, tzinfo=UTC), timedelta(seconds=2.5)),
        ),
    ]

    # node_identity
    assert state.node_id == "test-node-42"
    assert state.created_at == datetime(2026, 6, 22, tzinfo=UTC)


def test_a_completed_download_reads_its_completion(local_db: Path) -> None:
    with closing(sqlite3.connect(local_db)) as w, w:
        w.execute(
            "INSERT INTO downloads (file_id, network, native_id, target_id, state,"
            " queued_at_micros, completed_at_micros)"
            " VALUES (x'00', 'ed2k', ?, '062A', 'completed', ?, ?)",
            ("aabbccdd" * 4, _QUEUED_AT_MICROS, _QUEUED_AT_MICROS + 172_800_250_000),
        )

    (download,) = _read_node_state(local_db).downloads

    assert download.state is DownloadState.COMPLETED
    assert download.completed_at == datetime(2026, 6, 24, 10, 0, 0, 250000, tzinfo=UTC)
    assert download.latest_progress_at is None


def test_a_download_reads_back_each_instant_its_store_wrote(local_db: Path) -> None:
    file = FileKey(Network.ED2K, "aabbccdd" * 4)
    queued_at = datetime(2026, 6, 22, 10, 0, 0, 123456, tzinfo=UTC)
    progressed_at = queued_at + timedelta(hours=1, microseconds=1)
    completed_at = queued_at + timedelta(days=1, microseconds=7)
    with closing(sqlite3.connect(local_db, autocommit=True)) as connection:
        tracked_download_store = SqliteTrackedDownloadStore(connection)
        tracked_download_store.record_queued(file, TargetId("062A"), 100, queued_at)
        tracked_download_store.set_seen(
            [DownloadStatus(file, 40, 100, False, None, None)], progressed_at
        )
        tracked_download_store.set_completed(file, completed_at)

    assert _read_node_state(local_db).downloads == (
        TrackedDownload(
            file=file,
            target_id=TargetId("062A"),
            state=DownloadState.COMPLETED,
            queued_at=queued_at,
            completed_at=completed_at,
            latest_progress_at=progressed_at,
            waiting_reason=None,
            failure_reason=None,
        ),
    )


def test_the_node_identity_reads_back_the_instant_its_store_wrote(local_db: Path) -> None:
    created_at = datetime(2026, 6, 22, 10, 0, 0, 123456, tzinfo=UTC)
    with closing(sqlite3.connect(local_db, autocommit=True)) as connection:
        SqliteNodeIdStore(connection).record_node_id(NodeId("test-node-42"), created_at)

    state = _read_node_state(local_db)

    assert (state.node_id, state.created_at) == ("test-node-42", created_at)


# ---------------------------------------------------------------------------
# Empty DB (observer mode): covers the None branches
# ---------------------------------------------------------------------------


def test_node_state_empty_db(local_db: Path) -> None:
    """Empty DB (observer mode): everything empty or None, no error."""
    state = _read_node_state(local_db)

    assert isinstance(state, NodeState)
    assert state.downloads == ()
    assert state.backoff_state_by_key == {}
    assert state.node_id is None
    assert state.created_at is None
