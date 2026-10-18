import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.connection import open_local, utc_iso
from p2pwatch.adapters.driven.persistence_sqlite.download_repository import SqliteDownloadRepository
from p2pwatch.adapters.driven.persistence_sqlite.errors import PersistenceError
from p2pwatch.domain.download.states import DownloadState
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.ports.driven.download_client import DownloadStatus, FailureReason, WaitingReason

_A = FileKey(Network.ED2K, "a" * 32)
_B = FileKey(Network.ED2K, "b" * 32)
_C = FileKey(Network.ED2K, "c" * 32)
_T0 = datetime(2026, 6, 12, tzinfo=UTC)
_DAY = timedelta(days=1)


def _status(file: FileKey, done: int = 0, waiting: WaitingReason | None = None) -> DownloadStatus:
    return DownloadStatus(file, done, 100, False, waiting, None)


def _lifecycle(connection: sqlite3.Connection, file: FileKey) -> tuple[object, ...]:
    return tuple(
        connection.execute(
            "SELECT bytes_done, last_progress_at, waiting_reason, failure_reason FROM downloads"
            " WHERE file_id = ?",
            (file.file_id,),
        ).fetchone()
    )


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    local = open_local(tmp_path / "local.db")
    yield local
    local.close()


@pytest.fixture
def repository(connection: sqlite3.Connection) -> SqliteDownloadRepository:
    return SqliteDownloadRepository(connection)


def test_record_queued_inserts_a_new_download(repository: SqliteDownloadRepository) -> None:
    assert repository.record_queued(_A, "062A", 100, _T0) is True
    assert repository.is_tracked(_A) is True


def test_record_queued_keys_the_row_by_file_id_and_keeps_the_file_key(
    repository: SqliteDownloadRepository, connection: sqlite3.Connection
) -> None:
    repository.record_queued(_A, "062A", 100, _T0)
    assert connection.execute("SELECT file_id, network, native_id FROM downloads").fetchall() == [
        (_A.file_id, "ed2k", _A.native_id)
    ]


def test_record_queued_is_dedup_safe(repository: SqliteDownloadRepository) -> None:
    assert repository.record_queued(_A, "062A", 100, _T0) is True
    assert repository.record_queued(_A, "062A", 100, _T0 + _DAY) is False  # duplicate ignored


def test_is_downloaded_is_false_for_unknown_hash(repository: SqliteDownloadRepository) -> None:
    assert repository.is_tracked(_A) is False


def test_set_state_updates_the_state(repository: SqliteDownloadRepository) -> None:
    repository.record_queued(_A, "062A", 100, _T0)
    repository.set_state(_A, DownloadState.DOWNLOADING)
    assert repository.tracked_states()[_A] is DownloadState.DOWNLOADING


def test_record_completed_stamps_the_completed_at_it_is_given(
    repository: SqliteDownloadRepository, connection: sqlite3.Connection
) -> None:
    repository.record_queued(_A, "062A", 100, _T0)
    repository.record_completed(_A, _T0 + _DAY)
    assert repository.tracked_states()[_A] is DownloadState.COMPLETED
    stamped = connection.execute(
        "SELECT completed_at FROM downloads WHERE file_id = ?", (_A.file_id,)
    ).fetchone()[0]
    assert stamped == utc_iso(_T0 + _DAY)


def test_set_state_non_completed_leaves_completed_at_null(
    repository: SqliteDownloadRepository, connection: sqlite3.Connection
) -> None:
    repository.record_queued(_A, "062A", 100, _T0)
    repository.set_state(_A, DownloadState.DOWNLOADING)
    stamped = connection.execute(
        "SELECT completed_at FROM downloads WHERE file_id = ?", (_A.file_id,)
    ).fetchone()[0]
    assert stamped is None


def test_set_state_on_unknown_hash_raises(repository: SqliteDownloadRepository) -> None:
    with pytest.raises(PersistenceError):
        repository.set_state(_A, DownloadState.DOWNLOADING)


def test_record_completed_on_unknown_hash_raises(repository: SqliteDownloadRepository) -> None:
    with pytest.raises(PersistenceError, match="not found"):
        repository.record_completed(_A, _T0)


def test_active_states_maps_hash_to_state(repository: SqliteDownloadRepository) -> None:
    repository.record_queued(_A, "062A", 100, _T0)
    repository.record_queued(_B, "063A", 200, _T0)
    repository.set_state(_B, DownloadState.FAILED)
    states = repository.tracked_states()
    assert states == {_A: DownloadState.QUEUED, _B: DownloadState.FAILED}


def test_record_queued_is_atomic_on_injected_failure(
    repository: SqliteDownloadRepository, connection: sqlite3.Connection
) -> None:
    connection.execute(
        "CREATE TRIGGER boom BEFORE INSERT ON downloads"
        " BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
    )
    with pytest.raises(PersistenceError, match="injected failure"):
        repository.record_queued(_A, "062A", 100, _T0)
    assert repository.is_tracked(_A) is False


def test_get_target_id_returns_target_for_known_hash(
    repository: SqliteDownloadRepository,
) -> None:
    repository.record_queued(_A, "062A", 100, _T0)
    assert repository.queued_target_id(_A) == "062A"


def test_get_target_id_is_none_for_unknown_hash(repository: SqliteDownloadRepository) -> None:
    assert repository.queued_target_id(_A) is None


def _last_seen(connection: sqlite3.Connection, file: FileKey) -> str:
    row = connection.execute(
        "SELECT last_seen_at FROM downloads WHERE file_id = ?", (file.file_id,)
    ).fetchone()
    return str(row[0])


def test_record_queued_stamps_last_seen_at_with_queued_at(
    repository: SqliteDownloadRepository, connection: sqlite3.Connection
) -> None:
    # A row amuled never picks up must still age out, from its queuing.
    repository.record_queued(_A, "062A", 100, _T0)
    queued_at = connection.execute(
        "SELECT queued_at FROM downloads WHERE file_id = ?", (_A.file_id,)
    ).fetchone()[0]
    assert queued_at == _last_seen(connection, _A) == utc_iso(_T0)


def test_mark_seen_stamps_the_seen_at_it_is_given(
    repository: SqliteDownloadRepository, connection: sqlite3.Connection
) -> None:
    repository.record_queued(_A, "062A", 100, _T0)
    repository.mark_seen([_status(_A)], _T0 + _DAY)
    assert _last_seen(connection, _A) == utc_iso(_T0 + _DAY)


def test_mark_seen_ignores_a_hash_it_does_not_know(
    repository: SqliteDownloadRepository,
) -> None:
    # A shared file the crawler never queued: no row, no raise.
    repository.mark_seen([_status(_A)], _T0)
    assert repository.is_tracked(_A) is False


def test_last_seen_at_by_file_reads_when_the_client_last_listed_each_download(
    repository: SqliteDownloadRepository,
) -> None:
    repository.record_queued(_A, "062A", 100, _T0)
    repository.record_queued(_B, "063A", 200, _T0)
    repository.set_state(_B, DownloadState.DOWNLOADING)
    repository.mark_seen([_status(_B)], _T0 + _DAY)
    assert repository.last_seen_at_by_file() == {_A: _T0, _B: _T0 + _DAY}


def test_last_seen_at_by_file_leaves_the_terminal_downloads_out(
    repository: SqliteDownloadRepository,
) -> None:
    for file in (_A, _B, _C):
        repository.record_queued(file, "062A", 100, _T0)
    repository.record_completed(_B, _T0)
    repository.set_state(_C, DownloadState.FAILED, FailureReason.LOST)
    assert repository.last_seen_at_by_file() == {_A: _T0}


def test_last_seen_at_by_file_reads_a_row_never_stamped_at_its_queuing(
    repository: SqliteDownloadRepository, connection: sqlite3.Connection
) -> None:
    # Only a row written by hand can hold a NULL: it ages from its queuing, as local 0005 did.
    repository.record_queued(_A, "062A", 100, _T0)
    connection.execute("UPDATE downloads SET last_seen_at = NULL")
    assert repository.last_seen_at_by_file() == {_A: _T0}


def test_a_queued_download_starts_at_zero_bytes_with_no_progress(
    repository: SqliteDownloadRepository, connection: sqlite3.Connection
) -> None:
    repository.record_queued(_A, "062A", 100, _T0)
    assert _lifecycle(connection, _A) == (0, None, None, None)


def test_mark_seen_stamps_progress_only_when_the_bytes_grow(
    repository: SqliteDownloadRepository, connection: sqlite3.Connection
) -> None:
    repository.record_queued(_A, "062A", 100, _T0)
    repository.mark_seen([_status(_A, 0, WaitingReason.NO_SOURCE)], _T0)
    assert _lifecycle(connection, _A) == (0, None, "no_source", None)
    grown_at = _T0 + timedelta(hours=1)
    repository.mark_seen([_status(_A, 40, WaitingReason.REMOTE_QUEUE)], grown_at)
    repository.mark_seen([_status(_A, 40)], grown_at + 3 * _DAY)
    assert _lifecycle(connection, _A) == (40, utc_iso(grown_at), None, None)


def test_mark_seen_stores_the_client_hashing_or_allocating_as_local_processing(
    repository: SqliteDownloadRepository, connection: sqlite3.Connection
) -> None:
    repository.record_queued(_A, "062A", 100, _T0)
    repository.mark_seen([_status(_A, 0, WaitingReason.LOCAL_PROCESSING)], _T0)
    assert _lifecycle(connection, _A) == (0, None, "local_processing", None)


def test_a_download_migrated_without_bytes_does_not_invent_progress(
    repository: SqliteDownloadRepository, connection: sqlite3.Connection
) -> None:
    repository.record_queued(_A, "062A", 100, _T0)
    connection.execute("UPDATE downloads SET bytes_done = NULL")  # a row from before local 0008
    repository.mark_seen([_status(_A, 40)], _T0)
    assert _lifecycle(connection, _A) == (40, None, None, None)


def test_set_state_records_a_failure_reason_and_any_other_state_clears_it(
    repository: SqliteDownloadRepository, connection: sqlite3.Connection
) -> None:
    repository.record_queued(_A, "062A", 100, _T0)
    repository.set_state(_A, DownloadState.FAILED, FailureReason.ERROR)
    assert _lifecycle(connection, _A)[3] == "error"
    repository.set_state(_A, DownloadState.DOWNLOADING)
    assert _lifecycle(connection, _A)[3] is None
    repository.set_state(_A, DownloadState.FAILED, FailureReason.ERROR)
    repository.record_completed(_A, _T0)  # a failed download can still complete
    assert _lifecycle(connection, _A)[3] is None
