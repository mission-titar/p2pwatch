"""Read-only tests of local.db via SqliteNodeStateReader (Task 8, W-D8 §node_state)."""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from p2pwatch.adapters.driven.persistence_sqlite.sqlite_node_state_reader import (
    SqliteNodeStateReader,
)
from p2pwatch.adapters.driven.persistence_sqlite.thread_read_connections import (
    ThreadReadConnections,
)
from p2pwatch.domain.download.states import DownloadState, FailureReason, WaitingReason
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.node_state import NodeState, TrackedDownload
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState

_STARTED_AT_MICROS = 1_781_258_400_000_000  # 2026-06-12T10:00:00Z

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_node_state(path: Path) -> NodeState:
    """Read local.db through the webui's read-only connection."""
    with ThreadReadConnections(path) as reader_provider:
        return SqliteNodeStateReader(reader_provider).read_node_state()


# ---------------------------------------------------------------------------
# Populated DB
# ---------------------------------------------------------------------------


def test_node_state_populated(local_db: Path) -> None:
    """Populated DB: downloads, backoff_states, node_runtime."""
    # --- populate ---
    with closing(sqlite3.connect(local_db)) as w, w:
        w.execute(
            "INSERT INTO downloads (file_id, network, native_id, target_id, state, queued_at,"
            " size_bytes, latest_progress_at, waiting_reason, failure_reason)"
            " VALUES (x'00', 'ed2k', ?, '062A', 'failed', ?, ?, ?, ?, ?)",
            (
                "aabbccdd" * 4,
                "2026-06-22T10:00:00.000000+00:00",
                1024,
                "2026-06-23T10:00:00.000000+00:00",
                "no_source",
                "error",
            ),
        )
        w.executemany(
            "INSERT INTO backoff_states VALUES (?, ?, ?, ?, ?)",
            [("amuled", "kad", 1, _STARTED_AT_MICROS, 2.5), ("amuled", None, 3, 0, 120.0)],
        )
        w.execute(
            "INSERT INTO node_runtime VALUES (?,?)",
            ("node_id", "test-node-42"),
        )
        w.execute(
            "INSERT INTO node_runtime VALUES (?,?)",
            ("created_at", "2026-06-22T00:00:00.000000+00:00"),
        )
        w.commit()

    state = _read_node_state(local_db)

    # downloads
    assert state.downloads == (
        TrackedDownload(
            file=FileKey(Network.ED2K, "aabbccdd" * 4),
            target_id="062A",
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
            BackoffKey("amuled", None),
            BackoffState(3, datetime(1970, 1, 1, tzinfo=UTC), timedelta(seconds=120)),
        ),
        (
            BackoffKey("amuled", "kad"),
            BackoffState(1, datetime(2026, 6, 12, 10, tzinfo=UTC), timedelta(seconds=2.5)),
        ),
    ]

    # node_runtime
    assert state.node_id == "test-node-42"
    assert state.created_at == datetime(2026, 6, 22, tzinfo=UTC)


def test_a_completed_download_reads_its_completion(local_db: Path) -> None:
    with closing(sqlite3.connect(local_db)) as w, w:
        w.execute(
            "INSERT INTO downloads (file_id, network, native_id, target_id, state, queued_at,"
            " completed_at) VALUES (x'00', 'ed2k', ?, '062A', 'completed', ?, ?)",
            (
                "aabbccdd" * 4,
                "2026-06-22T10:00:00.000000+00:00",
                "2026-06-24T10:00:00.250000+00:00",
            ),
        )

    (download,) = _read_node_state(local_db).downloads

    assert download.state is DownloadState.COMPLETED
    assert download.completed_at == datetime(2026, 6, 24, 10, 0, 0, 250000, tzinfo=UTC)
    assert download.latest_progress_at is None


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
