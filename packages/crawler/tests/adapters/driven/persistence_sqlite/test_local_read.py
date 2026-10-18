"""Read-only tests of local.db via LocalReader (Task 8 — W-D8 §node_state)."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.local_read import LocalReader
from p2pwatch.adapters.driving.webui.views import BackoffRow, DownloadRow, NodeState

pytestmark = pytest.mark.usefixtures("close_test_connections")

_STARTED_AT_MICROS = 1_781_258_400_000_000  # 2026-06-12T10:00:00Z

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _open_local(path: Path) -> sqlite3.Connection:
    """Open local.db in read-only mode (row_factory enabled)."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Populated DB
# ---------------------------------------------------------------------------


def test_node_state_populated(local_db: Path) -> None:
    """Populated DB: downloads, backoff_states, node_runtime."""
    # --- populate ---
    with sqlite3.connect(local_db) as w:
        w.execute(
            "INSERT INTO downloads (file_id, network, native_id, target_id, state, queued_at,"
            " size_bytes, last_progress_at, waiting_reason, failure_reason)"
            " VALUES (x'00', 'ed2k', ?, '062A', 'active', '2026-06-22T10:00:00Z', ?, ?, ?, ?)",
            ("aabbccdd" * 4, 1024, "2026-06-23T10:00:00Z", "no_source", "error"),
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
            ("created_at", "2026-06-22T00:00:00Z"),
        )
        w.commit()

    conn = _open_local(local_db)
    state = LocalReader(conn).node_state()
    conn.close()

    # downloads
    assert len(state.downloads) == 1
    dl = state.downloads[0]
    assert isinstance(dl, DownloadRow)
    assert dl.native_id == "aabbccdd" * 4
    assert dl.target_id == "062A"
    assert dl.state == "active"
    assert dl.queued_at == "2026-06-22T10:00:00Z"
    assert dl.completed_at is None
    assert dl.size_bytes == 1024
    assert dl.last_progress_at == "2026-06-23T10:00:00Z"
    assert dl.waiting_reason == "no_source"
    assert dl.failure_reason == "error"

    # backoff, the whole client first, each retry at its start plus its delay
    assert state.backoff_rows == (
        BackoffRow("amuled", None, 3, datetime(1970, 1, 1, 0, 2, tzinfo=UTC)),
        BackoffRow("amuled", "kad", 1, datetime(2026, 6, 12, 10, 0, 2, 500000, tzinfo=UTC)),
    )

    # node_runtime
    assert state.node_id == "test-node-42"
    assert state.created_at == "2026-06-22T00:00:00Z"


# ---------------------------------------------------------------------------
# Empty DB (observer mode) — covers the None branches
# ---------------------------------------------------------------------------


def test_node_state_empty_db(local_db: Path) -> None:
    """Empty DB (observer mode): everything empty / None — no error."""
    conn = _open_local(local_db)
    state = LocalReader(conn).node_state()
    conn.close()

    assert isinstance(state, NodeState)
    assert state.downloads == ()
    assert state.backoff_rows == ()
    assert state.node_id is None
    assert state.created_at is None
