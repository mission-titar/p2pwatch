import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from catalog_matching.domain.identifiers import TargetId
from p2pwatch.adapters.driven.persistence_sqlite.errors import PersistenceError
from p2pwatch.adapters.driven.persistence_sqlite.micros import instant_to_micros
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_tracked_download_store import (
    SqliteTrackedDownloadStore,
)
from p2pwatch.domain.download.states import DownloadState, FailureReason, WaitingReason
from p2pwatch.domain.download.status import DownloadStatus
from p2pwatch.domain.file_key import FileKey, Network
from tests.contracts.application.ports.driven.tracked_download_store_contract import (
    TrackedDownloadStoreContract,
)
from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_local

_A = FileKey(network=Network.ED2K, native_id="a" * 32)
_T0 = datetime(2026, 6, 12, 0, 0, 0, 123456, tzinfo=UTC)
_DAY = timedelta(days=1)


def _status(file: FileKey, done: int = 0, waiting: WaitingReason | None = None) -> DownloadStatus:
    return DownloadStatus(
        file=file,
        bytes_done=done,
        size_bytes=100,
        completed=False,
        waiting_reason=waiting,
        failure_reason=None,
    )


def _lifecycle(connection: sqlite3.Connection, file: FileKey) -> dict[str, Any]:
    [lifecycle] = rows(
        connection,
        "SELECT bytes_done, latest_progress_at_micros, waiting_reason, failure_reason"
        " FROM downloads WHERE file_id = ?",
        (file.file_id,),
    )
    return lifecycle


def _lifecycle_row(
    bytes_done: int,
    latest_progress_at_micros: int | None,
    waiting_reason: str | None,
    failure_reason: str | None,
) -> dict[str, Any]:
    return {
        "bytes_done": bytes_done,
        "latest_progress_at_micros": latest_progress_at_micros,
        "waiting_reason": waiting_reason,
        "failure_reason": failure_reason,
    }


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    local = open_local(tmp_path / "local.db")
    yield local
    local.close()


@pytest.fixture
def tracked_download_store(connection: sqlite3.Connection) -> SqliteTrackedDownloadStore:
    return SqliteTrackedDownloadStore(connection)


class TestSqliteTrackedDownloadStore(TrackedDownloadStoreContract):
    @pytest.fixture
    def tracked_download_store(self, connection: sqlite3.Connection) -> SqliteTrackedDownloadStore:
        return SqliteTrackedDownloadStore(connection)


def test_record_queued_keys_the_row_by_file_id_and_keeps_the_file_key(
    tracked_download_store: SqliteTrackedDownloadStore, connection: sqlite3.Connection
) -> None:
    tracked_download_store.record_queued(
        _A, target_id=TargetId("062A"), size_bytes=100, queued_at=_T0
    )
    assert rows(connection, "SELECT file_id, network, native_id FROM downloads") == [
        {"file_id": _A.file_id, "network": "ed2k", "native_id": _A.native_id}
    ]


def test_record_queued_is_dedup_safe(
    tracked_download_store: SqliteTrackedDownloadStore, connection: sqlite3.Connection
) -> None:
    tracked_download_store.record_queued(
        _A, target_id=TargetId("062A"), size_bytes=100, queued_at=_T0
    )
    tracked_download_store.record_queued(
        _A, target_id=TargetId("063A"), size_bytes=200, queued_at=_T0 + _DAY
    )  # duplicate ignored
    assert rows(connection, "SELECT target_id, size_bytes, queued_at_micros FROM downloads") == [
        {"target_id": "062A", "size_bytes": 100, "queued_at_micros": instant_to_micros(_T0)}
    ]


def test_set_completed_stamps_the_completed_at_it_is_given(
    tracked_download_store: SqliteTrackedDownloadStore, connection: sqlite3.Connection
) -> None:
    tracked_download_store.record_queued(
        _A, target_id=TargetId("062A"), size_bytes=100, queued_at=_T0
    )
    tracked_download_store.set_completed(_A, completed_at=_T0 + _DAY)
    assert rows(
        connection,
        "SELECT typeof(completed_at_micros) AS completed_at_type, completed_at_micros"
        " FROM downloads WHERE file_id = ?",
        (_A.file_id,),
    ) == [{"completed_at_type": "integer", "completed_at_micros": instant_to_micros(_T0 + _DAY)}]


def test_set_state_non_completed_leaves_completed_at_null(
    tracked_download_store: SqliteTrackedDownloadStore, connection: sqlite3.Connection
) -> None:
    tracked_download_store.record_queued(
        _A, target_id=TargetId("062A"), size_bytes=100, queued_at=_T0
    )
    tracked_download_store.set_state(_A, state=DownloadState.DOWNLOADING)
    assert rows(
        connection, "SELECT completed_at_micros FROM downloads WHERE file_id = ?", (_A.file_id,)
    ) == [{"completed_at_micros": None}]


def test_set_state_on_unknown_hash_raises(
    tracked_download_store: SqliteTrackedDownloadStore,
) -> None:
    with pytest.raises(PersistenceError):
        tracked_download_store.set_state(_A, state=DownloadState.DOWNLOADING)


def test_set_completed_on_unknown_hash_raises(
    tracked_download_store: SqliteTrackedDownloadStore,
) -> None:
    with pytest.raises(PersistenceError, match="not found"):
        tracked_download_store.set_completed(_A, completed_at=_T0)


def test_record_queued_is_atomic_on_injected_failure(
    tracked_download_store: SqliteTrackedDownloadStore, connection: sqlite3.Connection
) -> None:
    connection.execute(
        "CREATE TRIGGER boom BEFORE INSERT ON downloads"
        " BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
    )
    with pytest.raises(PersistenceError, match="injected failure"):
        tracked_download_store.record_queued(
            _A, target_id=TargetId("062A"), size_bytes=100, queued_at=_T0
        )
    assert tracked_download_store.is_tracked(_A) is False


def _latest_seen(connection: sqlite3.Connection, file: FileKey) -> tuple[str, int]:
    [latest_seen] = rows(
        connection,
        "SELECT typeof(latest_seen_at_micros) AS latest_seen_at_type, latest_seen_at_micros"
        " FROM downloads WHERE file_id = ?",
        (file.file_id,),
    )
    return latest_seen["latest_seen_at_type"], latest_seen["latest_seen_at_micros"]


def test_record_queued_stamps_latest_seen_at_with_queued_at(
    tracked_download_store: SqliteTrackedDownloadStore, connection: sqlite3.Connection
) -> None:
    # A row amuled never picks up must still age out, from its queuing.
    tracked_download_store.record_queued(
        _A, target_id=TargetId("062A"), size_bytes=100, queued_at=_T0
    )
    [queued] = rows(
        connection,
        "SELECT typeof(queued_at_micros) AS queued_at_type, queued_at_micros"
        " FROM downloads WHERE file_id = ?",
        (_A.file_id,),
    )
    queued_at = (queued["queued_at_type"], queued["queued_at_micros"])
    assert queued_at == _latest_seen(connection, _A) == ("integer", instant_to_micros(_T0))


def test_latest_seen_at_by_file_reads_a_row_never_stamped_at_its_queuing(
    tracked_download_store: SqliteTrackedDownloadStore, connection: sqlite3.Connection
) -> None:
    # Only a row written by hand can hold a NULL: it ages from its queuing, as local 0005 did.
    tracked_download_store.record_queued(
        _A, target_id=TargetId("062A"), size_bytes=100, queued_at=_T0
    )
    connection.execute("UPDATE downloads SET latest_seen_at_micros = NULL")
    assert tracked_download_store.read_latest_seen_at_by_file() == {_A: _T0}


def test_a_queued_download_starts_at_zero_bytes_with_no_progress(
    tracked_download_store: SqliteTrackedDownloadStore, connection: sqlite3.Connection
) -> None:
    tracked_download_store.record_queued(
        _A, target_id=TargetId("062A"), size_bytes=100, queued_at=_T0
    )
    assert _lifecycle(connection, _A) == _lifecycle_row(0, None, None, None)


def test_set_seen_stamps_progress_only_when_the_bytes_grow(
    tracked_download_store: SqliteTrackedDownloadStore, connection: sqlite3.Connection
) -> None:
    tracked_download_store.record_queued(
        _A, target_id=TargetId("062A"), size_bytes=100, queued_at=_T0
    )
    tracked_download_store.set_seen([_status(_A, 0, WaitingReason.NO_SOURCE)], seen_at=_T0)
    assert _lifecycle(connection, _A) == _lifecycle_row(0, None, "no_source", None)
    grown_at = _T0 + timedelta(hours=1)
    tracked_download_store.set_seen([_status(_A, 40, WaitingReason.REMOTE_QUEUE)], seen_at=grown_at)
    tracked_download_store.set_seen([_status(_A, 40)], seen_at=grown_at + 3 * _DAY)
    assert _lifecycle(connection, _A) == _lifecycle_row(40, instant_to_micros(grown_at), None, None)
    assert _latest_seen(connection, _A) == ("integer", instant_to_micros(grown_at + 3 * _DAY))
    assert rows(
        connection,
        "SELECT typeof(latest_progress_at_micros) AS latest_progress_at_type FROM downloads",
    ) == [{"latest_progress_at_type": "integer"}]


def test_set_seen_stores_the_client_hashing_or_allocating_as_local_processing(
    tracked_download_store: SqliteTrackedDownloadStore, connection: sqlite3.Connection
) -> None:
    tracked_download_store.record_queued(
        _A, target_id=TargetId("062A"), size_bytes=100, queued_at=_T0
    )
    tracked_download_store.set_seen([_status(_A, 0, WaitingReason.LOCAL_PROCESSING)], seen_at=_T0)
    assert _lifecycle(connection, _A) == _lifecycle_row(0, None, "local_processing", None)


def test_a_download_migrated_without_bytes_does_not_invent_progress(
    tracked_download_store: SqliteTrackedDownloadStore, connection: sqlite3.Connection
) -> None:
    tracked_download_store.record_queued(
        _A, target_id=TargetId("062A"), size_bytes=100, queued_at=_T0
    )
    connection.execute("UPDATE downloads SET bytes_done = NULL")  # a row from before local 0008
    tracked_download_store.set_seen([_status(_A, 40)], seen_at=_T0)
    assert _lifecycle(connection, _A) == _lifecycle_row(40, None, None, None)


def test_set_state_records_a_failure_reason_and_any_other_state_clears_it(
    tracked_download_store: SqliteTrackedDownloadStore, connection: sqlite3.Connection
) -> None:
    tracked_download_store.record_queued(
        _A, target_id=TargetId("062A"), size_bytes=100, queued_at=_T0
    )
    tracked_download_store.set_state(
        _A, state=DownloadState.FAILED, failure_reason=FailureReason.ERROR
    )
    assert _lifecycle(connection, _A)["failure_reason"] == "error"
    tracked_download_store.set_state(_A, state=DownloadState.DOWNLOADING)
    assert _lifecycle(connection, _A)["failure_reason"] is None
    tracked_download_store.set_state(
        _A, state=DownloadState.FAILED, failure_reason=FailureReason.ERROR
    )
    tracked_download_store.set_completed(
        _A, completed_at=_T0
    )  # a failed download can still complete
    assert _lifecycle(connection, _A)["failure_reason"] is None
