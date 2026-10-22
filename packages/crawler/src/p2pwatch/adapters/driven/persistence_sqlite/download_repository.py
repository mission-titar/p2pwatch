"""``SqliteDownloadRepository``: the state of downloads (local.db, download spec §7).

Implements persistence of the downloads managed by the crawler. ``downloads`` is NOT
append-only (mutable state, not the catalog) → UPSERT/UPDATE allowed, no triggers. Same
disciplines as the other repos (data-model spec §7): the given instant formatted BEFORE ``BEGIN``,
``BEGIN IMMEDIATE`` + rollback on ``BaseException`` (a NON-sqlite failure does not leave the
connection ``in_transaction``), ``wrap_sqlite_errors``.

Methods take a ``FileKey``; rows are keyed by its ``file_id`` (stage 2 spec D19). Each write
stores the instant the use-case gives it. ``record_queued`` is dedup-safe (PK = ``file_id``,
``ON CONFLICT DO NOTHING``); ``record_completed`` stamps ``completed_at``; ``mark_seen`` stamps
``last_seen_at`` and the lifecycle columns (stage 2 spec D12), which ``read_last_seen_at_by_file``
reads back for the lost-download detection; ``read_tracked_states`` returns the file→state map
(the loop reconciles the client's list with it).
"""

import sqlite3
from collections.abc import Iterable
from contextlib import suppress
from datetime import datetime
from typing import Literal

from p2pwatch.adapters.driven.persistence_sqlite.connection import utc_iso
from p2pwatch.adapters.driven.persistence_sqlite.errors import PersistenceError, wrap_sqlite_errors
from p2pwatch.domain.download.states import DownloadState, FailureReason
from p2pwatch.domain.download.status import DownloadStatus
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.ports.driven.download_reader import DownloadReader
from p2pwatch.ports.driven.download_writer import DownloadWriter

_INSERT_QUEUED = """
INSERT INTO downloads
    (file_id, network, native_id, target_id, state, queued_at, size_bytes, last_seen_at,
     bytes_done)
VALUES (?, ?, ?, ?, 'queued', ?, ?, ?, 0)
ON CONFLICT (file_id) DO NOTHING
"""

_SET_STATE = "UPDATE downloads SET state = ?, failure_reason = ? WHERE file_id = ?"

_SET_STATE_COMPLETED = """
UPDATE downloads SET state = ?, failure_reason = NULL, completed_at = ? WHERE file_id = ?
"""

_IS_TRACKED = "SELECT 1 FROM downloads WHERE file_id = ?"

_TRACKED_STATES = "SELECT network, native_id, state FROM downloads"

_QUEUED_TARGET_ID = "SELECT target_id FROM downloads WHERE file_id = ?"

# Every right-hand side reads the row as it was, so the CASE compares against the old bytes.
_MARK_SEEN = """
UPDATE downloads SET
    last_seen_at = :seen_at,
    last_progress_at = CASE WHEN :bytes_done > bytes_done THEN :seen_at ELSE last_progress_at END,
    bytes_done = :bytes_done,
    waiting_reason = :waiting_reason
WHERE file_id = :file_id
"""

# The non-terminal states listed here MUST stay synchronized with _TERMINAL_STATES (states.py).
_LAST_SEEN_AT_BY_FILE = """
SELECT network, native_id, COALESCE(last_seen_at, queued_at) FROM downloads
WHERE state IN ('queued', 'downloading')
"""


class SqliteDownloadRepository(DownloadWriter, DownloadReader):
    """SQLite implementation of the downloads' ports."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def record_queued(
        self, file: FileKey, target_id: str, size_bytes: int, queued_at: datetime
    ) -> bool:
        """INSERT of a ``queued`` download (dedup-safe). ``True`` if new, ``False`` if duplicate."""
        queued_at_iso = utc_iso(queued_at)
        with wrap_sqlite_errors():
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = self._connection.execute(
                    _INSERT_QUEUED,
                    (
                        file.file_id,
                        file.network,
                        file.native_id,
                        target_id,
                        queued_at_iso,
                        size_bytes,
                        queued_at_iso,
                    ),
                )
                self._connection.execute("COMMIT")
            except BaseException:
                with suppress(sqlite3.Error):
                    self._connection.execute("ROLLBACK")
                raise
        return cursor.rowcount == 1

    def set_state(
        self,
        file: FileKey,
        state: Literal[DownloadState.DOWNLOADING, DownloadState.FAILED],
        failure_reason: FailureReason | None = None,
    ) -> None:
        """UPDATE the state and its ``failure_reason``, which any other call clears.

        Requires an existing download (an unknown file → ``PersistenceError``: caller-code bug).
        ``failed`` does not overwrite the ``completed_at``.
        """
        with wrap_sqlite_errors():
            cursor = self._connection.execute(
                _SET_STATE, (state.value, failure_reason, file.file_id)
            )
        if cursor.rowcount != 1:
            raise PersistenceError(f"download {file.native_id} not found (caller bug)")

    def record_completed(self, file: FileKey, completed_at: datetime) -> None:
        """Marks the download ``completed`` at ``completed_at`` and clears its ``failure_reason``.

        Requires an existing download (an unknown file → ``PersistenceError``: caller-code bug).
        """
        with wrap_sqlite_errors():
            cursor = self._connection.execute(
                _SET_STATE_COMPLETED,
                (DownloadState.COMPLETED.value, utc_iso(completed_at), file.file_id),
            )
        if cursor.rowcount != 1:
            raise PersistenceError(f"download {file.native_id} not found (caller bug)")

    def is_tracked(self, file: FileKey) -> bool:
        """``True`` if this file is already known to ``downloads`` (dedup, spec §6)."""
        with wrap_sqlite_errors():
            row = self._connection.execute(_IS_TRACKED, (file.file_id,)).fetchone()
        return row is not None

    def mark_seen(self, statuses: Iterable[DownloadStatus], seen_at: datetime) -> None:
        """Stamps ``last_seen_at`` and the progress of each download the client lists.

        ``last_progress_at`` moves only when ``bytes_done`` grows. An unknown file updates
        nothing (a shared file the crawler never queued): no error.
        """
        seen_at_iso = utc_iso(seen_at)
        with wrap_sqlite_errors():
            self._connection.executemany(
                _MARK_SEEN,
                [
                    {
                        "seen_at": seen_at_iso,
                        "bytes_done": status.bytes_done,
                        "waiting_reason": status.waiting_reason,
                        "file_id": status.file.file_id,
                    }
                    for status in statuses
                ],
            )

    def read_last_seen_at_by_file(self) -> dict[FileKey, datetime]:
        """Each ``queued`` or ``downloading`` download's ``last_seen_at``: when the client last
        listed it, else when it was queued."""
        with wrap_sqlite_errors():
            rows = self._connection.execute(_LAST_SEEN_AT_BY_FILE).fetchall()
        return {FileKey(Network(row[0]), row[1]): datetime.fromisoformat(row[2]) for row in rows}

    def read_tracked_states(self) -> dict[FileKey, DownloadState]:
        """File→state map of ALL tracked downloads, whatever their state."""
        with wrap_sqlite_errors():
            rows = self._connection.execute(_TRACKED_STATES).fetchall()
        return {FileKey(Network(row[0]), row[1]): DownloadState(row[2]) for row in rows}

    def read_queued_target_id(self, file: FileKey) -> str | None:
        """``target_id`` the file was queued for, or ``None`` (never queued).

        The download loop uses it to label the completion notification; ``None`` is a normal
        case (a shared file the crawler never queued), reported as ``unknown``.
        """
        with wrap_sqlite_errors():
            row = self._connection.execute(_QUEUED_TARGET_ID, (file.file_id,)).fetchone()
        if row is None:
            return None
        return str(row[0])
